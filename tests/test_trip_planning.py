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

    def test_home_charger_on_every_trip_is_used_only_when_needed(self):
        # Home has a charger, so every evening is a chance to charge: the plan
        # must not suggest one per evening, only when the next days need it.
        legs = [leg for day in range(23, 28) for leg in _commute(day, km=20)]
        plan = plan_trips(legs, _settings(charger_at_start=True))
        assert plan.feasible
        assert len(plan.charges) == 1
        assert plan.charges[0].location == "Home"
        assert all(leg.soc_end >= 20 for leg in plan.legs)

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

    def test_long_leg_with_higher_max_charges_to_max(self):
        # 200 km = 32 kWh = 80 % of the pack: needs 100 % to arrive at 20 %.
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 200, "Rome", duration_min=150)]
        plan = plan_trips(legs, _settings(start_soc=50, max_soc=100))
        charge = plan.charges[0]
        assert charge.to_soc == 100.0
        assert plan.legs[0].soc_end == pytest.approx(20.0)
        assert plan.feasible

    def test_max_soc_is_a_hard_limit(self):
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 200, "Rome", duration_min=150)]
        plan = plan_trips(legs, _settings(start_soc=50))
        assert plan.charges[0].to_soc == 80.0
        assert not plan.feasible
        assert any("between your limits" in w for w in plan.warnings)

    def test_custom_limits(self):
        legs = [PlannedLeg(datetime(2026, 11, 23, 8, 0), 100, "Trip", duration_min=60)]
        plan = plan_trips(legs, _settings(start_soc=40, min_soc=10, max_soc=90))
        assert plan.charges[0].to_soc == 90.0
        # 90 % - 40 % = 50 %; (50 % - 10 %) of 40 kWh = 16 kWh = 100 km.
        assert plan.legs[0].range_to_min_km == 100

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
        legs = [
            PlannedLeg(
                datetime(2026, 11, 23, 8, 0),
                10,
                "Home",
                duration_min=15,
                charger_at_destination=True,
            ),
            PlannedLeg(datetime(2026, 11, 23, 18, 0), 10, "Shop", duration_min=15),
        ]
        plan = plan_trips(legs, _settings(start_soc=31, topup_below_soc=30))
        assert [c.window_index for c in plan.charges] == [1]
        assert plan.charges[0].reason == "topup"
        assert plan.charges[0].to_soc == 80.0

    def test_no_charge_before_first_trip_if_battery_is_enough(self):
        # Low battery and a charger at the start, but the first trip can be
        # driven and there is a charger where it ends: charge there.
        legs = _commute(23, km=10, office_charger=True)
        plan = plan_trips(legs, _settings(start_soc=26, topup_below_soc=50))
        assert plan.charges
        assert all(c.window_index > 0 for c in plan.charges)
        assert plan.feasible

    def test_only_places_with_a_charger(self):
        legs = _commute(23, km=50)  # charger only at home, in the evening
        plan = plan_trips(legs, _settings(start_soc=70, charger_at_start=False))
        assert all(c.location == "Home" for c in plan.charges)

    def test_trips_already_departed_are_ignored(self):
        legs = [
            PlannedLeg(datetime(2026, 11, 22, 8, 0), 50, "Past", duration_min=60),
            PlannedLeg(datetime(2026, 11, 23, 8, 0), 25, "Office", duration_min=30),
        ]
        plan = plan_trips(legs, _settings())
        assert [leg.label for leg in plan.legs] == ["Office"]
        assert plan.legs[0].soc_start == 60.0
        assert all(c.start >= START for c in plan.charges)
        assert any("already departed" in w for w in plan.warnings)

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
            plan_trips([], _settings(min_soc=90, max_soc=80))


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
                "charger_at_start": True,
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


class TestTripPlannerLibraryApi:
    def test_library_roundtrip_drops_orphan_routes(self, auth_client):
        assert auth_client.get("/api/trip-planner/library").json() == {
            "places": [],
            "routes": [],
        }
        home = {"id": "h", "name": "Home", "latitude": 43.7, "longitude": 11.2}
        work = {"id": "w", "name": "Work"}  # typed by hand, no coordinates
        body = {
            "places": [{**home, "charger": True}, work],
            "routes": [
                {
                    "id": "r1",
                    "from_place_id": "h",
                    "to_place_id": "w",
                    "distance_km": 18,
                    "departure_time": "08:00",
                },
                {
                    "id": "r2",
                    "from_place_id": "h",
                    "to_place_id": "x",
                    "distance_km": 5,
                },
            ],
        }
        resp = auth_client.put("/api/trip-planner/library", json=body)
        assert resp.status_code == 200, resp.text
        data = auth_client.get("/api/trip-planner/library").json()
        assert [p["id"] for p in data["places"]] == ["h", "w"]
        assert data["places"][0]["charger"] is True
        assert data["places"][1]["latitude"] is None
        assert [r["id"] for r in data["routes"]] == ["r1"]

    def test_invalid_departure_time_rejected(self, auth_client):
        body = {
            "places": [],
            "routes": [
                {
                    "id": "r",
                    "from_place_id": "a",
                    "to_place_id": "b",
                    "distance_km": 1,
                    "departure_time": "25:00",
                }
            ],
        }
        assert (
            auth_client.put("/api/trip-planner/library", json=body).status_code == 422
        )

    def test_search_and_route(self, auth_client, monkeypatch):
        from leapconnect.api.routers import trip_planning as router_mod
        from leapconnect.infrastructure.geocoding import Place
        from leapconnect.infrastructure.routing import RouteInfo

        async def fake_search(query, *, limit=1, language="it"):
            return [Place(43.77, 11.25, "Duomo", "Piazza del Duomo, Firenze")]

        async def fake_route(lat1, lon1, lat2, lon2):
            return RouteInfo(distance_km=12.3, duration_min=21)

        monkeypatch.setattr(router_mod, "search_places", fake_search)
        monkeypatch.setattr(router_mod, "driving_route", fake_route)
        resp = auth_client.get("/api/trip-planner/search", params={"q": "duomo"})
        assert resp.json()[0]["name"] == "Duomo"
        resp = auth_client.get(
            "/api/trip-planner/route",
            params={"from_lat": 43.7, "from_lon": 11.2, "to_lat": 43.8, "to_lon": 11.3},
        )
        assert resp.json() == {"distance_km": 12.3, "duration_min": 21}
