# 01 — Repository Audit (Kiên)

> **Audit date:** 2026-09-14  
> **Auditor:** Kiên (Senior Backend/Data Engineer)  
> **Project root:** `D:\Kien\hackathon\web_extract_project\web-extract-agent`  
> **Repository:** READ-ONLY audit — no source code modified.

---

## 1. Current Architecture

### Overview

The project is a **Web Data Extraction & Management Platform** — a hackathon competition project that allows non-technical users to configure web scraping via natural language field descriptions. The system crawls websites, uses AI to extract structured data, and stores results in either SQLite (DB mode) or JSON files (file mode).

### Tech Stack (confirmed from `requirements.txt` + `CLAUDE.md`)

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | FastAPI | 0.141.1 |
| Frontend (MVP) | Streamlit | 1.63.0 |
| Scheduler | APScheduler | 3.11.3 |
| Database | SQLite (stdlib `sqlite3`) | — |
| Scraping (static) | httpx | 0.28.1 |
| Scraping (JS-heavy) | Playwright | 1.62.0 |
| HTML parsing | BeautifulSoup4 | 4.15.0 |
| Validation | Pydantic | 2.13.5 |
| Test | pytest + pytest-mock | 9.1.1 / 3.15.1 |
| Python | 3.12.14 | `.python-version` |

### Architecture Pattern

- **Adapter pattern** for all external components: `FetchEngine`, `AIClient`, `StorageEngine` — each has an abstract base + concrete implementation + test double capability.
- **Dependency injection** via `create_app(fetcher, ai_client, storage, scheduler)` — enables testing without real services.
- **No ORM** — raw `sqlite3` with hand-written SQL. No SQLAlchemy, no Tortoise, no SQLModel.
- **No migration framework** — manual `_migrate_columns()` via `ALTER TABLE ADD COLUMN` in `sqlite_storage.py`.
- **Dynamic schema via JSON** — field data stored in `records.data` as JSON text, NOT in separate SQL columns per job.

### High-Level Data Flow

```
User (Streamlit UI)
  │
  ▼ HTTP
FastAPI Backend (src/api/main.py)
  │
  ├── POST /crawl ──────► pipeline.run_crawl_job() / run_file_crawl_job()
  │                          │
  │                          ├── fetch_and_clean()
  │                          │     ├── FetchEngine.fetch()     (httpx / Playwright)
  │                          │     ├── robots.txt check        (HttpRobotsChecker)
  │                          │     ├── rate-limit              (DomainRateLimiter)
  │                          │     └── clean_html()            (BeautifulSoup → Markdown)
  │                          │
  │                          ├── ai_extract()
  │                          │     ├── extract_structured_data() (JSON-LD / Open Graph)
  │                          │     ├── apply_selector()          (cached CSS selector)
  │                          │     └── AIClient.extract()        (GreenNode MaaS / Qwen/GLM)
  │                          │
  │                          └── StorageEngine.save_record()  (SQLite) OR write_record() (JSON file)
  │
  ├── POST /schedules ──► CrawlScheduler.add_job()
  │                          ├── StorageEngine.create_scheduled_job()
  │                          └── APScheduler.add_job()
  │
  ├── GET /datasets ────► StorageEngine.list_datasets()
  ├── GET /datasets/{id}/records ──► StorageEngine.list_records()
  ├── GET /exports/{path} ──► FileResponse (download JSON)
  └── /admin/* ─────────► AI debug assistant (suggest-fix, read-only)
```

---

## 2. Important Folder Structure

