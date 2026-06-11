# SWACHHNETRA CleanCity IoT — Backend API
### GVMC Visakhapatnam · Smart Sanitation Monitoring System

---

## 🏗️ Architecture Overview

```
IoT Sensors (ESP32)
      │  POST /api/facilities/{id}/readings
      ▼
┌─────────────┐     WebSocket /ws/live     ┌──────────────────┐
│  FastAPI    │ ─────────────────────────► │  CleanCity       │
│  Backend    │                            │  Dashboard       │
│  (Python)   │ ◄──── REST API calls ───── │  (HTML Frontend) │
└──────┬──────┘                            └──────────────────┘
       │
       ▼
┌─────────────┐
│  SQLite     │  (swap to PostgreSQL in production)
│  Database   │
└─────────────┘
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
cd cleancity_backend
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env if needed — defaults work out of the box
```

### 3. Start the server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open the API docs
```
http://localhost:8000/api/docs      ← Swagger UI (interactive)
http://localhost:8000/api/redoc     ← ReDoc (reference)
```

### 5. (Optional) Start the IoT simulator
In a second terminal — mimics 15 ESP32 nodes pushing live readings:
```bash
python iot_simulator.py              # Normal mode
python iot_simulator.py --chaos      # Inject random spikes (great for demos!)
```

---

## 📁 Project Structure

```
cleancity_backend/
├── app/
│   ├── main.py               ← FastAPI app + CORS + router registration
│   ├── database.py           ← SQLite setup, schema, seed data
│   ├── models/
│   │   └── schemas.py        ← Pydantic request/response models
│   ├── routers/
│   │   ├── facilities.py     ← /api/facilities — CRUD + sensor readings
│   │   ├── alerts.py         ← /api/alerts — list, resolve alerts
│   │   ├── dispatch.py       ← /api/dispatch — send crews
│   │   ├── analytics.py      ← /api/analytics — KPIs, charts, trends
│   │   ├── simulate.py       ← /api/simulate — inject fake sensor events
│   │   ├── auth.py           ← /api/auth — login + JWT
│   │   └── websocket_router.py ← /ws/live — real-time push
│   └── services/
│       ├── thresholds.py     ← NH₃/VOC/door threshold logic + scoring
│       └── ws_manager.py     ← WebSocket connection manager + broadcast
├── tests/
│   └── test_api.py           ← Full test suite (55+ tests)
├── iot_simulator.py          ← Simulates ESP32 nodes
├── requirements.txt
├── pytest.ini
└── .env.example
```

---

## 🔌 API Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login → returns JWT token |
| GET  | `/api/auth/me` | Get current user info |

**Default credentials:** `admin` / `admin123`

### Facilities
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/facilities/` | List all (filter: `?zone=`, `?status=`, `?search=`) |
| GET    | `/api/facilities/{id}` | Get single facility |
| POST   | `/api/facilities/` | Create new facility |
| PATCH  | `/api/facilities/{id}` | Update facility |
| DELETE | `/api/facilities/{id}` | Soft-delete facility |
| POST   | `/api/facilities/{id}/readings` | **IoT device pushes sensor data here** |
| GET    | `/api/facilities/{id}/readings` | Reading history |

### Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/alerts/` | List alerts (filter: `?severity=`, `?resolved=`) |
| GET    | `/api/alerts/active/count` | Count by severity |
| POST   | `/api/alerts/{id}/resolve` | Resolve one alert |
| POST   | `/api/alerts/resolve-all` | Mark All Clear |

### Dispatch
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/api/dispatch/` | Dispatch crew(s) to facility list |
| POST   | `/api/dispatch/all` | **Dispatch All Cleaners** |
| GET    | `/api/dispatch/` | Dispatch history |
| POST   | `/api/dispatch/{id}/complete` | Mark cleaning done |

### Simulate
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/api/simulate/` | **Trigger alert scenario** |
| GET    | `/api/simulate/types` | List available scenario types |

