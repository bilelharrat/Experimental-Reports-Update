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

## Data

Companies live in `data/companies.yaml`. Reports are one YAML file each in
`data/reports/`. Knowledge-base threads are per-company files in
`data/threads/`. The whole `data/` directory is gitignored.