```
web-extract-agent/
├── src/
│   ├── ai/                    # AI client (GreenNode MaaS) + debug assistant
│   │   ├── base.py            # AIClient ABC, FieldExtraction, ExtractionResult
│   │   ├── greennode_client.py# GreenNodeChatClient — OpenAI-compatible endpoint
│   │   └── debug_assistant.py # suggest_fix() — admin panel AI (separate from extract)
│   ├── api/                   # FastAPI routes
│   │   ├── main.py            # create_app(), /crawl, /datasets, /schedules, /exports, /health
│   │   └── admin.py           # /admin/errors, /admin/errors/{id}/suggest-fix
│   ├── clean/                 # HTML cleaning
│   │   └── html_cleaner.py    # clean_html() → CleanedDocument (Markdown)
│   ├── extract/               # Structured data extraction + selector caching
│   │   ├── structured_data.py # JSON-LD + Open Graph extraction, field synonym matching
│   │   └── selector_finder.py # CSS selector generation + application (cache strategy)
│   ├── fetch/                 # Fetch engines + compliance
│   │   ├── base.py            # FetchEngine ABC, FetchResult, RobotsChecker ABC
│   │   ├── httpx_fetcher.py   # HttpxFetcher — static sites
│   │   ├── playwright_fetcher.py # PlaywrightFetcher — JS-heavy sites
│   │   ├── rate_limiter.py    # DomainRateLimiter — per-domain delay
│   │   └── robots.py          # HttpRobotsChecker — robots.txt fetch + cache + parse
│   ├── storage/               # Storage layer
│   │   ├── base.py            # StorageEngine ABC + all dataclasses (Dataset, Record, etc.)
│   │   ├── sqlite_storage.py  # SQLiteStorage — concrete implementation
│   │   └── file_writer.py     # JSON file writer (append/new_file/overwrite_row)
│   ├── config.py              # Settings dataclass + load_settings() from .env
│   ├── pipeline.py            # run_crawl_job() + run_file_crawl_job() + ai_extract()
│   └── scheduler.py           # CrawlScheduler — APScheduler wrapper
├── ui/                        # Streamlit frontend
│   ├── app.py                 # 5-step UI (source → fields → run → data → schedule)
│   ├── pages/
│   │   └── 9_Admin_Debug.py   # Admin debug panel (AI suggest-fix)
│   └── README.md
├── tests/                     # pytest tests (mirror src/ structure)
│   ├── ai/                    # test_greennode_client.py, test_debug_assistant.py
│   ├── api/                   # test_main.py, test_admin.py
│   ├── clean/                 # test_html_cleaner.py
│   ├── extract/               # test_selector_finder.py, test_structured_data.py
│   ├── fetch/                 # test_httpx_fetcher.py, test_playwright_fetcher.py, etc.
│   ├── storage/               # test_file_writer.py, test_sqlite_storage.py
│   ├── test_config.py
│   ├── test_pipeline.py
│   └── test_scheduler.py
├── deploy/                    # Deployment configs
│   ├── nginx-ui.conf          # nginx reverse proxy for Streamlit + /health
│   └── start-ui.sh            # Streamlit + nginx startup script
├── .claude/                   # Claude Code settings
│   └── settings.json
├── .env.example               # Environment variable template
├── .gitignore
├── .python-version            # 3.12.14
├── CHANGELOG.md
├── CLAUDE.md                  # Architecture principles + conventions
├── conftest.py                # pytest path fixup
├── docker-compose.yml         # Dev/test local (API + UI)
├── Dockerfile                 # Original single-container (port 8000)
├── Dockerfile.api             # GreenNode AgentBase API runtime (port 8080)
├── Dockerfile.ui              # GreenNode AgentBase UI runtime (port 8080 via nginx)
├── README.md
└── requirements.txt           # Pinned dependencies (pip freeze)
```

---

## 3. Backend Structure

### Entry Point

- **`src/api/main.py:310`** — `app = _build_default_app()` — module-level instance for `uvicorn src.api.main:app`.
- **`src/api/main.py:285`** — `_build_default_app()` — loads `Settings`, constructs `HttpxFetcher`, `GreenNodeChatClient`, `SQLiteStorage`, calls `create_app()`.
- **`src/api/main.py:103`** — `create_app(fetcher, ai_client, storage, scheduler, ...)` — factory with DI; all routes defined inside closure.

### Pipeline (core business logic)

- **`src/pipeline.py:158`** — `run_crawl_job()` — DB storage flow: dataset creation/schema-match → fetch → extract → dedup (content_hash) → save_record.
- **`src/pipeline.py:234`** — `run_file_crawl_job()` — File storage flow: fetch → extract → write_record (no dedup, no dataset).
- **`src/pipeline.py:88`** — `ai_extract()` — Shared extraction logic: structured data → cached selector → AI fallback. Used by both flows.
- **`src/pipeline.py:75`** — `fetch_and_clean()` — Shared fetch + HTML cleaning. Returns `FetchAndClean` dataclass.

### Scheduler

- **`src/scheduler.py:28`** — `CrawlScheduler` — wraps APScheduler `BackgroundScheduler`. Persists jobs in `scheduled_jobs` table (survives restart). Calls `run_crawl_job()` or `run_file_crawl_job()` based on `storage_mode`.

### Config

- **`src/config.py:12`** — `Settings` frozen dataclass. Loaded from `.env` via `python-dotenv`. All env vars documented in `.env.example`.

---

## 4. Database Structure

### ORM/Library

- **No ORM.** Raw `sqlite3` module from Python stdlib.
- **`src/storage/sqlite_storage.py:113`** — `SQLiteStorage(StorageEngine)` — concrete implementation.
- Uses `sqlite3.connect(db_path, check_same_thread=False)` — single shared connection, thread-safe=False flag set for multi-thread access (APScheduler runs in background thread).

### Abstract Interface

- **`src/storage/base.py:119`** — `StorageEngine(ABC)` — defines all storage operations as abstract methods.

### Tables (from `src/storage/sqlite_storage.py:23-85`)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `datasets` | 1 dataset = 1 schema shape | `dataset_id` (PK, UUID hex), `dataset_name`, `schema_signature` (JSON array of field names), `created_at` |
| `dataset_sources` | URL sources per dataset (audit trail) | `dataset_id` (FK), `source_url`, `active` (int 0/1), `added_at` |
| `records` | Actual scraped data records | `record_id` (PK, UUID hex), `dataset_id` (FK), `source_url`, `data` (JSON text), `content_hash` (SHA256), `evidence` (JSON text), `confidence` (REAL), `needs_review` (int 0/1), `crawled_at`, `as_of` |
| `extraction_strategies` | Cached CSS selectors per (domain, field) | `domain`, `field_name` (composite PK), `selector`, `sample_value`, `updated_at` |
| `scheduled_jobs` | APScheduler job persistence | `job_id` (PK, UUID hex), `dataset_id` (FK, nullable), `url`, `field_descriptions` (JSON), `storage_mode`, `file_path`, `write_mode`, `key_field`, `trigger_type`, `trigger_args` (JSON), `enabled`, `created_at`, `last_run_at`, `last_status`, `last_error_traceback` |
| `audit_log` | Admin feature usage log | `id` (PK), `event_type`, `job_id`, `occurred_at`, `detail` (JSON) |

