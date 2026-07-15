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
sample `.env`.

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
- **Deep search** (the Search button / Enter) uses the OpenAI Responses API
  with `web_search` and a JSON-schema structured output for richer results
  with 2026 highlights, key people, last funding round, etc. Cached per query
  for 24h. Requires `OPENAI_API_KEY`; falls back to local-only matches when
  unset.

```sh
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4.1   # optional, defaults to gpt-4.1
./run.sh
```

## Library

Each company's research page has a Library section showing every generated
report (versioned by id) and any uploaded files. PDFs, PPT, PPTX, and MD
files up to 100MB are accepted via drag-and-drop; PDFs, PowerPoint previews,
and Markdown files can be opened in-browser, all files can be downloaded.

## Data

- `server/seed_data/company_records.yaml` — Git-tracked curated company seed
  records, including PRD/demo company profile fields
- `server/seed_data/company_fixtures.yaml` — opt-in deterministic QA fixture
  companies
- `data/companies.yaml` — local materialized company list
- `data/reports/<id>.yaml` — generated reports (one per run; full history)
- `data/threads/<company>.yaml` — knowledge-base Q&A threads
- `data/uploads/<company>/` — uploaded PDFs, PPT/PPTX, and MD files with an `index.yaml`
- `data/cache/companies_ai/` — persisted deep-search results (no auto-expiry)

The whole `data/` directory is gitignored. Server startup generates local
runtime state from tracked seeds. To run that materialization explicitly:

```sh
python -m server.local_generation
```

Use `python -m server.local_generation --json` for a machine-readable summary.
Use `python -m server.local_generation --include-fixture-companies` when a QA
run needs the Databricks, Stripe, NextNav, and empty-state fixtures.
