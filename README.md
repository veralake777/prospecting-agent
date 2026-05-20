# Daily Vertical Business Prospecting Agent

Production-oriented Python/FastAPI + Google Sheets prospecting system that discovers, classifies, enriches, dedupes, scores, suppresses, and exports daily human-callable business leads.

## Setup
1. Create a Google Cloud project.
2. Enable **Google Sheets API**.
3. Enable **Google Drive API** (for spreadsheet creation if needed).
4. Optional for stronger discovery: enable **Places API (New)** and create a Google Maps Platform API key.
5. Create a service account.
6. Download service account JSON.
7. Share your target Google Sheet with the service account email.
   - Current configured service account: `codex-prospecting-agent@prospecting-agent-496419.iam.gserviceaccount.com` (Editor access confirmed).
8. Copy `.env.example` to `.env` and fill credentials.

## Initialize sheet tabs
```bash
python -m prospect_agent.main init-sheets
```

## Run daily
```bash
python -m prospect_agent.main run-daily --target 1000
```

## How to use this project (quickstart)
1. **Install dependencies**
   ```bash
   pip install -e .
   ```
   Or with requirements file:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Then set:
   - `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` to your service-account JSON path.
   - `GOOGLE_SHEETS_SPREADSHEET_ID` to your target sheet ID.
   - `SEARCH_PROVIDER=duckduckgo` for free organic business-site discovery.
   - `PLACES_PROVIDER=osm` for free OpenStreetMap/Nominatim place discovery.
   - To use Google Places instead, set `FREE_MODE=false`, `PLACES_PROVIDER=google`, and `PLACES_API_KEY`.
   - `GOOGLE_PLACES_MAX_TEXT_SEARCHES_PER_RUN=180`, `GOOGLE_PLACES_MAX_DETAILS_PER_RUN=35`, and `GOOGLE_PLACES_TEXT_SEARCH_PAGE_SIZE=3` are the default cost guards for five weekday runs.
   - `MAX_DISCOVERY_QUERIES_PER_RUN` controls how many market/vertical queries one run will try before returning partial results.
   - `SHUFFLE_DISCOVERY_ORDER=true` spreads small runs across different markets/verticals instead of always starting with Atlanta.
   - `DISCOVERY_SEED=` can be set when you want a repeatable query order for smoke tests; blank means the current date is used.
   - `QUERIES_PER_VERTICAL=2` controls how many query variants are attempted for each city/vertical pair.
   - `RECENT_CALL_LIST_DAYS=90` prevents the same business from being exported again during the cooldown window.
   - `USE_COMMON_CRAWL=true` enriches discovered domains with URL/subdomain intelligence from the Common Crawl CDXJ index.
   - `MAX_CRAWL_PAGES_PER_DOMAIN` controls how many booking-like links are captured from each business homepage; set it to `0` to disable live homepage crawling.
   - `OSM_SEARCH_RADIUS_METERS=80000` controls the OpenStreetMap radius around each priority city.
3. **Initialize required tabs/headers in Google Sheets**
   ```bash
   python -m prospect_agent.main init-sheets
   ```
4. **Run a small smoke test**
   ```bash
   python -m prospect_agent.main run-daily --target 25 --max-queries 25 --timeout 4
   ```
5. **Run full daily build**
   ```bash
   python -m prospect_agent.main run-daily --target 1000
   ```
6. **Schedule unattended runs at 7:00 AM ET**
   ```bash
   python -m prospect_agent.main schedule-daily
   ```
   This uses `RUN_TIME_LOCAL` and `RUN_TIMEZONE` from `.env`.

### Expected output locations in Sheets
- Core master tab: `Daily Call Lists`
- Dated run tab (created per run date): `Daily Call List YYYY-MM-DD`
- Booking evidence columns: `booking_url`, `booking_platform`, and `evidence_url` are written to `Businesses` and daily call-list tabs.
- Social contact columns: `social_url` and `social_platform` are written to `Businesses` and daily call-list tabs when the homepage crawl finds a public social profile.
- Booking-page documentation: `Websites` stores crawl-level metadata, `Pages` stores each discovered booking/waiver/ticket/reservation URL, and `Lead Signals` stores `booking_page`, `booking_platform`, and `social_profile` evidence rows.
- Other required tabs are initialized by `init-sheets`.

