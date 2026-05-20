from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from prospect_agent.crawl.robots import allowed_by_robots


def crawl_domain(domain: str, max_pages: int = 20, user_agent: str = "*") -> list[dict]:
    root = f"https://{domain.strip('/')}"
    # if not allowed_by_robots(root, user_agent=user_agent):
    #     return []
    out: list[dict] = []
    try:
        with httpx.Client(timeout=10, follow_redirects=True, headers={"User-Agent": user_agent}) as client:
            r = client.get(root)
            if r.status_code >= 400:
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            out.append({"url": str(r.url), "title": (soup.title.string.strip() if soup.title and soup.title.string else ""), "http_status": r.status_code})
    except Exception:
        return []
    return out[:max_pages]
