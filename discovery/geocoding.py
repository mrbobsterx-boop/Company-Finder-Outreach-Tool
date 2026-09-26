"""Geocoding: turns "country, region, city" into a bounding box for Overpass.

Photon (run by Komoot, https://photon.komoot.io) is the default: it's free,
keyless, and — unlike the public Nominatim demo server — doesn't reject
programmatic clients (Nominatim's usage policy has tightened enforcement
against exactly this kind of small-scale scripted use, returning a bare
403 even for a single well-behaved request). NominatimClient is kept below
for anyone self-hosting their own Nominatim instance, where that policy
doesn't apply.
"""
from __future__ import annotations

import logging
import math
import time
from typing import NamedTuple, Optional

import requests

logger = logging.getLogger(__name__)


class BoundingBox(NamedTuple):
    south: float
    north: float
    west: float
    east: float


def _bbox_from_point(lat: float, lon: float, radius_km: float) -> BoundingBox:
    """Approximate a bounding box as a square of the given radius around a point.

    Used when the geocoder returns only a point (no administrative extent).
    ~111 km per degree of latitude; longitude degrees shrink with cos(lat).
    """
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.1))
    return BoundingBox(
        south=lat - lat_delta, north=lat + lat_delta,
        west=lon - lon_delta, east=lon + lon_delta,
    )


class PhotonClient:
    def __init__(
        self,
        base_url: str = "https://photon.komoot.io",
        user_agent: str = "company-finder-outreach-tool/0.1",
        min_request_interval: float = 1.0,
        bbox_radius_km: float = 6.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.min_request_interval = min_request_interval
        self.bbox_radius_km = bbox_radius_km
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
            f"{self.base_url}/api/",
            params={"q": query, "limit": 1},
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        self._last_request_time = time.monotonic()
        response.raise_for_status()
        features = response.json().get("features") or []
        if not features:
            logger.warning("Photon found no results for %r", query)
            return None

        properties = features[0].get("properties", {})
        # Photon's "extent" is [west_lon, north_lat, east_lon, south_lat] —
        # present for administrative areas (countries/regions/cities), which
        # is exactly what we always query for here.
        extent = properties.get("extent")
        if extent and len(extent) == 4:
            west, north, east, south = extent
            return BoundingBox(south=south, north=north, west=west, east=east)

        lon, lat = features[0]["geometry"]["coordinates"]
        return _bbox_from_point(lat, lon, self.bbox_radius_km)


class NominatimClient:
    """For self-hosted Nominatim instances — the public demo server at
    nominatim.openstreetmap.org actively blocks scripted clients per its
    usage policy, so this isn't used by default (see PhotonClient above).
    """

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
