from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from prospect_agent.classify.vertical_classifier import classify_vertical
from prospect_agent.config import PRIORITY_MARKETS
from prospect_agent.discovery.query_builder import VERTICALS, build_queries
from prospect_agent.enrich.lead_scorer import score_lead
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.providers.directory import DirectoryProvider
from prospect_agent.providers.places import PlacesProvider
from prospect_agent.providers.search import SearchProvider
from prospect_agent.storage.google_sheets import GoogleSheetsStorage


def _norm(v: str) -> str:
    return "".join(ch.lower() for ch in (v or "") if ch.isalnum() or ch.isspace()).strip()


def _business_key(b: dict) -> tuple[str, str, str, str]:
    return (
        b.get("google_place_id", "") or "",
        _norm(b.get("domain", "")),
        "".join(ch for ch in str(b.get("phone", "")) if ch.isdigit()),
        f"{_norm(b.get('name',''))}|{_norm(b.get('city',''))}|{_norm(b.get('state',''))}",
    )


def run_daily(target: int = 1000, storage: GoogleSheetsStorage | None = None) -> dict:
    storage = storage or GoogleSheetsStorage()
    run_id = str(uuid4())
    today = str(date.today())
    now = datetime.utcnow().isoformat()
    storage.create_discovery_run({"run_id": run_id, "run_date": today, "status": "running", "target_count": target, "started_at": now})

    existing = storage.get_existing_businesses()
    recent_ids = storage.get_recent_daily_call_list_business_ids(days=90)
    suppression = storage.get_suppression_list()

    by_keys = {_business_key(b): b for b in existing}
    sup_phones = {"".join(ch for ch in str(s.get("phone", "")) if ch.isdigit()) for s in suppression}
    sup_domains = {_norm(s.get("domain", "")) for s in suppression}

    search, places, directory = SearchProvider(), PlacesProvider(), DirectoryProvider()
    leads, queries = [], []

    for state, cities in PRIORITY_MARKETS.items():
        for city in cities:
            for vertical in VERTICALS:
                for query in build_queries(vertical, city, state)[:2]:
                    queries.append({"query_id": str(uuid4()), "run_id": run_id, "source": "free", "query": query, "vertical": vertical, "city": city, "state": state, "status": "ok", "results_count": 3, "created_at": now})
                    for src, provider in (("search", search), ("places", places), ("directory", directory)):
                        for cand in provider.search(query):
                            txt = f"{cand.get('name','')} {query}"
                            c = classify_vertical(txt)
                            if c["confidence"] < 0.65:
                                continue
                            sig = extract_signals(txt)
                            plats = detect_platforms(txt)
                            score, tier = score_lead(sig, {"website_url": cand.get("website_url", ""), "google_review_count": 100, "has_known_platform": bool(plats)})
                            if score < 40:
                                continue
                            domain = _norm((cand.get("website_url", "").split("//")[-1].split("/")[0]))
                            phone_norm = "".join(ch for ch in str(cand.get("phone", "")) if ch.isdigit())
                            key = ("", domain, phone_norm, f"{_norm(cand.get('name',''))}|{_norm(city)}|{_norm(state)}")
                            matched = by_keys.get(key)
                            if matched:
                                storage.update_business(matched.get("business_id", ""), {"last_seen_at": now, "updated_at": now})
                                if matched.get("business_id") in recent_ids:
                                    continue
                                business_id = matched.get("business_id")
                            else:
                                business_id = str(uuid4())
                            if phone_norm in sup_phones or domain in sup_domains:
                                continue
                            row = {
                                "business_id": business_id,
                                "name": cand.get("name", ""),
                                "normalized_name": _norm(cand.get("name", "")),
                                "vertical": c["primary_vertical"],
                                "sub_vertical": c["sub_vertical"],
                                "vertical_confidence": c["confidence"],
                                "website_url": cand.get("website_url", ""),
                                "domain": domain,
                                "phone": cand.get("phone", ""),
                                "city": city,
                                "state": state,
                                "source": src,
                                "source_url": cand.get("source_url", ""),
                                "lead_score": score,
                                "lead_tier": tier,
                                "created_at": now,
                                "updated_at": now,
                            }
                            leads.append(row)
                            if len(leads) >= target:
                                break
                        if len(leads) >= target:
                            break
                    if len(leads) >= target:
                        break
                if len(leads) >= target:
                    break
            if len(leads) >= target:
                break
        if len(leads) >= target:
            break

    storage.append_discovery_queries(queries)
    storage.append_businesses(leads)
    call_rows = [{"list_id": str(uuid4()), "run_id": run_id, "list_date": today, "rank": i + 1, "business_id": b["business_id"], "name": b["name"], "vertical": b["vertical"], "sub_vertical": b["sub_vertical"], "phone": b["phone"], "website_url": b["website_url"], "city": b["city"], "state": b["state"], "source_url": b["source_url"], "lead_score": b["lead_score"], "lead_tier": b["lead_tier"], "reason": "Qualified by vertical + score", "suggested_call_angle": "They show public booking/event signals. Pitch lifecycle follow-up.", "compliance_notes": "Public business source.", "exported": True, "created_at": now} for i, b in enumerate(leads)]
    storage.append_daily_call_list(call_rows)
    storage.update_discovery_run(run_id, {"status": "completed", "discovered_count": len(leads), "net_new_count": len(leads), "qualified_count": len(leads), "exported_count": len(leads), "finished_at": now})
    return {"run_id": run_id, "qualified": len(leads)}
