"""SQLite database for caching Tempiro energy data and spot prices."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Use DATA_DIR environment variable for persistent storage in HA Add-on
DATA_DIR = os.environ.get("DATA_DIR", str(Path(__file__).parent))
DB_PATH = Path(DATA_DIR) / "tempiro_data.db"


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Energy readings from Tempiro (15-minute intervals)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS energy_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            delta_power REAL NOT NULL,
            accumulated_value REAL NOT NULL,
            current_value REAL,
            UNIQUE(device_id, timestamp)
        )
    """)

    # Spot prices from elprisetjustnu.se (hourly)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spot_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            price_area TEXT NOT NULL,
            price_sek REAL NOT NULL,
            price_eur REAL,
            UNIQUE(timestamp, price_area)
        )
    """)

    # Sync status tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL,
            device_id TEXT,
            last_sync TEXT NOT NULL,
            oldest_data TEXT,
            UNIQUE(sync_type, device_id)
        )
    """)

    # Create indexes for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_energy_device_time
        ON energy_readings(device_id, timestamp)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_energy_time
        ON energy_readings(timestamp)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_spot_time
        ON spot_prices(timestamp)
    """)

    conn.commit()
    conn.close()


def save_energy_readings(device_id: str, device_name: str, readings: list):
    """Save energy readings to database (upsert)."""
    conn = get_connection()
    cursor = conn.cursor()

    for r in readings:
        cursor.execute("""
            INSERT OR REPLACE INTO energy_readings
            (device_id, device_name, timestamp, delta_power, accumulated_value, current_value)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            device_id,
            device_name,
            r["DateTime"],
            r["DeltaPower"],
            r["AccumulatedValue"],
            r.get("CurrentValue", 0)
        ))

    conn.commit()
    conn.close()
    return len(readings)


def save_spot_prices(prices: list, price_area: str = "SE3"):
    """Save spot prices to database (upsert)."""
    conn = get_connection()
    cursor = conn.cursor()

    for p in prices:
        cursor.execute("""
            INSERT OR REPLACE INTO spot_prices
            (timestamp, price_area, price_sek, price_eur)
            VALUES (?, ?, ?, ?)
        """, (
            p["time_start"],
            price_area,
            p["SEK_per_kWh"] * 100,  # Convert to öre
            p.get("EUR_per_kWh")
        ))

    conn.commit()
    conn.close()
    return len(prices)


def update_sync_status(sync_type: str, device_id: str = None, oldest_data: str = None):
    """Update sync status for a device or price area."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO sync_status
        (sync_type, device_id, last_sync, oldest_data)
        VALUES (?, ?, ?, ?)
    """, (sync_type, device_id, datetime.now().isoformat(), oldest_data))

    conn.commit()
    conn.close()


