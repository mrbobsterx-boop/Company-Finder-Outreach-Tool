"""Free discovery provider backed by OpenStreetMap (Photon + Overpass).

Photon resolves "country, region, city" to a bounding box; Overpass then
returns every node/way tagged with the business category inside that box.
Both are free and keyless, but have fair-use limits, so this client throttles
itself rather than firing requests back to back.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import requests

from discovery.base import DiscoveryProvider
from discovery.categories import resolve_category
from discovery.geocoding import BoundingBox, PhotonClient
from storage.models import Company

logger = logging.getLogger(__name__)


def _build_overpass_query(bbox: BoundingBox, tags, timeout: int = 60) -> str:
    bbox_str = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
    clauses = []
    for tag in tags:
        for element in ("node", "way"):
            clauses.append(f'  {element}["{tag.key}"="{tag.value}"]({bbox_str});')
    body = "\n".join(clauses)
    return f"[out:json][timeout:{timeout}];\n(\n{body}\n);\nout center tags;"


def _extract_website(tags: dict) -> Optional[str]:
    for key in ("website", "contact:website", "url"):
        if tags.get(key):
            return tags[key]
    return None


def _extract_address(tags: dict) -> Optional[str]:
    parts = [tags.get("addr:street"), tags.get("addr:housenumber")]
    street_line = " ".join(p for p in parts if p)
    if tags.get("addr:full"):
        return tags["addr:full"]
    postcode_city = " ".join(
        p for p in (tags.get("addr:postcode"), tags.get("addr:city")) if p
    )
    address = ", ".join(p for p in (street_line, postcode_city) if p)
    return address or None


def _element_to_company(
    element: dict, city: str, region: Optional[str], country: str, category: str
) -> Optional[Company]:
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None

    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")

    return Company(
        name=name,
        address=_extract_address(tags),
        city=tags.get("addr:city") or city,
        region=region,
        country=country,
        lat=lat,
        lon=lon,
        website=_extract_website(tags),
        osm_id=f"{element['type']}/{element['id']}",
        category=category,
    )


class OSMDiscoveryProvider(DiscoveryProvider):
    def __init__(
        self,
        overpass_base_url: str = "https://overpass.kumi.systems/api/interpreter",
        geocoder_base_url: str = "https://photon.komoot.io",
        user_agent: str = "company-finder-outreach-tool/0.1",
        request_delay_seconds: float = 1.0,
        bbox_radius_km: float = 6.0,
    ):
        self.overpass_base_url = overpass_base_url.rstrip("/")
        self.user_agent = user_agent
        self.request_delay_seconds = request_delay_seconds
        self.geocoder = PhotonClient(
            base_url=geocoder_base_url,
            user_agent=user_agent,
            min_request_interval=max(request_delay_seconds, 1.0),
            bbox_radius_km=bbox_radius_km,
        )

    def search(
        self,
        country: str,
        region: Optional[str],
        city: Optional[str],
        category: str,
    ) -> List[Company]:
        bbox = self.geocoder.geocode_bbox(country=country, region=region, city=city)
        if bbox is None:
            logger.warning(
                "Could not geocode %s / %s / %s — skipping Overpass query",
                country, region, city,
            )
            return []

        tags = resolve_category(category)
        query = _build_overpass_query(bbox, tags)

        time.sleep(self.request_delay_seconds)
        response = requests.post(
            self.overpass_base_url,
            data={"data": query},
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Language": "en",
            },
            timeout=90,
        )
        if not response.ok:
            logger.error("Overpass query was:\n%s", query)
            logger.error("Overpass response body:\n%s", response.text[:2000])
            raise RuntimeError(
                f"Overpass request failed with HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        payload = response.json()

        companies: list[Company] = []
        seen_osm_ids: set[str] = set()
        for element in payload.get("elements", []):
            company = _element_to_company(
                element, city=city or "", region=region, country=country, category=category
            )
            if company is None or company.osm_id in seen_osm_ids:
                continue
            seen_osm_ids.add(company.osm_id)
            companies.append(company)

        logger.info(
            "OSM discovery found %d companies for %s in %s/%s/%s",
            len(companies), category, country, region, city,
        )
        return companies
