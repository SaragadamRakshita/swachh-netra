"""
CleanCity IoT — Backend API
GVMC Visakhapatnam Smart Sanitation System
"""

import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import uvicorn

from app.routers import facilities, alerts, dispatch, analytics, simulate, auth, websocket_router
from app.database import init_db

app = FastAPI(
    title="CleanCity IoT API",
    description="Smart Public Sanitation Monitoring — GVMC Visakhapatnam",
    version="2.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── CORS (allow dashboard frontend) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── STARTUP ──
@app.on_event("startup")
async def startup():
    await init_db()
    print("✅ CleanCity backend started — DB seeded")
    try:
        from app.services.firebase_sync import sync_all_to_firebase
        import asyncio
        asyncio.create_task(sync_all_to_firebase())
    except Exception as e:
        print(f"⚠️ Failed to trigger Firebase startup sync: {e}")


# ── ROUTERS ──
app.include_router(auth.router,        prefix="/api/auth",       tags=["Auth"])
app.include_router(facilities.router,  prefix="/api/facilities", tags=["Facilities"])
app.include_router(alerts.router,      prefix="/api/alerts",     tags=["Alerts"])
app.include_router(dispatch.router,    prefix="/api/dispatch",   tags=["Dispatch"])
app.include_router(analytics.router,   prefix="/api/analytics",  tags=["Analytics"])
app.include_router(simulate.router,    prefix="/api/simulate",   tags=["Simulate"])
app.include_router(websocket_router.router, prefix="/ws",        tags=["WebSocket"])

@app.get("/", include_in_schema=False)
async def root():
    return {"service": "CleanCity IoT API", "version": "2.2.0", "status": "running",
            "docs": "/api/docs"}

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html_path = os.path.join(base_dir, "swachhnetra.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse(f"swachhnetra.html not found at {html_path}", status_code=404)


@app.get("/api/health", tags=["Health"])
async def health():
    return {"status": "ok", "nodes_online": 63, "city": "Visakhapatnam"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
