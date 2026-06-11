"""
/api/facilities — CRUD + latest sensor readings
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.schemas import FacilityOut, FacilityCreate, FacilityUpdate, SensorReadingIn, SensorReadingOut
from app.services.thresholds import evaluate_reading, calculate_score
from app.services.ws_manager import broadcast_sensor_update, broadcast_alert

router = APIRouter()


# ── GET all facilities ──
@router.get("/", response_model=List[dict])
async def list_facilities(
    zone: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    db = await get_db()
    sql = "SELECT f.*, r.nh3_ppm, r.voc_ppm, r.door_count, r.humidity, r.temperature, r.water_flow, r.recorded_at AS reading_at FROM facilities f LEFT JOIN sensor_readings r ON r.id = (SELECT id FROM sensor_readings WHERE facility_id = f.id ORDER BY recorded_at DESC LIMIT 1) WHERE f.is_active=1"
    params = []
    if zone:
        sql += " AND f.zone=?"; params.append(zone)
    if status:
        sql += " AND f.status=?"; params.append(status)
    if search:
        sql += " AND (f.name LIKE ? OR f.id LIKE ? OR f.zone LIKE ?)"; params += [f"%{search}%"]*3

    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── GET single facility ──
@router.get("/{facility_id}")
async def get_facility(facility_id: str):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM facilities WHERE id=? AND is_active=1", (facility_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "Facility not found")
    return dict(row)


# ── POST new facility ──
@router.post("/", status_code=201)
async def create_facility(body: FacilityCreate):
    db = await get_db()
    now = datetime.utcnow().isoformat()
    try:
        await db.execute(
            "INSERT INTO facilities (id,name,zone,location,latitude,longitude,status,score,last_cleaned,is_active) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (body.id, body.name, body.zone, body.location, body.latitude, body.longitude, "ok", 100, now)
        )
        await db.commit()
    except Exception as e:
        raise HTTPException(400, f"Facility already exists or invalid data: {e}")
    return {"message": "Facility created", "id": body.id}


# ── PATCH facility ──
@router.patch("/{facility_id}")
async def update_facility(facility_id: str, body: FacilityUpdate):
    db = await get_db()
    updates, params = [], []
    if body.name    is not None: updates.append("name=?");    params.append(body.name)
    if body.status  is not None: updates.append("status=?");  params.append(body.status.value)
    if body.score   is not None: updates.append("score=?");   params.append(body.score)
    if body.zone    is not None: updates.append("zone=?");    params.append(body.zone)
    if not updates:
        raise HTTPException(400, "No fields to update")
    params.append(facility_id)
    await db.execute(f"UPDATE facilities SET {', '.join(updates)} WHERE id=?", params)
    await db.commit()
    return {"message": "Updated", "id": facility_id}


# ── DELETE (soft) facility ──
@router.delete("/{facility_id}")
async def delete_facility(facility_id: str):
    db = await get_db()
    await db.execute("UPDATE facilities SET is_active=0 WHERE id=?", (facility_id,))
    await db.commit()
    return {"message": "Facility deactivated", "id": facility_id}


# ── POST sensor reading (IoT device pushes here) ──
@router.post("/{facility_id}/readings", status_code=201)
async def post_reading(facility_id: str, body: SensorReadingIn):
    db = await get_db()
    now = datetime.utcnow().isoformat()

    # Check facility exists
    cur = await db.execute("SELECT * FROM facilities WHERE id=?", (facility_id,))
    facility = await cur.fetchone()
    if not facility:
        raise HTTPException(404, "Facility not found")

    # Save reading
    await db.execute(
        """INSERT INTO sensor_readings
           (facility_id,nh3_ppm,voc_ppm,door_count,humidity,temperature,water_flow,recorded_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (facility_id, body.nh3_ppm, body.voc_ppm, body.door_count,
         body.humidity, body.temperature, body.water_flow, now)
    )

    # Evaluate thresholds
    status, triggers = evaluate_reading(
        body.nh3_ppm, body.voc_ppm, body.door_count,
        body.humidity, body.temperature, body.water_flow
    )

    # Calculate score (assume 60 min since last clean as default)
    score = calculate_score(body.nh3_ppm, body.voc_ppm, body.door_count, 60, body.water_flow)

    # Update facility status + score
    await db.execute(
        "UPDATE facilities SET status=?, score=? WHERE id=?",
        (status, score, facility_id)
    )

    # Insert new alerts
    new_alerts = []
    for t in triggers:
        cursor = await db.execute(
            """INSERT INTO alerts
               (facility_id,alert_type,severity,message,value,threshold,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (facility_id, t.sensor, t.severity, t.message, t.value, t.threshold, now)
        )
        alert_id = cursor.lastrowid
        new_alerts.append({"id": alert_id, "message": t.message, "severity": t.severity})

    # Activity log
    if triggers:
        top = max(triggers, key=lambda x: x.severity)
        icon = "🔴" if top.severity == "critical" else "🟡"
        await db.execute(
            "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES (?,?,?,?,?)",
            (top.severity, icon, top.message, facility_id, now)
        )

    await db.commit()

    reading_dict = {
        "facility_id": facility_id, "nh3_ppm": body.nh3_ppm, "voc_ppm": body.voc_ppm,
        "door_count": body.door_count, "humidity": body.humidity,
        "temperature": body.temperature, "water_flow": body.water_flow,
        "status": status, "score": score, "recorded_at": now
    }

    # Broadcast via WebSocket
    await broadcast_sensor_update(facility_id, reading_dict)
    for a in new_alerts:
        await broadcast_alert({**a, "facility_id": facility_id})

    # Sync to Firebase Realtime Database
    try:
        from app.services.firebase_sync import sync_facility, sync_city_stats, push_alert_to_firebase
        await sync_facility(facility_id)
        for a in new_alerts:
            await push_alert_to_firebase(a["id"])
        await sync_city_stats()
    except Exception as e:
        print(f"⚠️ Firebase sync error in post_reading: {e}")

    return {"message": "Reading recorded", "status": status, "score": score, "alerts_raised": len(new_alerts)}


# ── GET reading history ──
@router.get("/{facility_id}/readings", response_model=List[SensorReadingOut])
async def get_readings(
    facility_id: str,
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM sensor_readings WHERE facility_id=? ORDER BY recorded_at DESC LIMIT ? OFFSET ?",
        (facility_id, limit, offset)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
