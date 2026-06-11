"""
/api/alerts — list, resolve, and query alerts
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.schemas import AlertResolve

router = APIRouter()


@router.get("/")
async def list_alerts(
    severity: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    facility_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    db = await get_db()
    sql = """
        SELECT a.*, f.name AS facility_name, f.zone
        FROM alerts a
        JOIN facilities f ON f.id = a.facility_id
        WHERE 1=1
    """
    params = []
    if severity:      sql += " AND a.severity=?";    params.append(severity)
    if resolved is not None: sql += " AND a.resolved=?"; params.append(1 if resolved else 0)
    if facility_id:   sql += " AND a.facility_id=?"; params.append(facility_id)
    sql += " ORDER BY a.created_at DESC LIMIT ?"
    params.append(limit)

    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/active/count")
async def active_alert_count():
    db = await get_db()
    cursor = await db.execute(
        "SELECT severity, COUNT(*) as cnt FROM alerts WHERE resolved=0 GROUP BY severity"
    )
    rows = await cursor.fetchall()
    result = {"critical": 0, "warning": 0, "total": 0}
    for r in rows:
        result[r["severity"]] = r["cnt"]
        result["total"] += r["cnt"]
    return result


@router.get("/{alert_id}")
async def get_alert(alert_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "Alert not found")
    return dict(row)


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, body: AlertResolve = AlertResolve()):
    db = await get_db()
    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE alerts SET resolved=1, resolved_at=? WHERE id=?",
        (now, alert_id)
    )
    await db.execute(
        "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) SELECT 'ok','✅','Alert #' || id || ' resolved: ' || message, facility_id, ? FROM alerts WHERE id=?",
        (now, alert_id)
    )
    await db.commit()

    # Sync to Firebase Realtime Database
    try:
        from app.services.firebase_sync import resolve_alert_in_firebase, sync_city_stats
        await resolve_alert_in_firebase(alert_id)
        await sync_city_stats()
    except Exception as e:
        print(f"⚠️ Firebase sync error in resolve_alert: {e}")

    return {"message": "Alert resolved", "id": alert_id}


@router.post("/resolve-all")
async def resolve_all_alerts():
    db = await get_db()
    now = datetime.utcnow().isoformat()
    cursor = await db.execute("UPDATE alerts SET resolved=1, resolved_at=? WHERE resolved=0", (now,))
    await db.execute(
        "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES ('ok','✅','All active alerts resolved — Mark All Clear executed',NULL,?)",
        (now,)
    )
    await db.commit()

    # Sync to Firebase Realtime Database
    try:
        from app.services.firebase_sync import resolve_all_alerts_in_firebase, sync_city_stats
        await resolve_all_alerts_in_firebase()
        await sync_city_stats()
    except Exception as e:
        print(f"⚠️ Firebase sync error in resolve_all_alerts: {e}")

    return {"message": "All alerts resolved", "count": cursor.rowcount}
