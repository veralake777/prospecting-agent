from __future__ import annotations

from datetime import datetime, date
from uuid import uuid4
from pydantic import BaseModel, Field


def uuid_str() -> str:
    return str(uuid4())


class Business(BaseModel):
    business_id: str = Field(default_factory=uuid_str)
    name: str
    normalized_name: str = ""
    vertical: str = "unknown"
    sub_vertical: str = ""
    vertical_confidence: float = 0.0
    website_url: str = ""
    domain: str = ""
    phone: str = ""
    email: str = ""
    city: str = ""
    state: str = ""
    google_place_id: str = ""
    source: str = ""
    source_url: str = ""
    google_review_count: int = 0
    do_not_call: bool = False
    lead_score: int = 0
    lead_tier: str = "low_priority"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DiscoveryRun(BaseModel):
    run_id: str = Field(default_factory=uuid_str)
    run_date: date = Field(default_factory=date.today)
    status: str = "running"
    target_count: int = 1000
    discovered_count: int = 0
    net_new_count: int = 0
    qualified_count: int = 0
    exported_count: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    error_message: str = ""
