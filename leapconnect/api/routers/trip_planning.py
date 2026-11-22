"""Trip planner routes: compute a charging plan and keep the planner form."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from leapconnect.api.deps import RepoDep
from leapconnect.api.schemas import TripPlanDraft, TripPlanRequest, TripPlanResponse
from leapconnect.application.trip_planning import (
    load_trip_plan_draft,
    save_trip_plan_draft,
)
from leapconnect.domain.trip_planning import PlannedLeg, PlannerSettings, plan_trips

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
