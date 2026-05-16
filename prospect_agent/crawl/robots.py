from __future__ import annotations

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser


_ROBOT_CACHE: dict[str, RobotFileParser] = {}


def allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _ROBOT_CACHE:
        rp = RobotFileParser()
        rp.set_url(urljoin(base, "/robots.txt"))
        try:
            rp.read()
        except Exception:
            return False
        _ROBOT_CACHE[base] = rp
    return _ROBOT_CACHE[base].can_fetch(user_agent, url)
