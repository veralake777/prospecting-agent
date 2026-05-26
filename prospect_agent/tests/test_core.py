import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from prospect_agent.classify.vertical_classifier import classify_vertical
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.lead_scorer import score_lead, score_lead_detail
from prospect_agent.config import Settings
from prospect_agent.discovery.discovery_runner import _discovery_plan, run_daily
from prospect_agent.main import _format_run_daily_result
from prospect_agent.providers.common_crawl import CommonCrawlDomainIntel, CommonCrawlProvider
from prospect_agent.providers.directory import DirectoryProvider
from prospect_agent.providers.places import PlacesProvider
from prospect_agent.providers.search import SearchProvider, is_direct_business_url, normalize_url
from prospect_agent.providers.website_crawl import WebsiteCrawler, WebsiteIntel
from prospect_agent.storage.google_sheets import GoogleSheetsConfigurationError, GoogleSheetsStorage


def test_vertical_classification():
    r = classify_vertical("Indoor golf simulator with booking and trackman")
    assert r["primary_vertical"] in {"golf_simulator", "golf"}
    assert r["confidence"] >= 0.65


def test_signal_extraction():
    s = extract_signals("Book now for birthday parties and memberships with waiver")
    assert s["has_online_booking"] and s["has_birthday_parties"] and s["has_waiver"]


def test_platform_detection():
    p = detect_platforms("<script src='https://cdn.shopify.com/x.js'></script>")
    assert any(x["platform"] == "Shopify" for x in p)


def test_url_quality_filters_reject_directories_and_normalize_domains():
    assert normalize_url("www.realfun.test") == "https://www.realfun.test"
    assert is_direct_business_url("www.realfun.test")
    assert not is_direct_business_url("https://www.yelp.com/biz/example")
    assert not is_direct_business_url("https://fake.example.com")


def test_lead_score():
    score, tier = score_lead({"has_online_booking": True, "has_birthday_parties": True}, {"website_url": "https://x.com"})
    assert score >= 35
    assert tier in {"low_priority", "nurture", "good", "high_value"}


def test_lead_score_detail_explains_contactable_baseline():
    detail = score_lead_detail(
        {},
        {
            "website_url": "https://examplebiz.test",
            "direct_business_website": True,
            "has_phone": True,
            "source_verified": True,
        },
    )

    assert detail.score == 40
    assert detail.signal_reasons == []
    assert "direct business website" in " ".join(detail.reasons)


def test_common_crawl_summarizes_domain_url_intelligence():
    intel = CommonCrawlProvider._summarize_urls(
        "examplebiz.com",
        [
            "https://atlanta.examplebiz.com/",
            "https://www.examplebiz.com/locations/atlanta",
            "https://www.examplebiz.com/booking/birthday-parties",
            "https://www.examplebiz.com/waiver",
            "https://www.examplebiz.com/fareharbor/reservations",
        ],
    )

    assert "atlanta.examplebiz.com" in intel.subdomains
    assert intel.location_urls
    assert intel.booking_urls
    assert intel.signal_urls
    assert "FareHarbor" in intel.platforms


def test_discovery_plan_spreads_smoke_queries_across_markets():
    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        discovery_seed="smoke",
    )
    first_ten = _discovery_plan(settings, "2026-05-16")[:10]

    assert first_ten[0][1] != "Atlanta"
    assert len({(state, city) for state, city, _, _ in first_ten}) >= 4
    assert first_ten == _discovery_plan(settings, "2026-05-16")[:10]

    listed = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        shuffle_discovery_order=False,
    )
    assert _discovery_plan(listed, "2026-05-16")[0][:3] == ("GA", "Atlanta", "attractions")