### Migration Approach

- **`src/storage/sqlite_storage.py:94-105`** — `_MIGRATION_COLUMNS` dict — manual `ALTER TABLE ADD COLUMN` for new columns on existing tables.
- **`src/storage/sqlite_storage.py:126-131`** — `_migrate_columns()` — checks `PRAGMA table_info()` and adds missing columns.
- **No migration framework** (no Alembic, no Flyway, no custom migration runner).
- Comment explicitly notes: "SQLite không hỗ trợ ALTER COLUMN mà không dựng lại bảng" — for dev DB only, can delete `.db` file to recreate.

### Data Models (dataclasses in `src/storage/base.py`)

| Dataclass | File:Line | Fields |
|-----------|-----------|--------|
| `Dataset` | `base.py:27` | `dataset_id`, `dataset_name`, `schema_signature: list[str]`, `created_at` |
| `DatasetSource` | `base.py:35` | `dataset_id`, `source_url`, `active`, `added_at` |
| `ExtractionStrategy` | `base.py:43` | `domain`, `field_name`, `selector`, `sample_value`, `updated_at` |
| `ScheduledJob` | `base.py:56` | `job_id`, `url`, `field_descriptions`, `trigger_type`, `trigger_args`, `enabled`, `created_at`, `dataset_id`, `storage_mode`, `file_path`, `write_mode`, `key_field`, `last_run_at`, `last_status`, `last_error_traceback` |
| `AuditLogEntry` | `base.py:89` | `id`, `event_type`, `job_id`, `occurred_at`, `detail` |
| `Record` | `base.py:101` | `record_id`, `dataset_id`, `source_url`, `data: dict`, `content_hash`, `evidence: dict`, `confidence`, `needs_review`, `crawled_at`, `as_of` |

---

## 5. API Structure

### Endpoints (from `src/api/main.py`)

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| GET | `/health` | `main.py:129` | Liveness/readiness check — returns `{"status":"ok"}` |
| POST | `/crawl` | `main.py:136` | Crawl 1 URL — supports `storage_mode` "db" or "file" |
| GET | `/datasets` | `main.py:201` | List all datasets |
| GET | `/datasets/{dataset_id}/records` | `main.py:205` | List records in a dataset (limit/offset) |
| GET | `/exports/{file_path:path}` | `main.py:211` | Download exported JSON file |
| POST | `/schedules` | `main.py:221` | Create scheduled crawl job |
| GET | `/schedules` | `main.py:261` | List all scheduled jobs |
| DELETE | `/schedules/{job_id}` | `main.py:265` | Delete scheduled job |
| GET | `/admin/errors` | `admin.py:78` | List jobs with `last_status == "error"` |
| POST | `/admin/errors/{job_id}/suggest-fix` | `admin.py:83` | AI suggest-fix for errored job (read-only) |

### Request/Response Models (Pydantic, `src/api/main.py`)

| Model | Line | Fields |
|-------|------|--------|
| `CrawlRequest` | `main.py:39` | `url`, `field_descriptions: dict[str,str]`, `dataset_id`, `dataset_name`, `storage_mode`, `file_path`, `write_mode`, `key_field` |
| `CrawlResponse` | `main.py:50` | `status`, `dataset_id`, `record_id`, `file_path`, `data`, `confidence`, `needs_review`, `detail` |
| `ScheduleCreateRequest` | `main.py:61` | `url`, `field_descriptions`, `trigger_type`, `trigger_args`, `dataset_id`, `storage_mode`, `file_path`, `write_mode`, `key_field` |

### Key API Behaviors

- **`/crawl` with `storage_mode="db"`**: requires `dataset_id` (existing) or `dataset_name` (new). Schema mismatch returns 409. Fetch/extract failure returns 502.
- **`/crawl` with `storage_mode="file"`**: requires `file_path` + `write_mode`. No dataset, no dedup. `write_mode` options: `append`, `new_file`, `overwrite_row` (needs `key_field`).
- **`/schedules` with `storage_mode="db"`**: requires `dataset_id` + matching `schema_signature`.
- **`/schedules` with `storage_mode="file"`**: requires `file_path` + `write_mode`.

---

## 6. Data Flow

### Crawl Flow (DB mode — `run_crawl_job`)

1. **Schema resolution** (`pipeline.py:182-197`): If `dataset_id` provided → validate schema match. If not → create new dataset with `dataset_name`.
2. **Fetch + clean** (`pipeline.py:199-202`): `fetch_and_clean()` → `FetchResult` + `content_hash` (SHA256 of cleaned Markdown).
3. **Source tracking** (`pipeline.py:204-206`): Add URL to `dataset_sources` if not already active.
4. **Dedup check** (`pipeline.py:208-211`): Compare `content_hash` with latest record for this source. If unchanged → return `"unchanged"`.
5. **AI extraction** (`pipeline.py:213`): `ai_extract()` → structured data → cached selector → AI fallback.
6. **Save record** (`pipeline.py:222-231`): `storage.save_record()` with `needs_review = confidence < threshold`.

### Crawl Flow (File mode — `run_file_crawl_job`)

1. **Fetch + clean** (`pipeline.py:255-258`): Same as DB mode.
2. **AI extraction** (`pipeline.py:260`): Same `ai_extract()` — shared logic.
3. **Write file** (`pipeline.py:279-290`): `write_record()` to JSON file. No dedup, no dataset.

