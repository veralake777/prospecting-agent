from __future__ import annotations
from datetime import datetime, date
from uuid import uuid4
from prospect_agent.discovery.query_builder import VERTICALS, build_queries
from prospect_agent.classify.vertical_classifier import classify_vertical
from prospect_agent.enrich.signal_extractor import extract_signals
from prospect_agent.enrich.platform_detector import detect_platforms
from prospect_agent.enrich.lead_scorer import score_lead
from prospect_agent.storage.google_sheets import GoogleSheetsStorage
from prospect_agent.config import PRIORITY_MARKETS


def _norm(v:str)->str: return "".join(ch.lower() for ch in v if ch.isalnum() or ch.isspace()).strip()

def run_daily(target: int = 1000, storage: GoogleSheetsStorage | None = None) -> dict:
    storage = storage or GoogleSheetsStorage()
    run_id = str(uuid4())
    storage.create_discovery_run({"run_id": run_id, "run_date": str(date.today()), "status": "running", "target_count": target, "started_at": datetime.utcnow().isoformat()})
    leads=[]
    for state,cities in PRIORITY_MARKETS.items():
        for city in cities:
            for vertical in VERTICALS:
                query = build_queries(vertical, city, state)[0]
                txt = f"{vertical} {city} {state} booking birthday membership waiver"
                c = classify_vertical(txt)
                sig = extract_signals(txt)
                plats = detect_platforms("wordpress booking")
                score,tier = score_lead(sig,{"website_url":"https://example.com","google_review_count":120,"has_known_platform":bool(plats)})
                if c["confidence"] >= 0.65 and score >= 40:
                    bid = str(uuid4())
                    leads.append({"business_id": bid,"name": f"{vertical.title()} {city}","normalized_name": _norm(f"{vertical} {city}"),"vertical": c["primary_vertical"],"sub_vertical": c["sub_vertical"],"vertical_confidence": c["confidence"],"website_url":"https://example.com","domain":"example.com","phone":"(555)555-0000","city":city,"state":state,"source":"synthetic","source_url":"https://example.com/source","google_review_count":120,"lead_score":score,"lead_tier":tier,"created_at":datetime.utcnow().isoformat(),"updated_at":datetime.utcnow().isoformat()})
                    if len(leads) >= target:
                        storage.append_businesses(leads)
                        storage.append_daily_call_list([{"list_id":str(uuid4()),"run_id":run_id,"list_date":str(date.today()),"rank":i+1,**{k:v for k,v in b.items() if k in ["business_id","name","vertical","sub_vertical","phone","website_url","city","state","source_url","lead_score","lead_tier"]},"reason":"Qualified by score and vertical","suggested_call_angle":"They offer booking and parties. Pitch lifecycle follow-up.","compliance_notes":"Public business listing.","exported":True,"created_at":datetime.utcnow().isoformat()} for i,b in enumerate(leads)])
                        storage.update_discovery_run(run_id,{"status":"completed","qualified_count":len(leads),"exported_count":len(leads),"finished_at":datetime.utcnow().isoformat()})
                        return {"run_id":run_id,"qualified":len(leads)}
                storage.append_discovery_queries([{"query_id":str(uuid4()),"run_id":run_id,"source":"synthetic","query":query,"vertical":vertical,"city":city,"state":state,"status":"ok","results_count":1,"created_at":datetime.utcnow().isoformat()}])
    return {"run_id": run_id, "qualified": len(leads)}
