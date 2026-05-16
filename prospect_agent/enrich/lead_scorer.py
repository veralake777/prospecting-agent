def score_lead(signals: dict, meta: dict) -> tuple[int, str]:
    score = 0
    score += 20 if signals.get("has_online_booking") else 0
    score += 15 if signals.get("has_birthday_parties") or signals.get("has_group_events") else 0
    score += 10 if signals.get("has_memberships") or signals.get("has_season_passes") else 0
    score += 10 if signals.get("has_camps") or signals.get("has_leagues") or signals.get("has_group_events") else 0
    score += 10 if signals.get("has_waiver") else 0
    score += 10 if meta.get("google_review_count", 0) >= 100 else 0
    score += 10 if meta.get("has_known_platform") else 0
    score += 5 if signals.get("has_email_signup") else 0
    score += 5 if signals.get("has_gift_cards") else 0
    score += 5 if signals.get("has_multiple_locations") else 0
    score -= 10 if not meta.get("website_url") else 0
    score -= 10 if meta.get("website_unreachable") else 0
    score -= 10 if meta.get("invalid_vertical") else 0
    score -= 20 if meta.get("suppressed") else 0
    score = max(0, min(100, score))
    tier = "high_value" if score >= 80 else "good" if score >= 60 else "nurture" if score >= 40 else "low_priority"
    return score, tier
