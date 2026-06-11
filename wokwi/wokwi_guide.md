# 🗺️ Guide: Testing with Wokwi ESP32 Simulator

This guide outlines how to use the Wokwi simulation to push live sensor readings to your FastAPI server, which in turn syncs in real time with the Firebase Realtime Database and updates the admin dashboard.

---

## 🛠️ Step 1: Start the Backend & Frontend

1. Run the backend server using the one-command launcher:
   ```bash
   python backend/start.py
   ```
   *Make sure you see the confirmation:*
   `🔥 Firebase Realtime Database initialized successfully.`

2. Open the frontend dashboard (`swachhnetra.html`) in your browser.
3. Sign in as **Admin** using the credentials: `admin` / `admin123`.
4. Ensure the green connection dot at the bottom of the screen says:
   `🔥 Firebase Realtime Database connected — live data active`

---

## 🚀 Step 2: Open and Run the Wokwi Simulator

### Option A: Using Wokwi Web Editor (Easiest)

1. Open your browser and navigate to [Wokwi.com](https://wokwi.com).
2. Start a new **ESP32** project.
3. Replace the content of `diagram.json` with the layout in [wokwi/diagram.json](file:///c:/Users/nikhi/OneDrive/Desktop/swachhnetra_complete/wokwi/diagram.json).
4. Replace the content of `sketch.ino` with the firmware in [wokwi/sketch.ino](file:///c:/Users/nikhi/OneDrive/Desktop/swachhnetra_complete/wokwi/sketch.ino).
5. Click **Library Manager** (tab on the left side/top in Wokwi) and search for/add:
   - `DHT sensor library for ESPx` (or `DHTesp` by Beegee_Tokae)
6. Click the **Play** button to start the simulation.

### Option B: Using VS Code Wokwi Extension

1. Install the **Wokwi Simulator** extension in VS Code.
2. Ensure you have your Wokwi API Token configured.
3. Right-click [wokwi/diagram.json](file:///c:/Users/nikhi/OneDrive/Desktop/swachhnetra_complete/wokwi/diagram.json) and select **Wokwi: Start Simulator**.

---

## 🎛️ Step 3: Interactive Testing

Once the simulation starts, the ESP32 connects to `Wokwi-GUEST` virtual WiFi and starts transmitting readings to the host's backend API (`http://10.0.2.2:8000/api/facilities/VZ-001/readings`) every 5 seconds.

You can interact with the virtual sensors in Wokwi and watch the dashboard update live:

| Action in Wokwi | Target Metric | Expected Dashboard Behavior (VZ-001) |
|---|---|---|
| **Rotate NH3 Potentiometer** | Ammonia (NH₃) ppm | Elevate > 50 to trigger a red **CRITICAL** alert, dropping the facility score. |
| **Rotate VOC Potentiometer** | VOC ppm | Elevate > 65 to trigger a **CRITICAL** alert, warning status > 40. |
| **Click Push Button** | Door usage count | Increments usage count by 1. Exceed 120 to trigger high footfall. |
| **Toggle Slide Switch** | Water flow status | Slide to HIGH to simulate water supply failure (0.0 L/min). |
| **Click DHT22 Sensor** | Temp & Humidity | Change values to see live humidity changes. |

---

## 🔍 How it Works Under the Hood

```
   [ Wokwi ESP32 Simulator ]
              │ (POST readings every 5s)
              ▼
   [ FastAPI Backend API ]  ──► (Saves to SQLite cleancity.db)
              │
              ▼ (Firebase Admin SDK sync)
  [ Firebase Realtime Database ]
              │
              ▼ (WebSockets / Firebase listeners)
 [ Admin/Citizen Dashboard (HTML) ]  ──► (Instant UI update!)
```
