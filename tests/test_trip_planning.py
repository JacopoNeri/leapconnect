"""Tests for the multi-day trip planner (charging suggestions)."""

from datetime import datetime

import pytest

from leapconnect.domain.trip_planning import PlannedLeg, PlannerSettings, plan_trips

START = datetime(2026, 11, 22, 20, 0)


def _settings(**overrides) -> PlannerSettings:
    base = {
        "start_time": START,
        "start_soc": 60.0,
        "capacity_kwh": 40.0,
        "consumption_kwh_100km": 16.0,
        "start_label": "Home",
        "charger_at_start": True,
        "default_charger_power_kw": 7.0,
        "charging_efficiency": 1.0,
        "safety_margin_pct": 0.0,
        "topup_below_soc": None,
    }
    base.update(overrides)
    return PlannerSettings(**base)


def _commute(day: int, km: float = 25.0, *, office_charger: bool = False):
    """Home -> office at 08:00, office -> home (charger) at 18:00."""
    return [
        PlannedLeg(
            datetime(2026, 11, day, 8, 0),
            km,
            "Office",
            duration_min=30,
            charger_at_destination=office_charger,
        ),
        PlannedLeg(
            datetime(2026, 11, day, 18, 0),
            km,
            "Home",
            duration_min=30,
            charger_at_destination=True,
        ),
    ]


class TestSimulation:
    def test_no_legs_returns_start_soc(self):
        plan = plan_trips([], _settings())
        assert plan.legs == [] and plan.charges == []
        assert plan.final_soc == 60.0

    def test_soc_and_range_after_each_leg(self):
        # 25 km * 16 kWh/100km = 4 kWh = 10 % of a 40 kWh pack.
        plan = plan_trips(_commute(23), _settings())
        assert [leg.soc_end for leg in plan.legs] == [50.0, 40.0]
        first = plan.legs[0]
        assert first.energy_kwh == 4.0
        assert first.remaining_kwh == 20.0
        assert first.range_km == 125  # 20 kWh / 0.16 kWh/km
        assert first.range_to_min_km == 75  # (50 % - 20 %) of 40 kWh
        assert plan.charges == []
        assert plan.feasible

    def test_safety_margin_increases_consumption(self):
        plan = plan_trips(_commute(23), _settings(safety_margin_pct=10))
        assert plan.legs[0].energy_kwh == pytest.approx(4.4)

    def test_legs_are_sorted_by_departure(self):
        plan = plan_trips(list(reversed(_commute(23))), _settings())
        assert [leg.label for leg in plan.legs] == ["Office", "Home"]

    def test_duration_estimated_from_average_speed(self):
        leg = PlannedLeg(datetime(2026, 11, 23, 8, 0), 100, "Far")
        plan = plan_trips([leg], _settings(avg_speed_kmh=50))
        assert plan.legs[0].arrival == datetime(2026, 11, 23, 10, 0)


