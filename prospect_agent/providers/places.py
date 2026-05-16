from __future__ import annotations


class PlacesProvider:
    def search(self, query: str) -> list[dict]:
        return [{"name": f"{query.title()} Place", "website_url": "https://example.org", "source_url": "https://example.org/place", "phone": "(555)555-0200"}]
