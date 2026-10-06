"""Loads config.yaml into a plain nested dict, with sane defaults.

Kept dependency-free (no pydantic) since the schema is small and the CLI
is the only consumer.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parent / "config.example.yaml"

_DEFAULTS: dict[str, Any] = {
    "database": {"path": "data/company_finder.sqlite3"},
    "discovery": {
        "provider": "osm",
        "geocoder_base_url": "https://photon.komoot.io",
        # Tried in order; falls through to the next on failure/timeout.
        "overpass_urls": [
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.openstreetmap.ru/api/interpreter",
        ],
        "request_delay_seconds": 1.0,
        "bbox_radius_km": 6.0,
        "user_agent": "company-finder-outreach-tool/0.1 (contact: set-your-email@example.com)",
    },
    "enrichment": {
        "contact_page_keywords": [
            "contact", "kontakt", "impressum", "imprint",
            "about", "uber-uns", "über-uns", "ueber-uns", "company",
        ],
        "user_agent": "company-finder-outreach-tool/0.1 (contact: set-your-email@example.com; +https://example.com/bot)",
        "domain_delay_seconds": 1.0,
        "min_delay_seconds": 0.5,
        "max_delay_seconds": 2.0,
        "request_timeout_seconds": 10,
        "cache_dir": "enrichment/cache",
        "use_playwright_fallback": False,
        "ai_fallback": {
            "backend": "off",  # off | cloud_api | local_ollama
            "cloud_api_model": "claude-sonnet-5",
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3.1:8b",
            "max_page_chars": 4000,
        },
    },
    "compliance": {
        "strict_consent_countries": ["DE", "IT", "AT", "FR"],
        "personal_email_domains": [
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "icloud.com", "gmx.com", "gmx.de", "web.de", "aol.com",
            "mail.ru", "yandex.ru", "protonmail.com",
        ],
        "business_email_prefixes": ["info", "kontakt", "contact", "office", "sales", "hello"],
        "min_days_between_emails": 90,
    },
    "mailer": {
        "provider": "smtp",
        "smtp_host": "smtp-relay.brevo.com",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "from_email": "you@example.com",
        "from_name": "Your Company",
        "unsubscribe_base_url": "https://example.com/unsubscribe",
        "throttle_seconds": 8,
        "templates_dir": "mailer/templates",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml, falling back to config.example.yaml, merged onto defaults.

    Environment variables can override secrets, e.g. COMPANY_FINDER_SMTP_PASSWORD.
    """
    candidate = Path(path) if path else DEFAULT_CONFIG_PATH
    if not candidate.exists():
        candidate = EXAMPLE_CONFIG_PATH

    user_config: dict[str, Any] = {}
    if candidate.exists():
        with open(candidate, "r", encoding="utf-8") as fh:
            user_config = yaml.safe_load(fh) or {}

    cfg = _deep_merge(_DEFAULTS, user_config)

    env_overrides = {
        "COMPANY_FINDER_SMTP_USERNAME": ("mailer", "smtp_username"),
        "COMPANY_FINDER_SMTP_PASSWORD": ("mailer", "smtp_password"),
        "COMPANY_FINDER_ANTHROPIC_API_KEY": ("enrichment", "ai_fallback", "cloud_api_key"),
    }
    for env_name, path_tuple in env_overrides.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        node = cfg
        for key in path_tuple[:-1]:
            node = node.setdefault(key, {})
        node[path_tuple[-1]] = value

    return cfg
