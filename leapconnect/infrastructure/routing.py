"""Driving distance and time between two points via the public OSRM server.

Used by the trip planner so the user can pick places instead of typing
distances. The OSRM demo server is meant for light use: results are cached
in memory (the same home/work pairs come back all the time) and requests
carry an identifying User-Agent.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from leapconnect.infrastructure.geocoding import USER_AGENT

OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"
_CACHE_SIZE = 500


@dataclass(frozen=True)
class RouteInfo:
    distance_km: float
    duration_min: float


_cache: dict[tuple[float, float, float, float], RouteInfo] = {}


def _key(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple:
    # ~10 m precision: enough to reuse results for the same saved place.
    return (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))


async def driving_route(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> RouteInfo:
    """Fastest driving route from (lat1, lon1) to (lat2, lon2).

    Raises ``LookupError`` when OSRM finds no route; network and HTTP errors
    are raised to the caller.
    """
    key = _key(lat1, lon1, lat2, lon2)
    if key in _cache:
        return _cache[key]
    coords = f"{lon1:.6f},{lat1:.6f};{lon2:.6f},{lat2:.6f}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            OSRM_ROUTE_URL.format(coords=coords),
            params={"overview": "false"},
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
    routes = data.get("routes") or []
    if data.get("code") != "Ok" or not routes:
        raise LookupError(data.get("message") or "No route found")
    info = RouteInfo(
        distance_km=round(routes[0]["distance"] / 1000, 1),
        duration_min=round(routes[0]["duration"] / 60),
    )
    if len(_cache) >= _CACHE_SIZE:
        _cache.pop(next(iter(_cache)))
    _cache[key] = info
    return info
