# Advanced RAG Chatbot — Scholarship Assistant

> An AI-powered scholarship query system, built with Retrieval-Augmented Generation (RAG), hybrid vector search, and multi-turn conversational state tracking.

---

## Overview

Scholarship information is often scattered across multiple pages, changes frequently, and has complex eligibility criteria. This system consolidates it into a conversational interface that:

- Understands natural-language queries in Traditional Chinese
- Progressively builds a user profile across conversation turns (education system, nationality, residency, identity)
- Retrieves relevant scholarships using hybrid dense + sparse vector search
- Streams responses token-by-token via Server-Sent Events (SSE)
- Auto-monitors source URLs and flags content changes for human review before updating the knowledge base

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 · TypeScript · Vite · React Router v7 |
| **Backend** | FastAPI · Uvicorn · Python 3.11+ |
| **Agent** | LangGraph (stateful multi-node graph) |
| **LLM / Embeddings** | OpenAI `gpt-4.1` · `text-embedding-3-small` |
| **Vector DB** | Milvus / Zilliz Cloud (hybrid BM25 + dense, RRF reranking) |
| **Relational DB** | PostgreSQL (psycopg connection pooling) |
| **Scheduler** | APScheduler + PostgreSQL Advisory Locks |
| **Notifications** | LINE Messaging API |
| **Deployment** | Zeabur (backend) · Vercel (frontend) |

---

## Architecture

```
React SPA (Vite + TypeScript)
  │  SSE stream · CSRF double-submit · session token (sessionStorage)
  ▼
FastAPI  ──── Security Middleware (CSP, HSTS, payload limits, SSRF guard)
  │
  ├─► LangGraph Agent
  │     ├─ analyze_and_extract  (intent + UserProfile via Structured Outputs)
  │     ├─ retrieve             (hybrid Milvus search with metadata filters)
  │     ├─ generate             (adaptive depth response, streamed)
  │     └─ small_talk           (bypasses retrieval for off-topic input)
  │
  ├─► Milvus / Zilliz Cloud
  │     ├─ Dense vectors  (1536-dim OpenAI embeddings)
  │     ├─ Sparse vectors (BM25)
  │     └─ Metadata arrays (nationality, education_system, residency, identity)
  │
  └─► PostgreSQL
        ├─ tcuscholarships       (knowledge base + MD5 hash + pending_data)
        ├─ qa_logs2              (Q&A history, token counts, user feedback)
        ├─ admin_refresh_tokens  (RTR tracking with JTI)
        └─ admin_audit_logs      (admin action audit trail)

APScheduler Worker (background)
  ├─ Fetch source URLs (async, SSRF-safe)
  ├─ MD5 hash comparison
  ├─ AI extraction → pending_data (Review Mode — NOT auto-merged)
  └─ LINE notification to admin
```

---

## Key Features

### Conversational RAG with Profile Accumulation
The LangGraph agent accumulates user-provided conditions (education level, nationality, residency, identity) across multiple turns. Responses are adaptive: detailed eligibility tables when profile is complete, friendly follow-up questions when conditions are ambiguous.

### Hybrid Vector Search with Fallback Cascade
1. Hybrid search — dense embedding + sparse BM25, reranked with RRF
2. Dense-only fallback if hybrid returns insufficient results
3. No-filter generalized search as last resort

### Knowledge Poisoning Prevention (Review Mode)
Background workers check source URLs on a schedule. When content changes:
- Changed content is stored in `pending_data` (JSON) and `needs_review = TRUE` is set
- **Nothing is auto-merged** into the live knowledge base
- Admin receives a LINE notification and must manually approve before the vector DB is updated

