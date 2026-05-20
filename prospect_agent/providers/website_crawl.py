from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from prospect_agent.config import Settings
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.providers.common_crawl import BOOKING_URL_TERMS
from prospect_agent.providers.search import hostname, is_direct_business_url, normalize_url


SOCIAL_DOMAINS = {
    "Facebook": ("facebook.com", "fb.com"),
    "Instagram": ("instagram.com",),
    "TikTok": ("tiktok.com",),
    "LinkedIn": ("linkedin.com",),
    "YouTube": ("youtube.com", "youtu.be"),
    "X": ("x.com", "twitter.com"),
    "Pinterest": ("pinterest.com",),
}

SOCIAL_PRIORITY = ("Facebook", "Instagram", "TikTok", "LinkedIn", "YouTube", "X", "Pinterest")


@dataclass
class WebsiteIntel:
    root_url: str = ""
    final_url: str = ""
    http_status: int = 0
    title: str = ""
    meta_description: str = ""
    text_excerpt: str = ""
    booking_urls: list[str] = field(default_factory=list)
    social_links: list[dict[str, str]] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(
            part
            for part in (
                self.title,
                self.meta_description,
                self.text_excerpt,
                " ".join(self.booking_urls),
                " ".join(link.get("url", "") for link in self.social_links),
                " ".join(self.platforms),
            )
            if part
        )

    def signals(self) -> dict[str, bool]:
        return extract_signals(self.text())


class WebsiteCrawler:
    """Small homepage crawl focused on evidence URLs, not a full web crawl."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def lookup(self, root_url: str) -> WebsiteIntel:
        root = normalize_url(root_url)
        if not root or not is_direct_business_url(root) or self.settings.max_crawl_pages_per_domain <= 0:
            return WebsiteIntel(root_url=root)
        timeout = httpx.Timeout(self.settings.discovery_http_timeout_seconds, connect=3.0)
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": self.settings.user_agent}) as client:
                response = client.get(root)
        except httpx.HTTPError:
            return WebsiteIntel(root_url=root)

        if response.status_code >= 400:
            return WebsiteIntel(root_url=root, final_url=str(response.url), http_status=response.status_code)
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and response.text.lstrip()[:1] != "<":
            return WebsiteIntel(root_url=root, final_url=str(response.url), http_status=response.status_code)
        return self._summarize_html(root, str(response.url), response.status_code, response.text)

    def _summarize_html(self, root_url: str, final_url: str, http_status: int, html: str) -> WebsiteIntel:
        soup = BeautifulSoup(html[:250_000], "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
        meta_description = meta.get("content", "").strip() if meta else ""
        text_excerpt = soup.get_text(" ", strip=True)[:5000]
        booking_urls = self._extract_booking_urls(soup, final_url)
        social_links = self._extract_social_links(soup, final_url)
        platform_hits = detect_platforms(" ".join([html[:250_000], *booking_urls]))
        platforms = _unique(hit["platform"] for hit in platform_hits)
        return WebsiteIntel(
            root_url=root_url,
            final_url=final_url,
            http_status=http_status,
            title=title,
            meta_description=meta_description,
            text_excerpt=text_excerpt,
            booking_urls=booking_urls,
            social_links=social_links,
            platforms=platforms,
        )

    def _extract_booking_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        limit = max(1, self.settings.max_crawl_pages_per_domain)

        for element in soup.select("a[href], form[action]"):
            raw_url = element.get("href") or element.get("action") or ""
            resolved = _clean_link(raw_url, base_url)
            if not resolved:
                continue
            text = element.get_text(" ", strip=True)
            combined = f"{text} {resolved}"
            if _looks_like_booking_link(combined):
                urls.append(resolved)
            if len(_unique(urls)) >= limit:
                break

        return _unique(urls)[:limit]

    def _extract_social_links(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        for element in soup.select("a[href]"):
            resolved = _clean_link(element.get("href") or "", base_url)
            if not resolved:
                continue
            platform = _social_platform(resolved)
            if not platform:
                continue
            link = {"platform": platform, "url": resolved}
            if link not in links:
                links.append(link)
        return sorted(links, key=lambda item: SOCIAL_PRIORITY.index(item["platform"]) if item["platform"] in SOCIAL_PRIORITY else 99)


def _clean_link(raw_url: str, base_url: str) -> str:
    raw = (raw_url or "").strip()
    if not raw or raw.startswith(("#", "mailto:", "tel:", "sms:", "javascript:")):
        return ""
    absolute = urljoin(base_url, raw)
    absolute = urldefrag(absolute)[0]
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return ""
    normalized = normalize_url(absolute)
    if not hostname(normalized):
        return ""
    return normalized


def _looks_like_booking_link(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in BOOKING_URL_TERMS) or bool(detect_platforms(lowered))


def _social_platform(url: str) -> str:
    parsed = urlparse(url)
    host = hostname(url)
    path = parsed.path.strip("/").lower()
    if not host or not path:
        return ""
    if any(marker in path for marker in ("share", "sharer", "intent", "dialog", "plugins", "login", "search", "status/")):
        return ""
    for platform, domains in SOCIAL_DOMAINS.items():
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            if platform == "LinkedIn" and not path.startswith(("company/", "school/", "showcase/", "in/")):
                return ""
            if platform == "YouTube" and not path.startswith(("@", "channel/", "c/", "user/")):
                return ""
            if platform == "Facebook" and path.startswith(("events/", "groups/", "marketplace/", "pages/category/")):
                return ""
            if platform in {"Instagram", "TikTok", "X", "Pinterest"} and path.startswith(("p/", "reel/", "tv/", "explore/", "hashtag/", "i/", "intent/")):
                return ""
            return platform
    return ""


def _unique(values) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
