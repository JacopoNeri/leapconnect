"""Trip planner use cases: the planner form per vehicle, and the library.

The plan itself is computed on demand by the pure
``leapconnect.domain.trip_planning.plan_trips``; only the user's input (the
list of legs and the preferences) is stored, as JSON in the settings table,
so the same plan is available from every device. The library (saved
places and frequent routes) is shared by every vehicle.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leapconnect.application.ports.repositories import AppRepository

#: Upper bound for the stored JSON, to keep the settings table small.
MAX_DRAFT_BYTES = 64_000


def _draft_key(vin: str) -> str:
    return f"trip_plan_draft_{vin}"


async def load_trip_plan_draft(repo: AppRepository, vin: str) -> dict | None:
    """The saved planner form for *vin*, or None if absent/corrupt."""
    raw = await repo.get_setting(_draft_key(vin))
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


async def save_trip_plan_draft(
    repo: AppRepository, vin: str, draft: dict | None
) -> None:
    """Store (or clear, with None) the planner form for *vin*."""
    raw = "" if draft is None else json.dumps(draft, separators=(",", ":"))
    if len(raw.encode()) > MAX_DRAFT_BYTES:
        raise ValueError("Trip plan is too large to be saved")
    await repo.save_setting(_draft_key(vin), raw)


LIBRARY_KEY = "trip_planner_library"
MAX_LIBRARY_BYTES = 128_000


async def load_trip_planner_library(repo: AppRepository) -> dict:
    """Saved places and routes: ``{"places": [...], "routes": [...]}``."""
    raw = await repo.get_setting(LIBRARY_KEY)
    empty: dict = {"places": [], "routes": []}
    if not raw:
        return empty
    try:
        value = json.loads(raw)
    except ValueError:
        return empty
    return value if isinstance(value, dict) else empty


async def save_trip_planner_library(repo: AppRepository, library: dict) -> dict:
    """Replace the saved places and routes.

    Routes pointing to a place that no longer exists are dropped; the
    library as stored is returned.
    """
    place_ids = {p["id"] for p in library.get("places", [])}
    library = {
        "places": library.get("places", []),
        "routes": [
            r
            for r in library.get("routes", [])
            if r["from_place_id"] in place_ids and r["to_place_id"] in place_ids
        ],
    }
    raw = json.dumps(library, separators=(",", ":"))
    if len(raw.encode()) > MAX_LIBRARY_BYTES:
        raise ValueError("Too many saved places and routes")
    await repo.save_setting(LIBRARY_KEY, raw)
    return library
