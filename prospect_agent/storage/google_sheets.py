from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from prospect_agent.config import Settings

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
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._tab_cache: dict[str, list[dict[str, Any]]] = {k: [] for k in TAB_SCHEMAS}
        self._sheets = None

    def _sheet(self):
        if self._sheets is not None:
            return self._sheets
        if not self.settings.google_service_account_json_path or not self.settings.google_sheets_spreadsheet_id:
            return None
        creds = Credentials.from_service_account_file(
            str(Path(self.settings.google_service_account_json_path)),
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"],
        )
        self._sheets = build("sheets", "v4", credentials=creds).spreadsheets()
        return self._sheets

    def init_storage(self):
        if not self._sheet():
            return True
        meta = self._sheet().get(spreadsheetId=self.settings.google_sheets_spreadsheet_id).execute()
        existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
        requests = []
        for tab, headers in TAB_SCHEMAS.items():
            if tab not in existing:
                requests.append({"addSheet": {"properties": {"title": tab}}})
        if requests:
            self._sheet().batchUpdate(
                spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                body={"requests": requests},
            ).execute()
        for tab, headers in TAB_SCHEMAS.items():
            vals = self._sheet().values().get(spreadsheetId=self.settings.google_sheets_spreadsheet_id, range=f"'{tab}'!1:1").execute().get("values", [])
            if not vals:
                self._sheet().values().update(
                    spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                    range=f"'{tab}'!A1",
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ).execute()
        return True

    def _append(self, tab: str, rows: list[dict[str, Any]]):
        if not rows:
            return
        headers = TAB_SCHEMAS.get(tab, list(rows[0].keys()))
        self._tab_cache.setdefault(tab, []).extend(rows)
        if not self._sheet():
            return
        values = [[r.get(h, "") for h in headers] for r in rows]
        with_backoff(lambda: self._sheet().values().append(
            spreadsheetId=self.settings.google_sheets_spreadsheet_id,
            range=f"'{tab}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute())

    def _read_tab(self, tab: str) -> list[dict[str, Any]]:
        if not self._sheet():
            return self._tab_cache.get(tab, [])
        vals = self._sheet().values().get(spreadsheetId=self.settings.google_sheets_spreadsheet_id, range=f"'{tab}'!A:ZZ").execute().get("values", [])
        if not vals:
            return []
        headers, data = vals[0], vals[1:]
        rows = [{h: row[i] if i < len(row) else "" for i, h in enumerate(headers)} for row in data]
        self._tab_cache[tab] = rows
        return rows

    def append_businesses(self, rows): self._append("Businesses", rows)
    def append_websites(self, rows): self._append("Websites", rows)
    def append_pages(self, rows):
        for r in rows:
            r["clean_text_excerpt"] = (r.get("clean_text_excerpt") or "")[:1000]
        self._append("Pages", rows)
    def append_lead_signals(self, rows): self._append("Lead Signals", rows)
    def append_discovery_queries(self, rows): self._append("Discovery Queries", rows)
    def append_daily_call_list(self, rows):
        self._append("Daily Call Lists", rows)
        if rows:
            date_tab = f"Daily Call List {rows[0].get('list_date', datetime.utcnow().date().isoformat())}"
            if self._sheet():
                try:
                    self._sheet().batchUpdate(spreadsheetId=self.settings.google_sheets_spreadsheet_id, body={"requests": [{"addSheet": {"properties": {"title": date_tab}}}]}).execute()
                    self._sheet().values().update(spreadsheetId=self.settings.google_sheets_spreadsheet_id, range=f"'{date_tab}'!A1", valueInputOption="RAW", body={"values": [TAB_SCHEMAS["Daily Call Lists"]]}).execute()
                except Exception:
                    pass
            self._append(date_tab, rows)
    def append_crawl_errors(self, rows): self._append("Crawl Errors", rows)
    def append_suppression(self, row): self._append("Suppression List", [row])

    def create_discovery_run(self, row):
        self._append("Discovery Runs", [row])
        return row["run_id"]

    def update_discovery_run(self, run_id, patch):
        for r in self._read_tab("Discovery Runs"):
            if r.get("run_id") == run_id:
                r.update(patch)

    def get_existing_businesses(self): return self._read_tab("Businesses")
    def get_suppression_list(self): return self._read_tab("Suppression List")
    def update_business(self, business_id, patch):
        for r in self._read_tab("Businesses"):
            if r.get("business_id") == business_id:
                r.update(patch)

    def get_recent_daily_call_list_business_ids(self, days=90):
        cutoff = datetime.utcnow() - timedelta(days=days)
        out = set()
        for r in self._read_tab("Daily Call Lists"):
            dt = datetime.fromisoformat(str(r.get("created_at"))) if r.get("created_at") else datetime.utcnow()
            if dt >= cutoff and r.get("business_id"):
                out.add(r["business_id"])
        return out


def with_backoff(func, retries: int = 4):
    for i in range(retries):
        try:
            return func()
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2**i)
