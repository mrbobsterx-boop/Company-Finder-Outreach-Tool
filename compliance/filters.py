"""Compliance gate every recipient must pass before `mailer` ever sees them.

Nothing bypasses `is_unsubscribed` — not even --force — since resending to
someone who opted out is the one mistake this module exists to make
impossible "at the code level", not just by convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional


@dataclass
class RecipientCandidate:
    company_id: int
    company_name: str
    country: Optional[str]
    email: str


@dataclass
class RecipientDecision:
    candidate: RecipientCandidate
    allowed: bool
    reasons: List[str]


def is_business_email(email: str, config: dict) -> bool:
    """True unless the address is on a known personal-webmail domain."""
    domain = email.rsplit("@", 1)[-1].lower()
    personal_domains = {d.lower() for d in config.get("personal_email_domains", [])}
    return domain not in personal_domains


def requires_legal_review(country: Optional[str], config: dict) -> bool:
    strict_countries = {c.upper() for c in config.get("strict_consent_countries", [])}
    return bool(country) and country.upper() in strict_countries


def _parse_sqlite_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def within_frequency_window(last_sent_at: Optional[str], config: dict) -> bool:
    """True if a previous send to this address is still inside the cool-down window."""
    if not last_sent_at:
        return False
    min_days = config.get("min_days_between_emails", 90)
    last_sent = _parse_sqlite_datetime(last_sent_at)
    return datetime.now(timezone.utc) - last_sent < timedelta(days=min_days)


def filter_recipients(
    candidates: List[RecipientCandidate],
    repository,
    compliance_config: dict,
    force: bool = False,
    allow_strict_countries: bool = False,
) -> List[RecipientDecision]:
    """Run every candidate through the compliance pipeline.

    Returns a decision per candidate (allowed + reasons for exclusion, so
    `send --dry-run` can show *why* someone was skipped, not just who).
    """
    decisions: List[RecipientDecision] = []

    for candidate in candidates:
        reasons: List[str] = []
        email = candidate.email.strip().lower()

        # Unsubscribes are absolute: never overridden by --force.
        if repository.is_unsubscribed(email):
            reasons.append("unsubscribed")

        if not is_business_email(email, compliance_config):
            reasons.append("personal_email_domain")

        if requires_legal_review(candidate.country, compliance_config) and not allow_strict_countries:
            reasons.append("requires_legal_review")

        if not force:
            last_sent_at = repository.last_sent_at(email)
            if within_frequency_window(last_sent_at, compliance_config):
                reasons.append("frequency_limit")

        decisions.append(
            RecipientDecision(candidate=candidate, allowed=not reasons, reasons=reasons)
        )

    return decisions