def test_website_crawl_extracts_booking_links_and_platforms():
    crawler = WebsiteCrawler(Settings(google_service_account_json_path="", google_sheets_spreadsheet_id="", max_crawl_pages_per_domain=5))
    intel = crawler._summarize_html(
        "https://familyfun.examplebiz.com",
        "https://familyfun.examplebiz.com/",
        200,
        """
        <html>
          <head><title>Family Fun</title><meta name="description" content="Book birthdays online"></head>
          <body>
            <a href="/birthday-parties/book-now">Book a party</a>
            <a href="https://fareharbor.com/embeds/book/familyfun/items/">Reserve tickets</a>
            <form action="https://waiver.smartwaiver.com/w/familyfun"></form>
            <a href="mailto:events@familyfun.examplebiz.com?subject=Party">Email events</a>
            <p>Questions? info@familyfun.examplebiz.com.</p>
            <a href="https://www.facebook.com/familyfun">Facebook</a>
            <a href="https://www.instagram.com/familyfun/">Instagram</a>
            <a href="https://www.facebook.com/sharer/sharer.php?u=https://familyfun.examplebiz.com">Share</a>
          </body>
        </html>
        """,
    )

    assert intel.booking_urls[0] == "https://familyfun.examplebiz.com/birthday-parties/book-now"
    assert "https://fareharbor.com/embeds/book/familyfun/items/" in intel.booking_urls
    assert "https://waiver.smartwaiver.com/w/familyfun" in intel.booking_urls
    assert "FareHarbor" in intel.platforms
    assert "Smartwaiver" in intel.platforms
    assert intel.emails == ["events@familyfun.examplebiz.com", "info@familyfun.examplebiz.com"]
    assert intel.social_links == [
        {"platform": "Facebook", "url": "https://www.facebook.com/familyfun"},
        {"platform": "Instagram", "url": "https://www.instagram.com/familyfun/"},
    ]


def test_overpass_candidates_keep_real_place_contact_data():
    provider = PlacesProvider(Settings(google_service_account_json_path="", google_sheets_spreadsheet_id=""))
    rows = provider._overpass_candidates(
        [
            {
                "type": "node",
                "id": 123,
                "lat": 33.0,
                "lon": -84.0,
                "tags": {
                    "name": "Atlanta Family Fun Center",
                    "leisure": "trampoline_park",
                    "website": "www.atlantafamilyfun.examplebiz.com",
                    "phone": "+1-404-555-1212",
                    "contact:email": "info@atlantafamilyfun.examplebiz.com",
                    "addr:housenumber": "123",
                    "addr:street": "Main Street",
                },
            }
        ],
        "Atlanta",
        "GA",
    )

    assert rows[0]["website_url"] == "https://www.atlantafamilyfun.examplebiz.com"
    assert rows[0]["phone"] == "+1-404-555-1212"
    assert rows[0]["email"] == "info@atlantafamilyfun.examplebiz.com"
    assert rows[0]["source_id"] == "osm:node:123"


def test_overpass_uses_radius_for_non_atlanta_priority_markets():
    provider = PlacesProvider(Settings(google_service_account_json_path="", google_sheets_spreadsheet_id="", osm_search_radius_meters=90000))
    query = provider._overpass_query("Tampa", "FL", [(("leisure", "miniature_golf"),)])

    assert "around:90000,27.9506,-82.4572" in query
    assert "area.searchArea" not in query


def test_overpass_keeps_place_candidates_without_contact_for_diagnostics():
    provider = PlacesProvider(Settings(google_service_account_json_path="", google_sheets_spreadsheet_id=""))
    rows = provider._overpass_candidates(
        [
            {
                "type": "node",
                "id": 456,
                "lat": 27.0,
                "lon": -82.0,
                "tags": {"name": "Sparse Laser Tag", "leisure": "laser_tag"},
            }
        ],
        "Tampa",
        "FL",
    )

    assert rows[0]["name"] == "Sparse Laser Tag"
    assert rows[0]["website_url"] == ""
    assert rows[0]["phone"] == ""
    assert rows[0]["email"] == ""