### Extraction Priority (`ai_extract` in `pipeline.py:88-155`)

1. **Structured data** (`structured_data.py`): JSON-LD `<script type="application/ld+json">` + Open Graph `<meta property="og:*">`. Matched via `_FIELD_SYNONYMS` table. Confidence = 1.0.
2. **Cached selector** (`selector_finder.py`): Previously found CSS selector for (domain, field). Applied via BeautifulSoup `select_one()`. Confidence = 0.9.
3. **AI fallback** (`greennode_client.py`): GreenNode MaaS chat completions. Returns JSON with `value`, `confidence`, `evidence` per field.

---

## 7. Scraping Flow

### Fetch Pipeline

```
HttpxFetcher.fetch(url)
  ├── robots_checker.can_fetch(url, user_agent)  → if blocked: return FetchResult(success=False, error="blocked_by_robots_txt")
  ├── rate_limiter.wait(domain_of(url))           → sleep if needed
  └── httpx.Client.get(url, headers={"User-Agent": ...})
        └── return FetchResult(url, final_url, status_code, html, fetched_at, success, error)
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| `FetchEngine` (ABC) | `src/fetch/base.py:63` | Interface for all fetch engines |
| `FetchResult` | `src/fetch/base.py:20` | Frozen dataclass: `url`, `final_url`, `status_code`, `html`, `fetched_at`, `success`, `error` |
| `HttpxFetcher` | `src/fetch/httpx_fetcher.py:20` | Static site fetcher (httpx) |
| `PlaywrightFetcher` | `src/fetch/playwright_fetcher.py:48` | JS-heavy site fetcher (Chromium headless) — NOT enabled by default |
| `HttpRobotsChecker` | `src/fetch/robots.py:49` | robots.txt fetch + cache (TTL 1h) + parse. Fail-closed on 5xx/network errors. |
| `DomainRateLimiter` | `src/fetch/rate_limiter.py:19` | Per-domain minimum delay between requests. Thread-safe with lock. |
| `domain_of(url)` | `src/fetch/base.py:76` | Extract netloc from URL — shared by fetch, rate-limit, robots, cache. |

### HTML Cleaning

- **`src/clean/html_cleaner.py:48`** — `clean_html(html) → CleanedDocument`
- Strips: `script`, `style`, `noscript`, `nav`, `footer`, `header`, `aside`, `form`, `iframe`, `svg`, `button`, `input`, `select`, `textarea`, `template`.
- Renders: headings (`h1-h6`), paragraphs (`p`), lists (`ul/ol`), tables → Markdown.
- Returns: `CleanedDocument(title, markdown, original_length, cleaned_length)`.

### Job/Task Model

- **`ScheduledJob`** (`src/storage/base.py:56`): Stored in `scheduled_jobs` table. `trigger_type` + `trigger_args` passed directly to APScheduler.
- **`CrawlScheduler`** (`src/scheduler.py:28`): Wraps `BackgroundScheduler`. On `start()`, reloads all enabled jobs from storage. On `_run_job()`, catches exceptions, stores traceback in `last_error_traceback`.
- **Job execution** (`scheduler.py:103-145`): Rbranches on `storage_mode` → calls `run_crawl_job()` or `run_file_crawl_job()`. Always updates `last_run_at`, `last_status`, `last_error_traceback`.

---

## 8. Existing Metadata Flow

### What Exists

| Metadata Type | Location | Description |
|---------------|----------|-------------|
| `schema_signature` | `datasets.schema_signature` | JSON array of field names (sorted). Used for schema matching. |
| `content_hash` | `records.content_hash` | SHA256 of cleaned Markdown. Used for change detection (dedup). |
| `evidence` | `records.evidence` | JSON dict mapping field name → source quote from AI extraction. |
| `confidence` | `records.confidence` | Average confidence across all fields (0.0-1.0). |
| `needs_review` | `records.needs_review` | Boolean flag: `confidence < AI_CONFIDENCE_THRESHOLD`. |
| `crawled_at` | `records.crawled_at` | UTC timestamp when record was saved. |
| `as_of` | `records.as_of` | Optional "as-of" date (data validity per content, not crawl time). Currently always `None` — not populated. |
| `source_url` | `records.source_url` | URL the record was crawled from. |
| `active` | `dataset_sources.active` | Whether a source URL is currently active (audit trail for source changes). |
| `extraction_strategies` | `extraction_strategies` table | Cached CSS selectors per (domain, field_name) with `sample_value` + `updated_at`. |
| `last_status` / `last_error_traceback` | `scheduled_jobs` | Job execution status + traceback for admin debug. |
| `audit_log` | `audit_log` table | Logs admin feature usage (e.g., `debug_suggest_fix` events). |

### What Does NOT Exist

- **No Data Dictionary** — no table/column documentation, no field-level metadata catalog.
- **No Data Lineage** — no tracking of data origin chain (source → transformation → destination).
- **No `as_of` population** — the column exists but is always `None` in current code.
- **No source versioning** — `dataset_sources` tracks active/inactive but no version history of source content changes.
- **No schema evolution tracking** — `schema_signature` is immutable per dataset; no history of schema changes.

---

## 9. Docker/Deployment Structure

### Docker Files

| File | Purpose | Port | Base Image |
|------|---------|------|------------|
| `Dockerfile` | Original single-container (dev) | 8000 | `python:3.12-slim` |
| `Dockerfile.api` | GreenNode AgentBase API runtime | 8080 (ENV PORT) | `python:3.12-slim` |
| `Dockerfile.ui` | GreenNode AgentBase UI runtime | 8080 (nginx) | `python:3.12-slim` |
| `docker-compose.yml` | Dev/test local (API + UI) | 8000:8080, 8501:8080 | — |

### GreenNode AgentBase Deployment

- **2 separate Agent Runtimes**: API (FastAPI) + UI (Streamlit behind nginx).
- **Port 8080** required by platform — both Dockerfiles expose 8080.
- **`/health` endpoint**: API has FastAPI route; UI has nginx static route (`deploy/nginx-ui.conf:9-12`).
- **Registry**: `<GREENNODE_REGISTRY_URL>` is a **placeholder** — not yet confirmed (README explicitly notes this).
- **Volume**: `DB_PATH` needs persistent volume mount — not yet configured for GreenNode.

### docker-compose.yml (dev/test)

- API: `Dockerfile.api`, port 8000:8080, env from `.env`, volume `./data:/app/data`.
- UI: `Dockerfile.ui`, port 8501:8080, `API_BASE_URL=http://api:8080`, depends_on `api`.
- Both use `restart: unless-stopped`.

