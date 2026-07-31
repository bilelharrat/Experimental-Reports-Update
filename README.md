# bsh-research-center

FastAPI + Vue/Vite/Tailwind app for company research.

## Layout

- `server/` — FastAPI app. JSON API under `/api/*`, serves the SPA from `frontend/dist`.
- `frontend/` — Vite + Vue 3 + Tailwind. Built into `frontend/dist/`.
- `data/` — durable YAML storage (gitignored). Created on first run.
- `run.sh` — installs deps, builds the frontend if missing, launches uvicorn.

## Run

```sh
./run.sh
```

Then open http://127.0.0.1:8010.

Force a frontend rebuild:

```sh
REBUILD_FRONTEND=1 ./run.sh
```

## Authentication & access control

Every `/api/*` route is gated by `require_api_token` (`server/api.py`),
which **fails closed**: with no credentials it returns 401.

Accepted credentials, in order:

1. **Session token** (primary). `POST /api/auth/token` with `{email, password}`
   returns a 30-day token and sets an httponly `bsh_session` cookie. The SPA
   sends the token as `Authorization: Bearer <token>` on API fetches; browser
   downloads (`<a href>`) and SSE (`EventSource`) rely on the cookie. There is
   no `?token=` query-parameter channel — it leaked credentials into logs and
   history.
2. **Shared token** (machine/tooling only). `Authorization: Bearer $BSH_RESEARCH_API_TOKEN`.
   Resolves to the read-only **`service`** role — it can read but cannot perform
   any permission-gated mutation (e.g. "Regenerate all"). It is **never** admin
   and is **never** injected into the served HTML.

Cookie-authenticated mutations require an `X-BSH-Client` header (CSRF guard);
`SameSite=Lax` provides the primary protection. Bearer-authenticated requests
are CSRF-immune and skip the check.

### Local development

Running without any credentials is off by default. To allow it locally, set
`BSH_ALLOW_ANON_DEV=1` (grants **admin** — local, full-access escape hatch).
**Never set this in production.** For plain-http local dev also set
`BSH_COOKIE_SECURE=0` so the session cookie is accepted. Both are in the
tracked `.env.example` (copy it to `.env`, which is gitignored). All other
environment variables are documented there too.

### Account management (operator CLI)

No passwords ship in source. Seed accounts are created with `must_reset` and an
unusable random password (or `BSH_BOOTSTRAP_PASSWORD` if set). Manage accounts:

```sh
python -m server.auth_store set-password <email>   # prompts, no echo
python -m server.auth_store create-user <email>
python -m server.auth_store list
python -m server.auth_store revoke <email>          # log out one user
python -m server.auth_store revoke-all              # after a compromise
```

Users can self-serve via `POST /api/auth/change-password`.

### Production checklist

- Rotate `BSH_RESEARCH_API_TOKEN` to a long random secret (the old
  `BSH-8688` was leaked and is burned), or leave it unset.
- Ensure `BSH_ALLOW_ANON_DEV` is unset.
- Set a real password for every seed account and run `revoke-all` once.
- Cookies are `Secure` automatically behind TLS (`X-Forwarded-Proto: https`).

## Frontend dev

```sh
cd frontend
npm install
npm run dev   # proxies /api to http://127.0.0.1:8010
```

## Search

- **Autocomplete** uses the SEC EDGAR ticker index (~13K US public companies,
  cached for 24h) merged with already-tracked local companies. No auth, no
  rate limits.
- **Deep search** (the Search button / Enter) spawns the Claude Code CLI
  (`claude -p` with WebSearch/WebFetch and a strict JSON schema) for richer
  results with 2026 highlights, key people, last funding round, etc. Cached
  per query (no TTL). Requires the `claude` CLI on PATH (`npm install -g
  @anthropic-ai/claude-code`, then run `claude` once to authenticate); falls
  back to local-registry matches when unavailable. See
  `server/companies_ai.py`.

## Library

Each company's research page has a Library section showing every generated
report (versioned by id) and any uploaded files. PDFs, PPT, PPTX, and MD
files up to 100MB are accepted via drag-and-drop; PDFs, PowerPoint previews,
and Markdown files can be opened in-browser, all files can be downloaded.

## Data

Tracked seeds:

- `server/seed_data/company_records.yaml` — Git-tracked curated company seed
  records, including PRD/demo company profile fields
- `server/seed_data/company_fixtures.yaml` — opt-in deterministic QA fixture
  companies

### Data directory map

Everything under `data/` is generated at runtime. Directories prefixed `_`
hold background-job progress logs (JSONL) rather than durable records.
Owning module in parentheses:

| Path | Contents (owner) |
| --- | --- |
| `data/companies.yaml` | materialized company list (`storage`) |
| `data/company_ext/` | per-company extended sidecar records (`storage`) |
| `data/reports/<id>.yaml` | generated reports, full history (`storage`) |
| `data/threads/<company>.yaml` | knowledge-base Q&A threads (`storage`) |
| `data/uploads/<company>/` | Document Library uploads + `index.yaml` (`files_store`) |
| `data/research/<company>/` | background research docs + `index.yaml` (`research_store`) |
| `data/memos/` | memo pipeline run dirs (`memo_prep`, `memo_analysis`) |
| `data/memo_editor/` | memo studio editor state (`memo_editor_store`) |
| `data/external/` | news / external research / hormuz sources (`external_store`, `hormuz_store`) |
| `data/hormuz_appendix/` | generated Hormuz bilingual appendixes (`hormuz_store`) |
| `data/consoles/` | company console sessions + attachments (`console_store`) |
| `data/serena_analysis/`, `data/serena_training/` | Serena research-tool artifacts (`serena_analysis`) |
| `data/stock_research/` | stock trackers, hypotheses, sources (`stock_research`, `hypothesis_store`) |
| `data/intake/` | unresolved evidence intake queue (`evidence_store`) |
| `data/analytics/events.jsonl` | append-only product analytics (`analytics_store`) |
| `data/settings/` | preferences + Serena background memo (`product_store`, `memo_prep`) |
| `data/cache/` | deep-search + EDGAR caches, no auto-expiry (`cache`) |
| `data/users.json`, `data/sessions.json` | accounts and hashed session tokens (`auth_store`) |
| `data/_api/`, `data/_regen/`, `data/_trader/`, `data/_trader_sections/`, `data/_trader_stats/`, `data/_weekly_stocks/` | job progress JSONL + checkpoints (`api`, `weekly_stocks`) |
| `data/report_visuals/`, `data/visual_briefs/` | generated report imagery (large; prune periodically) |

**Domain names:** "Serena" is the research analyst persona — the
memo/research pipelines named for her live in `serena_analysis.py` and the
memo modules. "Hormuz" is the Strait-of-Hormuz daily geopolitical research
feature: sources land under `data/external/hormuz_research/`, and the
`hormuz_*` modules build the bilingual appendix from them. See
`docs/architecture.md` for the full module map.

The whole `data/` directory is gitignored. Server startup generates local
runtime state from tracked seeds. To run that materialization explicitly:

```sh
python -m server.local_generation
```

Use `python -m server.local_generation --json` for a machine-readable summary.
Use `python -m server.local_generation --include-fixture-companies` when a QA
run needs the Databricks, Stripe, NextNav, and empty-state fixtures.
