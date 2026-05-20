from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from prospect_agent.config import Settings
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.providers.search import hostname, normalize_url


MULTI_LOCATION_TERMS = (
    "location",
    "locations",
    "venues",
    "stores",
    "clubs",
    "franchise",
    "find-a",
)

BOOKING_URL_TERMS = (
    "book",
    "booking",
    "reserve",
    "reservation",
    "tee-time",
    "tee-times",
    "party",
    "parties",
    "birthday",
    "event",
    "events",
    "waiver",
    "member",
    "membership",
    "camp",
    "league",
    "ticket",
    "tickets",
    "gift",
)


@dataclass
class CommonCrawlDomainIntel:
    domain: str
    urls: list[str] = field(default_factory=list)
    subdomains: list[str] = field(default_factory=list)
    location_urls: list[str] = field(default_factory=list)
    booking_urls: list[str] = field(default_factory=list)
    signal_urls: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)

    @property
    def url_count(self) -> int:
        return len(self.urls)

    @property
    def has_multi_location_signal(self) -> bool:
        return bool(self.subdomains or self.location_urls)

    def text(self) -> str:
        return " ".join(self.urls)

    def signals(self) -> dict[str, bool]:
        return extract_signals(self.text())

    def summary(self) -> str:
        if not self.url_count:
            return ""
        parts = [f"Common Crawl URLs: {self.url_count}"]
        if self.subdomains:
            parts.append(f"subdomains: {', '.join(self.subdomains[:5])}")
        if self.location_urls:
            parts.append(f"location URLs: {len(self.location_urls)}")
        if self.booking_urls:
            parts.append(f"booking URLs: {len(self.booking_urls)}")
        if self.signal_urls:
            parts.append(f"signal URLs: {len(self.signal_urls)}")
        if self.platforms:
            parts.append(f"platforms: {', '.join(self.platforms)}")
        return "; ".join(parts)


class CommonCrawlProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._index_api: str | None = None

    def lookup_domain(self, domain: str) -> CommonCrawlDomainIntel:
        clean_domain = hostname(domain)
        if not clean_domain or not self.settings.use_common_crawl:
            return CommonCrawlDomainIntel(domain=clean_domain)

        records = self._fetch_index_records(clean_domain)
        urls = self._unique_urls(record.get("url", "") for record in records)
        return self._summarize_urls(clean_domain, urls)

    def _fetch_index_records(self, domain: str) -> list[dict]:
        api = self._index_endpoint()
        if not api:
            return []
        timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds, connect=3.0)
        params = [
            ("url", domain),
            ("matchType", "domain"),
            ("output", "json"),
            ("filter", "status:200"),
            ("collapse", "urlkey"),
            ("limit", str(self.settings.common_crawl_max_urls_per_domain)),
        ]
        try:
            with httpx.Client(timeout=timeout, headers={"User-Agent": self.settings.user_agent}) as client:
                response = client.get(api, params=params)
                response.raise_for_status()
        except httpx.HTTPError:
            return []

        records = []
        for line in response.text.splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            mime = f"{record.get('mime', '')} {record.get('mime-detected', '')}".lower()
            if "html" in mime:
                records.append(record)
        return records

    def _index_endpoint(self) -> str:
        if self._index_api is not None:
            return self._index_api
        if self.settings.common_crawl_index:
            index = self.settings.common_crawl_index.strip()
            self._index_api = index if index.startswith("http") else f"https://index.commoncrawl.org/{index}-index"
            return self._index_api

        timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds, connect=3.0)
        try:
            with httpx.Client(timeout=timeout, headers={"User-Agent": self.settings.user_agent}) as client:
                response = client.get("https://index.commoncrawl.org/collinfo.json")
                response.raise_for_status()
                collections = response.json()
        except (httpx.HTTPError, ValueError):
            self._index_api = ""
            return self._index_api

        latest = collections[0] if collections else {}
        self._index_api = latest.get("cdx-api") or (
            f"https://index.commoncrawl.org/{latest.get('id')}-index" if latest.get("id") else ""
        )
        return self._index_api

    @staticmethod
    def _unique_urls(urls) -> list[str]:
        seen = set()
        out = []
        for url in urls:
            normalized = normalize_url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

    @staticmethod
    def _summarize_urls(domain: str, urls: list[str]) -> CommonCrawlDomainIntel:
        base = hostname(domain)
        subdomains = set()
        location_urls = []
        booking_urls = []
        signal_urls = []
        platforms = {item["platform"] for item in detect_platforms(" ".join(urls))}
        signal_names = extract_signals(" ".join(urls))

        for url in urls:
            parsed = urlparse(url)
            host = hostname(url)
            path = parsed.path.lower()
            if host and host != base and host.endswith(f".{base}"):
                subdomains.add(host)
            if any(term in path for term in MULTI_LOCATION_TERMS):
                location_urls.append(url)
            if any(term in path for term in BOOKING_URL_TERMS):
                booking_urls.append(url)
            if any(signal_names.values()) and any(term in path for term in BOOKING_URL_TERMS):
                signal_urls.append(url)

        return CommonCrawlDomainIntel(
            domain=base,
            urls=urls,
            subdomains=sorted(subdomains),
            location_urls=location_urls,
            booking_urls=booking_urls,
            signal_urls=signal_urls,
            platforms=sorted(platforms),
        )
