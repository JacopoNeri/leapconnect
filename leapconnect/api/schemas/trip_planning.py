"""Trip planner DTOs: the planned legs + settings in, the charging plan out.

Datetimes are naive local times (``YYYY-MM-DDTHH:MM``), exactly as the user
enters them in the browser.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PlannedLegSchema(BaseModel):
    label: str = Field("", max_length=80)
    departure: datetime
    distance_km: float = Field(..., gt=0, le=2000)
    duration_min: float | None = Field(None, gt=0, le=2880)
    charger_at_destination: bool = False
    charger_power_kw: float | None = Field(None, gt=0, le=400)
    consumption_kwh_100km: float | None = Field(None, gt=0, le=60)


class PlannerSettingsSchema(BaseModel):
    start_time: datetime
    start_soc: float = Field(..., ge=0, le=100)
    capacity_kwh: float = Field(..., ge=5, le=250)
    consumption_kwh_100km: float = Field(..., gt=0, le=60)
    start_label: str = Field("Home", max_length=80)
    charger_at_start: bool = False
    start_charger_power_kw: float | None = Field(None, gt=0, le=400)
    default_charger_power_kw: float = Field(7.0, gt=0, le=400)
    charging_efficiency: float = Field(0.9, gt=0, le=1)
    max_soc: float = Field(80, gt=0, le=100)
    min_soc: float = Field(20, ge=0, lt=100)
    safety_margin_pct: float = Field(10, ge=0, le=100)
    avg_speed_kmh: float = Field(50, gt=0, le=200)
    charge_timing: Literal["asap", "late"] = "asap"
    topup_below_soc: float | None = Field(None, ge=0, le=100)


class TripPlanRequest(BaseModel):
    settings: PlannerSettingsSchema
    legs: list[PlannedLegSchema] = Field(default_factory=list, max_length=100)


class ChargeSuggestionSchema(BaseModel):
    window_index: int
    location: str
    start: datetime
    end: datetime
    from_soc: float
    to_soc: float
    energy_kwh: float
    grid_energy_kwh: float
    power_kw: float
    reason: Literal["required", "topup"]
    limited_by_time: bool


class LegResultSchema(BaseModel):
    index: int
    label: str
    departure: datetime
    arrival: datetime
    distance_km: float
    energy_kwh: float
    soc_start: float
    soc_end: float
    remaining_kwh: float
    range_km: float
    range_to_min_km: float
    below_min: bool
    charge_before: ChargeSuggestionSchema | None = None


class TripPlanResponse(BaseModel):
    legs: list[LegResultSchema]
    charges: list[ChargeSuggestionSchema]
    warnings: list[str]
    final_soc: float
    final_charge: ChargeSuggestionSchema | None = None
    feasible: bool


class TripPlanDraft(BaseModel):
    """The planner form as last saved by the user (any shape the UI needs)."""

    draft: dict | None = None


class PlaceSchema(BaseModel):
    """A place saved in the planner library (home, work, gym...)."""

    id: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=80)
    address: str = Field("", max_length=300)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    charger: bool = False
    charger_power_kw: float | None = Field(None, gt=0, le=400)


class SavedRouteSchema(BaseModel):
    """A frequent trip between two saved places."""

    id: str = Field(..., min_length=1, max_length=40)
    from_place_id: str = Field(..., max_length=40)
    to_place_id: str = Field(..., max_length=40)
    distance_km: float = Field(..., gt=0, le=2000)
    duration_min: float | None = Field(None, gt=0, le=2880)
    #: Usual departure time, ``HH:MM``.
    departure_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class TripPlannerLibrary(BaseModel):
    places: list[PlaceSchema] = Field(default_factory=list, max_length=200)
    routes: list[SavedRouteSchema] = Field(default_factory=list, max_length=200)


class PlaceSearchResult(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float


class RouteEstimate(BaseModel):
    distance_km: float
    duration_min: float