def test_google_places_new_candidate_mapping_and_cost_caps():
    place = {
        "id": "places/google-123",
        "displayName": {"text": "Atlanta Family Fun Center"},
        "formattedAddress": "123 Main St, Atlanta, GA",
        "location": {"latitude": 33.7, "longitude": -84.4},
        "primaryType": "amusement_center",
        "types": ["point_of_interest", "establishment"],
        "googleMapsUri": "https://maps.google.com/?cid=123",
    }
    detail = {
        "nationalPhoneNumber": "(404) 555-1212",
        "websiteUri": "https://atlantafamilyfun.examplebiz.com",
        "googleMapsUri": "https://maps.google.com/?cid=123",
        "rating": 4.7,
        "userRatingCount": 123,
    }

    row = PlacesProvider._google_candidate_from_place(place, detail, "Atlanta", "GA")

    assert row["name"] == "Atlanta Family Fun Center"
    assert row["website_url"] == "https://atlantafamilyfun.examplebiz.com"
    assert row["phone"] == "(404) 555-1212"
    assert row["email"] == ""
    assert row["google_place_id"] == "places/google-123"
    assert row["google_rating"] == 4.7
    assert row["google_review_count"] == 123
    assert row["city"] == "Atlanta"
    assert "amusement_center" in row["category"]

    provider = PlacesProvider(
        Settings(
            google_service_account_json_path="",
            google_sheets_spreadsheet_id="",
            places_api_key="key",
            google_places_max_text_searches_per_run=0,
            google_places_max_details_per_run=0,
        )
    )
    assert provider._google_places_search("arcades Atlanta GA") == []
    assert provider._google_place_details(object(), "places/google-123") == {}


def test_run_daily_result_formatter_is_readable():
    output = _format_run_daily_result(
        {
            "run_id": "run-123",
            "qualified": 25,
            "new_businesses": 25,
            "matched_existing": 5,
            "skipped_recent": 3,
            "recent_days": 90,
            "include_recent": False,
            "queries_attempted": 22,
            "markets_attempted": 20,
            "discovery_seed": "2026-05-16",
            "candidates_seen": 74,
            "usable_candidates": 74,
            "classified_candidates": 74,
            "scored_candidates": 30,
            "research_candidates": 4,
            "suppressed_candidates": 0,
            "source_result_counts": {"search": 0, "places": 74, "directory": 0},
            "source_usable_counts": {"search": 0, "places": 74, "directory": 0},
            "common_crawl_domains": 3,
            "websites_crawled": 24,
            "stopped_reason": "",
        }
    )

    assert "Daily discovery complete" in output
    assert "- Qualified for call list: 25" in output
    assert "- Research candidates: 4" in output
    assert "- Places: 74 raw / 74 usable" in output
    assert "{'run_id'" not in output


def test_init_storage_explains_google_sheets_permission_errors(monkeypatch):
    class FailingRequest:
        def execute(self):
            response = Response({"status": "403", "reason": "Forbidden"})
            raise HttpError(response, b'{"error": {"message": "The caller does not have permission"}}')

    class FailingSheet:
        def get(self, **kwargs):
            return FailingRequest()

    settings = Settings(
        google_service_account_json_path="service-account.json",
        google_sheets_spreadsheet_id="sheet-123",
    )
    storage = GoogleSheetsStorage(settings=settings)
    storage._service_account_email = "service-account@example.com"
    monkeypatch.setattr(storage, "_sheet", lambda: FailingSheet())

    with pytest.raises(GoogleSheetsConfigurationError) as exc_info:
        storage.init_storage()

    message = str(exc_info.value)
    assert "sheet-123" in message
    assert "service-account@example.com" in message
    assert "Editor" in message


def test_run_daily_does_not_qualify_stub_candidates():
    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="stub",
        places_provider="stub",
        max_discovery_queries_per_run=4,
        use_common_crawl=False,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(25, storage)

    assert result["qualified"] == 0
    assert result["queries_attempted"] == 4
    assert "query budget" in result["stopped_reason"]
    assert len(storage.get_existing_businesses()) == 0


