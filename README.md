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
report (versioned by id) and any uploaded files. PDFs, PPT, and PPTX up to
100MB are accepted via drag-and-drop; PDFs can be opened in-browser, all
files can be downloaded.

## Data

- `data/companies.yaml` — company list
- `data/reports/<id>.yaml` — generated reports (one per run; full history)
- `data/threads/<company>.yaml` — knowledge-base Q&A threads
- `data/uploads/<company>/` — uploaded PDFs and PPT/PPTX with an `index.yaml`
- `data/cache/companies_ai/` — persisted deep-search results (no auto-expiry)

The whole `data/` directory is gitignored.
