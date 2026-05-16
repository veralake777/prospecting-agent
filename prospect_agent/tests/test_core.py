from prospect_agent.classify.vertical_classifier import classify_vertical
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.lead_scorer import score_lead


def test_vertical_classification():
    r = classify_vertical("Indoor golf simulator with booking and trackman")
    assert r["primary_vertical"] in {"golf_simulator", "golf"}


def test_signal_extraction():
    s = extract_signals("Book now for birthday parties and memberships with waiver")
    assert s["has_online_booking"] and s["has_birthday_parties"] and s["has_waiver"]


def test_platform_detection():
    p = detect_platforms("<script src='https://cdn.shopify.com/x.js'></script>")
    assert any(x["platform"] == "Shopify" for x in p)


def test_lead_score():
    score, tier = score_lead({"has_online_booking": True, "has_birthday_parties": True}, {"website_url": "https://x.com"})
    assert score >= 35
    assert tier in {"low_priority", "nurture", "good", "high_value"}