class TestChargingSuggestions:
    def test_charges_only_when_needed_and_up_to_80(self):
        # Three days of 50 km commutes (20 % per leg, 40 % a day) from 60 %:
        # day 1 ends at 20 % exactly, so charge to 80 % that evening; day 2
        # ends at 40 %, not enough for day 3, so charge again.
        legs = _commute(23) + _commute(24) + _commute(25)
        legs = [
            PlannedLeg(
                leg.departure,
                50,
                leg.label,
                duration_min=30,
                charger_at_destination=leg.charger_at_destination,
            )
            for leg in legs
        ]
        plan = plan_trips(legs, _settings())
        assert plan.feasible
        assert all(leg.soc_end >= 20 for leg in plan.legs)
        assert [c.window_index for c in plan.charges] == [2, 4]
        for charge in plan.charges:
            assert charge.to_soc == 80.0
            assert charge.location == "Home"
            assert charge.reason == "required"
            assert not charge.above_target

    def test_charge_times_asap_from_arrival(self):
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 100, "Trip", duration_min=60)]
        plan = plan_trips(legs, _settings(start_soc=30))
        charge = plan.charges[0]
        # 30 % -> 80 % of 40 kWh = 20 kWh at 7 kW = 2 h 51.4 min -> 2 h 55.
        assert charge.start == START
        assert charge.end == datetime(2026, 11, 22, 22, 55)
        assert charge.energy_kwh == 20.0

    def test_charge_times_late_finish_at_departure(self):
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 100, "Trip", duration_min=60)]
        plan = plan_trips(legs, _settings(start_soc=30, charge_timing="late"))
        charge = plan.charges[0]
        assert charge.end == datetime(2026, 11, 23, 8, 0)
        assert charge.start == datetime(2026, 11, 23, 5, 5)

    def test_long_leg_requires_charging_above_target(self):
        # 200 km = 32 kWh = 80 % of the pack: needs 100 % to arrive at 20 %.
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 200, "Rome", duration_min=150)]
        plan = plan_trips(legs, _settings(start_soc=50))
        charge = plan.charges[0]
        assert charge.to_soc == 100.0
        assert charge.above_target
        assert plan.legs[0].soc_end == pytest.approx(20.0)
        assert any("above 80%" in w for w in plan.warnings)

    def test_short_window_is_limited_by_time(self):
        legs = [
            PlannedLeg(datetime(2026, 11, 22, 20, 30), 150, "Trip", duration_min=90)
        ]
        plan = plan_trips(legs, _settings(start_soc=40))
        charge = plan.charges[0]
        assert charge.limited_by_time
        assert charge.end == datetime(2026, 11, 22, 20, 30)
        assert not plan.feasible
        assert any("too short" in w for w in plan.warnings)

    def test_charges_later_when_a_later_charger_is_enough(self):
        # Charger at the office: no need to plug in at home tonight.
        legs = _commute(23, km=40, office_charger=True)
        plan = plan_trips(legs, _settings(start_soc=45))
        assert plan.feasible
        assert all(c.window_index != 0 for c in plan.charges)

    def test_no_charger_anywhere_reports_infeasible(self):
        legs = [
            PlannedLeg(datetime(2026, 11, 23, 8, 0), 120, "Milan", duration_min=90),
            PlannedLeg(datetime(2026, 11, 23, 17, 0), 120, "Home", duration_min=90),
        ]
        plan = plan_trips(legs, _settings(start_soc=90, charger_at_start=False))
        assert plan.charges == []
        assert not plan.feasible
        assert plan.legs[1].below_min
        assert any("charge at Milan" in w for w in plan.warnings)

    def test_topup_threshold_charges_even_if_not_required(self):
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 10, "Shop", duration_min=15)]
        plan = plan_trips(legs, _settings(start_soc=28, topup_below_soc=30))
        assert plan.charges[0].reason == "topup"
        assert plan.charges[0].to_soc == 80.0

    def test_final_charge_after_last_leg(self):
        legs = [
            PlannedLeg(
                datetime(2026, 11, 23, 8, 0),
                25,
                "Home",
                duration_min=30,
                charger_at_destination=True,
            )
        ]
        plan = plan_trips(legs, _settings(start_soc=35, topup_below_soc=30))
        assert plan.final_charge is not None
        assert plan.final_charge.from_soc == 25.0
        assert plan.final_charge.to_soc == 80.0

    def test_overlapping_legs_warn(self):
        legs = [
            PlannedLeg(datetime(2026, 11, 23, 8, 0), 50, "A", duration_min=60),
            PlannedLeg(datetime(2026, 11, 23, 8, 30), 50, "B", duration_min=60),
        ]
        plan = plan_trips(legs, _settings())
        assert any("departs before A arrives" in w for w in plan.warnings)

    def test_invalid_settings_raise(self):
        with pytest.raises(ValueError):
            plan_trips([], _settings(capacity_kwh=0))
        with pytest.raises(ValueError):
            plan_trips([], _settings(min_soc=90, target_soc=80))


class TestTripPlanApi:
    def test_requires_session(self, client):
        resp = client.post("/api/vehicles/VIN1/trip-plan", json={})
        assert resp.status_code == 401

    def test_compute_plan(self, auth_client):
        body = {
            "settings": {
                "start_time": "2026-11-22T20:00",
                "start_soc": 30,
                "capacity_kwh": 40,
                "consumption_kwh_100km": 16,
            },
            "legs": [
                {"label": "Work", "departure": "2026-11-23T08:00", "distance_km": 100},
            ],
        }
        resp = auth_client.post("/api/vehicles/VIN1/trip-plan", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["charges"][0]["to_soc"] == 80.0
        assert data["legs"][0]["label"] == "Work"
        assert data["legs"][0]["soc_end"] < 80
        assert data["feasible"] is True

    def test_invalid_soc_rejected(self, auth_client):
        body = {
            "settings": {
                "start_time": "2026-11-22T20:00",
                "start_soc": 130,
                "capacity_kwh": 40,
                "consumption_kwh_100km": 16,
            },
            "legs": [],
        }
        resp = auth_client.post("/api/vehicles/VIN1/trip-plan", json=body)
        assert resp.status_code == 422

    def test_draft_roundtrip(self, auth_client):
        assert auth_client.get("/api/vehicles/VIN1/trip-plan/draft").json() == {
            "draft": None
        }
        draft = {"legs": [{"label": "Work", "distance_km": 30}], "start_soc": 55}
        resp = auth_client.put(
            "/api/vehicles/VIN1/trip-plan/draft", json={"draft": draft}
        )
        assert resp.status_code == 200
        assert (
            auth_client.get("/api/vehicles/VIN1/trip-plan/draft").json()["draft"]
            == draft
        )
        # Drafts are per vehicle.
        assert (
            auth_client.get("/api/vehicles/VIN2/trip-plan/draft").json()["draft"]
            is None
        )
        auth_client.put("/api/vehicles/VIN1/trip-plan/draft", json={"draft": None})
        assert (
            auth_client.get("/api/vehicles/VIN1/trip-plan/draft").json()["draft"]
            is None
        )
