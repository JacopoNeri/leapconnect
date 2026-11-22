"""Multi-day trip planner: when to charge so the battery stays in its sweet spot.

The user lists the trips (legs) they will drive over the next days. Between
two legs the car is parked somewhere — a *window* — and may or may not have a
charger there. The planner simulates the state of charge (SOC) leg by leg and
suggests charging sessions (day, start and end time, from/to SOC) so that:

- the SOC never drops below ``min_soc`` (20 % by default) at any arrival;
- charging never goes above ``max_soc`` (80 % by default): both limits are
  hard, and when the trips cannot be driven within them the plan says so;
- charges are suggested only at places with a charger, only from
  ``start_time`` on (trips that already departed are ignored), and as late as
  possible: a session is suggested only when the SOC would otherwise not be
  enough to reach the next opportunity (computed with a backward pass that
  knows how much every later window can add), or when the SOC is below
  ``topup_below_soc`` -- never before the first trip unless that trip needs it.

Everything here is pure: times are naive local datetimes, as entered by the
user, and all energy figures are in kWh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

ChargeTiming = Literal["asap", "late"]

#: Tolerance used when comparing SOC levels (percentage points).
_EPS = 0.05
#: Charging sessions are rounded up to this many minutes.
_ROUND_MINUTES = 5


@dataclass(frozen=True)
class PlannedLeg:
    """One trip the user plans to drive."""

    departure: datetime
    distance_km: float
    label: str = ""
    #: Driving time; estimated from ``PlannerSettings.avg_speed_kmh`` if None.
    duration_min: float | None = None
    #: Whether the car can be charged where this leg ends.
    charger_at_destination: bool = False
    #: Power of that charger (kW); falls back to the default charger power.
    charger_power_kw: float | None = None
    #: Per-leg consumption override (e.g. a motorway leg), kWh/100 km.
    consumption_kwh_100km: float | None = None


@dataclass(frozen=True)
class PlannerSettings:
    """Vehicle state and charging preferences the plan starts from."""

    start_time: datetime
    start_soc: float
    capacity_kwh: float
    consumption_kwh_100km: float
    start_label: str = "Start"
    charger_at_start: bool = False
    start_charger_power_kw: float | None = None
    default_charger_power_kw: float = 7.0
    #: Share of the charger energy that ends up in the battery.
    charging_efficiency: float = 0.9
    #: Highest acceptable SOC: charging never goes above it.
    max_soc: float = 80.0
    #: Lowest acceptable SOC: no arrival should drop below it.
    min_soc: float = 20.0
    #: Extra consumption added to every leg (percent), for weather/traffic.
    safety_margin_pct: float = 10.0
    avg_speed_kmh: float = 50.0
    #: ``asap`` = start charging on arrival, ``late`` = finish at departure.
    charge_timing: ChargeTiming = "asap"
    #: Top up to ``max_soc`` at any charger after the first trip when below
    #: this SOC (None = off).
    topup_below_soc: float | None = None


@dataclass(frozen=True)
class ChargeSuggestion:
    """A suggested charging session in a parking window."""

    window_index: int
    location: str
    start: datetime
    end: datetime
    from_soc: float
    to_soc: float
    #: Energy stored in the battery.
    energy_kwh: float
    #: Energy drawn from the charger (stored energy / efficiency).
    grid_energy_kwh: float
    power_kw: float
    #: ``required`` (needed for the next legs) or ``topup`` (low SOC).
    reason: Literal["required", "topup"]
    #: True when the window is too short to reach the wanted SOC.
    limited_by_time: bool = False


@dataclass(frozen=True)
class LegResult:
    """A leg with the simulated battery state at departure and arrival."""

    index: int
    label: str
    departure: datetime
    arrival: datetime
    distance_km: float
    energy_kwh: float
    soc_start: float
    soc_end: float
    #: Energy left in the battery on arrival.
    remaining_kwh: float
    #: Estimated range on arrival, down to 0 %.
    range_km: float
    #: Estimated range on arrival before reaching ``min_soc``.
    range_to_min_km: float
    below_min: bool
    charge_before: ChargeSuggestion | None = None


@dataclass(frozen=True)
class TripPlan:
    legs: list[LegResult]
    charges: list[ChargeSuggestion]
    warnings: list[str] = field(default_factory=list)
    final_soc: float = 0.0
    #: Charge suggested after the last leg (if any), also in ``charges``.
    final_charge: ChargeSuggestion | None = None
    #: True when no arrival drops below ``min_soc``.
    feasible: bool = True


@dataclass(frozen=True)
class _Window:
    """A parking period before leg ``index`` (or after the last one)."""

    index: int
    location: str
    start: datetime
    #: None for the open-ended window after the last leg.
    end: datetime | None
    charger: bool
    power_kw: float

    def hours(self) -> float:
        if self.end is None:
            return math.inf
        return max(0.0, (self.end - self.start).total_seconds() / 3600)


def _round_soc(value: float) -> float:
    return round(value, 1)


def _leg_duration(leg: PlannedLeg, settings: PlannerSettings) -> timedelta:
    if leg.duration_min is not None and leg.duration_min > 0:
        return timedelta(minutes=leg.duration_min)
    speed = settings.avg_speed_kmh if settings.avg_speed_kmh > 0 else 50.0
    return timedelta(minutes=round(leg.distance_km / speed * 60))


def _leg_label(leg: PlannedLeg, index: int) -> str:
    return leg.label.strip() or f"Trip {index + 1}"


def _soc_per_hour(window: _Window, settings: PlannerSettings) -> float:
    """SOC points the window's charger adds per hour."""
    stored_kw = window.power_kw * settings.charging_efficiency
    return stored_kw / settings.capacity_kwh * 100