def test_run_daily_qualifies_real_direct_candidates(monkeypatch):
    def real_candidate(self, query):
        return [
            {
                "name": "Atlanta Family Fun Center",
                "website_url": "https://atlantafamilyfun.examplebiz.com",
                "source_url": "https://atlantafamilyfun.examplebiz.com",
                "phone": "(404) 555-1212",
                "snippet": "Book online birthday parties, group events, memberships, waivers, and gift cards.",
            }
        ]

    monkeypatch.setattr(SearchProvider, "search", real_candidate)
    monkeypatch.setattr(PlacesProvider, "search", lambda self, query: [])
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        use_common_crawl=False,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(1, storage)

    assert result["qualified"] == 1
    business = storage.get_existing_businesses()[0]
    assert business["source"] == "search"
    assert business["domain"] == "atlantafamilyfun.examplebiz.com"


def test_run_daily_lists_verified_place_candidates_for_sdr_research(monkeypatch):
    def sparse_place(self, query):
        return [
            {
                "name": "Sparse Laser Tag",
                "website_url": "",
                "source_url": "https://www.openstreetmap.org/node/456",
                "phone": "",
                "source_id": "osm:node:456",
                "category": "laser tag",
            }
        ]

    monkeypatch.setattr(SearchProvider, "search", lambda self, query: [])
    monkeypatch.setattr(PlacesProvider, "search", sparse_place)
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        max_discovery_queries_per_run=1,
        shuffle_discovery_order=False,
        use_common_crawl=False,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(1, storage)

    assert result["qualified"] == 1
    assert result["scored_candidates"] == 0
    assert result["research_candidates"] == 1
    business = storage.get_existing_businesses()[0]
    assert business["lead_tier"] == "research"
    assert business["status"] == "needs_research"
    call_row = storage._tab_cache["Daily Call Lists"][0]
    assert "Needs SDR discovery" in call_row["reason"]
    assert "SDR should research" in call_row["suggested_call_angle"]


def test_run_daily_can_target_contactable_leads_plus_research(monkeypatch):
    calls = {"count": 0}

    def mixed_places(self, query):
        calls["count"] += 1
        if calls["count"] == 1:
            return [
                {
                    "name": "Sparse Laser Tag",
                    "website_url": "",
                    "source_url": "https://www.openstreetmap.org/node/456",
                    "phone": "",
                    "source_id": "osm:node:456",
                    "category": "laser tag",
                }
            ]
        return [
            {
                "name": "Contactable Laser Tag",
                "website_url": "https://contactablelasertag.examplebiz.com",
                "source_url": "https://www.openstreetmap.org/node/789",
                "phone": "(404) 555-1212",
                "source_id": "osm:node:789",
                "category": "laser tag",
            }
        ]

    monkeypatch.setattr(SearchProvider, "search", lambda self, query: [])
    monkeypatch.setattr(PlacesProvider, "search", mixed_places)
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        max_discovery_queries_per_run=2,
        queries_per_vertical=2,
        shuffle_discovery_order=False,
        use_common_crawl=False,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(1, storage, target_contactable=True)

    assert result["qualified"] == 2
    assert result["contactable_qualified"] == 1
    assert result["target_mode"] == "contactable"
    assert result["research_candidates"] == 1
    call_rows = storage._tab_cache["Daily Call Lists"]
    assert call_rows[0]["lead_tier"] == "research"
    assert call_rows[1]["phone"] == "(404) 555-1212"


def test_run_daily_treats_email_only_place_as_contactable(monkeypatch):
    def email_place(self, query):
        return [
            {
                "name": "Email Laser Tag",
                "website_url": "",
                "source_url": "https://www.openstreetmap.org/node/987",
                "phone": "",
                "email": "events@emaillasertag.examplebiz.com",
                "source_id": "osm:node:987",
                "category": "laser tag",
            }
        ]

    monkeypatch.setattr(SearchProvider, "search", lambda self, query: [])
    monkeypatch.setattr(PlacesProvider, "search", email_place)
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        max_discovery_queries_per_run=1,
        shuffle_discovery_order=False,
        use_common_crawl=False,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(1, storage, target_contactable=True)

    assert result["qualified"] == 1
    assert result["contactable_qualified"] == 1
    business = storage.get_existing_businesses()[0]
    assert business["email"] == "events@emaillasertag.examplebiz.com"
    assert business["status"] == ""
    call_row = storage._tab_cache["Daily Call Lists"][0]
    assert call_row["email"] == business["email"]
    assert "Public email" in call_row["suggested_call_angle"]


