from __future__ import annotations


class DirectoryProvider:
    def search(self, query: str) -> list[dict]:
        return [{"name": f"{query.title()} Directory Listing", "website_url": "https://example.net", "source_url": "https://example.net/directory", "phone": "(555)555-0300"}]
