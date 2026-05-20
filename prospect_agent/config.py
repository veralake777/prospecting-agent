from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    google_service_account_json_path: str = Field(default="")
    google_sheets_spreadsheet_id: str = Field(default="")
    google_drive_folder_id: str = Field(default="")
    search_provider: str = Field(default="stub")
    search_api_key: str = Field(default="")
    places_provider: str = Field(default="stub")
    places_api_key: str = Field(default="")
    google_places_max_text_searches_per_run: int = Field(default=180)
    google_places_max_details_per_run: int = Field(default=35)
    google_places_text_search_page_size: int = Field(default=3)
    openai_api_key: str = Field(default="")
    free_mode: bool = Field(default=True)
    use_llm_classifier: bool = Field(default=False)
    daily_target_leads: int = Field(default=1000)
    recent_call_list_days: int = Field(default=90)
    max_discovery_queries_per_run: int = Field(default=25)
    queries_per_vertical: int = Field(default=2)
    shuffle_discovery_order: bool = Field(default=True)
    discovery_seed: str = Field(default="")
    discovery_http_timeout_seconds: float = Field(default=4.0)
    progress_interval_queries: int = Field(default=1)
    use_common_crawl: bool = Field(default=True)
    common_crawl_index: str = Field(default="")
    common_crawl_max_urls_per_domain: int = Field(default=25)
    common_crawl_max_domains_per_run: int = Field(default=3)
    max_crawl_pages_per_domain: int = Field(default=20)
    osm_search_radius_meters: int = Field(default=80000)
    user_agent: str = Field(default='VeraLakeProspectBot/1.0 (+business research; contact: veralake@gmail.com)')
    default_country: str = Field(default="US")
    export_csv: bool = Field(default=False)
    run_time_local: str = Field(default="07:00")
    run_timezone: str = Field(default="America/New_York")

    data_dir: Path = Field(default=Path("data"))


PRIORITY_MARKETS = {
    "GA": ["Atlanta", "Savannah", "Augusta", "Athens", "Marietta"],
    "FL": ["Orlando", "Tampa", "Miami", "Jacksonville", "Fort Lauderdale"],
    "TX": ["Houston", "Dallas", "Austin", "San Antonio", "Fort Worth"],
    "NC": ["Charlotte", "Raleigh", "Durham", "Greensboro", "Wilmington"],
    "SC": ["Charleston", "Columbia", "Greenville", "Myrtle Beach", "Spartanburg"],
    "TN": ["Nashville", "Memphis", "Knoxville", "Chattanooga", "Franklin"],
    "AL": ["Birmingham", "Huntsville", "Montgomery", "Mobile", "Tuscaloosa"],
    "AZ": ["Phoenix", "Scottsdale", "Tucson", "Mesa", "Tempe"],
    "CO": ["Denver", "Colorado Springs", "Boulder", "Aurora", "Fort Collins"],
    "CA": ["Los Angeles", "San Diego", "San Jose", "Sacramento", "Anaheim"],
    "NY": ["New York", "Buffalo", "Rochester", "Albany", "Syracuse"],
    "NJ": ["Newark", "Jersey City", "Paterson", "Edison", "Trenton"],
    "PA": ["Philadelphia", "Pittsburgh", "Allentown", "Harrisburg", "Erie"],
    "OH": ["Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron"],
    "IL": ["Chicago", "Aurora", "Naperville", "Peoria", "Rockford"],
}
