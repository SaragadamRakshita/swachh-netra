"""
/api/simulate — inject fake sensor events for demo / hackathon POC
Triggers a real alert pipeline so the WS feed and log update live.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import random

from app.database import get_db
from app.models.schemas import SimulateRequest, SimulateResponse
from app.services.thresholds import evaluate_reading, calculate_score
from app.services.ws_manager import broadcast_sensor_update, broadcast_alert, broadcast_simulate

router = APIRouter()

SIM_CONFIGS = {
    "nh3": {
        "label": "NH₃ Spike",
        "icon": "🟠",
        "value_range": (85, 120),
        "threshold": 50,
        "description": "Ammonia level critical — immediate cleaning required",
    },
    "voc": {
        "label": "VOC Surge",
        "icon": "💨",
        "value_range": (78, 95),
        "threshold": 65,
        "description": "VOC concentration elevated — ventilation check needed",
    },
    "door_count": {
        "label": "Crowd Surge",
        "icon": "👥",
        "value_range": (160, 230),
        "threshold": 120,
        "description": "High footfall exceeded threshold — schedule immediate cleaning",
    },
    "water_flow": {
        "label": "Water Failure",
        "icon": "🚱",
        "value_range": (0, 0),
        "threshold": 0.1,
        "description": "Water flow sensor reads zero — infrastructure failure",
    },
}


@router.post("/", response_model=SimulateResponse)
async def run_simulation(body: SimulateRequest):
    """
    Inject a simulated sensor alert for a given facility.
    This runs the full pipeline: saves reading → evaluates thresholds → raises alert → broadcasts via WS.
    """
    db = await get_db()
    now = datetime.utcnow().isoformat()

    # Verify facility
    cur = await db.execute("SELECT * FROM facilities WHERE id=?", (body.facility_id,))
    facility = await cur.fetchone()
    if not facility:
        raise HTTPException(404, f"Facility {body.facility_id} not found")

    cfg = SIM_CONFIGS.get(body.sim_type.value)
    if not cfg:
        raise HTTPException(400, f"Unknown sim_type: {body.sim_type}")

    # Get current reading to use as baseline
    cur = await db.execute(
        "SELECT * FROM sensor_readings WHERE facility_id=? ORDER BY recorded_at DESC LIMIT 1",
        (body.facility_id,)
    )
    current = await cur.fetchone()
    baseline = dict(current) if current else {
        "nh3_ppm": 15, "voc_ppm": 22, "door_count": 60,
        "humidity": 60, "temperature": 30.0, "water_flow": 1.5
    }

    # Build simulated values
    lo, hi = cfg["value_range"]
    triggered_value = body.custom_value if body.custom_value is not None else (
        random.uniform(lo, hi) if lo != hi else lo
    )
    triggered_value = round(triggered_value, 1)

    nh3 = triggered_value if body.sim_type.value == "nh3" else baseline["nh3_ppm"]
    voc = triggered_value if body.sim_type.value == "voc" else baseline["voc_ppm"]
    doors = int(triggered_value) if body.sim_type.value == "door_count" else baseline["door_count"]
    water = 0.0 if body.sim_type.value == "water_flow" else (baseline.get("water_flow") or 1.5)
    humidity = baseline.get("humidity", 65)
    temperature = baseline.get("temperature", 30.0)

    # Save reading
    await db.execute(
        """INSERT INTO sensor_readings
           (facility_id,nh3_ppm,voc_ppm,door_count,humidity,temperature,water_flow,recorded_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (body.facility_id, nh3, voc, doors, humidity, temperature, water, now)
    )

    # Evaluate + score
    status, triggers = evaluate_reading(nh3, voc, doors, humidity, temperature, water)
    score = calculate_score(nh3, voc, doors, 120, water)

    # Update facility
    await db.execute(
        "UPDATE facilities SET status=?, score=? WHERE id=?",
        (status, score, body.facility_id)
    )

    # Save alert
    message = f"[SIMULATED] {cfg['label']} at {facility['name']}: {triggered_value} (threshold: {cfg['threshold']})"
    cur = await db.execute(
        """INSERT INTO alerts
           (facility_id,alert_type,severity,message,value,threshold,created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (body.facility_id, body.sim_type.value, "critical", message,
         triggered_value, cfg["threshold"], now)
    )
    alert_id = cur.lastrowid

    # Activity log
    await db.execute(
        "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES ('alert',?,?,?,?)",
        (cfg["icon"], message, body.facility_id, now)
    )

    await db.commit()

    # Broadcast everything
    reading_payload = {
        "facility_id": body.facility_id,
        "nh3_ppm": nh3, "voc_ppm": voc, "door_count": doors,
        "humidity": humidity, "status": status, "score": score,
        "recorded_at": now, "simulated": True,
    }
    await broadcast_sensor_update(body.facility_id, reading_payload)
    await broadcast_alert({"id": alert_id, "facility_id": body.facility_id, "message": message, "severity": "critical"})
    await broadcast_simulate(body.facility_id, {
        "sim_type": body.sim_type.value,
        "label": cfg["label"],
        "icon": cfg["icon"],
        "triggered_value": triggered_value,
        "threshold": cfg["threshold"],
        "facility_name": facility["name"],
    })

    return SimulateResponse(
        facility_id=body.facility_id,
        sim_type=body.sim_type.value,
        triggered_value=triggered_value,
        threshold=cfg["threshold"],
        alert_id=alert_id,
        message=message,
    )


@router.get("/types")
async def simulation_types():
    """List all available simulation scenarios."""
    return [
        {"type": k, "label": v["label"], "icon": v["icon"],
         "threshold": v["threshold"], "description": v["description"]}
        for k, v in SIM_CONFIGS.items()
    ]
