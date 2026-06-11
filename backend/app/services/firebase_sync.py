"""
Firebase Realtime Database Synchronization Service.
Synchronizes sensor readings, alerts, and city stats from SQLite to Firebase.
Uses asyncio.to_thread to run the blocking firebase-admin calls without blocking FastAPI's event loop.
"""

import os
import json
import asyncio
from typing import Dict, Any, List
import firebase_admin
from firebase_admin import credentials, db as fb_db

# File name of the Firebase Admin SDK private key
CRED_FILENAME = "serviceAccountKey.json"

_firebase_initialized = False

def get_firebase_db():
    """Get the Firebase Realtime Database client reference, initializing the SDK if needed."""
    global _firebase_initialized
    if _firebase_initialized:
        return fb_db

    # Check if Firebase application is already initialized elsewhere
    if firebase_admin._apps:
        _firebase_initialized = True
        return fb_db

    # Locate credential file in the backend root directory relative to this file
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cred_path = os.path.join(base_dir, CRED_FILENAME)

    if not os.path.exists(cred_path):
        # Fallback to local working directory
        cred_path = os.path.join(os.getcwd(), CRED_FILENAME)

    if os.path.exists(cred_path):
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://swachh-netra-d5f5f-default-rtdb.firebaseio.com/'
            })
            _firebase_initialized = True
            print("🔥 Firebase Realtime Database initialized successfully.")
            return fb_db
        except Exception as e:
            print(f"❌ Failed to initialize Firebase: {e}")
            return None
    else:
        print(f"❌ Firebase service account key not found at {cred_path}")
        return None


async def sync_facility(facility_id: str):
    """Fetch the latest facility details and its most recent sensor reading from SQLite, and sync to Firebase."""
    db = get_firebase_db()
    if not db:
        return

    from app.database import get_db
    sqlite_db = await get_db()

    # Query latest state
    sql = """
        SELECT f.*, r.nh3_ppm, r.voc_ppm, r.door_count, r.humidity, r.temperature, r.water_flow, r.recorded_at
        FROM facilities f
        LEFT JOIN sensor_readings r ON r.id = (
            SELECT id FROM sensor_readings 
            WHERE facility_id = f.id 
            ORDER BY recorded_at DESC LIMIT 1
        )
        WHERE f.id = ? AND f.is_active = 1
    """
    cursor = await sqlite_db.execute(sql, (facility_id,))
    row = await cursor.fetchone()
    if not row:
        return

    f_dict = dict(row)

    # Clean and map the payload variables for the frontend listeners
    payload = {
        "nh3": f_dict.get("nh3_ppm"),
        "voc": f_dict.get("voc_ppm"),
        "doors": f_dict.get("door_count"),
        "humidity": f_dict.get("humidity"),
        "score": f_dict.get("score"),
        "status": f_dict.get("status"),
        "last_cleaned": f_dict.get("last_cleaned"),
    }

    def run_sync():
        try:
            ref = db.reference(f"facilities/{facility_id}")
            ref.update(payload)
        except Exception as err:
            print(f"⚠️ Firebase sync_facility error for {facility_id}: {err}")

    await asyncio.to_thread(run_sync)


async def sync_city_stats():
    """Aggregate statistics from SQLite and update /city_stats in Firebase Realtime Database."""
    db = get_firebase_db()
    if not db:
        return

    from app.database import get_db
    sqlite_db = await get_db()

    # Get status counts
    cursor = await sqlite_db.execute(
        "SELECT status, COUNT(*) as cnt FROM facilities WHERE is_active=1 GROUP BY status"
    )
    rows = await cursor.fetchall()
    counts = {"ok": 0, "warning": 0, "alert": 0}
    for r in rows:
        counts[r["status"]] = r["cnt"]

    # Calculate average city score
    cursor = await sqlite_db.execute(
        "SELECT AVG(score) FROM facilities WHERE is_active=1"
    )
    avg_row = await cursor.fetchone()
    city_score = round(avg_row[0]) if avg_row and avg_row[0] is not None else 100

    # Get active alert count
    cursor = await sqlite_db.execute(
        "SELECT COUNT(*) FROM alerts WHERE resolved=0"
    )
    alert_row = await cursor.fetchone()
    active_alerts = alert_row[0] if alert_row else 0

    payload = {
        "city_score": city_score,
        "clean_count": counts["ok"],
        "warning_count": counts["warning"],
        "critical_count": counts["alert"],
        "active_alerts": active_alerts
    }

    def run_sync():
        try:
            ref = db.reference("city_stats")
            ref.set(payload)
        except Exception as err:
            print(f"⚠️ Firebase sync_city_stats error: {err}")

    await asyncio.to_thread(run_sync)


