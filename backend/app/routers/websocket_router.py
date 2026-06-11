"""
/ws — WebSocket endpoint for real-time dashboard updates.
The frontend connects here to receive live sensor updates, alerts, and dispatch events.
"""

import asyncio
import json
import random
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import manager
from app.database import get_db

router = APIRouter()

FACILITY_IDS = [
    "VZ-001","VZ-002","VZ-003","VZ-004","VZ-005",
    "VZ-006","VZ-007","VZ-008","VZ-009","VZ-010",
    "VZ-011","VZ-012","VZ-013","VZ-014","VZ-015",
]


@router.websocket("/live")
async def websocket_live(ws: WebSocket):
    """
    Main live feed endpoint.
    - Client connects → receives current snapshot
    - Server pushes sensor updates every 5 seconds
    - Server pushes any real alerts/dispatches triggered by API calls
    """
    await manager.connect(ws)
    try:
        # Send welcome snapshot
        db = await get_db()
        cur = await db.execute(
            "SELECT id, name, zone, status, score FROM facilities WHERE is_active=1"
        )
        facilities = [dict(r) for r in await cur.fetchall()]
        await manager.send_to(ws, {
            "type": "snapshot",
            "data": {"facilities": facilities, "connected_at": datetime.utcnow().isoformat()}
        })

        # Keep alive loop + simulate small live drift every 5s
        while True:
            await asyncio.sleep(5)
            # Send a simulated micro-update for a random facility
            fid = random.choice(FACILITY_IDS)
            cur = await db.execute(
                "SELECT * FROM sensor_readings WHERE facility_id=? ORDER BY recorded_at DESC LIMIT 1",
                (fid,)
            )
            row = await cur.fetchone()
            if row:
                drift = lambda v: max(0, v + random.randint(-2, 2))
                update = {
                    "type": "sensor_update",
                    "facility_id": fid,
                    "data": {
                        "nh3_ppm":    drift(row["nh3_ppm"]),
                        "voc_ppm":    drift(row["voc_ppm"]),
                        "door_count": row["door_count"] + random.randint(0, 2),
                        "humidity":   row["humidity"],
                        "recorded_at": datetime.utcnow().isoformat(),
                        "live_drift": True,
                    }
                }
                await manager.send_to(ws, update)

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        print(f"WS error: {e}")
        manager.disconnect(ws)


@router.websocket("/alerts")
async def websocket_alerts_only(ws: WebSocket):
    """Alerts-only feed — lighter channel for mobile clients."""
    await manager.connect(ws)
    try:
        while True:
            await asyncio.sleep(30)
            await manager.send_to(ws, {"type": "ping", "ts": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(ws)
