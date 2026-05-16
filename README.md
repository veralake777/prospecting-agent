# Daily Vertical Business Prospecting Agent

Production-oriented Python/FastAPI + Google Sheets prospecting system that discovers, classifies, enriches, dedupes, scores, suppresses, and exports daily human-callable business leads.

## Setup
1. Create a Google Cloud project.
2. Enable **Google Sheets API**.
3. Enable **Google Drive API** (for spreadsheet creation if needed).
4. Create a service account.
5. Download service account JSON.
6. Share your target Google Sheet with the service account email.
   - Current configured service account: `codex-prospecting-agent@prospecting-agent-496419.iam.gserviceaccount.com` (Editor access confirmed).
7. Copy `.env.example` to `.env` and fill credentials.

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
3. **Initialize required tabs/headers in Google Sheets**
   ```bash
   python -m prospect_agent.main init-sheets
   ```
4. **Run a small smoke test**
   ```bash
   python -m prospect_agent.main run-daily --target 25
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
- Other required tabs are initialized by `init-sheets`.

### Operational notes
- The system is configured for free-compatible operation by default (`FREE_MODE=true`).
- If credentials are missing, storage falls back to in-memory behavior for local development.
- Use `suppress` command to add phone/domain suppression records before future runs.

## Additional commands
- `python -m prospect_agent.main discover --vertical climbing_gym --city Atlanta --state GA`
- `python -m prospect_agent.main crawl --domain example.com`
- `python -m prospect_agent.main enrich --business-id UUID`
- `python -m prospect_agent.main score --business-id UUID`
- `python -m prospect_agent.main suppress --phone "555-555-5555" --reason "Opted out"`
- `python -m prospect_agent.main suppress --domain "example.com" --reason "Do not contact"`
- `python -m prospect_agent.main export-daily --date YYYY-MM-DD`
- `python -m prospect_agent.main recrawl-stale --days 60`

## Extensibility
- Add verticals in `prospect_agent/discovery/query_builder.py` and `prospect_agent/classify/vertical_classifier.py`.
- Add search providers in `prospect_agent/providers/`.
- Storage interface in `prospect_agent/storage/google_sheets.py` allows future swap to DB storage.

## Google Sheets limits
Google Sheets is good for MVP scale but has API quota and practical row-size limits. Use batch writes, cache rows, store excerpts only, and consider migration to a database for larger volume/analytics.