### Operational notes
- The system is configured for free-compatible operation by default (`FREE_MODE=true`).
- `stub` and `manual` providers are dry modes and do not generate fake lead rows.
- Directory/listing domains and `.example.*` placeholder URLs are rejected before leads are written.
- `run-daily` prints discovery progress to stderr and stops at `MAX_DISCOVERY_QUERIES_PER_RUN` instead of scanning indefinitely.
- You can override those controls per run with `--max-queries`, `--queries-per-vertical`, `--seed`, `--listed-order`, `--timeout`, `--recent-days`, `--include-recent`, `--no-progress`, and `--json`.
- `run-daily` prints a human-readable summary by default; use `--json` for raw machine-readable output.
- Back-to-back runs usually return fewer or zero leads because businesses already exported to `Daily Call Lists` are skipped for `RECENT_CALL_LIST_DAYS`.
- For smoke tests, use `--include-recent` when you want to validate discovery without the 90-day cooldown hiding businesses that were already exported.
- Verified place-source candidates in the target vertical can still be listed when phone, website, or social links are missing; those rows are marked `lead_tier=research` / `status=needs_research` so SDRs can do contact discovery.
- Common Crawl enrichment is capped by `COMMON_CRAWL_MAX_DOMAINS_PER_RUN` and `COMMON_CRAWL_MAX_URLS_PER_DOMAIN`; keep the domain cap low for smoke tests.
- Homepage crawling is intentionally shallow: it fetches the business homepage, extracts booking/reservation/waiver/event/ticket links and public social profiles, then detects integrations such as FareHarbor, Roller, Xola, Checkfront, Smartwaiver, Rock Gym Pro, and similar platforms from URLs and page HTML.
- Free OpenStreetMap discovery depends on how businesses are tagged in OSM; major cities can still return sparse results for categories like laser tag, golf simulators, or go-karts if those venues are not tagged with matching OSM leisure/sport values.
- If credentials are missing, storage falls back to in-memory behavior for local development.
- Use `suppress` command to add phone/domain suppression records before future runs.

## Google Places discovery
Google Places is the recommended paid-but-guarded provider when OSM and free search are too sparse.

```env
FREE_MODE=false
PLACES_PROVIDER=google
PLACES_API_KEY=your-google-maps-platform-api-key
GOOGLE_PLACES_MAX_TEXT_SEARCHES_PER_RUN=180
GOOGLE_PLACES_MAX_DETAILS_PER_RUN=35
GOOGLE_PLACES_TEXT_SEARCH_PAGE_SIZE=3
```

The provider uses Places API (New) with field masks:
- Text Search returns basic candidate data only: place ID, name, address, location, types, and Google Maps URL.
- Place Details is used only for capped candidates to fetch phone, website, Google rating, and Google review count.
- The caps are per process/run and stop additional Google calls even if `--max-queries` is higher.

### Google Places pricing notes
As of May 2026, Google lists these relevant Places API (New) tiers:

| SKU | Free monthly cap | Price after free cap |
| --- | ---: | ---: |
| Place Details Essentials (IDs Only) | Unlimited | Free |
| Text Search Essentials (IDs Only) | Unlimited | Free |
| Place Details Essentials | 10,000 | $5 / 1,000 |
| Text Search Pro | 5,000 | $32 / 1,000 |
| Place Details Pro | 5,000 | $17 / 1,000 |
| Text Search Enterprise | 1,000 | $35 / 1,000 |
| Place Details Enterprise | 1,000 | $20 / 1,000 |

Phone number, website URL, rating, and review count are Enterprise fields in Places API (New), so the app avoids requesting them in Text Search and only requests them through capped Place Details calls. Full review text and AI review summaries are not requested by default.

### Recommended free-tier limits
For five weekday runs, assume about 22 runs per month. These settings stay below the relevant free monthly caps with room for manual smoke tests:

| Setting | Recommended | Approx monthly usage at 22 runs |
| --- | ---: | ---: |
| `GOOGLE_PLACES_MAX_TEXT_SEARCHES_PER_RUN` | `180` | `3,960` of `5,000` Text Search Pro calls |
| `GOOGLE_PLACES_MAX_DETAILS_PER_RUN` | `35` | `770` of `1,000` Place Details Enterprise calls |
| `GOOGLE_PLACES_TEXT_SEARCH_PAGE_SIZE` | `3` | Limits raw candidates/details pressure |

Suggested daily command:

```bash
python -m prospect_agent.main run-daily --target 25 --max-queries 180 --queries-per-vertical 1
```

If you run more than five days per week, lower those caps or expect paid usage.

## Additional commands
- `python -m prospect_agent.main discover --vertical climbing_gym --city Atlanta --state GA`
- `python -m prospect_agent.main crawl --domain example.com`
- `python -m prospect_agent.main enrich --business-id UUID`
- `python -m prospect_agent.main score --business-id UUID`
- `python -m prospect_agent.main suppress --phone "555-555-5555" --reason "Opted out"`
- `python -m prospect_agent.main suppress --domain "example.com" --reason "Do not contact"`
- `python -m prospect_agent.main purge-placeholder-leads` to preview removal of generated placeholder rows.
- `python -m prospect_agent.main purge-placeholder-leads --apply` to remove generated placeholder rows from Businesses and Daily Call Lists.
- `python -m prospect_agent.main export-daily --date YYYY-MM-DD`
- `python -m prospect_agent.main recrawl-stale --days 60`

## Extensibility
- Add verticals in `prospect_agent/discovery/query_builder.py` and `prospect_agent/classify/vertical_classifier.py`.
- Add search providers in `prospect_agent/providers/`.
- Storage interface in `prospect_agent/storage/google_sheets.py` allows future swap to DB storage.

## Google Sheets limits
Google Sheets is good for MVP scale but has API quota and practical row-size limits. Use batch writes, cache rows, store excerpts only, and consider migration to a database for larger volume/analytics.
