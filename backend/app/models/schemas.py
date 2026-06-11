"""
Pydantic models for request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class StatusEnum(str, Enum):
    ok = "ok"
    warning = "warning"
    alert = "alert"
    maintenance = "maintenance"


class SeverityEnum(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertTypeEnum(str, Enum):
    nh3 = "nh3"
    voc = "voc"
    door_count = "door_count"
    water_flow = "water_flow"
    temperature = "temperature"
    humidity = "humidity"


# ── Facility ──
class FacilityBase(BaseModel):
    name: str
    zone: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class FacilityCreate(FacilityBase):
    id: str

class FacilityUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    location: Optional[str] = None
    status: Optional[StatusEnum] = None
    score: Optional[int] = Field(None, ge=0, le=100)

class FacilityOut(FacilityBase):
    id: str
    status: StatusEnum
    score: int
    last_cleaned: Optional[str]
    is_active: bool
    latest_reading: Optional["SensorReadingOut"] = None

    class Config:
        from_attributes = True


# ── Sensor Reading ──
class SensorReadingIn(BaseModel):
    facility_id: str
    nh3_ppm: float = Field(..., ge=0, le=500, description="Ammonia ppm")
    voc_ppm: float = Field(..., ge=0, le=500, description="VOC ppm")
    door_count: int = Field(..., ge=0)
    humidity: float = Field(..., ge=0, le=100)
    temperature: Optional[float] = None
    water_flow: Optional[float] = None

class SensorReadingOut(BaseModel):
    id: int
    facility_id: str
    nh3_ppm: float
    voc_ppm: float
    door_count: int
    humidity: float
    temperature: Optional[float]
    water_flow: Optional[float]
    recorded_at: str

    class Config:
        from_attributes = True


# ── Alert ──
class AlertOut(BaseModel):
    id: int
    facility_id: str
    alert_type: str
    severity: str
    message: str
    value: Optional[float]
    threshold: Optional[float]
    resolved: bool
    resolved_at: Optional[str]
    created_at: str

class AlertResolve(BaseModel):
    notes: Optional[str] = None


# ── Dispatch ──
class DispatchRequest(BaseModel):
    facility_ids: List[str] = Field(..., min_items=1)
    dispatched_by: str = "dashboard"
    team: Optional[str] = None
    notes: Optional[str] = None

class DispatchOut(BaseModel):
    id: int
    facility_id: str
    dispatched_by: str
    team: Optional[str]
    status: str
    notes: Optional[str]
    dispatched_at: str
    completed_at: Optional[str]


# ── Simulate ──
class SimulateRequest(BaseModel):
    facility_id: str
    sim_type: AlertTypeEnum
    custom_value: Optional[float] = None

class SimulateResponse(BaseModel):
    facility_id: str
    sim_type: str
    triggered_value: float
    threshold: float
    alert_id: int
    message: str


# ── Analytics ──
class CitySummary(BaseModel):
    city_score: int
    total_facilities: int
    clean_count: int
    warning_count: int
    critical_count: int
    total_uses_today: int
    avg_response_minutes: int
    monthly_savings_inr: int
    clean_rate_pct: float
    active_alerts: int


# ── Auth ──
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str


# ── Activity Log ──
class LogEntry(BaseModel):
    id: int
    event_type: str
    icon: Optional[str]
    message: str
    facility_id: Optional[str]
    created_at: str


# ── WebSocket message ──
class WSMessage(BaseModel):
    type: str          # "sensor_update" | "alert" | "dispatch" | "simulate"
    facility_id: Optional[str]
    data: dict


FacilityOut.model_rebuild()
