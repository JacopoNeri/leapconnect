"""Trip planner use case: persist the planner form per vehicle.

The plan itself is computed on demand by the pure
``leapconnect.domain.trip_planning.plan_trips``; only the user's input (the
list of legs and the preferences) is stored, as JSON in the settings table,
so the same plan is available from every device.
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
