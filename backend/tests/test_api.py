"""
CleanCity IoT — Test Suite
Run with: pytest tests/ -v
"""

import pytest
import asyncio
import json
from httpx import AsyncClient, ASGITransport

# ── We patch the DB to use in-memory SQLite for tests ──
import os
os.environ["DATABASE_URL"] = ":memory:"

from app.main import app
from app.database import init_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    await init_db()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_token(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ═══════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "CleanCity IoT API"


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["city"] == "Visakhapatnam"


# ═══════════════════════════════════════
# AUTH
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_login_success(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    resp = await client.post("/api/auth/login", json={"username": "nobody", "password": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["sub"] == "admin"


@pytest.mark.asyncio
async def test_me_no_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


# ═══════════════════════════════════════
# FACILITIES
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_list_facilities(client):
    resp = await client.get("/api/facilities/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 15


@pytest.mark.asyncio
async def test_get_facility(client):
    resp = await client.get("/api/facilities/VZ-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "VZ-001"
    assert "name" in data
    assert "zone" in data


@pytest.mark.asyncio
async def test_get_facility_not_found(client):
    resp = await client.get("/api/facilities/VZ-999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_filter_facilities_by_zone(client):
    resp = await client.get("/api/facilities/?zone=Beach Road")
    assert resp.status_code == 200
    data = resp.json()
    for f in data:
        assert f["zone"] == "Beach Road"


@pytest.mark.asyncio
async def test_filter_facilities_by_status(client):
    resp = await client.get("/api/facilities/?status=alert")
    assert resp.status_code == 200
    data = resp.json()
    for f in data:
        assert f["status"] == "alert"


@pytest.mark.asyncio
async def test_search_facilities(client):
    resp = await client.get("/api/facilities/?search=railway")
    assert resp.status_code == 200
    data = resp.json()
    assert any("Railway" in f["name"] or "railway" in f["name"].lower() for f in data)


@pytest.mark.asyncio
async def test_create_facility(client):
    payload = {"id": "VZ-TEST", "name": "Test Facility", "zone": "Test Zone", "location": "Test Location"}
    resp = await client.post("/api/facilities/", json=payload)
    assert resp.status_code == 201
    assert resp.json()["id"] == "VZ-TEST"


@pytest.mark.asyncio
async def test_update_facility(client):
    resp = await client.patch("/api/facilities/VZ-005", json={"score": 95})
    assert resp.status_code == 200
    assert resp.json()["id"] == "VZ-005"


@pytest.mark.asyncio
async def test_delete_facility(client):
    resp = await client.delete("/api/facilities/VZ-TEST")
    assert resp.status_code == 200


# ═══════════════════════════════════════
# SENSOR READINGS
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_post_sensor_reading_clean(client):
    """Clean reading — below all thresholds."""
    payload = {"facility_id": "VZ-005", "nh3_ppm": 10, "voc_ppm": 15, "door_count": 30, "humidity": 55.0}
    resp = await client.post("/api/facilities/VZ-005/readings", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ok"
    assert data["alerts_raised"] == 0
    assert data["score"] >= 75


@pytest.mark.asyncio
async def test_post_sensor_reading_critical(client):
    """Critical NH₃ reading."""
    payload = {"facility_id": "VZ-001", "nh3_ppm": 110, "voc_ppm": 80, "door_count": 350, "humidity": 72.0}
    resp = await client.post("/api/facilities/VZ-001/readings", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "alert"
    assert data["alerts_raised"] >= 1
    assert data["score"] < 50


@pytest.mark.asyncio
async def test_post_sensor_reading_warning(client):
    """Warning level reading."""
    payload = {"facility_id": "VZ-007", "nh3_ppm": 35, "voc_ppm": 55, "door_count": 90, "humidity": 65.0}
    resp = await client.post("/api/facilities/VZ-007/readings", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("warning", "alert")


@pytest.mark.asyncio
async def test_post_sensor_reading_water_failure(client):
    """Water flow zero → critical."""
    payload = {
        "facility_id": "VZ-004", "nh3_ppm": 20, "voc_ppm": 30,
        "door_count": 40, "humidity": 60.0, "water_flow": 0.0
    }
    resp = await client.post("/api/facilities/VZ-004/readings", json=payload)
    assert resp.status_code == 201
    assert resp.json()["alerts_raised"] >= 1


@pytest.mark.asyncio
async def test_get_readings_history(client):
    resp = await client.get("/api/facilities/VZ-001/readings?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ═══════════════════════════════════════
# ALERTS
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_list_alerts(client):
    resp = await client.get("/api/alerts/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_active_alert_count(client):
    resp = await client.get("/api/alerts/active/count")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "critical" in data


@pytest.mark.asyncio
async def test_filter_alerts_by_severity(client):
    resp = await client.get("/api/alerts/?severity=critical")
    assert resp.status_code == 200
    for alert in resp.json():
        assert alert["severity"] == "critical"


@pytest.mark.asyncio
async def test_resolve_alert(client):
    # First get an unresolved alert
    resp = await client.get("/api/alerts/?resolved=false&limit=1")
    alerts = resp.json()
    if not alerts:
        pytest.skip("No unresolved alerts to test")
    alert_id = alerts[0]["id"]
    resp = await client.post(f"/api/alerts/{alert_id}/resolve")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_resolve_all_alerts(client):
    resp = await client.post("/api/alerts/resolve-all")
    assert resp.status_code == 200
    assert "count" in resp.json()


# ═══════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_dispatch_single(client):
    payload = {"facility_ids": ["VZ-001"], "dispatched_by": "test-operator", "team": "Team A"}
    resp = await client.post("/api/dispatch/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["facility_id"] == "VZ-001"
    assert data[0]["status"] == "dispatched"


@pytest.mark.asyncio
async def test_dispatch_multiple(client):
    payload = {"facility_ids": ["VZ-002", "VZ-003"], "dispatched_by": "test-operator"}
    resp = await client.post("/api/dispatch/", json=payload)
    assert resp.status_code == 201
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_dispatch_all(client):
    resp = await client.post("/api/dispatch/all")
    assert resp.status_code == 201
    data = resp.json()
    assert "dispatched" in data
    assert isinstance(data["dispatched"], int)


@pytest.mark.asyncio
async def test_list_dispatches(client):
    resp = await client.get("/api/dispatch/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_complete_dispatch(client):
    # Create a dispatch first
    payload = {"facility_ids": ["VZ-006"], "dispatched_by": "test"}
    resp = await client.post("/api/dispatch/", json=payload)
    dispatch_id = resp.json()[0]["id"]
    # Complete it
    resp = await client.post(f"/api/dispatch/{dispatch_id}/complete")
    assert resp.status_code == 200


# ═══════════════════════════════════════
# SIMULATE
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_simulate_nh3_spike(client):
    payload = {"facility_id": "VZ-010", "sim_type": "nh3"}
    resp = await client.post("/api/simulate/", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["sim_type"] == "nh3"
    assert data["triggered_value"] >= 85
    assert data["alert_id"] > 0


@pytest.mark.asyncio
async def test_simulate_voc_surge(client):
    payload = {"facility_id": "VZ-010", "sim_type": "voc"}
    resp = await client.post("/api/simulate/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["sim_type"] == "voc"


@pytest.mark.asyncio
async def test_simulate_crowd(client):
    payload = {"facility_id": "VZ-010", "sim_type": "door_count"}
    resp = await client.post("/api/simulate/", json=payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_simulate_water_failure(client):
    payload = {"facility_id": "VZ-010", "sim_type": "water_flow"}
    resp = await client.post("/api/simulate/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["triggered_value"] == 0.0


@pytest.mark.asyncio
async def test_simulate_custom_value(client):
    payload = {"facility_id": "VZ-010", "sim_type": "nh3", "custom_value": 99.5}
    resp = await client.post("/api/simulate/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["triggered_value"] == 99.5


@pytest.mark.asyncio
async def test_simulate_unknown_facility(client):
    payload = {"facility_id": "VZ-FAKE", "sim_type": "nh3"}
    resp = await client.post("/api/simulate/", json=payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_simulate_types_list(client):
    resp = await client.get("/api/simulate/types")
    assert resp.status_code == 200
    types = resp.json()
    assert len(types) == 4
    assert any(t["type"] == "nh3" for t in types)


# ═══════════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_city_summary(client):
    resp = await client.get("/api/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "city_score" in data
    assert "total_facilities" in data
    assert 0 <= data["city_score"] <= 100


@pytest.mark.asyncio
async def test_hourly_footfall(client):
    resp = await client.get("/api/analytics/hourly")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 24


@pytest.mark.asyncio
async def test_zone_breakdown(client):
    resp = await client.get("/api/analytics/zones")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_top_performers(client):
    resp = await client.get("/api/analytics/top-performers")
    assert resp.status_code == 200
    data = resp.json()
    # Should be sorted descending by score
    scores = [f["score"] for f in data]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_weekly_trends(client):
    resp = await client.get("/api/analytics/trends/weekly")
    assert resp.status_code == 200
    assert len(resp.json()) == 7


@pytest.mark.asyncio
async def test_activity_log(client):
    resp = await client.get("/api/analytics/activity-log")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_staff_status(client):
    resp = await client.get("/api/analytics/staff-status")
    assert resp.status_code == 200
    assert len(resp.json()) == 5


@pytest.mark.asyncio
async def test_weather(client):
    resp = await client.get("/api/analytics/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "Visakhapatnam"
    assert "temperature_c" in data


# ═══════════════════════════════════════
# THRESHOLD LOGIC UNIT TESTS
# ═══════════════════════════════════════

def test_threshold_clean():
    from app.services.thresholds import evaluate_reading
    status, triggers = evaluate_reading(10, 20, 30, 55)
    assert status == "ok"
    assert len(triggers) == 0


def test_threshold_nh3_warning():
    from app.services.thresholds import evaluate_reading
    status, triggers = evaluate_reading(35, 20, 30, 55)
    assert status == "warning"
    assert any(t.sensor == "nh3" for t in triggers)


def test_threshold_nh3_critical():
    from app.services.thresholds import evaluate_reading
    status, triggers = evaluate_reading(80, 20, 30, 55)
    assert status == "alert"
    assert any(t.severity == "critical" for t in triggers)


def test_threshold_voc_critical():
    from app.services.thresholds import evaluate_reading
    status, triggers = evaluate_reading(10, 90, 30, 55)
    assert status == "alert"


def test_threshold_door_count_critical():
    from app.services.thresholds import evaluate_reading
    status, triggers = evaluate_reading(10, 20, 200, 55)
    assert status == "alert"


def test_threshold_water_failure():
    from app.services.thresholds import evaluate_reading
    status, triggers = evaluate_reading(10, 20, 30, 55, water_flow=0.0)
    assert status == "alert"
    assert any(t.sensor == "water_flow" for t in triggers)


def test_score_clean_facility():
    from app.services.thresholds import calculate_score
    score = calculate_score(8, 15, 30, 25)
    assert score >= 85


def test_score_dirty_facility():
    from app.services.thresholds import calculate_score
    score = calculate_score(100, 90, 300, 360)
    assert score < 40


def test_city_score():
    from app.services.thresholds import city_score_from_facilities
    assert city_score_from_facilities([90, 80, 70, 60]) == 75
    assert city_score_from_facilities([]) == 0