def _max_gain(window: _Window, settings: PlannerSettings) -> float:
    if not window.charger or window.power_kw <= 0:
        return 0.0
    return window.hours() * _soc_per_hour(window, settings)


def _past_legs_warning(count: int) -> str:
    what = (
        "trip that already departed was"
        if count == 1
        else ("trips that already departed were")
    )
    return f"{count} {what} ignored: the plan starts from the battery level now."


def _build_windows(
    legs: list[PlannedLeg],
    arrivals: list[datetime],
    settings: PlannerSettings,
) -> list[_Window]:
    """Window ``k`` precedes leg ``k``; the extra last one follows the last leg."""
    default_power = settings.default_charger_power_kw
    windows = [
        _Window(
            index=0,
            location=settings.start_label.strip() or "Start",
            start=settings.start_time,
            end=max(settings.start_time, legs[0].departure),
            charger=settings.charger_at_start,
            power_kw=settings.start_charger_power_kw or default_power,
        )
    ]
    for k in range(1, len(legs) + 1):
        prev = legs[k - 1]
        start = arrivals[k - 1]
        end = max(start, legs[k].departure) if k < len(legs) else None
        windows.append(
            _Window(
                index=k,
                location=_leg_label(prev, k - 1),
                start=start,
                end=end,
                charger=prev.charger_at_destination,
                power_kw=prev.charger_power_kw or default_power,
            )
        )
    return windows


def _session_times(
    window: _Window, from_soc: float, to_soc: float, settings: PlannerSettings
) -> tuple[datetime, datetime]:
    hours = (to_soc - from_soc) / _soc_per_hour(window, settings)
    minutes = math.ceil(hours * 60 / _ROUND_MINUTES) * _ROUND_MINUTES
    duration = timedelta(minutes=minutes)
    if settings.charge_timing == "late" and window.end is not None:
        end = window.end
        start = max(window.start, end - duration)
        return start, end
    start = window.start
    end = start + duration
    if window.end is not None:
        end = min(end, window.end)
    return start, end


def _plan_charge(
    window: _Window,
    soc: float,
    required: float,
    settings: PlannerSettings,
) -> ChargeSuggestion | None:
    """Charging session for ``window`` given the SOC needed when leaving it."""
    if not window.charger or window.power_kw <= 0:
        return None
    needed = soc < required - _EPS
    # Top-ups only after the first trip: before it, charge only if needed.
    topup = (
        window.index > 0
        and settings.topup_below_soc is not None
        and soc < settings.topup_below_soc - _EPS
    )
    if not (needed or topup):
        return None

    wanted = settings.max_soc
    reachable = min(wanted, soc + _max_gain(window, settings))
    if reachable <= soc + _EPS:
        return None

    start, end = _session_times(window, soc, reachable, settings)
    energy = (reachable - soc) / 100 * settings.capacity_kwh
    return ChargeSuggestion(
        window_index=window.index,
        location=window.location,
        start=start,
        end=end,
        from_soc=_round_soc(soc),
        to_soc=_round_soc(reachable),
        energy_kwh=round(energy, 2),
        grid_energy_kwh=round(energy / settings.charging_efficiency, 2),
        power_kw=window.power_kw,
        reason="required" if needed else "topup",
        limited_by_time=reachable < wanted - _EPS,
    )


def _validate(settings: PlannerSettings) -> None:
    if settings.capacity_kwh <= 0:
        raise ValueError("Battery capacity must be positive")
    if settings.consumption_kwh_100km <= 0:
        raise ValueError("Consumption must be positive")
    if not 0 < settings.charging_efficiency <= 1:
        raise ValueError("Charging efficiency must be in (0, 1]")
    if not 0 <= settings.min_soc < settings.max_soc <= 100:
        raise ValueError("Expected 0 <= minimum SOC < maximum SOC <= 100")
    if not 0 <= settings.start_soc <= 100:
        raise ValueError("Start SOC must be between 0 and 100")


