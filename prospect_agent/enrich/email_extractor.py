from __future__ import annotations

import re
from urllib.parse import unquote


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net"}
NO_REPLY_PREFIXES = {"noreply", "no-reply", "donotreply", "do-not-reply"}


def clean_email(value: str) -> str:
    raw = unquote(str(value or "").strip())
    if raw.lower().startswith("mailto:"):
        raw = raw[7:]
    raw = raw.split("?", 1)[0].strip().strip(".,;:!?)]}\"'>").strip("([{\"'<")
    if not raw or "@" not in raw or any(ch.isspace() for ch in raw):
        return ""
    local, domain = raw.rsplit("@", 1)
    local = local.strip().lower()
    domain = domain.strip().lower().strip(".")
    if not local or not domain or "." not in domain:
        return ""
    if domain in PLACEHOLDER_DOMAINS or any(domain.endswith(f".{placeholder}") for placeholder in PLACEHOLDER_DOMAINS):
        return ""
    if local in NO_REPLY_PREFIXES:
        return ""
    return f"{local}@{domain}"


def extract_emails(texts) -> list[str]:
    if isinstance(texts, str):
        texts = [texts]
    seen = set()
    out = []
    for text in texts or []:
        for match in EMAIL_RE.finditer(str(text or "")):
            email = clean_email(match.group(0))
            if email and email not in seen:
                seen.add(email)
                out.append(email)
    return out


def first_email(*values: str) -> str:
    emails = extract_emails(values)
    return emails[0] if emails else ""
