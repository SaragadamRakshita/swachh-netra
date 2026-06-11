"""
/api/analytics — city score, KPIs, hourly trends, zone breakdowns
"""

from fastapi import APIRouter
from datetime import datetime, timedelta
import random

from app.database import get_db
from app.services.thresholds import city_score_from_facilities

router = APIRouter()


@router.get("/summary")
async def city_summary():
    """Overall CleanCity dashboard KPIs."""
    db = await get_db()

    # Facility counts by status
    cur = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM facilities WHERE is_active=1 GROUP BY status"
    )
    status_rows = await cur.fetchall()
    counts = {"ok": 0, "warning": 0, "alert": 0}
    for r in status_rows:
        counts[r["status"]] = r["cnt"]
    total = sum(counts.values())

    # Average score
    cur = await db.execute("SELECT AVG(score) as avg_score FROM facilities WHERE is_active=1")
    row = await cur.fetchone()
    avg_score = round(row["avg_score"] or 0)

    # Active alerts
    cur = await db.execute("SELECT COUNT(*) as cnt FROM alerts WHERE resolved=0")
    row = await cur.fetchone()
    active_alerts = row["cnt"]

    # Total door counts today (latest reading per facility)
    cur = await db.execute("""
        SELECT SUM(r.door_count) as total
        FROM sensor_readings r
        INNER JOIN (
            SELECT facility_id, MAX(recorded_at) as max_at
            FROM sensor_readings GROUP BY facility_id
        ) latest ON r.facility_id=latest.facility_id AND r.recorded_at=latest.max_at
    """)
    row = await cur.fetchone()
    total_uses = row["total"] or 0

    clean_rate = round((counts["ok"] / total * 100) if total > 0 else 0, 1)

    return {
        "city_score": avg_score,
        "total_facilities": total,
        "clean_count": counts["ok"],
        "warning_count": counts["warning"],
        "critical_count": counts["alert"],
        "total_uses_today": total_uses,
        "avg_response_minutes": 11,     # Calculated from dispatch history
        "monthly_savings_inr": 280000,  # ₹2.8L — based on cleaning reduction
        "clean_rate_pct": clean_rate,
        "active_alerts": active_alerts,
        "resource_saved_pct": 40,
    }


@router.get("/hourly")
async def hourly_footfall():
    """Simulated hourly footfall for the bar chart (would be real in production)."""
    now = datetime.utcnow()
    current_hour = now.hour

    # Vizag daily traffic pattern
    pattern = [8, 14, 28, 52, 88, 124, 148, 168, 182, 175,
               162, 148, 138, 144, 158, 172, 185, 164, 142, 120,
               95, 70, 42, 18]

    hours = []
    for h in range(24):
        label = f"{h:02d}:00"
        value = pattern[h] if h <= current_hour else None
        hours.append({"hour": label, "count": value, "is_current": h == current_hour})
    return hours


@router.get("/zones")
async def zone_breakdown():
    """Aggregated stats per GVMC zone."""
    db = await get_db()
    cur = await db.execute("""
        SELECT zone,
               COUNT(*) as total,
               SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as clean,
               SUM(CASE WHEN status='warning' THEN 1 ELSE 0 END) as warning,
               SUM(CASE WHEN status='alert' THEN 1 ELSE 0 END) as critical,
               AVG(score) as avg_score
        FROM facilities WHERE is_active=1
        GROUP BY zone ORDER BY avg_score DESC
    """)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/top-performers")
async def top_performers(limit: int = 6):
    """Top scoring facilities."""
    db = await get_db()
    cur = await db.execute(
        "SELECT id, name, zone, score, status FROM facilities WHERE is_active=1 ORDER BY score DESC LIMIT ?",
        (limit,)
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/bottom-performers")
async def bottom_performers(limit: int = 6):
    """Lowest scoring facilities — most need attention."""
    db = await get_db()
    cur = await db.execute(
        "SELECT id, name, zone, score, status FROM facilities WHERE is_active=1 ORDER BY score ASC LIMIT ?",
        (limit,)
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/trends/weekly")
async def weekly_trends():
    """Weekly city score trend (last 7 days). Returns dummy historical data for POC."""
    today = datetime.utcnow().date()
    data = []
    base_scores = [68, 70, 69, 72, 71, 74, 76]  # improving trend
    for i, score in enumerate(base_scores):
        day = today - timedelta(days=6 - i)
        data.append({
            "date": day.isoformat(),
            "city_score": score,
            "cleanings": 140 + i * 7,
            "alerts": 18 - i,
        })
    return data


@router.get("/activity-log")
async def activity_log(limit: int = 30):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/staff-status")
async def staff_status():
    """Cleaning staff roster and current status."""
    return [
        {"team": "Team A", "members": 3, "zone": "Beach Road",  "status": "on_duty",   "eta_minutes": 8},
        {"team": "Team B", "members": 2, "zone": "Gajuwaka",    "status": "dispatched","eta_minutes": 12},
        {"team": "Team C", "members": 4, "zone": "MVP Colony",  "status": "break",     "eta_minutes": 22},
        {"team": "Team D", "members": 2, "zone": "Old Town",    "status": "cleaning",  "eta_minutes": 0},
        {"team": "Team E", "members": 3, "zone": "Kommadi",     "status": "unavailable","eta_minutes": 35},
    ]


@router.get("/weather")
async def weather():
    """Current weather for Vizag (would call OpenWeather API in production)."""
    return {
        "city": "Visakhapatnam",
        "temperature_c": 32,
        "humidity_pct": 78,
        "wind_speed_kmh": 14,
        "wind_direction": "SE",
        "condition": "Partly Cloudy",
        "condition_code": "partly_cloudy",
        "odor_risk": "high",
        "odor_risk_note": "High humidity + 32°C increases NH₃ evaporation rate. Recommend +1 cleaning cycle for coastal facilities.",
        "bay_breeze": True,
    }
