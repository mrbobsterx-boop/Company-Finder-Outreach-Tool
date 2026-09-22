"""robots.txt compliance and per-domain rate limiting for the scraper."""
from __future__ import annotations

import time
import urllib.robotparser
from typing import Dict
from urllib.parse import urlparse


class RobotsChecker:
    """Caches parsed robots.txt per domain so it's fetched once per run."""

    def __init__(self, user_agent: str, timeout: int = 10):
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: Dict[str, urllib.robotparser.RobotFileParser] = {}

    def _get_parser(self, url: str) -> urllib.robotparser.RobotFileParser:
        parsed = urlparse(url)
        domain_key = f"{parsed.scheme}://{parsed.netloc}"
        if domain_key not in self._cache:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(f"{domain_key}/robots.txt")
            try:
                parser.read()
            except Exception:
                # If robots.txt is unreachable, default to permissive
                # (matches how most crawlers behave on a fetch error).
                parser = urllib.robotparser.RobotFileParser()
                parser.disallow_all = False
            self._cache[domain_key] = parser
        return self._cache[domain_key]

    def can_fetch(self, url: str) -> bool:
        parser = self._get_parser(url)
        return parser.can_fetch(self.user_agent, url)


class DomainRateLimiter:
    """Enforces a minimum delay between requests to the same domain."""

    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval_seconds = min_interval_seconds
        self._last_request_time: Dict[str, float] = {}

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        last_time = self._last_request_time.get(domain)
        if last_time is not None:
            elapsed = time.monotonic() - last_time
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_time[domain] = time.monotonic()
