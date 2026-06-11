"""
Database — SQLite (dev) / PostgreSQL (prod)
Uses aiosqlite for async support.
Swap DATABASE_URL in .env to switch databases.
"""

import os
import json
import random
from datetime import datetime, timedelta

import aiosqlite

DATABASE_URL = os.getenv("DATABASE_URL", "cleancity.db")

# ── Shared connection ──
_db = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_URL)
        _db.row_factory = aiosqlite.Row
    return _db

# ── Schema ──
SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    zone        TEXT NOT NULL,
    location    TEXT NOT NULL,
    latitude    REAL,
    longitude   REAL,
    status      TEXT DEFAULT 'ok',
    score       INTEGER DEFAULT 100,
    last_cleaned TEXT,
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id TEXT NOT NULL,
    nh3_ppm     REAL NOT NULL,
    voc_ppm     REAL NOT NULL,
    door_count  INTEGER NOT NULL,
    humidity    REAL NOT NULL,
    temperature REAL,
    water_flow  REAL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id TEXT NOT NULL,
    alert_type  TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL,
    value       REAL,
    threshold   REAL,
    resolved    INTEGER DEFAULT 0,
    resolved_at TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY(facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS dispatches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id  TEXT NOT NULL,
    dispatched_by TEXT NOT NULL,
    team         TEXT,
    status       TEXT DEFAULT 'dispatched',
    notes        TEXT,
    dispatched_at TEXT NOT NULL,
    completed_at  TEXT,
    FOREIGN KEY(facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    icon        TEXT,
    message     TEXT NOT NULL,
    facility_id TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role        TEXT DEFAULT 'operator',
    name        TEXT,
    created_at  TEXT NOT NULL
);
"""

# ── Seed data ──
SEED_FACILITIES = [
    ("VZ-001","RK Beach — Block 3","Beach Road","Ramakrishna Beach",17.7100,83.3360,"alert",31),
    ("VZ-002","Gajuwaka Bus Terminus","Gajuwaka","Gajuwaka Junction",17.6900,83.2100,"alert",36),
    ("VZ-003","Steel Plant Gate-2","Gajuwaka","VSP Township",17.7000,83.2000,"alert",42),
    ("VZ-004","VUDA Park South Gate","MVP Colony","VUDA Layout",17.7200,83.3100,"alert",46),
    ("VZ-005","Vizag Railway Stn PF-1","Old Town","Visakhapatnam Jn.",17.6868,83.2185,"ok",96),
    ("VZ-006","MVP Colony Market","MVP Colony","MVP Double Road",17.7400,83.3300,"ok",91),
    ("VZ-007","Rushikonda Beach","Kommadi","Rushikonda Tourist Area",17.7700,83.3700,"warning",61),
    ("VZ-008","Simhachalam Temple","Old Town","Simhachalam Hill",17.7400,83.2700,"warning",58),
    ("VZ-009","KGH Hospital","Old Town","King George Hospital",17.6900,83.2100,"ok",89),
    ("VZ-010","Waltair Club Beach","Beach Road","Waltair Uplands",17.7200,83.3400,"ok",86),
    ("VZ-011","Madhurwada Market","Madhurwada","Madhurwada Circle",17.7900,83.3600,"warning",67),
    ("VZ-012","Bheemunipatnam Beach","Bheemunipatnam","Bheemunipatnam",17.8900,83.4600,"ok",74),
    ("VZ-013","PM Palem Market","Madhurwada","PM Palem",17.7800,83.3500,"ok",82),
    ("VZ-014","Kommadi Junction","Kommadi","Kommadi",17.7600,83.3800,"alert",49),
    ("VZ-015","Tenneti Park Gate","Beach Road","Tenneti Park",17.7300,83.3500,"ok",87),
]

SEED_READINGS = [
    ("VZ-001", 107, 82, 318, 74, 32.5, 0.8),
    ("VZ-002", 91,  74, 418, 68, 33.0, 1.2),
    ("VZ-003", 72,  88, 241, 62, 34.5, 1.0),
    ("VZ-004", 68,  58, 197, 71, 31.8, 0.0),
    ("VZ-005", 9,   14, 82,  58, 30.0, 2.1),
    ("VZ-006", 12,  18, 104, 55, 29.5, 1.8),
    ("VZ-007", 38,  71, 213, 80, 31.0, 1.5),
    ("VZ-008", 41,  53, 380, 66, 30.8, 1.9),
    ("VZ-009", 10,  16, 74,  59, 29.0, 2.2),
    ("VZ-010", 14,  22, 56,  77, 30.5, 1.7),
    ("VZ-011", 32,  44, 162, 63, 31.5, 1.3),
    ("VZ-012", 18,  26, 48,  70, 30.2, 1.6),
    ("VZ-013", 23,  35, 89,  61, 30.8, 1.9),
    ("VZ-014", 58,  62, 248, 67, 32.0, 1.1),
    ("VZ-015", 16,  24, 93,  76, 31.2, 1.8),
]

async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()

    # Check if already seeded
    cursor = await db.execute("SELECT COUNT(*) FROM facilities")
    row = await cursor.fetchone()
    if row[0] > 0:
        return

    now = datetime.utcnow().isoformat()
    for f in SEED_FACILITIES:
        last = (datetime.utcnow() - timedelta(minutes=random.randint(20, 260))).isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO facilities VALUES (?,?,?,?,?,?,?,?,?,1)",
            (*f, last)
        )

    for r in SEED_READINGS:
        await db.execute(
            """INSERT INTO sensor_readings
               (facility_id,nh3_ppm,voc_ppm,door_count,humidity,temperature,water_flow,recorded_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (*r, now)
        )

    # Seed some alerts
    alert_seeds = [
        ("VZ-001","nh3","critical","NH₃ level critical: 107 ppm",107,50),
        ("VZ-002","door_count","critical","Usage threshold exceeded: 418 uses",418,120),
        ("VZ-003","voc","critical","VOC elevated: 88 ppm",88,65),
        ("VZ-007","voc","warning","VOC warning: 71 ppm",71,65),
        ("VZ-008","door_count","warning","High usage: 380 uses",380,120),
    ]
    for a in alert_seeds:
        await db.execute(
            """INSERT INTO alerts (facility_id,alert_type,severity,message,value,threshold,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (*a, now)
        )

    # Seed default admin user (password: admin123)
    import hashlib
    pw = hashlib.sha256(b"admin123").hexdigest()
    await db.execute(
        "INSERT OR IGNORE INTO users (username,password_hash,role,name,created_at) VALUES (?,?,?,?,?)",
        ("admin", pw, "admin", "GVMC Admin", now)
    )

    # Seed activity log
    logs = [
        ("alert","🔴","NH₃ spike detected at RK Beach Block-3: 107 ppm","VZ-001"),
        ("ok","✅","Vizag Railway Station PF-1 cleaned — Score: 96/100","VZ-005"),
        ("warning","🟡","VOC at Rushikonda Beach crossed 70 ppm","VZ-007"),
        ("alert","🚱","Water flow failure at VUDA Park South Gate","VZ-004"),
        ("info","📋","Daily report auto-generated and sent to supervisor",None),
    ]
    for l in logs:
        await db.execute(
            "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES (?,?,?,?,?)",
            (*l, now)
        )

    await db.commit()
    print("✅ Database seeded with Vizag facility data")
