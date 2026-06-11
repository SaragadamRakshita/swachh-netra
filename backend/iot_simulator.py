#!/usr/bin/env python3
"""
IoT Sensor Simulator
Mimics 15 ESP32 nodes pushing live sensor readings to the CleanCity backend.
Run this alongside the server to see live data flowing through the system.

Usage:
    python iot_simulator.py                  # Gentle realistic drift
    python iot_simulator.py --chaos          # Inject random spikes for demo
    python iot_simulator.py --facility VZ-001 --interval 2
"""

import asyncio
import aiohttp
import random
import argparse
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

FACILITIES = [
    {"id": "VZ-001", "base_nh3": 105, "base_voc": 80,  "base_doors": 310, "base_hum": 74},
    {"id": "VZ-002", "base_nh3": 88,  "base_voc": 72,  "base_doors": 410, "base_hum": 68},
    {"id": "VZ-003", "base_nh3": 70,  "base_voc": 85,  "base_doors": 238, "base_hum": 62},
    {"id": "VZ-004", "base_nh3": 65,  "base_voc": 56,  "base_doors": 195, "base_hum": 71},
    {"id": "VZ-005", "base_nh3": 9,   "base_voc": 13,  "base_doors": 80,  "base_hum": 58},
    {"id": "VZ-006", "base_nh3": 11,  "base_voc": 17,  "base_doors": 102, "base_hum": 55},
    {"id": "VZ-007", "base_nh3": 37,  "base_voc": 70,  "base_doors": 210, "base_hum": 80},
    {"id": "VZ-008", "base_nh3": 40,  "base_voc": 51,  "base_doors": 375, "base_hum": 66},
    {"id": "VZ-009", "base_nh3": 10,  "base_voc": 15,  "base_doors": 72,  "base_hum": 59},
    {"id": "VZ-010", "base_nh3": 13,  "base_voc": 21,  "base_doors": 55,  "base_hum": 77},
    {"id": "VZ-011", "base_nh3": 31,  "base_voc": 43,  "base_doors": 160, "base_hum": 63},
    {"id": "VZ-012", "base_nh3": 17,  "base_voc": 25,  "base_doors": 47,  "base_hum": 70},
    {"id": "VZ-013", "base_nh3": 22,  "base_voc": 34,  "base_doors": 87,  "base_hum": 61},
    {"id": "VZ-014", "base_nh3": 56,  "base_voc": 60,  "base_doors": 245, "base_hum": 67},
    {"id": "VZ-015", "base_nh3": 15,  "base_voc": 23,  "base_doors": 91,  "base_hum": 76},
]

# Live state (drifts over time)
state = {f["id"]: {
    "nh3": f["base_nh3"],
    "voc": f["base_voc"],
    "doors": f["base_doors"],
    "hum": f["base_hum"],
    "temp": 31.0 + random.uniform(-1, 2),
    "water": round(1.0 + random.random(), 2),
} for f in FACILITIES}


def drift(value: float, delta: int = 3, min_val: float = 0, max_val: float = 200) -> float:
    return round(max(min_val, min(max_val, value + random.randint(-delta, delta))), 1)


async def send_reading(session: aiohttp.ClientSession, facility_id: str, chaos: bool = False):
    s = state[facility_id]

    # Drift values gradually
    s["nh3"]   = drift(s["nh3"],   2, 5, 150)
    s["voc"]   = drift(s["voc"],   2, 5, 120)
    s["doors"] = int(drift(s["doors"], 3, 0, 500))
    s["hum"]   = drift(s["hum"],   1, 30, 95)
    s["temp"]  = drift(s["temp"],  1, 22, 42)

    # Chaos mode — occasional spike
    if chaos and random.random() < 0.08:
        spike_type = random.choice(["nh3", "voc", "doors"])
        if spike_type == "nh3":
            s["nh3"] = random.randint(75, 130)
            print(f"  💥 SPIKE [{facility_id}] NH₃ → {s['nh3']} ppm")
        elif spike_type == "voc":
            s["voc"] = random.randint(70, 100)
            print(f"  💥 SPIKE [{facility_id}] VOC → {s['voc']} ppm")
        else:
            s["doors"] = random.randint(150, 300)
            print(f"  💥 SPIKE [{facility_id}] Doors → {s['doors']}")

    payload = {
        "facility_id": facility_id,
        "nh3_ppm":    s["nh3"],
        "voc_ppm":    s["voc"],
        "door_count": s["doors"],
        "humidity":   s["hum"],
        "temperature": s["temp"],
        "water_flow": s["water"],
    }

    try:
        url = f"{BASE_URL}/api/facilities/{facility_id}/readings"
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            result = await resp.json()
            status_icon = "🟢" if result.get("status") == "ok" else ("🟡" if result.get("status") == "warning" else "🔴")
            print(f"  {status_icon} {facility_id} | NH₃:{s['nh3']:.0f} VOC:{s['voc']:.0f} Doors:{s['doors']} | Score:{result.get('score','?')} Alerts:{result.get('alerts_raised',0)}")
    except Exception as e:
        print(f"  ❌ {facility_id} — connection error: {e}")


async def run_simulator(args):
    target_ids = [args.facility] if args.facility else [f["id"] for f in FACILITIES]
    interval = args.interval

    print(f"""
╔══════════════════════════════════════════════════════╗
║     CleanCity IoT Simulator — GVMC Visakhapatnam     ║
║  Nodes: {len(target_ids):<4}  Interval: {interval}s  Chaos: {'ON ' if args.chaos else 'OFF'}          ║
║  Target: {BASE_URL:<40} ║
╚══════════════════════════════════════════════════════╝
    """)

    async with aiohttp.ClientSession() as session:
        # Health check
        try:
            async with session.get(f"{BASE_URL}/api/health") as r:
                if r.status == 200:
                    print("✅ Server reachable — starting simulation...\n")
                else:
                    print(f"⚠️  Server returned {r.status}")
        except Exception:
            print("❌ Cannot reach server at", BASE_URL)
            print("   Make sure the backend is running: uvicorn app.main:app --reload\n")
            return

        cycle = 0
        while True:
            cycle += 1
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"\n── Cycle #{cycle:04d}  [{ts}] {'(CHAOS MODE)' if args.chaos else ''} ──")
            tasks = [send_reading(session, fid, args.chaos) for fid in target_ids]
            await asyncio.gather(*tasks)
            await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CleanCity IoT Simulator")
    parser.add_argument("--chaos",    action="store_true", help="Inject random spikes")
    parser.add_argument("--facility", type=str,            help="Simulate single facility only")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between readings (default: 5)")
    args = parser.parse_args()
    asyncio.run(run_simulator(args))
