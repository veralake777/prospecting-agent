from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

TAB_SCHEMAS = {
    "Businesses": ["business_id","name","normalized_name","vertical","sub_vertical","vertical_confidence","website_url","domain","phone","phone_type","email","address","city","state","postal_code","country","latitude","longitude","google_place_id","source","source_id","source_url","google_rating","google_review_count","status","lead_score","lead_tier","first_seen_at","last_seen_at","last_enriched_at","last_called_at","do_not_call","opt_out_reason","compliance_notes","created_at","updated_at"],
    "Websites": ["website_id","business_id","root_url","final_url","domain","http_status","title","meta_description","cms_detected","booking_platform","waiver_platform","pos_platform","ecommerce_platform","has_online_booking","has_parties","has_memberships","has_gift_cards","has_events","has_camps","has_leagues","has_waiver","has_email_signup","has_sms_mentions","has_multiple_locations","last_crawled_at","created_at","updated_at"],
    "Pages": ["page_id","website_id","business_id","url","path","title","meta_description","http_status","content_hash","clean_text_excerpt","page_type","created_at","updated_at"],
    "Lead Signals": ["signal_id","business_id","signal_type","signal_value","confidence","evidence_url","evidence_text","created_at"],
    "Discovery Runs": ["run_id","run_date","status","target_count","discovered_count","net_new_count","qualified_count","exported_count","started_at","finished_at","error_message"],
    "Discovery Queries": ["query_id","run_id","source","query","vertical","city","state","status","results_count","created_at"],
    "Daily Call Lists": ["list_id","run_id","list_date","rank","business_id","name","vertical","sub_vertical","phone","website_url","city","state","source_url","lead_score","lead_tier","reason","suggested_call_angle","compliance_notes","exported","created_at"],
    "Suppression List": ["suppression_id","phone","domain","business_name","reason","source","created_at"],
    "Crawl Errors": ["error_id","business_id","url","error_type","error_message","created_at"],
    "Settings": ["setting_key","setting_value","updated_at"],
}

class StorageProvider(ABC):
    @abstractmethod
    def init_storage(self): ...
    @abstractmethod
    def append_businesses(self, rows: list[dict[str, Any]]): ...
    @abstractmethod
    def update_business(self, business_id: str, patch: dict[str, Any]): ...
    @abstractmethod
    def get_existing_businesses(self) -> list[dict[str, Any]]: ...
    @abstractmethod
    def append_websites(self, rows: list[dict[str, Any]]): ...
    @abstractmethod
    def append_pages(self, rows: list[dict[str, Any]]): ...
    @abstractmethod
    def append_lead_signals(self, rows: list[dict[str, Any]]): ...
    @abstractmethod
    def create_discovery_run(self, row: dict[str, Any]) -> str: ...
    @abstractmethod
    def update_discovery_run(self, run_id: str, patch: dict[str, Any]): ...
    @abstractmethod
    def append_discovery_queries(self, rows: list[dict[str, Any]]): ...
    @abstractmethod
    def get_suppression_list(self) -> list[dict[str, Any]]: ...
    @abstractmethod
    def append_suppression(self, row: dict[str, Any]): ...
    @abstractmethod
    def append_daily_call_list(self, rows: list[dict[str, Any]]): ...
    @abstractmethod
    def get_recent_daily_call_list_business_ids(self, days: int = 90) -> set[str]: ...
    @abstractmethod
    def append_crawl_errors(self, rows: list[dict[str, Any]]): ...


class GoogleSheetsStorage(StorageProvider):
    def __init__(self):
        self._tab_cache: dict[str, list[dict[str, Any]]] = {k: [] for k in TAB_SCHEMAS}

    def init_storage(self):
        return True

    def _append(self, tab: str, rows: list[dict[str, Any]]):
        self._tab_cache[tab].extend(rows)

    def append_businesses(self, rows): self._append("Businesses", rows)
    def append_websites(self, rows): self._append("Websites", rows)
    def append_pages(self, rows):
        for r in rows:
            r["clean_text_excerpt"] = (r.get("clean_text_excerpt") or "")[:1000]
        self._append("Pages", rows)
    def append_lead_signals(self, rows): self._append("Lead Signals", rows)
    def append_discovery_queries(self, rows): self._append("Discovery Queries", rows)
    def append_daily_call_list(self, rows): self._append("Daily Call Lists", rows)
    def append_crawl_errors(self, rows): self._append("Crawl Errors", rows)
    def append_suppression(self, row): self._append("Suppression List", [row])

    def create_discovery_run(self, row):
        self._append("Discovery Runs", [row])
        return row["run_id"]

    def update_discovery_run(self, run_id, patch):
        for r in self._tab_cache["Discovery Runs"]:
            if r.get("run_id") == run_id:
                r.update(patch)
                return

    def get_existing_businesses(self): return self._tab_cache["Businesses"]
    def get_suppression_list(self): return self._tab_cache["Suppression List"]
    def update_business(self, business_id, patch):
        for r in self._tab_cache["Businesses"]:
            if r.get("business_id") == business_id:
                r.update(patch)

    def get_recent_daily_call_list_business_ids(self, days=90):
        cutoff = datetime.utcnow() - timedelta(days=days)
        out = set()
        for r in self._tab_cache["Daily Call Lists"]:
            dt = datetime.fromisoformat(str(r.get("created_at"))) if r.get("created_at") else datetime.utcnow()
            if dt >= cutoff:
                out.add(r.get("business_id", ""))
        return out


def with_backoff(func, retries: int = 4):
    for i in range(retries):
        try:
            return func()
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2**i)
