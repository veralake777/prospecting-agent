from __future__ import annotations


class DirectoryProvider:
    """Directory sources are discovery hints only, not callable business leads."""

    def search(self, query: str) -> list[dict]:
        return []
