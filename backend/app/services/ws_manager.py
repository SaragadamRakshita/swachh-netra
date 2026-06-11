"""
WebSocket connection manager.
Broadcasts real-time sensor updates, alerts, and dispatch events to all connected dashboard clients.
"""

import json
import asyncio
from typing import List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"🔌 WS client connected — total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        print(f"🔌 WS client disconnected — total: {len(self.active)}")

    async def broadcast(self, message: dict):
        """Send JSON to all connected clients."""
        dead = []
        payload = json.dumps(message)
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, message: dict):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.disconnect(ws)


# Singleton
manager = ConnectionManager()


async def broadcast_sensor_update(facility_id: str, reading: dict):
    await manager.broadcast({
        "type": "sensor_update",
        "facility_id": facility_id,
        "data": reading,
    })


async def broadcast_alert(alert: dict):
    await manager.broadcast({
        "type": "alert",
        "facility_id": alert.get("facility_id"),
        "data": alert,
    })


async def broadcast_dispatch(dispatch: dict):
    await manager.broadcast({
        "type": "dispatch",
        "facility_id": dispatch.get("facility_id"),
        "data": dispatch,
    })


async def broadcast_simulate(facility_id: str, sim_data: dict):
    await manager.broadcast({
        "type": "simulate",
        "facility_id": facility_id,
        "data": sim_data,
    })
