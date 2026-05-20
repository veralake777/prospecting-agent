from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LeadScore:
    score: int
    tier: str
    reasons: list[str]
    signal_reasons: list[str]


def score_lead(signals: dict, meta: dict) -> tuple[int, str]:
    detail = score_lead_detail(signals, meta)
    return detail.score, detail.tier


def score_lead_detail(signals: dict, meta: dict) -> LeadScore:
    score = 0
    reasons: list[str] = []
    signal_reasons: list[str] = []

    def add(points: int, reason: str, is_signal: bool = False) -> None:
        nonlocal score
        score += points
        reasons.append(f"+{points} {reason}")
        if is_signal:
            signal_reasons.append(reason)

    def subtract(points: int, reason: str) -> None:
        nonlocal score
        score -= points
        reasons.append(f"-{points} {reason}")

    if meta.get("direct_business_website"):
        add(15, "direct business website")
    if meta.get("has_phone"):
        add(15, "public phone")
    if meta.get("has_social_contact"):
        add(5, "social contact link")
    if meta.get("source_verified"):
        add(10, "verified place source")
    if meta.get("common_crawl_multi_location"):
        add(5, "multi-location URL evidence", is_signal=True)
    if signals.get("has_online_booking"):
        add(20, "online booking", is_signal=True)
    if signals.get("has_birthday_parties") or signals.get("has_group_events"):
        add(15, "birthday/group events", is_signal=True)
    if signals.get("has_memberships") or signals.get("has_season_passes"):
        add(10, "memberships/season passes", is_signal=True)
    if signals.get("has_camps") or signals.get("has_leagues") or signals.get("has_group_events"):
        add(10, "camps/leagues/group programming", is_signal=True)
    if signals.get("has_waiver"):
        add(10, "waiver flow", is_signal=True)
    if meta.get("google_review_count", 0) >= 100:
        add(10, "100+ Google reviews")
    if meta.get("has_known_platform"):
        add(10, "known commerce/booking platform", is_signal=True)
    if signals.get("has_email_signup"):
        add(5, "email signup", is_signal=True)
    if signals.get("has_gift_cards"):
        add(5, "gift cards", is_signal=True)
    if signals.get("has_multiple_locations"):
        add(5, "multiple locations", is_signal=True)
    if not meta.get("website_url"):
        subtract(10, "missing website")
    if meta.get("website_unreachable"):
        subtract(10, "website unreachable")
    if meta.get("invalid_vertical"):
        subtract(10, "invalid vertical")
    if meta.get("suppressed"):
        subtract(20, "suppressed")

    score = max(0, min(100, score))
    tier = "high_value" if score >= 80 else "good" if score >= 60 else "nurture" if score >= 40 else "low_priority"
    return LeadScore(score=score, tier=tier, reasons=reasons, signal_reasons=signal_reasons)