### Deploy Artifacts

- **`deploy/nginx-ui.conf`**: nginx listens on 8080, `/health` returns static 200, everything else proxies to Streamlit on 127.0.0.1:8501 with WebSocket support.
- **`deploy/start-ui.sh`**: Starts Streamlit on 127.0.0.1:8501 (background) + nginx (foreground).

---

## 10. Relevant Files for Kiên's Tasks

### Task 1: PostgreSQL/Database

| File | Relevance |
|------|-----------|
| `src/storage/base.py` | **Critical** — `StorageEngine` ABC defines the interface. New `PostgresStorage` must implement all abstract methods. |
| `src/storage/sqlite_storage.py` | **Critical** — Reference implementation. All SQL queries here need PostgreSQL equivalents. Key differences: `sqlite3.Row` → `psycopg2.RealDictCursor`, `json.dumps/loads` → `JSONB`, `INTEGER` for bool → `BOOLEAN`, `TEXT` timestamps → `TIMESTAMPTZ`. |
| `src/config.py:25` | `db_path` setting — needs `DATABASE_URL` or separate PostgreSQL config. |
| `src/api/main.py:297` | `SQLiteStorage(settings.db_path)` — needs to switch to `PostgresStorage`. |

### Task 2: Database Migration

| File | Relevance |
|------|-----------|
| `src/storage/sqlite_storage.py:94-105` | `_MIGRATION_COLUMNS` — current manual migration approach. Needs replacement with proper migration framework (Alembic). |
| `src/storage/sqlite_storage.py:126-131` | `_migrate_columns()` — current migration runner. |
| `src/storage/sqlite_storage.py:23-85` | `_SCHEMA_SQL` — all `CREATE TABLE IF NOT EXISTS` statements. These become initial migration. |

### Task 3: Data Dictionary

| File | Relevance |
|------|-----------|
| `src/storage/base.py:27-116` | All dataclasses (`Dataset`, `Record`, `ScheduledJob`, etc.) — field definitions to document. |
| `src/storage/sqlite_storage.py:23-85` | Table DDL — column types, constraints. |
| `src/extract/structured_data.py:124-144` | `_FIELD_SYNONYMS` — field name mapping table. Part of data dictionary. |
| `src/api/main.py:39-70` | API request/response models — payload contracts. |

### Task 4: Data Lineage

| File | Relevance |
|------|-----------|
| `src/storage/base.py:35` | `DatasetSource` — tracks source URLs per dataset (closest thing to lineage). |
| `src/storage/base.py:101` | `Record` — has `source_url`, `crawled_at`, `as_of` — lineage-relevant fields. |
| `src/pipeline.py:158-231` | `run_crawl_job()` — data flow from fetch → extract → store. Lineage chain. |
| `src/storage/sqlite_storage.py:185-202` | `replace_source()` — source change tracking (audit trail). |

### Task 5: CSV/XLSX Export

| File | Relevance |
|------|-----------|
| `src/storage/file_writer.py` | **Critical** — Current JSON-only export. Needs CSV/XLSX addition. |
| `ui/app.py:437-457` | `_records_to_csv()` — **CSV export already exists in UI!** But only client-side (Streamlit `st.download_button`). No backend CSV endpoint. |
| `src/api/main.py:210-218` | `GET /exports/{file_path}` — current file download endpoint (JSON only). |
| `src/storage/file_writer.py:24` | `EXPORTS_ROOT = Path("data/exports")` — export directory. |

### Task 6: Docker

| File | Relevance |
|------|-----------|
| `Dockerfile` | Original single-container. |
| `Dockerfile.api` | API runtime for GreenNode. Needs PostgreSQL client libs if switching from SQLite. |
| `Dockerfile.ui` | UI runtime for GreenNode. |
| `docker-compose.yml` | Dev/test orchestration. Needs PostgreSQL service added. |
| `deploy/nginx-ui.conf` | nginx config for UI. |
| `deploy/start-ui.sh` | UI startup script. |