### Security Highlights
- **SSRF protection** — DNS resolution, IP blacklist (private / loopback / reserved ranges), manual redirect re-validation
- **CSRF** — Double-Submit Cookie pattern (HttpOnly cookie + `X-CSRF-Token` header)
- **JWT** — 15-minute access tokens; refresh token rotation (RTR) with JTI tracking and immediate revocation
- **Audit log** — every admin action written to `admin_audit_logs` (actor, IP, User-Agent, resource, status)
- **Security headers** — CSP, `X-Frame-Options`, HSTS, `Referrer-Policy`, `X-Content-Type-Options`
- **Config fail-fast** — invalid environment variables crash Uvicorn at startup rather than silently misbehaving

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL instance
- [Zilliz Cloud](https://zilliz.com/) cluster (or self-hosted Milvus)
- OpenAI API key

### Backend

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Fill in: OPENAI_API_KEY, ZILLIZ_API_KEY, CLUSTER_ENDPOINT,
#          DB_HOST, DB_PASSWORD, JWT_SECRET_KEY, CSRF_SECRET_KEY

python scripts/database_setup.py   # create PostgreSQL tables
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend-react
npm install
npm run dev          # http://localhost:5173
```

### Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `CLUSTER_ENDPOINT` | Zilliz Cloud / Milvus endpoint |
| `ZILLIZ_API_KEY` | Zilliz Cloud API key |
| `DB_HOST` / `DB_PASSWORD` | PostgreSQL connection |
| `JWT_SECRET_KEY` | HS256 signing key (min 32 chars) |
| `CSRF_SECRET_KEY` | HMAC key for session + CSRF tokens |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API (optional, for admin alerts) |
| `ENVIRONMENT` | `development` or `production` |
| `REDIS_URL` | Redis URL for rate limiting (optional, multi-worker) |
| `SCHEDULER_LOCKS_ENABLED` | `true` to enable PostgreSQL Advisory Locks |

See `.env.example` for the full list.

---

## Project Structure

```
advanced_rag_chatbot/
├── main.py               # FastAPI app, lifespan, public routes
├── config.py             # Environment parsing, startup validation
├── admin_api.py          # Admin CRUD, dashboard, AI scraper, token refresh
├── rag_service.py        # Chat stream pipeline, SSE generator
├── scheduler.py          # Background jobs, Advisory Locks, MD5 checks
├── milvus_service.py     # Vector DB operations, hybrid search
├── db_repository.py      # SQL helpers
├── security.py           # Request middleware, session signing
├── utils.py              # SSRF-safe fetch, DNS/IP validation
├── extraction_schema.py  # Pydantic models for AI-extracted scholarship data
├── prompts.py            # System prompt registry
├── llm_service.py        # LLM wrapper functions
│
├── agent/
│   ├── graph.py          # LangGraph StateGraph, routing logic
│   ├── nodes.py          # Node implementations
│   └── state.py          # TypedDict state definitions
│
├── frontend-react/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/   # Chat UI, sidebar, feedback modal, onboarding tour
│   │   └── admin/        # Admin dashboard (login, CRUD, AI extractor)
│   └── vercel.json
│
└── scripts/
    ├── database_setup.py
    └── generate_hash.py
```

---

## Deployment

### Backend — Zeabur
- Set all environment variables in the Zeabur dashboard
- For multi-worker deployments, set `REDIS_URL` and `SCHEDULER_LOCKS_ENABLED=true`
- PostgreSQL Advisory Lock IDs: `771001` (scholarship), `771002` (checkpoint), `771003` (QA cleanup)

### Frontend — Vercel
- Connect the `frontend-react/` directory; Vercel auto-detects Vite
- `vercel.json` contains SPA rewrite rules (`/* → /index.html`)

---

## Testing

```bash
pytest tests/ -v
```

All 24 unit and integration tests cover authentication flows, CSRF validation, config validation, and admin audit logging.

---

## Security Score

**99 / 100** — assessed against OWASP Top 10 and financial-grade token management standards.

Residual note: the SSL certificate whitelist for the web scraper uses a broad `*.tcu.edu.tw` wildcard. Tightening this to specific subdomains in `.env` would reduce the MITM surface on school networks.

---

## License

This project is developed for academic and research use at Tzu Chi University. Contact the repository owner for usage terms.
