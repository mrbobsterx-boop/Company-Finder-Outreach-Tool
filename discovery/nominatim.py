"""Geocoding via Nominatim: turns "country, region, city" into a bounding box.

Nominatim's usage policy caps free use at 1 request/second and requires a
descriptive User-Agent — both are enforced here so callers can't
accidentally violate them.
"""
from __future__ import annotations

import logging
import time
from typing import NamedTuple, Optional

import requests

logger = logging.getLogger(__name__)


class BoundingBox(NamedTuple):
    south: float
    north: float
    west: float
    east: float


class NominatimClient:
    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org",
        user_agent: str = "company-finder-outreach-tool/0.1",
        min_request_interval: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.min_request_interval = min_request_interval
        self._last_request_time: float = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

    def geocode_bbox(
        self, country: str, region: Optional[str] = None, city: Optional[str] = None
    ) -> Optional[BoundingBox]:
        """Return the bounding box of the most specific location given.

        Prefers city, falls back to region, falls back to country.
        """
        query_parts = [part for part in (city, region, country) if part]
        query = ", ".join(query_parts)
        if not query:
            return None

        self._throttle()
        response = requests.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        self._last_request_time = time.monotonic()
        response.raise_for_status()
        results = response.json()
        if not results:
            logger.warning("Nominatim found no results for %r", query)
            return None

        bbox = results[0].get("boundingbox")
        if not bbox:
            return None
        south, north, west, east = (float(x) for x in bbox)
        return BoundingBox(south=south, north=north, west=west, east=east)