### Task 7: GreenNode Deployment Preparation

| File | Relevance |
|------|-----------|
| `Dockerfile.api` | Must listen on 8080, have `/health`. Already compliant. |
| `Dockerfile.ui` | Must listen on 8080 via nginx, have `/health`. Already compliant. |
| `README.md:89-144` | Deployment instructions — registry URL is placeholder. |
| `src/api/main.py:128-133` | `/health` endpoint. |
| `deploy/nginx-ui.conf:9-12` | UI `/health` via nginx. |

### Task 8: README/Documentation

| File | Relevance |
|------|-----------|
| `README.md` | Main project README — setup, deploy, compliance. |
| `CLAUDE.md` | Architecture principles, design constraints, tech stack. |
| `CHANGELOG.md` | Change history. |
| `ui/README.md` | UI-specific docs. |

---

## 11. Existing Functionality That Should Be Reused

| Functionality | Location | Reuse for |
|---------------|----------|-----------|
| `StorageEngine` ABC | `src/storage/base.py:119` | Implement `PostgresStorage` against same interface — zero changes to pipeline/API. |
| All dataclasses | `src/storage/base.py:27-116` | Reuse as-is for PostgreSQL — they're database-agnostic. |
| `create_app()` DI pattern | `src/api/main.py:103` | Swap `SQLiteStorage` → `PostgresStorage` in `_build_default_app()` only. |
| CSV export logic | `ui/app.py:437-457` | `_records_to_csv()` — extract to backend endpoint for API-side CSV/XLSX export. |
| `file_writer.py` path validation | `src/storage/file_writer.py:47-65` | `resolve_export_path()` — reuse for CSV/XLSX file paths. |
| `ScheduledJob` persistence | `src/storage/base.py:207-243` | Already database-agnostic — works with any `StorageEngine` impl. |
| `CrawlScheduler` | `src/scheduler.py:28` | Database-agnostic — only depends on `StorageEngine` interface. |
| Config pattern | `src/config.py:12` | Add `DATABASE_URL` field to `Settings` dataclass. |
| Docker health check | `src/api/main.py:128-133` + `deploy/nginx-ui.conf:9-12` | Already compliant with GreenNode requirements. |
| Test structure | `tests/` | Mirror for `PostgresStorage` tests — `tests/storage/test_postgres_storage.py`. |

---

## 12. Potential Conflicts

| Conflict | Details | Risk Level |
|----------|---------|------------|
| **SQLite ↔ PostgreSQL SQL dialect** | `sqlite3` uses `?` placeholders; PostgreSQL (psycopg2) uses `%s`. `ON CONFLICT(domain, field_name) DO UPDATE SET` (upsert) syntax may differ. `rowid` (SQLite implicit) does not exist in PostgreSQL — used as tiebreaker in `get_latest_record_for_source()` and `list_records()`. | **HIGH** |
| **JSON storage** | SQLite stores JSON as `TEXT` with `json.dumps/loads`. PostgreSQL has native `JSONB` with indexing. Need to decide: `JSONB` (better) or `TEXT` (compatible). | **MEDIUM** |
| **Boolean storage** | SQLite uses `INTEGER` (0/1) for booleans. PostgreSQL has native `BOOLEAN`. `bool(row["needs_review"])` and `int(needs_review)` conversions need adjustment. | **LOW** |
| **Timestamp handling** | SQLite stores timestamps as ISO strings (`TEXT`). PostgreSQL has `TIMESTAMPTZ`. `datetime.fromisoformat()` parsing in row converters needs removal/adaptation. | **MEDIUM** |
| **Thread safety** | `SQLiteStorage` uses `check_same_thread=False` with single connection. PostgreSQL needs connection pool (psycopg2 pool or asyncpg). | **MEDIUM** |
| **`check_same_thread=False`** | SQLite-specific flag. PostgreSQL connection handling is fundamentally different. | **LOW** |
| **Migration approach** | Current `_migrate_columns()` is SQLite-specific (`PRAGMA table_info`). PostgreSQL needs `information_schema.columns` or Alembic. | **MEDIUM** |
| **No `.env` in repo** | Each developer creates own `.env`. New `DATABASE_URL` needs to be added to `.env.example`. | **LOW** |
| **Docker image size** | Current images include Playwright + Chromium (~1GB+). Adding PostgreSQL client libs increases further. | **LOW** |

---

