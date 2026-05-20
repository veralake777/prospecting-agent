from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI

from prospect_agent.config import Settings
from prospect_agent.discovery.discovery_runner import run_daily
from prospect_agent.storage.google_sheets import GoogleSheetsConfigurationError, GoogleSheetsStorage

app = FastAPI(title="Daily Vertical Business Prospecting Agent")
settings = Settings()
storage = GoogleSheetsStorage(settings=settings)


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


def _enforce_free_mode() -> None:
    if not settings.free_mode:
        return
    free_search = {"", "stub", "manual", "free", "duckduckgo", "ddg"}
    free_places = {"", "stub", "manual", "free", "osm", "openstreetmap"}
    if settings.search_provider.strip().lower() not in free_search:
        raise ValueError("FREE_MODE blocks non-free search provider")
    if settings.places_provider.strip().lower() not in free_places:
        raise ValueError("FREE_MODE blocks non-free places provider")


def _schedule_daily() -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'apscheduler'. Install project dependencies (e.g., `pip install -e .`) "
            "or `pip install apscheduler` before using schedule-daily."
        ) from exc
    hour, minute = settings.run_time_local.split(":")
    scheduler = BlockingScheduler(timezone=settings.run_timezone)
    scheduler.add_job(lambda: run_daily(settings.daily_target_leads, storage), "cron", hour=int(hour), minute=int(minute), id="run_daily")
    print(f"Scheduled daily run at {settings.run_time_local} {settings.run_timezone}")
    scheduler.start()


def _format_run_daily_result(result: dict) -> str:
    source_counts = result.get("source_result_counts") or {}
    usable_counts = result.get("source_usable_counts") or {}
    lines = [
        "Daily discovery complete",
        f"Run ID: {result.get('run_id', '')}",
        "",
        "Leads",
        f"- Qualified for call list: {result.get('qualified', 0)}",
        f"- New businesses added: {result.get('new_businesses', 0)}",
        f"- Existing businesses matched: {result.get('matched_existing', 0)}",
        f"- Skipped by {result.get('recent_days', 0)}-day cooldown: {result.get('skipped_recent', 0)}",
        f"- Cooldown bypassed: {'yes' if result.get('include_recent') else 'no'}",
        "",
        "Discovery",
        f"- Queries attempted: {result.get('queries_attempted', 0)}",
        f"- Markets attempted: {result.get('markets_attempted', 0)}",
        f"- Discovery seed: {result.get('discovery_seed', '')}",
        "",
        "Candidate Funnel",
        f"- Raw candidates seen: {result.get('candidates_seen', 0)}",
        f"- Usable candidates: {result.get('usable_candidates', 0)}",
        f"- Classified candidates: {result.get('classified_candidates', 0)}",
        f"- Scored candidates: {result.get('scored_candidates', 0)}",
        f"- Research candidates: {result.get('research_candidates', 0)}",
        f"- Suppressed candidates: {result.get('suppressed_candidates', 0)}",
        "",
        "Sources",
        f"- Search: {source_counts.get('search', 0)} raw / {usable_counts.get('search', 0)} usable",
        f"- Places: {source_counts.get('places', 0)} raw / {usable_counts.get('places', 0)} usable",
        f"- Directory: {source_counts.get('directory', 0)} raw / {usable_counts.get('directory', 0)} usable",
        "",
        "Enrichment",
        f"- Common Crawl domains checked: {result.get('common_crawl_domains', 0)}",
        f"- Websites crawled: {result.get('websites_crawled', 0)}",
    ]
    if result.get("stopped_reason"):
        lines.extend(["", f"Note: {result['stopped_reason']}"])
    return "\n".join(lines)


def cli():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-sheets")
    d = sub.add_parser("run-daily")
    d.add_argument("--target", type=int, default=1000)
    d.add_argument("--max-queries", type=int)
    d.add_argument("--queries-per-vertical", type=int)
    d.add_argument("--seed", help="Override the daily discovery shuffle seed for repeatable smoke tests.")
    d.add_argument("--listed-order", action="store_true", help="Use the static market order instead of daily shuffling.")
    d.add_argument("--timeout", type=float)
    d.add_argument("--recent-days", type=int)
    d.add_argument("--include-recent", action="store_true")
    d.add_argument("--no-progress", action="store_true")
    d.add_argument("--json", action="store_true", help="Print raw JSON output instead of the human-readable summary.")
    sub.add_parser("schedule-daily")
    x = sub.add_parser("discover")
    x.add_argument("--vertical")
    x.add_argument("--city")
    x.add_argument("--state")
    c = sub.add_parser("crawl")
    c.add_argument("--domain")
    e = sub.add_parser("enrich")
    e.add_argument("--business-id")
    s = sub.add_parser("score")
    s.add_argument("--business-id")
    sp = sub.add_parser("suppress")
    sp.add_argument("--phone", default="")
    sp.add_argument("--domain", default="")
    sp.add_argument("--reason", required=True)
    purge = sub.add_parser("purge-placeholder-leads")
    purge.add_argument("--apply", action="store_true")
    ex = sub.add_parser("export-daily")
    ex.add_argument("--date", required=True)
    rc = sub.add_parser("recrawl-stale")
    rc.add_argument("--days", type=int, default=60)
    a = p.parse_args()

    try:
        _enforce_free_mode()
        if a.cmd == "init-sheets":
            storage.init_storage()
            print("Google Sheets storage initialized.")
        elif a.cmd == "run-daily":
            if a.max_queries is not None:
                settings.max_discovery_queries_per_run = a.max_queries
            if a.queries_per_vertical is not None:
                settings.queries_per_vertical = a.queries_per_vertical
            if a.seed:
                settings.discovery_seed = a.seed
            if a.listed_order:
                settings.shuffle_discovery_order = False
            if a.timeout is not None:
                settings.discovery_http_timeout_seconds = a.timeout
            progress = None if a.no_progress else lambda message: print(message, file=sys.stderr, flush=True)
            result = run_daily(a.target, storage, progress=progress, recent_days=a.recent_days, include_recent=a.include_recent)
            print(json.dumps(result, indent=2) if a.json else _format_run_daily_result(result))
        elif a.cmd == "schedule-daily":
            _schedule_daily()
        elif a.cmd == "suppress":
            storage.append_suppression({"suppression_id": str(uuid4()), "phone": a.phone, "domain": a.domain, "business_name": "", "reason": a.reason, "source": "manual", "created_at": datetime.utcnow().isoformat()})
            print("ok")
        elif a.cmd == "purge-placeholder-leads":
            stats = storage.purge_placeholder_rows(apply=a.apply)
            action = "removed" if a.apply else "would remove"
            print({"action": action, "tabs": stats})
        else:
            print("Command scaffolded")
    except GoogleSheetsConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()
