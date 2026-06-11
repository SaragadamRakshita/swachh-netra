# 🧼 SwachhNetra | Smart Sanitation Monitoring System
### GVMC Visakhapatnam · IoT Smart City Initiative

SwachhNetra is an advanced, real-time public sanitation monitoring dashboard designed for the Greater Visakhapatnam Municipal Corporation (GVMC). By integrating IoT sensors (NH₃, VOCs, Humidity, usage counters, and water flow) installed in public toilets, the system aggregates live ratings, issues automated cleaning dispatches, and generates analytics reports for municipal administrators.

---

## 🏗️ Architecture & Tech Stack

```
        +-------------------------------------------------------------+
        |                 IoT Sensors (ESP32 Simulation)              |
        +-------------------------------------------------------------+
                                       │
                        POST /api/facilities/{id}/readings
                                       ▼
  +───────────────────────────────────────────────────────────────────────────+
  |                             FASTAPI BACKEND                               |
  |                                                                           |
  |  - DB: SQLite (stores user credentials, historical readings, dispatches)   |
  |  - Real-Time Database: Syncs live status/ratings directly to Firebase     |
  |  - Authentication: Verifies Firebase ID Tokens & issues JWTs              |
  |  - WebSocket server: Broadcasts live events to active dashboards          |
  +───────────────────────────────────────────────────────────────────────────+
                 ▲                                            │
        REST API / JWT Auth                            WebSocket / Live RTDB
                 │                                            ▼
  +───────────────────────────────────────────────────────────────────────────+
  |                           HTML5 DASHBOARD PORTAL                          |
  |                                                                           |
  |  - Premium Glassmorphism UI (Dark/Light mode support)                     |
  |  - Secured by Firebase Auth (Google Sign-In & Email Authentication)       |
  |  - Live Interactive Map, KPI Analytics, and simulation panel              |
  +───────────────────────────────────────────────────────────────────────────+
```

### Stack Components:
- **Frontend**: Single-Page HTML5, Vanilla JavaScript, CSS3 Design System (DM Sans, JetBrains Mono, custom palettes).
- **Backend**: Python FastAPI, SQLite, Pydantic, uvicorn.
- **Real-time Synchronization**: Firebase Realtime Database (RTDB) & WebSockets.
- **Authentication**: Firebase Client SDK & Firebase Admin Python SDK (Google Sign-In).

---

## 📁 Repository Structure

```
swachhnetra_complete/
├── backend/                   # FastAPI Backend Server
│   ├── app/
│   │   ├── main.py            # API routes loading & application startup
│   │   ├── database.py        # SQLite connection, tables, and seeding
│   │   ├── models/            # Pydantic schemas
│   │   ├── routers/           # Sub-routers (/facilities, /alerts, /auth, etc.)
│   │   └── services/          # Real-time WebSocket and Firebase synchronization
│   ├── start.py               # One-Command Server and Simulation Launcher
│   ├── requirements.txt       # Python package list
│   └── serviceAccountKey.json.placeholder  # Instruction guide for service key
├── wokwi/                     # Wokwi ESP32 physical IoT simulation guides
│   ├── sketch.ino             # ESP32 C++ code pushing sensor telemetry
│   └── wokwi_guide.md         # Step-by-step setup for physical hardware simulation
├── swachhnetra.html           # Main Front-End Admin & Citizen Portal
└── README.md                  # Main project guide (This file)
```

---

## 🚀 Setup & Installation

### 1. Configure Firebase Credentials
1. Go to the [Firebase Console](https://console.firebase.google.com/).
2. Create a project named `swachh-netra`.
3. In **Project Settings** ➔ **Service Accounts**, click **Generate New Private Key**.
4. Rename the downloaded JSON file to `serviceAccountKey.json` and save it directly in the `/backend` folder.
5. In **Build** ➔ **Authentication**, enable **Google Sign-In** and **Email/Password**.

### 2. Configure Environment Variables
Copy the configuration template in `/backend` to configure local settings:
```bash
cd backend
cp .env.example .env
```
Inside the newly created `.env` file, ensure the following fields match your project:
```env
FIREBASE_PROJECT_ID=swachh-netra-d5f5f
GOOGLE_APPLICATION_CREDENTIALS=serviceAccountKey.json
```

### 3. Run the Project
Launch the backend server, database, and sensor simulator in a single command:
```bash
python start.py --sim
```
*This command will check dependencies, initialize/seed the local SQLite database, run the background sensor simulator, and automatically launch your browser to the local HTTP dashboard.*

---

## ⚙️ Running Locally
- **Local Dashboard UI**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Interactive API Documentation (Swagger)**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- **Health Check Endpoint**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### Demo Credentials:
- **Admin**: `admin` / `admin123`
- **Worker**: `worker` / `work123`
- **Citizen**: `citizen` / `citi123`

---

## 🔒 Security & Code Standards (GitHub Ready)
This project is configured to adhere to professional code scanning policies:
- Sensitive variables (private keys, DB configurations, environment files) are excluded from indexation via `.gitignore`.
- Authentication flow uses standard Google ID token exchanges over secure HTTP endpoints (`POST /api/auth/firebase`) preventing client-side credentials leakage.