def plan_trips(legs: list[PlannedLeg], settings: PlannerSettings) -> TripPlan:
    """Simulate ``legs`` from ``settings`` and suggest charging sessions."""
    _validate(settings)
    warnings: list[str] = []
    upcoming = [leg for leg in legs if leg.departure >= settings.start_time]
    if len(upcoming) < len(legs):
        warnings.append(_past_legs_warning(len(legs) - len(upcoming)))
    legs = sorted(upcoming, key=lambda leg: leg.departure)
    if not legs:
        return TripPlan(
            legs=[],
            charges=[],
            warnings=warnings,
            final_soc=_round_soc(settings.start_soc),
        )

    capacity = settings.capacity_kwh
    margin = 1 + max(0.0, settings.safety_margin_pct) / 100

    durations = [_leg_duration(leg, settings) for leg in legs]
    arrivals = [leg.departure + d for leg, d in zip(legs, durations, strict=True)]
    energies = [
        leg.distance_km
        * (leg.consumption_kwh_100km or settings.consumption_kwh_100km)
        / 100
        * margin
        for leg in legs
    ]
    drops = [e / capacity * 100 for e in energies]

    usable = settings.max_soc - settings.min_soc
    for k in range(1, len(legs)):
        if legs[k].departure < arrivals[k - 1]:
            warnings.append(
                f"{_leg_label(legs[k], k)} departs before "
                f"{_leg_label(legs[k - 1], k - 1)} arrives."
            )
    for k, drop in enumerate(drops):
        if drop > usable + _EPS:
            warnings.append(
                f"{_leg_label(legs[k], k)} needs {drop:.0f}% of the battery, more "
                f"than the {usable:.0f}% between your limits "
                f"({settings.min_soc:.0f}-{settings.max_soc:.0f}%): plan a "
                "charging stop along the way or widen the limits."
            )

    windows = _build_windows(legs, arrivals, settings)

    # Backward pass: required[k] = SOC needed when leaving window k (i.e. at
    # the departure of leg k) so every later arrival stays >= min_soc, given
    # how much each later window can add (capped at ``max_soc``).
    n = len(legs)
    required = [0.0] * n
    arrival_need = settings.min_soc  # SOC needed when arriving after leg k
    for k in range(n - 1, -1, -1):
        required[k] = drops[k] + arrival_need
        gain = min(_max_gain(windows[k], settings), usable)
        # A window never charges above ``max_soc``: beyond that the plan is
        # infeasible anyway (reported below), so do not push the need back.
        arrival_need = max(settings.min_soc, min(required[k], settings.max_soc) - gain)

    soc = settings.start_soc
    charges: list[ChargeSuggestion] = []
    results: list[LegResult] = []
    for k, leg in enumerate(legs):
        charge = _plan_charge(windows[k], soc, required[k], settings)
        if charge is not None:
            charges.append(charge)
            soc = charge.to_soc
            if charge.limited_by_time and soc < required[k] - _EPS:
                warnings.append(
                    f"The stop at {charge.location} is too short to charge enough "
                    f"for {_leg_label(leg, k)}."
                )

        soc_end = soc - drops[k]
        remaining = max(0.0, soc_end) / 100 * capacity
        per_km = settings.consumption_kwh_100km / 100
        results.append(
            LegResult(
                index=k,
                label=_leg_label(leg, k),
                departure=leg.departure,
                arrival=arrivals[k],
                distance_km=round(leg.distance_km, 1),
                energy_kwh=round(energies[k], 2),
                soc_start=_round_soc(soc),
                soc_end=_round_soc(soc_end),
                remaining_kwh=round(remaining, 2),
                range_km=round(remaining / per_km, 0),
                range_to_min_km=round(
                    max(0.0, soc_end - settings.min_soc) / 100 * capacity / per_km, 0
                ),
                below_min=soc_end < settings.min_soc - _EPS,
                charge_before=charge,
            )
        )
        soc = soc_end

    final_charge = _plan_charge(windows[-1], max(0.0, soc), settings.min_soc, settings)
    if final_charge is not None:
        charges.append(final_charge)

    below = [r for r in results if r.below_min]
    for r in below:
        window = windows[r.index]
        hint = (
            f" — a charge at {window.location} before leaving would avoid it"
            if not window.charger
            else ""
        )
        if r.soc_end < 0:
            warnings.append(
                f"{r.label}: the battery would run out before arriving{hint}."
            )
        else:
            warnings.append(
                f"{r.label}: arrival at {r.soc_end:.0f}%, below "
                f"{settings.min_soc:.0f}%{hint}."
            )

    return TripPlan(
        legs=results,
        charges=charges,
        warnings=warnings,
        final_soc=_round_soc(soc),
        final_charge=final_charge,
        feasible=not below,
    )
