SIGNALS = {
    "has_online_booking": ["book now", "booking", "reserve"],
    "has_birthday_parties": ["birthday"],
    "has_group_events": ["group events"],
    "has_field_trips": ["field trip"],
    "has_memberships": ["membership"],
    "has_season_passes": ["season pass"],
    "has_camps": ["camp"],
    "has_leagues": ["league"],
    "has_gift_cards": ["gift card"],
    "has_waiver": ["waiver"],
    "has_email_signup": ["subscribe", "newsletter"],
    "has_sms_mentions": ["sms", "text alerts"],
    "has_private_events": ["private event"],
    "has_corporate_events": ["corporate event"],
    "has_contact_form": ["contact us"],
    "has_pricing_page": ["pricing"],
    "has_reviews_or_testimonials": ["testimonials", "reviews"],
    "has_multiple_locations": ["locations", "our locations"],
}

def extract_signals(text: str) -> dict[str, bool]:
    s = text.lower()
    return {k: any(t in s for t in terms) for k, terms in SIGNALS.items()}