## 13. Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **No ORM, raw SQL** | All SQL is hand-written and SQLite-specific. Migrating to PostgreSQL requires rewriting every query in `sqlite_storage.py`. | Implement `PostgresStorage` against same `StorageEngine` ABC. Use parameterized queries with `%s` placeholders. |
| **`rowid` dependency** | `get_latest_record_for_source()` (`sqlite_storage.py:263-267`) and `list_records()` (`sqlite_storage.py:270-276`) and `list_audit_log()` (`sqlite_storage.py:402-414`) use `rowid DESC` as tiebreaker. PostgreSQL has no `rowid`. | Replace with `ORDER BY crawled_at DESC, record_id DESC` (UUID hex is not sequential — consider adding `SERIAL` or `BIGSERIAL` id column, or use `crawled_at` + `record_id` composite). |
| **Single SQLite connection** | `SQLiteStorage` uses one shared connection with `check_same_thread=False`. Under concurrent load (APScheduler + API requests), this may cause issues. PostgreSQL needs connection pooling. | Use `psycopg2.pool.SimpleConnectionPool` or `ThreadedConnectionPool`. |
| **No transaction isolation** | Current code uses implicit autocommit (`self._conn.commit()` after each operation). No explicit transaction boundaries. | PostgreSQL default isolation is READ COMMITTED — should be fine, but need to verify no race conditions in `create_scheduled_job` → `_register_job` sequence. |
| **No database indexes** | No `CREATE INDEX` statements in `_SCHEMA_SQL`. Queries like `get_latest_record_for_source` (filter by `dataset_id` + `source_url`, sort by `crawled_at`) will be slow with large data. | Add indexes: `records(dataset_id, source_url, crawled_at DESC)`, `scheduled_jobs(enabled)`, `extraction_strategies(domain, field_name)` (already PK). |
| **`as_of` never populated** | The `as_of` column exists but `run_crawl_job()` never sets it — always `None`. Data lineage work needs this field populated. | Determine source of `as_of` value (AI extraction? structured data? user input?). |
| **No foreign key enforcement** | SQLite doesn't enforce FK by default (needs `PRAGMA foreign_keys = ON`). Current code doesn't enable this. PostgreSQL enforces FK by default — may reveal existing data integrity issues. | Enable `PRAGMA foreign_keys = ON` in SQLite for testing parity. Validate existing data before migration. |
| **GreenNode registry URL unknown** | README explicitly states `<GREENNODE_REGISTRY_URL>` is a placeholder. Deployment cannot proceed without real URL. | Obtain real registry URL from GreenNode console/BTC. |
| **Docker not tested** | README notes: "chưa build/test thật với Docker daemon, mới review tĩnh." Docker images may have runtime issues. | Build and test Docker images locally before GreenNode deployment. |
| **Playwright in API image** | `Dockerfile.api` installs Playwright + Chromium (~500MB) even though API doesn't use PlaywrightFetcher by default. | Consider separate slim image without Playwright, or multi-stage build. |

---

## 14. Unknowns That Require Clarification

| # | Question | Why it matters |
|---|----------|----------------|
| 1 | **PostgreSQL version** on GreenNode? | Determines available features (JSONB, UPSERT syntax, etc.). |
| 2 | **PostgreSQL connection string format** for GreenNode? | `DATABASE_URL` format, SSL requirements, connection pool settings. |
| 3 | **Does GreenNode provide managed PostgreSQL?** Or self-hosted? | Determines backup, migration, connection pooling strategy. |
| 4 | **GreenNode Container Registry URL?** | Required for Docker push — currently placeholder. |
| 5 | **GreenNode volume/persistent storage mechanism?** | SQLite file needs persistent volume; PostgreSQL may need different storage config. |
| 6 | **What does Đăng's scraper output contract look like?** | If scraper changes, `FetchResult` / `FetchAndClean` contract may change — affects storage layer. |
| 7 | **What does Hiền's frontend expect from API?** | If frontend API expectations change, API response models (`CrawlResponse`, etc.) may need new fields. |
| 8 | **Is `as_of` supposed to be populated?** | Column exists but unused. Data lineage needs it. Who decides the value? |
| 9 | **Data Lineage scope?** | Full lineage graph (React Flow/D3) or simple source tracking? CLAUDE.md says "phase sau" — is it now in scope? |
| 10 | **Data Dictionary format?** | Static markdown? Interactive UI? API endpoint? Database table? |
| 11 | **CSV/XLSX export: backend or frontend?** | UI already has client-side CSV. Need backend endpoint? XLSX needs `openpyxl` dependency. |
| 12 | **Migration: SQLite → PostgreSQL data migration?** | Or fresh start on PostgreSQL? Existing SQLite data needs migration? |
| 13 | **Concurrent access pattern?** | How many concurrent API requests + scheduler jobs expected? Determines connection pool size. |
| 14 | **Are there existing tests for PostgreSQL?** | `tests/storage/test_sqlite_storage.py` exists — need `test_postgres_storage.py` with test DB. |

---

## Critical Dependencies

### What Kiên's work depends on from Đăng (Scraper/Extract)

| Dependency | Details | Current Contract |
|------------|---------|------------------|
| **`FetchResult` contract** | `src/fetch/base.py:20` — `url`, `final_url`, `status_code`, `html`, `fetched_at`, `success`, `error`. Storage layer receives `FetchResult` via `fetch_and_clean()` in pipeline. | If Đăng adds new fields to `FetchResult` (e.g., `response_headers`, `fetch_duration`), storage may need to persist them. |
| **`FieldExtraction` contract** | `src/ai/base.py:15` — `value`, `confidence`, `evidence`. Storage receives these via `ai_extract()` result. | If Đăng changes extraction output format (e.g., adds `extractor_type`, `selector_used`), `Record.data` / `Record.evidence` schema changes. |
| **`ExtractionResult` contract** | `src/ai/base.py:24` — `fields: dict[str, FieldExtraction]`, `raw_response`, `success`, `error`. | If extraction adds metadata (e.g., `model_version`, `tokens_used`), need new columns or JSON fields. |
| **Structured data extraction** | `src/extract/structured_data.py` — `StructuredData.values` dict. | If Đăng adds new structured data sources (e.g., microdata, RDFa), `match_field()` may return new source types — affects `evidence` format. |
| **Selector cache contract** | `src/extract/selector_finder.py` — `find_selector()` returns CSS selector string, `apply_selector()` returns text or None. | If selector format changes (e.g., XPath instead of CSS), `extraction_strategies.selector` column semantics change. |
| **HTML cleaner output** | `src/clean/html_cleaner.py` — `CleanedDocument(title, markdown, original_length, cleaned_length)`. | `content_hash` is SHA256 of `markdown` — if cleaning logic changes, all existing hashes become invalid (forces re-crawl of everything). |

