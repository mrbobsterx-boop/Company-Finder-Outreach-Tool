from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    website: Optional[str] = None
    osm_id: Optional[str] = None
    category: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class Contact:
    company_id: int
    email: Optional[str] = None
    phone: Optional[str] = None
    source_page: Optional[str] = None
    confidence: float = 0.5
    id: Optional[int] = None
    verified_at: Optional[str] = None


@dataclass
class OutreachLogEntry:
    company_id: int
    email: str
    status: str  # e.g. "sent", "dry_run", "failed", "skipped"
    id: Optional[int] = None
    sent_at: Optional[str] = None
    opened_at: Optional[str] = None
    unsubscribed_at: Optional[str] = None
