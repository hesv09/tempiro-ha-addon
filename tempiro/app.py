"""Tempiro Dashboard - Home Assistant Add-on version."""

import json
import os
import requests
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

import database

app = Flask(__name__)
CORS(app)

# Track last sync time
_last_sync = {"energy": None, "prices": None}

# Static directory for HTML files
STATIC_DIR = Path(__file__).parent / "static"


def read_html(filename):
    """Read HTML file dynamically."""
    with open(STATIC_DIR / filename, "r") as f:
        return f.read()


# Load config
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
with open(CONFIG_PATH) as f:
    config = json.load(f)

TEMPIRO_BASE = config["tempiro"]["base_url"]
USERNAME = config["tempiro"]["username"]
PASSWORD = config["tempiro"]["password"]
PRICE_AREA = config.get("price_area", "SE3")

# Token cache
_token_cache = {"token": None, "expires": None}


def get_token():
    """Authenticate and get/refresh bearer token."""
    now = datetime.now()
    if _token_cache["token"] and _token_cache["expires"] and now < _token_cache["expires"]:
        return _token_cache["token"]

    resp = requests.post(
        f"{TEMPIRO_BASE}/Token",
        json={"Username": USERNAME, "Password": PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["expires"] = now + timedelta(days=6)
    return token


def api_get(path, timeout=90):
    """Make authenticated GET request to Tempiro API."""
    token = get_token()
    resp = requests.get(
        f"{TEMPIRO_BASE}{path}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def api_put(path, payload):
    """Make authenticated PUT request to Tempiro API."""
    token = get_token()
    resp = requests.put(
        f"{TEMPIRO_BASE}{path}",
        json=payload,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else {}


# --- Background Sync ---

def sync_energy_data():
    """Sync energy data from Tempiro API to local database."""
    try:
        devices = api_get("/api/devices")
        now = datetime.now()
        from_date = (now - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00")
        to_date = now.strftime("%Y-%m-%dT%H:%M:%S")

        total_saved = 0
        for device in devices:
            device_id = device["Id"]
            device_name = device["Name"]
            values = api_get(f"/api/Values/{device_id}/interval?from={from_date}&to={to_date}&intervalMinutes=15")
            if values:
                saved = database.save_energy_readings(device_id, device_name, values)
                total_saved += saved

        _last_sync["energy"] = datetime.now().isoformat()
        print(f"[SYNC] Energy: {total_saved} readings saved")
        return total_saved
    except Exception as e:
        print(f"[SYNC] Energy error: {e}")
        return 0


def sync_spot_prices():
    """Sync spot prices from elprisetjustnu.se to local database."""
    try:
        total_saved = 0
        for days_ago in range(-1, 3):
            date = datetime.now() - timedelta(days=days_ago)
            date_str = date.strftime("%Y/%m-%d")
            url = f"https://www.elprisetjustnu.se/api/v1/prices/{date_str}_{PRICE_AREA}.json"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    prices = resp.json()
                    saved = database.save_spot_prices(prices, PRICE_AREA)
                    total_saved += saved
            except:
                pass

        _last_sync["prices"] = datetime.now().isoformat()
        print(f"[SYNC] Prices: {total_saved} prices saved")
        return total_saved
    except Exception as e:
        print(f"[SYNC] Prices error: {e}")
        return 0


def background_sync_loop():
    """Background thread that syncs data every hour."""
    while True:
        try:
            sync_energy_data()
            sync_spot_prices()
        except Exception as e:
            print(f"[SYNC] Background sync error: {e}")
        time.sleep(3600)


_sync_thread = None


def start_background_sync():
    """Start the background sync thread (only once)."""
    global _sync_thread
    if _sync_thread is None or not _sync_thread.is_alive():
        _sync_thread = threading.Thread(target=background_sync_loop, daemon=True)
        _sync_thread.start()
        print("[SYNC] Background sync started (every 1 hour)")


# --- Static Routes ---

@app.route("/")
def index():
    return Response(read_html("index.html"), mimetype="text/html")


@app.route("/analysis")
def analysis_page():
    return Response(read_html("analysis.html"), mimetype="text/html")


@app.route("/ha")
def ha_dashboard():
    """Simplified dashboard for Home Assistant iframe."""
    return Response(read_html("ha.html"), mimetype="text/html")


# --- Live API Routes ---

@app.route("/api/devices")
def devices():
    """Get all devices with current status."""
    data = api_get("/api/Devices")
    devices_list = []
    for d in data:
        devices_list.append({
            "id": d["Id"],
            "name": d["Name"],
            "deviceId": d["DeviceId"],
            "value": d["Value"],
            "currentPower": d["CurrentPower"],
            "batteryOK": d["BatteryOK"],
            "fuseVoltageOK": d["FuseVoltageOK"],
            "offline": d["OfflineFlag"],
            "lastUpdate": d["LastUpdate"],
            "spotArea": d["spotArea"],
            "hoursActive": d["hoursActive"],
        })
    return jsonify(devices_list)


@app.route("/api/devices/<device_id>/switch", methods=["PUT"])
def switch_device(device_id):
    """Turn device on (1) or off (0)."""
    body = request.get_json()
    value = body.get("value", 0)
    result = api_put(f"/api/Switch/{device_id}", {"Value": value, "Id": device_id})
    return jsonify({"ok": True, "result": result})


@app.route("/api/devices/<device_id>/values")
def device_values(device_id):
    """Get energy values for a device."""
    date_from = request.args.get("from", datetime.now().strftime("%Y-%m-%dT00:00:00"))
    date_to = request.args.get("to", datetime.now().strftime("%Y-%m-%dT23:59:59"))
    interval = request.args.get("interval", "15")
    data = api_get(
        f"/api/Values/{device_id}/interval?from={date_from}&to={date_to}&intervalMinutes={interval}"
    )
    return jsonify(data)


@app.route("/api/spot-prices")
def spot_prices():
    """Get current spot prices."""
    today = datetime.now().strftime("%Y/%m-%d")
    try:
        resp = requests.get(
            f"https://www.elprisetjustnu.se/api/v1/prices/{today}_{PRICE_AREA}.json",
            timeout=10,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# --- Analytics API Routes ---

@app.route("/api/analytics/status")
def analytics_status():
    """Get database statistics and sync status."""
    stats = database.get_database_stats()
    return jsonify(stats)


@app.route("/api/analytics/active-hours-24h")
def active_hours_24h():
    """Get active hours in the last 24 hours per device."""
    device_id = request.args.get("device_id")
    data = database.get_active_hours_24h(device_id)
    return jsonify(data)


@app.route("/api/analytics/hourly")
def hourly_stats():
    """Get hourly aggregated stats."""
    device_id = request.args.get("device_id")
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    if not from_date:
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    data = database.get_hourly_stats(device_id, from_date, to_date)
    return jsonify(data)


@app.route("/api/analytics/daily")
def daily_summary():
    """Get daily summary with total energy and cost."""
    device_id = request.args.get("device_id")
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    days = request.args.get("days")

    if days:
        days = int(days)
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        if not from_date:
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")

    data = database.get_daily_summary(device_id, from_date, to_date)
    return jsonify(data)


@app.route("/api/analytics/prices")
def price_history():
    """Get spot price history from database."""
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    data = database.get_spot_prices(from_date, to_date)
    return jsonify(data)


@app.route("/api/sync", methods=["POST"])
def manual_sync():
    """Trigger a manual sync."""
    energy_count = sync_energy_data()
    price_count = sync_spot_prices()
    return jsonify({
        "ok": True,
        "energy_readings_saved": energy_count,
        "prices_saved": price_count,
        "last_sync": _last_sync
    })


@app.route("/api/sync/status")
def sync_status():
    """Get status of background sync."""
    return jsonify({
        "last_sync": _last_sync,
        "sync_thread_alive": _sync_thread.is_alive() if _sync_thread else False
    })


if __name__ == "__main__":
    start_background_sync()
    print("[STARTUP] Running initial sync...")
    sync_energy_data()
    sync_spot_prices()

    app.run(
        host=config["server"]["host"],
        port=config["server"]["port"],
        debug=False,
    )
