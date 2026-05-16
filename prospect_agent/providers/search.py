from __future__ import annotations

import re


class SearchProvider:
    """Free-compatible stub/manual provider from query text."""

    def search(self, query: str) -> list[dict]:
        tokens = re.sub(r"\s+", " ", query).strip()
        return [{"name": f"{tokens.title()} Center", "website_url": "https://example.com", "source_url": "https://example.com/search", "phone": "(555)555-0100"}]
