#!/usr/bin/env python3
"""
Backfill script for fetching historical Tempiro energy data and spot prices.

This script fetches data in chunks to avoid overwhelming the slow Tempiro API.
Run it once to populate historical data, then use the daily sync for updates.

Usage:
    python backfill.py                    # Backfill last 90 days
    python backfill.py --days 30          # Backfill last 30 days
    python backfill.py --prices-only      # Only fetch spot prices
    python backfill.py --energy-only      # Only fetch energy data
    python backfill.py --status           # Show database status
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

import requests

import database

# Load config
with open("config.json") as f:
    config = json.load(f)

TEMPIRO_BASE = config["tempiro"]["base_url"]
USERNAME = config["tempiro"]["username"]
PASSWORD = config["tempiro"]["password"]

# Token cache
_token_cache = {"token": None, "expires": None}


def get_token():
    """Authenticate and get bearer token."""
    now = datetime.now()
    if _token_cache["token"] and _token_cache["expires"] and now < _token_cache["expires"]:
        return _token_cache["token"]

    print("  Authenticating with Tempiro API...")
    resp = requests.post(
        f"{TEMPIRO_BASE}/Token",
        json={"Username": USERNAME, "Password": PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires"] = now + timedelta(days=6)
    return _token_cache["token"]


def api_get(path, timeout=120):
    """Make authenticated GET request to Tempiro API."""
    token = get_token()
    resp = requests.get(
        f"{TEMPIRO_BASE}{path}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def get_devices():
    """Get all devices from Tempiro."""
    return api_get("/api/Devices")


def get_energy_values(device_id: str, from_dt: str, to_dt: str, interval_minutes: int = 15):
    """Get energy values for a device in a date range."""
    return api_get(
        f"/api/Values/{device_id}/interval?from={from_dt}&to={to_dt}&intervalMinutes={interval_minutes}",
        timeout=180  # Extra long timeout for large date ranges
    )


def fetch_spot_prices_for_date(date: datetime) -> list:
    """Fetch spot prices for a specific date from elprisetjustnu.se."""
    date_str = date.strftime("%Y/%m-%d")
    try:
        resp = requests.get(
            f"https://www.elprisetjustnu.se/api/v1/prices/{date_str}_SE3.json",
            timeout=10,
        )
        if resp.status_code == 404:
            return []  # No data for this date
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"    Warning: Could not fetch prices for {date.date()}: {e}")
        return []


def backfill_spot_prices(days: int = 90):
    """Backfill spot prices for the last N days."""
    print(f"\n=== Backfilling spot prices for last {days} days ===")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    total_saved = 0
    current = start_date

    while current <= end_date:
        prices = fetch_spot_prices_for_date(current)
        if prices:
            saved = database.save_spot_prices(prices)
            total_saved += saved
            print(f"  {current.date()}: {saved} prices saved")
        else:
            print(f"  {current.date()}: no data")

        current += timedelta(days=1)
        time.sleep(0.2)  # Be nice to the API

    database.update_sync_status("spot_prices", oldest_data=start_date.isoformat())
    print(f"\nTotal spot prices saved: {total_saved}")
    return total_saved


def backfill_energy_data(days: int = 90, chunk_days: int = 7):
    """
    Backfill energy data for all devices.

    Fetches data in chunks to avoid API timeouts.
    chunk_days: Number of days per API request (smaller = more reliable but slower)
    """
    print(f"\n=== Backfilling energy data for last {days} days ===")

    # Get all devices
    print("  Fetching device list...")
    devices = get_devices()
    print(f"  Found {len(devices)} devices: {[d['Name'] for d in devices]}")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    for device in devices:
        device_id = device["Id"]
        device_name = device["Name"]
        print(f"\n  Processing {device_name} ({device_id})...")

        total_saved = 0
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=chunk_days), end_date)

            from_str = current_start.strftime("%Y-%m-%dT00:00:00")
            to_str = current_end.strftime("%Y-%m-%dT23:59:59")

            print(f"    Fetching {current_start.date()} to {current_end.date()}...", end=" ", flush=True)

            try:
                start_time = time.time()
                values = get_energy_values(device_id, from_str, to_str)
                elapsed = time.time() - start_time

                if values:
                    # Skip the first value if it contains accumulated total (not a delta)
                    if len(values) > 1:
                        values_to_save = values[1:]  # Skip first which has total accumulated
                    else:
                        values_to_save = values

                    saved = database.save_energy_readings(device_id, device_name, values_to_save)
                    total_saved += saved
                    print(f"{saved} readings ({elapsed:.1f}s)")
                else:
                    print("no data")

            except requests.exceptions.Timeout:
                print("TIMEOUT - try smaller chunk_days")
            except Exception as e:
                print(f"ERROR: {e}")

            current_start = current_end + timedelta(days=1)

            # Add delay between requests to not overwhelm the API
            time.sleep(2)

        database.update_sync_status("energy", device_id, oldest_data=start_date.isoformat())
        print(f"    Total for {device_name}: {total_saved} readings")

    return True


def sync_recent_data(hours: int = 24):
    """Sync recent data (run this daily or hourly)."""
    print(f"\n=== Syncing recent data (last {hours} hours) ===")

    end_date = datetime.now()
    start_date = end_date - timedelta(hours=hours)

    # Sync spot prices for today and tomorrow (if available)
    print("\n  Syncing spot prices...")
    for offset in [0, 1]:
        date = datetime.now() + timedelta(days=offset)
        prices = fetch_spot_prices_for_date(date)
        if prices:
            saved = database.save_spot_prices(prices)
            print(f"    {date.date()}: {saved} prices")

    # Sync energy data
    print("\n  Syncing energy data...")
    devices = get_devices()

    from_str = start_date.strftime("%Y-%m-%dT00:00:00")
    to_str = end_date.strftime("%Y-%m-%dT23:59:59")

    for device in devices:
        device_id = device["Id"]
        device_name = device["Name"]

        print(f"    {device_name}...", end=" ", flush=True)

        try:
            values = get_energy_values(device_id, from_str, to_str)
            if values and len(values) > 1:
                saved = database.save_energy_readings(device_id, device_name, values[1:])
                print(f"{saved} readings")
            else:
                print("no new data")
        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(1)

    database.update_sync_status("recent_sync")


def show_status():
    """Show database status."""
    print("\n=== Database Status ===")
    stats = database.get_database_stats()

    print("\nEnergy Readings:")
    e = stats["energy_readings"]
    print(f"  Total records: {e['count']:,}")
    print(f"  Devices: {e['devices']}")
    print(f"  Date range: {e['oldest']} to {e['newest']}")

    print("\nSpot Prices:")
    p = stats["spot_prices"]
    print(f"  Total records: {p['count']:,}")
    print(f"  Date range: {p['oldest']} to {p['newest']}")

    # Show active hours last 24h
    print("\nActive Hours (last 24h):")
    active = database.get_active_hours_24h()
    for device_id, data in active.items():
        print(f"  {data['device_name']}: {data['active_hours']}h, {data['energy_kwh']:.3f} kWh")


def main():
    parser = argparse.ArgumentParser(description="Backfill Tempiro historical data")
    parser.add_argument("--days", type=int, default=90, help="Number of days to backfill (default: 90)")
    parser.add_argument("--chunk-days", type=int, default=7, help="Days per API request (default: 7)")
    parser.add_argument("--prices-only", action="store_true", help="Only fetch spot prices")
    parser.add_argument("--energy-only", action="store_true", help="Only fetch energy data")
    parser.add_argument("--sync", action="store_true", help="Sync recent data only (last 24h)")
    parser.add_argument("--status", action="store_true", help="Show database status")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.sync:
        sync_recent_data()
        show_status()
        return

    print(f"Starting backfill for {args.days} days...")
    print(f"Using {args.chunk_days}-day chunks for energy data")
    print("This may take a while due to slow Tempiro API...\n")

    if not args.energy_only:
        backfill_spot_prices(args.days)

    if not args.prices_only:
        backfill_energy_data(args.days, args.chunk_days)

    show_status()
    print("\nBackfill complete!")


if __name__ == "__main__":
    main()
