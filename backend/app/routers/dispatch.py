"""
/api/dispatch — dispatch one or all cleaning crews
"""

from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime

from app.database import get_db
from app.models.schemas import DispatchRequest, DispatchOut
from app.services.ws_manager import broadcast_dispatch

router = APIRouter()

TEAMS = ["Team A", "Team B", "Team C", "Team D", "Team E"]


@router.post("/", response_model=List[dict], status_code=201)
async def dispatch_crews(body: DispatchRequest):
    """Dispatch cleaning crew(s) to one or more facilities."""
    db = await get_db()
    now = datetime.utcnow().isoformat()
    results = []

    for idx, fid in enumerate(body.facility_ids):
        # Verify facility exists
        cur = await db.execute("SELECT name, zone FROM facilities WHERE id=? AND is_active=1", (fid,))
        f = await cur.fetchone()
        if not f:
            results.append({"facility_id": fid, "error": "Facility not found"})
            continue

        team = body.team or TEAMS[idx % len(TEAMS)]
        cursor = await db.execute(
            """INSERT INTO dispatches
               (facility_id, dispatched_by, team, status, notes, dispatched_at)
               VALUES (?,?,?,?,?,?)""",
            (fid, body.dispatched_by, team, "dispatched", body.notes, now)
        )
        dispatch_id = cursor.lastrowid

        # Log activity
        await db.execute(
            "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES ('info','🚨',?,?,?)",
            (f"Cleaning crew dispatched → {f['name']} ({team})", fid, now)
        )

        dispatch_data = {
            "id": dispatch_id, "facility_id": fid, "facility_name": f["name"],
            "zone": f["zone"], "team": team, "dispatched_by": body.dispatched_by,
            "status": "dispatched", "dispatched_at": now
        }
        results.append(dispatch_data)
        await broadcast_dispatch(dispatch_data)

    await db.commit()
    return results


@router.post("/all", status_code=201)
async def dispatch_all():
    """Dispatch crews to ALL critical and warning facilities."""
    db = await get_db()
    now = datetime.utcnow().isoformat()

    cursor = await db.execute(
        "SELECT id, name, zone FROM facilities WHERE status IN ('alert','warning') AND is_active=1"
    )
    facilities = await cursor.fetchall()

    if not facilities:
        return {"message": "No critical or warning facilities found", "dispatched": 0}

    results = []
    for idx, f in enumerate(facilities):
        team = TEAMS[idx % len(TEAMS)]
        cur2 = await db.execute(
            "INSERT INTO dispatches (facility_id,dispatched_by,team,status,dispatched_at) VALUES (?,?,?,?,?)",
            (f["id"], "dashboard-dispatch-all", team, "dispatched", now)
        )
        did = cur2.lastrowid
        await db.execute(
            "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES ('info','🚨',?,?,?)",
            (f"[DISPATCH ALL] → {f['name']} ({team})", f["id"], now)
        )
        d = {"id": did, "facility_id": f["id"], "facility_name": f["name"],
             "zone": f["zone"], "team": team, "status": "dispatched", "dispatched_at": now}
        results.append(d)
        await broadcast_dispatch(d)

    await db.commit()
    return {"message": f"Dispatched {len(results)} crews", "dispatched": len(results), "details": results}


@router.get("/")
async def list_dispatches(limit: int = 50):
    db = await get_db()
    cursor = await db.execute(
        """SELECT d.*, f.name AS facility_name, f.zone
           FROM dispatches d JOIN facilities f ON f.id=d.facility_id
           ORDER BY d.dispatched_at DESC LIMIT ?""",
        (limit,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("/{dispatch_id}/complete")
async def complete_dispatch(dispatch_id: int):
    db = await get_db()
    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE dispatches SET status='completed', completed_at=? WHERE id=?",
        (now, dispatch_id)
    )

    # Update facility last_cleaned + reset status if applicable
    cur = await db.execute("SELECT facility_id FROM dispatches WHERE id=?", (dispatch_id,))
    row = await cur.fetchone()
    if row:
        await db.execute(
            "UPDATE facilities SET last_cleaned=?, status='ok' WHERE id=?",
            (now, row["facility_id"])
        )
        await db.execute(
            "INSERT INTO activity_log (event_type,icon,message,facility_id,created_at) VALUES ('ok','✅',?,?,?)",
            (f"Cleaning completed — dispatch #{dispatch_id}", row["facility_id"], now)
        )
    await db.commit()

    # Sync to Firebase Realtime Database
    if row:
        try:
            from app.services.firebase_sync import sync_facility, sync_city_stats
            await sync_facility(row["facility_id"])
            await sync_city_stats()
        except Exception as e:
            print(f"⚠️ Firebase sync error in complete_dispatch: {e}")

    return {"message": "Dispatch marked complete", "id": dispatch_id}