def test_run_daily_uses_common_crawl_domain_intelligence(monkeypatch):
    def real_candidate(self, query):
        return [
            {
                "name": "Atlanta Family Fun Center",
                "website_url": "https://atlantafamilyfun.examplebiz.com",
                "source_url": "https://atlantafamilyfun.examplebiz.com",
                "phone": "(404) 555-1212",
                "snippet": "",
                "category": "laser tag",
            }
        ]

    def common_crawl_intel(self, domain):
        return CommonCrawlDomainIntel(
            domain=domain,
            urls=[
                f"https://{domain}/booking/birthday-parties",
                f"https://{domain}/locations/atlanta",
                f"https://{domain}/waiver",
                f"https://{domain}/fareharbor/reservations",
            ],
            booking_urls=[f"https://{domain}/booking/birthday-parties", f"https://{domain}/fareharbor/reservations"],
            location_urls=[f"https://{domain}/locations/atlanta"],
            signal_urls=[f"https://{domain}/booking/birthday-parties", f"https://{domain}/waiver", f"https://{domain}/fareharbor/reservations"],
            platforms=["FareHarbor"],
        )

    monkeypatch.setattr(SearchProvider, "search", real_candidate)
    monkeypatch.setattr(PlacesProvider, "search", lambda self, query: [])
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])
    monkeypatch.setattr(CommonCrawlProvider, "lookup_domain", common_crawl_intel)

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        common_crawl_max_domains_per_run=1,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(1, storage)

    assert result["qualified"] == 1
    assert result["common_crawl_domains"] == 1
    business = storage.get_existing_businesses()[0]
    assert business["booking_url"] == "https://atlantafamilyfun.examplebiz.com/booking/birthday-parties"
    assert business["booking_platform"] == "FareHarbor"
    assert "Common Crawl URLs: 4" in business["compliance_notes"]
    call_row = storage._tab_cache["Daily Call Lists"][0]
    assert call_row["booking_url"] == business["booking_url"]
    assert call_row["booking_platform"] == "FareHarbor"
    signal_values = {row["signal_value"] for row in storage._tab_cache["Lead Signals"]}
    assert business["booking_url"] in signal_values
    assert "FareHarbor" in signal_values


