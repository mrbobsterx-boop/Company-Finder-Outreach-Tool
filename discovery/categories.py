"""Maps a human-friendly --category string to OpenStreetMap tag filters.

OSM has no single "business category" tag — it splits businesses across
`shop=*`, `office=*`, and `amenity=*`. This table is the translation layer
so CLI users can type "webdev" instead of "office=it". Extend it as new
categories come up; an unmapped category falls back to matching against
all three keys directly (`categories.py` doesn't need to be exhaustive).
"""
from __future__ import annotations

from typing import NamedTuple


class OSMTag(NamedTuple):
    key: str
    value: str


CATEGORY_MAP: dict[str, list[OSMTag]] = {
    "webdev": [OSMTag("office", "it"), OSMTag("office", "web_design")],
    "it": [OSMTag("office", "it")],
    "marketing": [OSMTag("office", "advertising_agency"), OSMTag("office", "marketing")],
    "consulting": [OSMTag("office", "consulting")],
    "law": [OSMTag("office", "lawyer")],
    "accounting": [OSMTag("office", "accountant")],
    "insurance": [OSMTag("office", "insurance")],
    "real_estate": [OSMTag("office", "estate_agent")],
    "architecture": [OSMTag("office", "architect")],
    "company": [OSMTag("office", "company")],
    "office": [OSMTag("office", "company"), OSMTag("office", "yes")],
    "restaurant": [OSMTag("amenity", "restaurant")],
    "cafe": [OSMTag("amenity", "cafe")],
    "bar": [OSMTag("amenity", "bar")],
    "hotel": [OSMTag("tourism", "hotel")],
    "retail": [OSMTag("shop", "yes")],
    "clothing": [OSMTag("shop", "clothes")],
    "electronics": [OSMTag("shop", "electronics")],
    "hairdresser": [OSMTag("shop", "hairdresser")],
    "car_dealer": [OSMTag("shop", "car")],
    "supermarket": [OSMTag("shop", "supermarket")],
    "bakery": [OSMTag("shop", "bakery")],
    "gym": [OSMTag("leisure", "fitness_centre")],
    "medical": [OSMTag("amenity", "doctors"), OSMTag("amenity", "clinic")],
    "dentist": [OSMTag("amenity", "dentist")],
    "pharmacy": [OSMTag("amenity", "pharmacy")],
}


def resolve_category(category: str) -> list[OSMTag]:
    """Return OSM tags for a category, falling back to shop/office/amenity = category."""
    normalized = category.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in CATEGORY_MAP:
        return CATEGORY_MAP[normalized]
    return [
        OSMTag("shop", normalized),
        OSMTag("office", normalized),
        OSMTag("amenity", normalized),
    ]
