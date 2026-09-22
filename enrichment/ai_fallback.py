"""Optional AI fallback for contact pages where plain regex found nothing.

This only runs for the small remainder of pages where regex extraction on
known contact pages came up empty — never on the full page set — and only
when explicitly enabled in config.yaml (`enrichment.ai_fallback.backend`):

  - "off"          (default): never called, zero cost.
  - "local_ollama": free, runs against a local Ollama server.
  - "cloud_api":    pay-per-call to the Anthropic API; cheap at this volume
                     since it's only the "regex found nothing" remainder.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

import requests

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """You are extracting contact information from a snippet of a \
company website's contact/about page. Return ONLY a JSON object with two keys, \
"emails" and "phones", each a list of strings found verbatim in the text. \
If none are found, return empty lists. Do not invent data that is not in the text.

TEXT:
{text}
"""


@dataclass
class AIExtractionResult:
    emails: List[str]
    phones: List[str]


def _parse_json_response(raw: str) -> AIExtractionResult:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("AI fallback returned non-JSON response, discarding")
        return AIExtractionResult(emails=[], phones=[])
    return AIExtractionResult(
        emails=[e for e in data.get("emails", []) if isinstance(e, str)],
        phones=[p for p in data.get("phones", []) if isinstance(p, str)],
    )


def _extract_via_cloud_api(text: str, model: str, api_key: str) -> AIExtractionResult:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "ai_fallback.backend is 'cloud_api' but the 'anthropic' package "
            "is not installed. Run: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": _EXTRACTION_PROMPT.format(text=text)}],
    )
    raw = "".join(block.text for block in response.content if hasattr(block, "text"))
    return _parse_json_response(raw)


def _extract_via_local_ollama(text: str, base_url: str, model: str) -> AIExtractionResult:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": _EXTRACTION_PROMPT.format(text=text),
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    raw = response.json().get("response", "")
    return _parse_json_response(raw)


def extract_contacts_via_ai(text: str, config: dict) -> AIExtractionResult:
    """Dispatch to the configured backend. `config` is the `ai_fallback` sub-dict."""
    backend = config.get("backend", "off")
    max_chars = config.get("max_page_chars", 4000)
    trimmed = text[:max_chars]

    if backend == "off":
        return AIExtractionResult(emails=[], phones=[])
    if backend == "cloud_api":
        api_key = config.get("cloud_api_key")
        if not api_key:
            logger.warning(
                "ai_fallback.backend is 'cloud_api' but no API key is configured "
                "(set COMPANY_FINDER_ANTHROPIC_API_KEY) — skipping AI fallback"
            )
            return AIExtractionResult(emails=[], phones=[])
        return _extract_via_cloud_api(
            trimmed, model=config.get("cloud_api_model", "claude-sonnet-5"), api_key=api_key
        )
    if backend == "local_ollama":
        return _extract_via_local_ollama(
            trimmed,
            base_url=config.get("ollama_base_url", "http://localhost:11434"),
            model=config.get("ollama_model", "llama3.1:8b"),
        )

    raise ValueError(f"Unknown ai_fallback.backend: {backend!r}")
