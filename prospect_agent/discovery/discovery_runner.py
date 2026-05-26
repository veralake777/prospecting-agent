from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
import hashlib
import random
from urllib.parse import urlparse
from uuid import uuid4

from prospect_agent.classify.vertical_classifier import classify_vertical
from prospect_agent.config import PRIORITY_MARKETS, Settings
from prospect_agent.discovery.query_builder import VERTICALS, build_queries
from prospect_agent.enrich.email_extractor import first_email
from prospect_agent.enrich.lead_scorer import score_lead_detail
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.providers.common_crawl import CommonCrawlDomainIntel, CommonCrawlProvider
from prospect_agent.providers.directory import DirectoryProvider
from prospect_agent.providers.places import PlacesProvider
from prospect_agent.providers.search import is_direct_business_url, is_placeholder_url
from prospect_agent.providers.search import SearchProvider
from prospect_agent.providers.website_crawl import WebsiteCrawler, WebsiteIntel
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


def _seed_int(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _discovery_plan(settings: Settings, run_date: str) -> list[tuple[str, str, str, str]]:
    items = [
        (state, city, vertical)
        for state, cities in PRIORITY_MARKETS.items()
        for city in cities
        for vertical in VERTICALS
    ]
    seed = settings.discovery_seed or run_date
    if settings.shuffle_discovery_order:
        rng = random.Random(_seed_int(seed))
        rng.shuffle(items)

    queries_per_vertical = max(1, settings.queries_per_vertical)
    plan = []
    for state, city, vertical in items:
        queries = build_queries(vertical, city, state)
        if settings.shuffle_discovery_order:
            rng = random.Random(_seed_int(f"{seed}:{state}:{city}:{vertical}"))
            rng.shuffle(queries)
        for query in queries[:queries_per_vertical]:
            plan.append((state, city, vertical, query))
    return plan


def _domain_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _candidate_text(candidate: dict, query: str) -> str:
    fields = ("name", "category", "description", "snippet", "title")
    return " ".join(str(candidate.get(field, "")) for field in fields) + f" {query}"


def _is_usable_candidate(source: str, candidate: dict) -> bool:
    if source == "directory":
        return False
    website = candidate.get("website_url", "")
    if website and is_placeholder_url(website):
        return False
    if source == "search":
        return is_direct_business_url(website)
    return bool(is_direct_business_url(website) or candidate.get("phone") or candidate.get("google_place_id") or candidate.get("source_id"))


def _url_contains_booking_signal(url: str) -> bool:
    parsed = urlparse(url or "")
    lowered = " ".join(part.lower() for part in (parsed.path, parsed.query, parsed.fragment, parsed.netloc) if part)
    return any(
        term in lowered
        for term in (
            "book",
            "booking",
            "reserve",
            "reservation",
            "tee-time",
            "tee-times",
            "party",
            "parties",
            "birthday",
            "event",
            "waiver",
            "member",
            "camp",
            "league",
            "ticket",
            "gift",
        )
    )


def _booking_evidence(candidate: dict, intel: CommonCrawlDomainIntel, website: WebsiteIntel | None = None) -> dict:
    website = website or WebsiteIntel(root_url=candidate.get("website_url", ""))
    urls = []
    for url in [*website.booking_urls, *intel.booking_urls, *intel.signal_urls, candidate.get("website_url", "")]:
        if url and _url_contains_booking_signal(url) and url not in urls:
            urls.append(url)
    platform_hits = detect_platforms(
        " ".join(
            [
                *urls,
                candidate.get("website_url", ""),
                intel.text(),
                " ".join(intel.platforms),
                website.text(),
                " ".join(website.platforms),
            ]
        )
    )
    platforms = []
    for platform in [*website.platforms, *intel.platforms]:
        if platform and platform not in platforms:
            platforms.append(platform)
    for hit in platform_hits:
        platform = hit.get("platform", "")
        if platform and platform not in platforms:
            platforms.append(platform)
    return {
        "booking_url": urls[0] if urls else "",
        "evidence_url": urls[0] if urls else candidate.get("source_url", ""),
        "booking_platform": ", ".join(platforms),
        "booking_urls": urls,
    }


def _social_evidence(website: WebsiteIntel | None = None) -> dict:
    website = website or WebsiteIntel()
    links = website.social_links
    first = links[0] if links else {}
    return {
        "social_url": first.get("url", ""),
        "social_platform": first.get("platform", ""),
        "social_links": links,
    }


def _email_evidence(candidate: dict, website: WebsiteIntel | None = None) -> str:
    website = website or WebsiteIntel()
    return first_email(candidate.get("email", ""), *website.emails)


def _noop_progress(message: str) -> None:
    return None


def _score_reason(row: dict) -> str:
    if row.get("sdr_discovery_required"):
        return "Needs SDR discovery: no phone, email, website, or social profile found on public source."
    reasons = row.get("score_reasons") or []
    if not reasons:
        return "Qualified by vertical and contactability score"
    return "; ".join(reasons[:5])


def _suggested_call_angle(row: dict) -> str:
    if row.get("sdr_discovery_required"):
        return "No public contact path found yet. SDR should research website, phone, email, or social before outreach."
    if row.get("booking_platform"):
        return f"Booking evidence suggests {row['booking_platform']}. Review the booking link, then pitch lifecycle follow-up."
    if row.get("booking_url"):
        return "Booking page found. Review the linked page for integration clues, then pitch lifecycle follow-up."
    if row.get("email"):
        return f"Public email {row['email']} found. Use it as a backup contact path if phone outreach stalls."
    if row.get("social_url"):
        return f"{row['social_platform']} profile found. Use it as a backup contact path if phone outreach stalls."
    signals = row.get("signal_reasons") or []
    if signals:
        return f"They show {', '.join(signals[:3])}. Pitch lifecycle follow-up."
    return "Contactable public business. Verify booking, parties, memberships, waivers, and follow-up gaps before pitching."


def _requires_sdr_discovery(candidate: dict, social: dict, email: str = "") -> bool:
    return not any(
        (
            candidate.get("phone"),
            email,
            is_direct_business_url(candidate.get("website_url", "")),
            social.get("social_url"),
        )
    )


def _zero_result_reason(
    candidates_seen: int,
    usable_candidates: int,
    classified_candidates: int,
    scored_candidates: int,
    skipped_recent: int,
    suppressed_candidates: int,
    include_recent: bool,
    recent_days: int,
) -> str:
    if candidates_seen == 0:
        return "No raw candidates returned by discovery providers. Check network access, provider availability, or increase --max-queries."
    if usable_candidates == 0:
        return "Discovery returned candidates, but all were rejected as directories/placeholders or lacked contact/source data."
    if classified_candidates == 0:
        return "Discovery returned usable candidates, but none matched target verticals confidently enough."
    if scored_candidates == 0:
        return "Candidates matched target verticals, but none reached the lead score threshold."
    if skipped_recent and not include_recent:
        return (
            f"No fresh leads because {skipped_recent} scored candidate(s) were already exported within "
            f"the {recent_days}-day cooldown. Use --include-recent for smoke tests or lower --recent-days."
        )
    if suppressed_candidates:
        return "Scored candidates were removed by suppression rules."
    return "No leads remained after dedupe and eligibility filters."


def run_daily(
    target: int = 1000,
    storage: GoogleSheetsStorage | None = None,
    progress: Callable[[str], None] | None = None,
    recent_days: int | None = None,
    include_recent: bool = False,
    target_contactable: bool = False,
) -> dict:
    storage = storage or GoogleSheetsStorage()
    settings = storage.settings if hasattr(storage, "settings") else Settings()
    progress = progress or _noop_progress
    max_queries = max(1, settings.max_discovery_queries_per_run)
    progress_interval = max(1, settings.progress_interval_queries)
    run_id = str(uuid4())
    today = str(date.today())
    now = datetime.utcnow().isoformat()
    storage.create_discovery_run({"run_id": run_id, "run_date": today, "status": "running", "target_count": target, "started_at": now})

    existing = storage.get_existing_businesses()
    recent_days = settings.recent_call_list_days if recent_days is None else recent_days
    recent_ids = set() if include_recent else storage.get_recent_daily_call_list_business_ids(days=recent_days)
    suppression = storage.get_suppression_list()

    by_keys = {_business_key(b): b for b in existing}
    sup_phones = {"".join(ch for ch in str(s.get("phone", "")) if ch.isdigit()) for s in suppression}
    sup_domains = {_norm(s.get("domain", "")) for s in suppression}

    search, places, directory = SearchProvider(settings), PlacesProvider(settings), DirectoryProvider()
    common_crawl = CommonCrawlProvider(settings)
    website_crawler = WebsiteCrawler(settings)
    common_crawl_cache: dict[str, CommonCrawlDomainIntel] = {}
    website_cache: dict[str, WebsiteIntel] = {}
    common_crawl_domains = 0
    websites_crawled = 0
    leads, new_business_rows, website_rows, page_rows, lead_signal_rows, queries = [], [], [], [], [], []
    selected_business_ids = set()
    contactable_leads = 0
    attempted_queries = 0
    stopped_reason = ""
    skipped_recent = 0
    matched_existing = 0
    candidates_seen = 0
    usable_candidates = 0
    classified_candidates = 0
    scored_candidates = 0
    research_candidates = 0
    suppressed_candidates = 0
    source_result_counts = {"search": 0, "places": 0, "directory": 0}
    source_usable_counts = {"search": 0, "places": 0, "directory": 0}
    markets_attempted: set[str] = set()
    discovery_seed = settings.discovery_seed or today

    def target_reached() -> bool:
        return (contactable_leads if target_contactable else len(leads)) >= target

    for state, city, vertical, query in _discovery_plan(settings, today):
        if attempted_queries >= max_queries:
            stopped_reason = f"Reached discovery query budget ({max_queries}) before target ({target})"
            break
        attempted_queries += 1
        markets_attempted.add(f"{city}, {state}")
        if attempted_queries == 1 or attempted_queries % progress_interval == 0:
            progress(
                f"discovery query {attempted_queries}/{max_queries}: {city}, {state} {vertical}; "
                f"qualified={len(leads)}/{target}; contactable={contactable_leads}/{target}; "
                f"raw={candidates_seen}; scored={scored_candidates}; recent={skipped_recent}"
            )
        query_result_count = 0
        for src, provider in (("search", search), ("places", places), ("directory", directory)):
            for cand in provider.search(query):
                query_result_count += 1
                candidates_seen += 1
                source_result_counts[src] = source_result_counts.get(src, 0) + 1
                if not _is_usable_candidate(src, cand):
                    continue
                usable_candidates += 1
                source_usable_counts[src] = source_usable_counts.get(src, 0) + 1
                domain = _domain_from_url(cand.get("website_url", ""))
                cc_intel = CommonCrawlDomainIntel(domain=domain)
                if settings.use_common_crawl and domain:
                    if domain not in common_crawl_cache and common_crawl_domains < settings.common_crawl_max_domains_per_run:
                        common_crawl_domains += 1
                        common_crawl_cache[domain] = common_crawl.lookup_domain(domain)
                    cc_intel = common_crawl_cache.get(domain, cc_intel)
                site_intel = WebsiteIntel(root_url=cand.get("website_url", ""))
                if domain and cand.get("website_url"):
                    if domain not in website_cache:
                        website_cache[domain] = website_crawler.lookup(cand.get("website_url", ""))
                        if website_cache[domain].http_status:
                            websites_crawled += 1
                    site_intel = website_cache.get(domain, site_intel)
                txt = f"{_candidate_text(cand, query)} {cc_intel.text()} {site_intel.text()}"
                c = classify_vertical(txt)
                if c["confidence"] < 0.65:
                    continue
                classified_candidates += 1
                sig = extract_signals(txt)
                evidence = _booking_evidence(cand, cc_intel, site_intel)
                social = _social_evidence(site_intel)
                email = _email_evidence(cand, site_intel)
                sdr_discovery_required = _requires_sdr_discovery(cand, social, email)
                plats = detect_platforms(f"{txt} {evidence['booking_platform']}")
                phone_norm = "".join(ch for ch in str(cand.get("phone", "")) if ch.isdigit())
                score_detail = score_lead_detail(
                    sig,
                    {
                        "website_url": cand.get("website_url", ""),
                        "google_review_count": int(cand.get("google_review_count") or 0),
                        "has_known_platform": bool(plats),
                        "direct_business_website": is_direct_business_url(cand.get("website_url", "")),
                        "has_phone": bool(phone_norm),
                        "has_email": bool(email),
                        "has_social_contact": bool(social["social_links"]),
                        "source_verified": src == "places",
                        "common_crawl_multi_location": cc_intel.has_multi_location_signal,
                    },
                )
                score, tier = score_detail.score, score_detail.tier
                qualifies_by_score = score >= 40
                qualifies_for_research = src == "places"
                if not qualifies_by_score and not qualifies_for_research:
                    continue
                if qualifies_by_score:
                    scored_candidates += 1
                else:
                    research_candidates += 1
                    tier = "research"
                key = (cand.get("google_place_id", "") or "", _norm(domain), phone_norm, f"{_norm(cand.get('name',''))}|{_norm(city)}|{_norm(state)}")
                matched = by_keys.get(key)
                is_new_business = matched is None
                if matched:
                    matched_existing += 1
                    storage.update_business(matched.get("business_id", ""), {"last_seen_at": now, "updated_at": now})
                    if matched.get("business_id") in recent_ids:
                        skipped_recent += 1
                        continue
                    business_id = matched.get("business_id")
                else:
                    business_id = str(uuid4())
                if business_id in selected_business_ids:
                    continue
                if phone_norm in sup_phones or _norm(domain) in sup_domains:
                    suppressed_candidates += 1
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
                    "email": email,
                    "address": cand.get("address", ""),
                    "city": cand.get("city") or city,
                    "state": cand.get("state") or state,
                    "postal_code": cand.get("postal_code", ""),
                    "country": cand.get("country", ""),
                    "latitude": cand.get("latitude", ""),
                    "longitude": cand.get("longitude", ""),
                    "google_place_id": cand.get("google_place_id", ""),
                    "source": src,
                    "source_id": cand.get("source_id", ""),
                    "source_url": cand.get("source_url", ""),
                    "google_rating": cand.get("google_rating", ""),
                    "google_review_count": cand.get("google_review_count", ""),
                    "lead_score": score,
                    "lead_tier": tier,
                    "status": "needs_research" if sdr_discovery_required else "",
                    "booking_url": evidence["booking_url"],
                    "booking_platform": evidence["booking_platform"],
                    "evidence_url": evidence["evidence_url"],
                    "social_url": social["social_url"],
                    "social_platform": social["social_platform"],
                    "sdr_discovery_required": sdr_discovery_required,
                    "score_reasons": score_detail.reasons,
                    "signal_reasons": score_detail.signal_reasons,
                    "compliance_notes": cc_intel.summary(),
                    "created_at": now,
                    "updated_at": now,
                }
                by_keys[key] = row
                selected_business_ids.add(business_id)
                leads.append(row)
                if not sdr_discovery_required:
                    contactable_leads += 1
                if is_new_business:
                    new_business_rows.append(row)
                if site_intel.root_url:
                    website_id = str(uuid4())
                    website_rows.append({
                        "website_id": website_id,
                        "business_id": business_id,
                        "root_url": site_intel.root_url,
                        "final_url": site_intel.final_url,
                        "domain": domain,
                        "http_status": site_intel.http_status,
                        "title": site_intel.title,
                        "meta_description": site_intel.meta_description,
                        "booking_url": evidence["booking_url"],
                        "booking_platform": evidence["booking_platform"],
                        "social_urls": ", ".join(link["url"] for link in social["social_links"]),
                        "has_online_booking": sig.get("has_online_booking", False),
                        "has_parties": sig.get("has_birthday_parties", False) or sig.get("has_group_events", False),
                        "has_memberships": sig.get("has_memberships", False),
                        "has_gift_cards": sig.get("has_gift_cards", False),
                        "has_events": sig.get("has_group_events", False) or sig.get("has_private_events", False) or sig.get("has_corporate_events", False),
                        "has_camps": sig.get("has_camps", False),
                        "has_leagues": sig.get("has_leagues", False),
                        "has_waiver": sig.get("has_waiver", False),
                        "has_email_signup": sig.get("has_email_signup", False),
                        "has_sms_mentions": sig.get("has_sms_mentions", False),
                        "has_multiple_locations": sig.get("has_multiple_locations", False) or cc_intel.has_multi_location_signal,
                        "last_crawled_at": now,
                        "created_at": now,
                        "updated_at": now,
                    })
                    for booking_url in evidence["booking_urls"]:
                        parsed_booking_url = urlparse(booking_url)
                        page_rows.append({
                            "page_id": str(uuid4()),
                            "website_id": website_id,
                            "business_id": business_id,
                            "url": booking_url,
                            "path": parsed_booking_url.path,
                            "page_type": "booking",
                            "clean_text_excerpt": "Booking/ecommerce-like link discovered from homepage or Common Crawl URL evidence.",
                            "created_at": now,
                            "updated_at": now,
                        })
                for booking_url in evidence["booking_urls"]:
                    lead_signal_rows.append({
                        "signal_id": str(uuid4()),
                        "business_id": business_id,
                        "signal_type": "booking_page",
                        "signal_value": booking_url,
                        "confidence": 0.8,
                        "evidence_url": booking_url,
                        "evidence_text": "Booking-like URL discovered from homepage or Common Crawl URL evidence",
                        "created_at": now,
                    })
                if evidence["booking_platform"]:
                    lead_signal_rows.append({
                        "signal_id": str(uuid4()),
                        "business_id": business_id,
                        "signal_type": "booking_platform",
                        "signal_value": evidence["booking_platform"],
                        "confidence": 0.9,
                        "evidence_url": evidence["evidence_url"],
                        "evidence_text": "Platform detected from booking/evidence URL",
                        "created_at": now,
                    })
                for link in social["social_links"]:
                    lead_signal_rows.append({
                        "signal_id": str(uuid4()),
                        "business_id": business_id,
                        "signal_type": "social_profile",
                        "signal_value": link["url"],
                        "confidence": 0.8,
                        "evidence_url": link["url"],
                        "evidence_text": f"{link['platform']} profile discovered from homepage crawl",
                        "created_at": now,
                    })
                if target_reached():
                    break
            if target_reached():
                break
        queries.append({"query_id": str(uuid4()), "run_id": run_id, "source": "free", "query": query, "vertical": vertical, "city": city, "state": state, "status": "ok", "results_count": query_result_count, "created_at": now})
        if target_reached():
            break
    if len(leads) == 0:
        reason = _zero_result_reason(
            candidates_seen,
            usable_candidates,
            classified_candidates,
            scored_candidates,
            skipped_recent,
            suppressed_candidates,
            include_recent,
            recent_days,
        )
        stopped_reason = f"{reason} {stopped_reason}".strip() if stopped_reason else reason
    elif not stopped_reason and attempted_queries >= max_queries and not target_reached():
        stopped_reason = f"Reached discovery query budget ({max_queries}) before target ({target})"

    storage.append_discovery_queries(queries)
    storage.append_businesses(new_business_rows)
    storage.append_websites(website_rows)
    storage.append_pages(page_rows)
    storage.append_lead_signals(lead_signal_rows)
    call_rows = [
        {
            "list_id": str(uuid4()),
            "run_id": run_id,
            "list_date": today,
            "rank": i + 1,
            "business_id": b["business_id"],
            "name": b["name"],
            "vertical": b["vertical"],
            "sub_vertical": b["sub_vertical"],
            "phone": b["phone"],
            "email": b["email"],
            "website_url": b["website_url"],
            "city": b["city"],
            "state": b["state"],
            "source_url": b["source_url"],
            "booking_url": b["booking_url"],
            "booking_platform": b["booking_platform"],
            "evidence_url": b["evidence_url"],
            "social_url": b["social_url"],
            "social_platform": b["social_platform"],
            "lead_score": b["lead_score"],
            "lead_tier": b["lead_tier"],
            "reason": _score_reason(b),
            "suggested_call_angle": _suggested_call_angle(b),
            "compliance_notes": "Public business source.",
            "exported": True,
            "created_at": now,
        }
        for i, b in enumerate(leads)
    ]
    storage.append_daily_call_list(call_rows)
    storage.update_discovery_run(run_id, {"status": "completed", "discovered_count": len(leads), "net_new_count": len(new_business_rows), "qualified_count": len(leads), "exported_count": len(leads), "finished_at": now, "error_message": stopped_reason})
    progress(f"discovery complete: qualified={len(leads)}, contactable={contactable_leads}/{target}, queries={attempted_queries}/{max_queries}, skipped_recent={skipped_recent}")
    return {
        "run_id": run_id,
        "qualified": len(leads),
        "contactable_qualified": contactable_leads,
        "target_mode": "contactable" if target_contactable else "total",
        "new_businesses": len(new_business_rows),
        "matched_existing": matched_existing,
        "skipped_recent": skipped_recent,
        "recent_days": recent_days,
        "include_recent": include_recent,
        "queries_attempted": attempted_queries,
        "markets_attempted": len(markets_attempted),
        "discovery_seed": discovery_seed,
        "candidates_seen": candidates_seen,
        "usable_candidates": usable_candidates,
        "classified_candidates": classified_candidates,
        "scored_candidates": scored_candidates,
        "research_candidates": research_candidates,
        "suppressed_candidates": suppressed_candidates,
        "source_result_counts": source_result_counts,
        "source_usable_counts": source_usable_counts,
        "common_crawl_domains": common_crawl_domains,
        "websites_crawled": websites_crawled,
        "stopped_reason": stopped_reason,
    }