def get_sync_status(sync_type: str, device_id: str = None) -> Optional[dict]:
    """Get sync status for a device or price area."""
    conn = get_connection()
    cursor = conn.cursor()

    if device_id:
        cursor.execute("""
            SELECT * FROM sync_status WHERE sync_type = ? AND device_id = ?
        """, (sync_type, device_id))
    else:
        cursor.execute("""
            SELECT * FROM sync_status WHERE sync_type = ? AND device_id IS NULL
        """, (sync_type,))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_energy_readings(device_id: str = None, from_date: str = None, to_date: str = None) -> list:
    """Get energy readings from database."""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM energy_readings WHERE 1=1"
    params = []

    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    if from_date:
        query += " AND timestamp >= ?"
        params.append(from_date)
    if to_date:
        query += " AND timestamp <= ?"
        params.append(to_date)

    query += " ORDER BY timestamp ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_spot_prices(from_date: str = None, to_date: str = None, price_area: str = "SE3") -> list:
    """Get spot prices from database."""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM spot_prices WHERE price_area = ?"
    params = [price_area]

    if from_date:
        query += " AND timestamp >= ?"
        params.append(from_date)
    if to_date:
        query += " AND timestamp <= ?"
        params.append(to_date)

    query += " ORDER BY timestamp ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hourly_stats(device_id: str = None, from_date: str = None, to_date: str = None) -> list:
    """Get hourly aggregated stats with energy and cost."""
    conn = get_connection()
    cursor = conn.cursor()

    # Aggregate energy to hourly, join with spot prices
    # NOTE: Use current_value (Watts) × 0.25h instead of delta_power which is wrong in Tempiro API
    query = """
        SELECT
            strftime('%Y-%m-%d %H:00:00', e.timestamp) as hour,
            e.device_id,
            e.device_name,
            SUM(e.current_value * 0.25) / 1000 as energy_kwh,
            AVG(CASE WHEN e.current_value > 0 THEN 1 ELSE 0 END) as active_ratio,
            p.price_sek as spot_price_ore,
            SUM(e.current_value * 0.25) / 1000 * COALESCE(p.price_sek, 0) / 100 as cost_sek
        FROM energy_readings e
        LEFT JOIN spot_prices p ON strftime('%Y-%m-%d %H:00:00', e.timestamp) = strftime('%Y-%m-%d %H:00:00', p.timestamp)
            AND p.price_area = 'SE3'
        WHERE 1=1
    """
    params = []

    if device_id:
        query += " AND e.device_id = ?"
        params.append(device_id)
    if from_date:
        query += " AND e.timestamp >= ?"
        params.append(from_date)
    if to_date:
        query += " AND e.timestamp <= ?"
        params.append(to_date)

    query += " GROUP BY hour, e.device_id ORDER BY hour ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_summary(device_id: str = None, from_date: str = None, to_date: str = None) -> list:
    """Get daily summary with total energy and cost - FAST version using pre-aggregated data."""
    conn = get_connection()
    cursor = conn.cursor()

    # First, get daily energy per device (fast - just GROUP BY on indexed column)
    # NOTE: Use current_value (Watts) × 0.25h instead of delta_power which is wrong in Tempiro API
    energy_query = """
        SELECT
            date(timestamp) as date,
            device_id,
            device_name,
            SUM(current_value * 0.25) / 1000 as energy_kwh,
            COUNT(DISTINCT strftime('%H', timestamp)) as hours_with_data
        FROM energy_readings
        WHERE 1=1
    """
    params = []

    if device_id:
        energy_query += " AND device_id = ?"
        params.append(device_id)
    if from_date:
        energy_query += " AND timestamp >= ?"
        params.append(from_date)
    if to_date:
        energy_query += " AND timestamp <= ?"
        params.append(to_date + "T23:59:59")

    energy_query += " GROUP BY date(timestamp), device_id ORDER BY date ASC"

    cursor.execute(energy_query, params)
    energy_rows = cursor.fetchall()

    # Get average daily spot prices (fast - just GROUP BY on indexed column)
    price_query = """
        SELECT
            date(timestamp) as date,
            AVG(price_sek) as avg_price_ore
        FROM spot_prices
        WHERE price_area = 'SE3'
    """
    price_params = []
    if from_date:
        price_query += " AND timestamp >= ?"
        price_params.append(from_date)
    if to_date:
        price_query += " AND timestamp <= ?"
        price_params.append(to_date + "T23:59:59")

    price_query += " GROUP BY date(timestamp)"

    cursor.execute(price_query, price_params)
    price_rows = cursor.fetchall()
    conn.close()

    # Build price lookup dict
    prices_by_date = {r["date"]: r["avg_price_ore"] for r in price_rows}

    # Combine energy with prices
    result = []
    for r in energy_rows:
        row = dict(r)
        avg_price = prices_by_date.get(row["date"], 0) or 0
        row["cost_sek"] = row["energy_kwh"] * avg_price / 100  # öre to kr
        result.append(row)

    return result


def get_active_hours_24h(device_id: str = None) -> dict:
    """Get active hours in the last 24 hours per device."""
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

    # NOTE: Use current_value (Watts) × 0.25h instead of delta_power which is wrong in Tempiro API
    query = """
        SELECT
            device_id,
            device_name,
            COUNT(DISTINCT strftime('%Y-%m-%d %H', timestamp)) as active_hours,
            SUM(current_value * 0.25) / 1000 as energy_kwh
        FROM energy_readings
        WHERE timestamp >= ?
        AND current_value > 0
    """
    params = [cutoff]

    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)

    query += " GROUP BY device_id"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return {r["device_id"]: dict(r) for r in rows}


def get_database_stats() -> dict:
    """Get statistics about the database."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # Energy readings count and date range
    cursor.execute("""
        SELECT
            COUNT(*) as count,
            MIN(timestamp) as oldest,
            MAX(timestamp) as newest,
            COUNT(DISTINCT device_id) as devices
        FROM energy_readings
    """)
    row = cursor.fetchone()
    stats["energy_readings"] = dict(row)

    # Spot prices count and date range
    cursor.execute("""
        SELECT
            COUNT(*) as count,
            MIN(timestamp) as oldest,
            MAX(timestamp) as newest
        FROM spot_prices
    """)
    row = cursor.fetchone()
    stats["spot_prices"] = dict(row)

    conn.close()
    return stats


# Initialize database on import
init_db()
