# Vector Agents - Hackathon Repo

Signal-to-action growth loop prototype with:
- **Frontend:** Next.js (`frontend/`)
- **Backend:** FastAPI + LangGraph (`backend/`)

The frontend streams loop events from the backend and sends user actions back to continue the workflow.

## Project Structure

```text
.
├── backend/   # FastAPI + orchestration graph + tests
└── frontend/  # Next.js UI + API proxy routes
```

## Prerequisites

- **Node.js** 20+
- **npm** 10+
- **Python** 3.11 (recommended in this repo)

> On Windows, use `py -3.11` for backend commands.

## Environment Variables

The backend loads environment variables from the root `.env` file.

Some integrations are optional and degrade gracefully if keys are missing, but this file is the place to configure them.

### Root `.env` example

```env
# Optional but recommended if you want Postgres checkpointing/caching
SUPABASE_POSTGRES_URL=

# LLM options
LLM_PROVIDER=auto
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=

# Research signal providers (optional)
SERP_API_KEY=
NEWS_API_KEY=
NEWSAPI_KEY=
REDDIT_USER_AGENT=Veracity/1.0 (hackathon research bot)
JOB_SIGNALS_USER_AGENT=Veracity/1.0 (hackathon research bot)

# Apify Reddit actor (optional)
APIFY_TOKEN=
APIFY_REDDIT_ACTOR=spry_wholemeal/reddit-scraper
APIFY_REDDIT_MAX_ITEMS=50
APIFY_REDDIT_INPUT_JSON=

# Optional competitor overrides
COMPETITOR_TARGETS=
COMPETITOR_TARGETS_SRI_LANKA=
```

### Frontend env (optional)

If backend is not running at the default `http://127.0.0.1:8000`, create `frontend/.env.local`:

```env
BACKEND_URL=http://127.0.0.1:8000
```

## Local Development

Use **two terminals** from repo root.

### 1) Start backend

```bash
cd backend
py -3.11 -m pip install -r requirements.txt
py -3.11 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Backend health check:
- `GET http://127.0.0.1:8000/`

### 2) Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:
- `http://localhost:3000`

## API Endpoints (Backend)

- `POST /loop/start` — starts an SSE stream for a thread
- `POST /loop/action` — submits follow-up actions (`feedback`, `channel_select`, `deploy_variant`)

The frontend proxies these through:
- `GET /api/loop/proxy`
- `POST /api/loop/action`

## Testing

### Backend tests

```bash
cd backend
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install -r tests/requirements.txt
py -3.11 -m pytest tests/ -v
```

### Frontend checks

```bash
cd frontend
npm run lint
```

## Troubleshooting

- If VS Code shows unresolved backend imports while commands still run, confirm interpreter is **Python 3.11**.
- If provider keys are missing (e.g., SerpAPI/News), backend falls back to reduced signal collection.
- If Ollama is configured but unavailable, set `LLM_PROVIDER=auto` and/or verify local Ollama is running.

## Notes

- This repository currently keeps frontend and backend setup separate.
- `frontend/README.md` is the default Next.js scaffold; this root README is the source of truth for running the full system.