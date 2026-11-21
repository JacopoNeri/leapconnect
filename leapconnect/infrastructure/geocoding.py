"""Address search via OpenStreetMap Nominatim (Telegram /navigate command).

The web UI already uses Nominatim for reverse geocoding in the destination
picker; this adapter does the forward search for the bot. Nominatim's usage
policy asks for an identifying User-Agent and at most one request per second,
which a chat command naturally respects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

_LOGGER = logging.getLogger(__name__)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "LeapConnect (self-hosted Leapmotor dashboard)"


@dataclass(frozen=True)
class Place:
    """A geocoded place."""

    latitude: float
    longitude: float
    name: str
    address: str


def _place_from_result(item: dict) -> Place:
    address = item.get("display_name", "")
    details = item.get("address") or {}
    road = details.get("road") or details.get("pedestrian")
    if road and details.get("house_number"):
        road = f"{road} {details['house_number']}"
    name = item.get("name") or road or address.split(",")[0]
    return Place(
        latitude=float(item["lat"]),
        longitude=float(item["lon"]),
        name=name.strip(),
        address=address,
    )


async def search_places(
    query: str, *, limit: int = 1, language: str = "it"
) -> list[Place]:
    """Search an address or place name; best matches first.

    Returns an empty list when nothing matches. Network and HTTP errors are
    raised to the caller.
    """
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": limit,
    }
    headers = {"User-Agent": USER_AGENT, "Accept-Language": language}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(NOMINATIM_SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        results = resp.json()
    return [_place_from_result(item) for item in results if "lat" in item]
