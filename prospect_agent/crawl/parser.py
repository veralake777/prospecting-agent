def extract_excerpt(html: str, limit: int = 1000) -> str:
    return " ".join(html.split())[:limit]
