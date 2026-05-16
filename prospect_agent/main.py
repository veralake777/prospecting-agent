from __future__ import annotations
import argparse
from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI
from prospect_agent.discovery.discovery_runner import run_daily
from prospect_agent.storage.google_sheets import GoogleSheetsStorage

app = FastAPI(title="Daily Vertical Business Prospecting Agent")
storage = GoogleSheetsStorage()

@app.get("/health")
def health(): return {"ok": True, "ts": datetime.utcnow().isoformat()}


def cli():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-sheets")
    d=sub.add_parser("run-daily"); d.add_argument("--target", type=int, default=1000)
    x=sub.add_parser("discover"); x.add_argument("--vertical"); x.add_argument("--city"); x.add_argument("--state")
    c=sub.add_parser("crawl"); c.add_argument("--domain")
    e=sub.add_parser("enrich"); e.add_argument("--business-id")
    s=sub.add_parser("score"); s.add_argument("--business-id")
    sp=sub.add_parser("suppress"); sp.add_argument("--phone", default=""); sp.add_argument("--domain", default=""); sp.add_argument("--reason", required=True)
    ex=sub.add_parser("export-daily"); ex.add_argument("--date", required=True)
    rc=sub.add_parser("recrawl-stale"); rc.add_argument("--days", type=int, default=60)
    a=p.parse_args()
    if a.cmd=="init-sheets": print(storage.init_storage())
    elif a.cmd=="run-daily": print(run_daily(a.target, storage))
    elif a.cmd=="suppress": storage.append_suppression({"suppression_id":str(uuid4()),"phone":a.phone,"domain":a.domain,"business_name":"","reason":a.reason,"source":"manual","created_at":datetime.utcnow().isoformat()}); print("ok")
    else: print("Command scaffolded")

if __name__ == "__main__":
    cli()