### What Kiên's work depends on from Hiền (Frontend/UI)

| Dependency | Details | Current Contract |
|------------|---------|------------------|
| **API response structure** | `CrawlResponse` (`src/api/main.py:50`) — `status`, `dataset_id`, `record_id`, `file_path`, `data`, `confidence`, `needs_review`, `detail`. | If Hiền needs additional fields in API response (e.g., `record_count`, `export_url`, `lineage_graph`), backend must provide them. |
| **Dataset list format** | `GET /datasets` returns `list[dict]` with `dataclasses.asdict(Dataset)`. | If Hiền expects additional metadata per dataset (e.g., record count, last crawl time, source count), need new API fields or endpoint. |
| **Records list format** | `GET /datasets/{id}/records` returns `list[dict]` with `dataclasses.asdict(Record)`. | If Hiền needs pagination metadata, filtering, or sorting — current API only has `limit`/`offset`. |
| **Schedule format** | `GET /schedules` returns `list[dict]` with `dataclasses.asdict(ScheduledJob)`. | If Hiền needs schedule status summary, next run time, or job history — not currently available. |
| **Export download** | `GET /exports/{file_path}` returns `FileResponse` (JSON only). | If Hiền needs CSV/XLSX download from backend, need new endpoint or `format` query param. |
| **`needs_review` flag** | UI (`app.py:484-489`) shows warning count. API returns `needs_review` per record. | If Hiền changes review workflow (e.g., bulk review, filter by review status), need new API endpoints. |
| **`API_BASE_URL`** | UI reads from env var (`ui/app.py:19`). | If deployment topology changes (e.g., API gateway, multiple API instances), UI config may change. |

### Cross-dependencies (Kiên ↔ Đăng ↔ Hiền)

| Dependency | Kiên needs from | Description |
|------------|-----------------|-------------|
| **Job ID format** | Đăng | `ScheduledJob.job_id` is UUID hex (`uuid.uuid4().hex`). If Đăng changes job ID generation, all FK references and API paths break. |
| **`storage_mode` values** | Both | Currently `"db"` | `"file"`. If new storage modes added (e.g., `"postgres"`, `"csv"`), API validation + pipeline branching + scheduler all need updates. |
| **`schema_signature` format** | Đăng | Sorted list of field name strings. If Đăng changes field naming convention or adds field metadata to signature, schema matching logic breaks. |
| **Error status values** | Đăng | `last_status` values: `"saved"`, `"unchanged"`, `"fetch_failed"`, `"extract_failed"`, `"error"`, `"invalid_file_config"`, `"dataset_not_found"`, `"schema_mismatch"`. Admin panel filters on `"error"`. If new status values added, admin panel and UI status display need updates. |

---

## Summary

### Architecture
- FastAPI backend + Streamlit frontend, adapter pattern with DI, raw SQLite (no ORM), APScheduler for periodic jobs, GreenNode MaaS for AI extraction. Two parallel storage flows (DB vs file) sharing common fetch + extract pipeline.

### Relevant Files (top 10 for Kiên)
1. `src/storage/base.py` — StorageEngine ABC + all dataclasses
2. `src/storage/sqlite_storage.py` — Reference SQL implementation
3. `src/storage/file_writer.py` — JSON file export (needs CSV/XLSX)
4. `src/api/main.py` — API endpoints + DI factory
5. `src/config.py` — Settings (needs DATABASE_URL)
6. `src/pipeline.py` — Core data flow
7. `src/scheduler.py` — Job persistence + execution
8. `Dockerfile.api` / `Dockerfile.ui` — GreenNode deployment
9. `docker-compose.yml` — Dev orchestration (needs PostgreSQL service)
10. `ui/app.py:437-457` — Existing CSV export logic to extract to backend

### Dependencies
- **From Đăng**: `FetchResult` contract, `FieldExtraction`/`ExtractionResult` format, `content_hash` stability (depends on `clean_html` output), selector cache format, `schema_signature` format.
- **From Hiền**: API response field requirements, export format needs (CSV/XLSX), dataset/record display metadata needs, schedule UI requirements.

### Risks
- SQLite-specific SQL (`rowid`, `?` placeholders, `ON CONFLICT` syntax) won't work in PostgreSQL.
- No indexes — performance risk at scale.
- No FK enforcement in SQLite — may reveal data integrity issues on PostgreSQL.
- Docker images untested with real daemon.
- GreenNode registry URL unknown.

### Blockers
- **GreenNode PostgreSQL details** (version, connection string, managed vs self-hosted) — unknown.
- **GreenNode Container Registry URL** — placeholder in README.
- **GreenNode persistent volume mechanism** — unknown.
- **Data Lineage scope** — CLAUDE.md says "phase sau" but Kiên is assigned to it.
- **Data Dictionary format** — undefined.
- **`as_of` field population** — column exists but never set; lineage needs it.

---

**AUDIT COMPLETE**