async def push_alert_to_firebase(alert_id: int):
    """Pushes a specific alert with its details and metadata to Firebase Realtime Database under alerts/{alert_id}."""
    db = get_firebase_db()
    if not db:
        return

    from app.database import get_db
    sqlite_db = await get_db()

    sql = """
        SELECT a.*, f.name AS facility_name, f.zone
        FROM alerts a
        JOIN facilities f ON f.id = a.facility_id
        WHERE a.id = ?
    """
    cursor = await sqlite_db.execute(sql, (alert_id,))
    row = await cursor.fetchone()
    if not row:
        return

    a_dict = dict(row)

    payload = {
        "facility_id": a_dict["facility_id"],
        "facility_name": a_dict["facility_name"],
        "zone": a_dict["zone"],
        "alert_type": a_dict["alert_type"],
        "severity": a_dict["severity"],
        "message": a_dict["message"],
        "value": a_dict["value"],
        "threshold": a_dict["threshold"],
        "resolved": bool(a_dict["resolved"]),
        "created_at": a_dict["created_at"]
    }

    def run_sync():
        try:
            ref = db.reference(f"alerts/{alert_id}")
            ref.set(payload)
        except Exception as err:
            print(f"⚠️ Firebase push_alert_to_firebase error for alert #{alert_id}: {err}")

    await asyncio.to_thread(run_sync)


async def resolve_alert_in_firebase(alert_id: int):
    """Mark an alert as resolved in the Firebase Realtime Database."""
    db = get_firebase_db()
    if not db:
        return

    def run_sync():
        try:
            ref = db.reference(f"alerts/{alert_id}")
            ref.update({"resolved": True})
        except Exception as err:
            print(f"⚠️ Firebase resolve_alert_in_firebase error for alert #{alert_id}: {err}")

    await asyncio.to_thread(run_sync)


async def resolve_all_alerts_in_firebase():
    """Mark all active alerts as resolved in the Firebase Realtime Database."""
    db = get_firebase_db()
    if not db:
        return

    def run_sync():
        try:
            ref = db.reference("alerts")
            alerts_data = ref.get()
            if not alerts_data:
                return

            updates = {}
            for key, val in alerts_data.items():
                if isinstance(val, dict) and not val.get("resolved"):
                    updates[f"{key}/resolved"] = True
            if updates:
                ref.update(updates)
        except Exception as err:
            print(f"⚠️ Firebase resolve_all_alerts_in_firebase error: {err}")

    await asyncio.to_thread(run_sync)


async def sync_all_to_firebase():
    """Query current SQLite state and populate facilities, alerts, and city stats to Firebase Realtime Database."""
    db = get_firebase_db()
    if not db:
        return

    print("🔥 Starting full database sync to Firebase Realtime Database...")

    from app.database import get_db
    sqlite_db = await get_db()

    # 1. Sync facilities
    sql = """
        SELECT f.*, r.nh3_ppm, r.voc_ppm, r.door_count, r.humidity, r.temperature, r.water_flow, r.recorded_at
        FROM facilities f
        LEFT JOIN sensor_readings r ON r.id = (
            SELECT id FROM sensor_readings 
            WHERE facility_id = f.id 
            ORDER BY recorded_at DESC LIMIT 1
        )
        WHERE f.is_active = 1
    """
    cursor = await sqlite_db.execute(sql)
    rows = await cursor.fetchall()

    facilities_payload = {}
    for row in rows:
        f_dict = dict(row)
        facilities_payload[f_dict["id"]] = {
            "nh3": f_dict.get("nh3_ppm"),
            "voc": f_dict.get("voc_ppm"),
            "doors": f_dict.get("door_count"),
            "humidity": f_dict.get("humidity"),
            "score": f_dict.get("score"),
            "status": f_dict.get("status"),
            "last_cleaned": f_dict.get("last_cleaned"),
        }

    # 2. Sync alerts
    sql = """
        SELECT a.*, f.name AS facility_name, f.zone
        FROM alerts a
        JOIN facilities f ON f.id = a.facility_id
    """
    cursor = await sqlite_db.execute(sql)
    rows = await cursor.fetchall()

    alerts_payload = {}
    for row in rows:
        a_dict = dict(row)
        alerts_payload[str(a_dict["id"])] = {
            "facility_id": a_dict["facility_id"],
            "facility_name": a_dict["facility_name"],
            "zone": a_dict["zone"],
            "alert_type": a_dict["alert_type"],
            "severity": a_dict["severity"],
            "message": a_dict["message"],
            "value": a_dict["value"],
            "threshold": a_dict["threshold"],
            "resolved": bool(a_dict["resolved"]),
            "created_at": a_dict["created_at"]
        }

    # Write payload in a background thread
    def run_sync():
        try:
            db.reference("facilities").set(facilities_payload)
            db.reference("alerts").set(alerts_payload)
        except Exception as err:
            print(f"⚠️ Firebase sync_all_to_firebase write error: {err}")

    await asyncio.to_thread(run_sync)

    # 3. Sync city stats
    await sync_city_stats()
    print("🔥 Full database sync to Firebase Realtime Database completed.")
