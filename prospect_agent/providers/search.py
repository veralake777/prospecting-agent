from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from prospect_agent.config import Settings


DIRECTORY_DOMAINS = {
    "10best.com",
    "airbnb.com",
    "bringfido.com",
    "eventbrite.com",
    "facebook.com",
    "foursquare.com",
    "google.com",
    "groupon.com",
    "instagram.com",
    "mapquest.com",
    "maps.apple.com",
    "maps.google.com",
    "opentable.com",
    "reddit.com",
    "theknot.com",
    "thingstodopost.org",
    "tripadvisor.com",
    "trustpilot.com",
    "wikipedia.org",
    "yelp.com",
    "yellowpages.com",
}


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme:
        return value
    if value.startswith("//"):
        return f"https:{value}"
    return f"https://{value}"


def hostname(url: str) -> str:
    host = urlparse(normalize_url(url)).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_directory_url(url: str) -> bool:
    host = hostname(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in DIRECTORY_DOMAINS)


def is_placeholder_url(url: str) -> bool:
    host = hostname(url)
    return host in {"example.com", "example.org", "example.net"} or host.endswith((".example.com", ".example.org", ".example.net"))


def is_direct_business_url(url: str) -> bool:
    return bool(hostname(url)) and not is_placeholder_url(url) and not is_directory_url(url)


class SearchProvider:
    """Search provider for organic business websites.

    `stub` and `manual` intentionally return no rows; they are development modes,
    not sources of production leads.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def search(self, query: str) -> list[dict]:
        provider = self.settings.search_provider.strip().lower()
        if provider in {"", "stub", "manual"}:
            return []
        if provider in {"free", "duckduckgo", "ddg"}:
            return self._duckduckgo_search(query)
        return []

    def _duckduckgo_search(self, query: str) -> list[dict]:
        timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds, connect=3.0)
        html = ""
        endpoints = ("https://html.duckduckgo.com/html/", "https://duckduckgo.com/html/")
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": self.settings.user_agent}) as client:
                for endpoint in endpoints:
                    response = client.get(endpoint, params={"q": query})
                    response.raise_for_status()
                    if ".result" in response.text or "result__a" in response.text:
                        html = response.text
                        break
        except httpx.HTTPError:
            return []
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        candidates: list[dict] = []
        for result in soup.select(".result"):
            link = result.select_one(".result__a")
            if not link:
                continue
            url = normalize_url(self._unwrap_duckduckgo_url(link.get("href", "")))
            if not is_direct_business_url(url):
                continue
            snippet = result.select_one(".result__snippet")
            candidates.append(
                {
                    "name": link.get_text(" ", strip=True),
                    "website_url": url,
                    "source_url": url,
                    "snippet": snippet.get_text(" ", strip=True) if snippet else "",
                    "source_kind": "organic",
                }
            )
            if len(candidates) >= 5:
                break
        return candidates

    @staticmethod
    def _unwrap_duckduckgo_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            wrapped = parse_qs(parsed.query).get("uddg", [""])[0]
            if wrapped:
                return unquote(wrapped)
        return url