def test_run_daily_documents_homepage_booking_links(monkeypatch):
    def real_candidate(self, query):
        return [
            {
                "name": "Atlanta Family Fun Center",
                "website_url": "https://atlantafamilyfun.examplebiz.com",
                "source_url": "https://atlantafamilyfun.examplebiz.com",
                "phone": "(404) 555-1212",
                "snippet": "",
                "category": "laser tag",
            }
        ]

    def homepage_intel(self, url):
        return WebsiteIntel(
            root_url=url,
            final_url=url,
            http_status=200,
            title="Atlanta Family Fun Center",
            meta_description="Book birthday parties and reserve tickets.",
            text_excerpt="Book now for birthday parties and waivers.",
            booking_urls=[
                "https://fareharbor.com/embeds/book/atlantafamilyfun/items/",
                "https://waiver.smartwaiver.com/w/atlantafamilyfun",
            ],
            emails=["events@atlantafamilyfun.examplebiz.com"],
            social_links=[
                {"platform": "Facebook", "url": "https://www.facebook.com/atlantafamilyfun"},
                {"platform": "Instagram", "url": "https://www.instagram.com/atlantafamilyfun/"},
            ],
            platforms=["FareHarbor", "Smartwaiver"],
        )

    monkeypatch.setattr(SearchProvider, "search", real_candidate)
    monkeypatch.setattr(PlacesProvider, "search", lambda self, query: [])
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])
    monkeypatch.setattr(WebsiteCrawler, "lookup", homepage_intel)

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        use_common_crawl=False,
        max_discovery_queries_per_run=1,
    )
    storage = GoogleSheetsStorage(settings=settings)

    result = run_daily(1, storage)

    assert result["qualified"] == 1
    assert result["websites_crawled"] == 1
    business = storage.get_existing_businesses()[0]
    assert business["booking_url"] == "https://fareharbor.com/embeds/book/atlantafamilyfun/items/"
    assert business["booking_platform"] == "FareHarbor, Smartwaiver"
    assert business["email"] == "events@atlantafamilyfun.examplebiz.com"
    assert business["social_url"] == "https://www.facebook.com/atlantafamilyfun"
    assert business["social_platform"] == "Facebook"
    call_row = storage._tab_cache["Daily Call Lists"][0]
    assert call_row["email"] == business["email"]
    website_row = storage._tab_cache["Websites"][0]
    assert website_row["booking_url"] == business["booking_url"]
    assert website_row["booking_platform"] == business["booking_platform"]
    assert "https://www.instagram.com/atlantafamilyfun/" in website_row["social_urls"]
    page_urls = {row["url"] for row in storage._tab_cache["Pages"]}
    assert business["booking_url"] in page_urls
    assert "https://waiver.smartwaiver.com/w/atlantafamilyfun" in page_urls
    signal_values = {row["signal_value"] for row in storage._tab_cache["Lead Signals"]}
    assert business["booking_url"] in signal_values
    assert "FareHarbor, Smartwaiver" in signal_values
    assert business["social_url"] in signal_values


def test_run_daily_skips_recent_call_list_matches_without_dup_businesses(monkeypatch):
    def real_candidate(self, query):
        return [
            {
                "name": "Atlanta Family Fun Center",
                "website_url": "https://atlantafamilyfun.examplebiz.com",
                "source_url": "https://atlantafamilyfun.examplebiz.com",
                "phone": "(404) 555-1212",
                "snippet": "Book online birthday parties and waivers.",
                "category": "laser tag",
            }
        ]

    monkeypatch.setattr(SearchProvider, "search", real_candidate)
    monkeypatch.setattr(PlacesProvider, "search", lambda self, query: [])
    monkeypatch.setattr(DirectoryProvider, "search", lambda self, query: [])

    settings = Settings(
        google_service_account_json_path="",
        google_sheets_spreadsheet_id="",
        search_provider="duckduckgo",
        places_provider="osm",
        max_discovery_queries_per_run=1,
        use_common_crawl=False,
        max_crawl_pages_per_domain=0,
    )
    storage = GoogleSheetsStorage(settings=settings)

    first = run_daily(1, storage)
    second = run_daily(1, storage)
    third = run_daily(1, storage, include_recent=True)

    assert first["qualified"] == 1
    assert second["qualified"] == 0
    assert second["skipped_recent"] == 1
    assert third["qualified"] == 1
    assert third["new_businesses"] == 0
    assert len(storage.get_existing_businesses()) == 1
    call_list = storage._tab_cache["Daily Call Lists"]
    assert "direct business website" in call_list[0]["reason"]
    assert "birthday/group events" in call_list[0]["suggested_call_angle"]


def test_purge_placeholder_rows_is_dry_run_until_applied():
    settings = Settings(google_service_account_json_path="", google_sheets_spreadsheet_id="")
    storage = GoogleSheetsStorage(settings=settings)
    storage.append_businesses(
        [
            {"business_id": "bad", "name": "Generated Directory Listing", "website_url": "https://fake.example.com"},
            {"business_id": "good", "name": "Real Family Fun Center", "website_url": "https://realfun.test"},
        ]
    )

    preview = storage.purge_placeholder_rows(apply=False)
    assert preview["Businesses"]["removed"] == 1
    assert len(storage.get_existing_businesses()) == 2

    applied = storage.purge_placeholder_rows(apply=True)
    assert applied["Businesses"]["removed"] == 1
    assert [row["business_id"] for row in storage.get_existing_businesses()] == ["good"]
