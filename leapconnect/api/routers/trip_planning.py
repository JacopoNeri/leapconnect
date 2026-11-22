"""Trip planner routes: charging plan, planner form, places and routes."""

from __future__ import annotations

import logging
from dataclasses import asdict

import httpx
from fastapi import APIRouter, HTTPException, Query

from leapconnect.api.deps import RepoDep
from leapconnect.api.schemas import (
    PlaceSearchResult,
    RouteEstimate,
    TripPlanDraft,
    TripPlannerLibrary,
    TripPlanRequest,
    TripPlanResponse,
)
from leapconnect.application.trip_planning import (
    load_trip_plan_draft,
    load_trip_planner_library,
    save_trip_plan_draft,
    save_trip_planner_library,
)
from leapconnect.domain.trip_planning import PlannedLeg, PlannerSettings, plan_trips
from leapconnect.infrastructure.geocoding import search_places
from leapconnect.infrastructure.routing import driving_route

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["trip-planning"])


@router.post("/api/vehicles/{vin}/trip-plan", response_model=TripPlanResponse)
async def compute_trip_plan(vin: str, body: TripPlanRequest) -> TripPlanResponse:
    """Simulate the planned legs and suggest when to charge.

    Pure computation: works offline too, the caller supplies the start SOC.
    """
    try:
        plan = plan_trips(
            [PlannedLeg(**leg.model_dump()) for leg in body.legs],
            PlannerSettings(**body.settings.model_dump()),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TripPlanResponse.model_validate(asdict(plan))


@router.get("/api/vehicles/{vin}/trip-plan/draft", response_model=TripPlanDraft)
async def get_trip_plan_draft(vin: str, repo: RepoDep) -> TripPlanDraft:
    """The planner form last saved for this vehicle (``draft`` is null if none)."""
    return TripPlanDraft(draft=await load_trip_plan_draft(repo, vin))


@router.put("/api/vehicles/{vin}/trip-plan/draft", response_model=TripPlanDraft)
async def put_trip_plan_draft(
    vin: str, body: TripPlanDraft, repo: RepoDep
) -> TripPlanDraft:
    """Save (or clear, with ``draft: null``) the planner form for this vehicle."""
    try:
        await save_trip_plan_draft(repo, vin, body.draft)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return TripPlanDraft(draft=body.draft)


@router.get("/api/trip-planner/library", response_model=TripPlannerLibrary)
async def get_trip_planner_library(repo: RepoDep) -> TripPlannerLibrary:
    """Saved places and frequent routes (shared by every vehicle)."""
    return TripPlannerLibrary.model_validate(await load_trip_planner_library(repo))


@router.put("/api/trip-planner/library", response_model=TripPlannerLibrary)
async def put_trip_planner_library(
    body: TripPlannerLibrary, repo: RepoDep
) -> TripPlannerLibrary:
    """Replace the saved places and frequent routes."""
    try:
        stored = await save_trip_planner_library(repo, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return TripPlannerLibrary.model_validate(stored)


@router.get("/api/trip-planner/search", response_model=list[PlaceSearchResult])
async def search_trip_places(
    q: str = Query(..., min_length=2, max_length=200),
) -> list[PlaceSearchResult]:
    """Look up an address or place name (OpenStreetMap Nominatim)."""
    try:
        places = await search_places(q, limit=6)
    except httpx.HTTPError as exc:
        _LOGGER.warning("Place search failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Address search unavailable"
        ) from exc
    return [
        PlaceSearchResult(
            name=p.name, address=p.address, latitude=p.latitude, longitude=p.longitude
        )
        for p in places
    ]


@router.get("/api/trip-planner/route", response_model=RouteEstimate)
async def estimate_trip_route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
) -> RouteEstimate:
    """Driving distance and time between two points (OSRM)."""
    try:
        info = await driving_route(from_lat, from_lon, to_lat, to_lon)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="No driving route found") from exc
    except httpx.HTTPError as exc:
        _LOGGER.warning("Route lookup failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Route service unavailable"
        ) from exc
    return RouteEstimate(distance_km=info.distance_km, duration_min=info.duration_min)