**Simulate request body:**
```json
{
  "facility_id": "VZ-001",
  "sim_type": "nh3",         // nh3 | voc | door_count | water_flow
  "custom_value": 95.0       // optional — override generated value
}
```

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/analytics/summary` | City KPIs (score, counts, savings) |
| GET    | `/api/analytics/hourly` | Hourly footfall chart data |
| GET    | `/api/analytics/zones` | Per-zone breakdown |
| GET    | `/api/analytics/top-performers` | Highest scoring facilities |
| GET    | `/api/analytics/trends/weekly` | 7-day city score trend |
| GET    | `/api/analytics/activity-log` | Recent events |
| GET    | `/api/analytics/staff-status` | Cleaning team roster |
| GET    | `/api/analytics/weather` | Vizag weather + odor risk |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `ws://localhost:8000/ws/live` | Full live feed (sensor updates + alerts + dispatches) |
| `ws://localhost:8000/ws/alerts` | Alerts-only lightweight feed |

**WebSocket message types received by client:**
```json
{ "type": "snapshot",      "data": { "facilities": [...] } }
{ "type": "sensor_update", "facility_id": "VZ-001", "data": { "nh3_ppm": 95, ... } }
{ "type": "alert",         "facility_id": "VZ-001", "data": { "severity": "critical", ... } }
{ "type": "dispatch",      "facility_id": "VZ-001", "data": { "team": "Team A", ... } }
{ "type": "simulate",      "facility_id": "VZ-001", "data": { "sim_type": "nh3", ... } }
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v                    # All 55+ tests
pytest tests/ -v -k "threshold"     # Unit tests only
pytest tests/ -v -k "dispatch"      # Dispatch tests only
pytest tests/ --tb=short            # Shorter tracebacks
```

---

## 🧠 Threshold & Scoring Logic

### Alert Thresholds
| Sensor | Clean | Warning | Critical |
|--------|-------|---------|----------|
| NH₃ (ppm) | < 25 | 25–50 | > 50 |
| VOC (ppm) | < 40 | 40–65 | > 65 |
| Door Count | < 60 | 60–120 | > 120 |
| Humidity % | < 75 | 75–85 | > 85 |
| Water Flow | > 0 | — | = 0 |

### Facility Score Formula
```
Score = (NH₃+VOC score × 40%) + (Cleaning frequency × 30%) + (Footfall × 20%) + (Infrastructure × 10%)
```

---

## 🔄 Connecting the Frontend

Add this to your `cleancity_vizag_v2.html` to replace dummy data with live API data:

```javascript
// Replace dummy data with live API
const API = "http://localhost:8000";

// Fetch facilities on load
const res = await fetch(`${API}/api/facilities/`);
const facilities = await res.json();

// Connect WebSocket for live updates
const ws = new WebSocket(`ws://localhost:8000/ws/live`);
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "sensor_update") {
    // Update the card with msg.facility_id using msg.data values
    updateFacilityCard(msg.facility_id, msg.data);
  }
  if (msg.type === "alert") {
    addLog("alert", "🔴", msg.data.message);
    showToast(msg.data.message, "red");
  }
};

// Dispatch all via API
async function dispatchAllAPI() {
  const res = await fetch(`${API}/api/dispatch/all`, { method: "POST" });
  const data = await res.json();
  showToast(`✅ ${data.dispatched} crews dispatched`, "green");
}

// Simulate via API
async function simulateAlertAPI(facilityId, simType) {
  const res = await fetch(`${API}/api/simulate/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ facility_id: facilityId, sim_type: simType })
  });
  return res.json();
}
```

---

## 🛣️ Production Roadmap

| Feature | Status |
|---------|--------|
| SQLite (POC) | ✅ Done |
| PostgreSQL support | 🔧 Switch `DATABASE_URL` |
| JWT Auth | ✅ Done |
| WebSocket live feed | ✅ Done |
| IoT simulator | ✅ Done |
| WhatsApp alert integration | 📋 Planned |
| SMS via Twilio | 📋 Planned |
| OpenWeather API (real weather) | 📋 Planned |
| Docker deployment | 📋 See below |
| Rate limiting | 📋 Planned |
| Grafana dashboard | 📋 Planned |

### Docker (quick deploy)
```bash
# Build and run
docker build -t cleancity-api .
docker run -p 8000:8000 cleancity-api
```

---

*Built for GVMC Visakhapatnam Smart City Mission · CleanCity IoT v2.2*
