"""Email and phone extraction, including common obfuscation patterns.

Sites that want to avoid scraper harvesting often write `name [at] domain
[dot] com` instead of `name@domain.com`. This module normalizes the common
variants before applying the standard email regex, so plain regex handles
the large majority of cases without needing an AI fallback.
"""
from __future__ import annotations

import re
from typing import List, Optional

import phonenumbers

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Order matters: longer/bracketed variants before bare word variants so
# "[at]" isn't partially consumed by a looser pattern first. Surrounding
# whitespace is consumed too, since "example [dot] com" has spaces outside
# the brackets that would otherwise survive the substitution.
_AT_VARIANTS = [
    r"\s*\[\s*at\s*\]\s*", r"\s*\(\s*at\s*\)\s*", r"\s*\{\s*at\s*\}\s*",
    r"\s+at\s+", r"\s*&#64;\s*", r"\s*%40\s*",
]
_DOT_VARIANTS = [
    r"\s*\[\s*dot\s*\]\s*", r"\s*\(\s*dot\s*\)\s*", r"\s*\{\s*dot\s*\}\s*",
    r"\s+dot\s+", r"\s*&#46;\s*",
]

_AT_RE = re.compile("|".join(_AT_VARIANTS), re.IGNORECASE)
_DOT_RE = re.compile("|".join(_DOT_VARIANTS), re.IGNORECASE)
_LOOSE_AT_SPACING_RE = re.compile(r"\s*@\s*")


def deobfuscate_text(text: str) -> str:
    """Rewrite common email-obfuscation patterns back to plain `@` / `.`."""
    text = _AT_RE.sub("@", text)
    text = _DOT_RE.sub(".", text)
    text = _LOOSE_AT_SPACING_RE.sub("@", text)
    return text


def extract_emails(text: str) -> List[str]:
    """Extract, deobfuscate, and dedupe email addresses from free text."""
    if not text:
        return []
    normalized = deobfuscate_text(text)
    matches = EMAIL_RE.findall(normalized)
    seen: dict[str, None] = {}
    for match in matches:
        cleaned = match.strip(".").lower()
        if _looks_like_real_email(cleaned):
            seen.setdefault(cleaned, None)
    return list(seen.keys())


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def _looks_like_real_email(email: str) -> bool:
    """Filter out matches that are actually filenames (logo@2x.png-style CSS)."""
    return not email.endswith(_IMAGE_EXTENSIONS)


def extract_phones(text: str, default_region: Optional[str] = None) -> List[str]:
    """Extract phone numbers, normalized to E.164, using `phonenumbers`.

    `default_region` (an ISO country code like "DE") lets local-format
    numbers without a country code resolve correctly.
    """
    if not text:
        return []
    results: dict[str, None] = {}
    for match in phonenumbers.PhoneNumberMatcher(text, default_region):
        number = phonenumbers.format_number(
            match.number, phonenumbers.PhoneNumberFormat.E164
        )
        results.setdefault(number, None)
    return list(results.keys())
