"""Fetches a company's contact page(s) and extracts email/phone.

Strategy: fetch the homepage, find links whose text or href match known
contact-page keywords (contact, kontakt, impressum, about, ...), then fetch
just those pages rather than crawling the whole site. Regex extraction runs
first; the (optional, off by default) AI fallback only runs on pages where
regex found nothing, and only on the trimmed page text.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from enrichment.ai_fallback import extract_contacts_via_ai
from enrichment.cache import HtmlCache
from enrichment.patterns import extract_emails, extract_phones
from enrichment.robots import DomainRateLimiter, RobotsChecker

logger = logging.getLogger(__name__)


@dataclass
class ScrapedContact:
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    source_page: Optional[str] = None
    used_ai_fallback: bool = False


class CompanyScraper:
    def __init__(
        self,
        contact_page_keywords: List[str],
        user_agent: str,
        cache_dir: str,
        domain_delay_seconds: float = 1.0,
        min_delay_seconds: float = 0.5,
        max_delay_seconds: float = 2.0,
        request_timeout_seconds: int = 10,
        ai_fallback_config: Optional[dict] = None,
        repository=None,
    ):
        self.contact_page_keywords = [kw.lower() for kw in contact_page_keywords]
        self.user_agent = user_agent
        self.cache = HtmlCache(cache_dir)
        self.rate_limiter = DomainRateLimiter(domain_delay_seconds)
        self.robots = RobotsChecker(user_agent)
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.ai_fallback_config = ai_fallback_config or {"backend": "off"}
        self.repository = repository

    def _fetch(self, url: str) -> Optional[str]:
        cached = self.cache.get(url)
        if cached is not None:
            return cached

        if not self.robots.can_fetch(url):
            logger.info("robots.txt disallows fetching %s", url)
            return None

        self.rate_limiter.wait(url)
        domain = urlparse(url).netloc
        start = time.monotonic()
        status_code = None
        error = None
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.request_timeout_seconds,
            )
            status_code = response.status_code
            response.raise_for_status()
            html = response.text
        except requests.RequestException as exc:
            error = str(exc)
            html = None
        duration_ms = int((time.monotonic() - start) * 1000)

        if self.repository is not None:
            self.repository.log_scrape(domain, url, status_code, duration_ms, error)

        if html is not None:
            self.cache.set(url, html)
            time.sleep(random.uniform(self.min_delay_seconds, self.max_delay_seconds))
        return html

    def _find_contact_page_links(self, homepage_url: str, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: dict[str, None] = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            text = anchor.get_text(strip=True).lower()
            haystack = f"{href.lower()} {text}"
            if any(keyword in haystack for keyword in self.contact_page_keywords):
                absolute = urljoin(homepage_url, href)
                if urlparse(absolute).netloc == urlparse(homepage_url).netloc:
                    candidates.setdefault(absolute, None)
        return list(candidates.keys())

    @staticmethod
    def _page_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)

    def scrape_company(
        self, website_url: str, default_region: Optional[str] = None
    ) -> ScrapedContact:
        homepage_html = self._fetch(website_url)
        if homepage_html is None:
            return ScrapedContact()

        pages_to_check = [website_url] + self._find_contact_page_links(
            website_url, homepage_html
        )

        all_emails: dict[str, None] = {}
        all_phones: dict[str, None] = {}
        first_page_with_match: Optional[str] = None
        used_ai_fallback = False

        for page_url in pages_to_check:
            html = homepage_html if page_url == website_url else self._fetch(page_url)
            if html is None:
                continue

            text = self._page_text(html)
            emails = extract_emails(html) or extract_emails(text)
            phones = extract_phones(text, default_region)

            if not emails and not phones and self.ai_fallback_config.get("backend") != "off":
                ai_result = extract_contacts_via_ai(text, self.ai_fallback_config)
                emails = ai_result.emails
                phones = ai_result.phones
                if emails or phones:
                    used_ai_fallback = True

            if emails or phones:
                first_page_with_match = first_page_with_match or page_url
                for email in emails:
                    all_emails.setdefault(email, None)
                for phone in phones:
                    all_phones.setdefault(phone, None)

        return ScrapedContact(
            emails=list(all_emails.keys()),
            phones=list(all_phones.keys()),
            source_page=first_page_with_match,
            used_ai_fallback=used_ai_fallback,
        )
