---
name: project-voip-system
description: Stack, deployment topology, and service endpoints for the Booking Bot VoIP system
metadata:
  type: project
---

This is an AI-powered appointment booking bot that uses VAPI for voice (VoIP) calls as its telephony layer. The "VoIP" in this project refers to VAPI-mediated phone calls, not traditional SIP/RTP infrastructure.

## Architecture

- **Voice Layer:** VAPI (api.vapi.ai) — phone number +16508700884 routes calls to a Custom LLM endpoint
- **Custom LLM Endpoint:** `POST /webhook/vapi/chat/completions` — OpenAI-compatible, supports both streaming SSE and non-streaming JSON
- **Backend:** FastAPI + uvicorn, Python 3.12, runs locally on port 8000 (localhost only, no --host 0.0.0.0 in dev)
- **Production:** Railway → `https://booking-bot-production-b01f.up.railway.app` (Procfile: `uvicorn --host 0.0.0.0 --port $PORT`)
- **AI Graph:** LangGraph with 4 agents: orchestrator (Haiku), booking (Sonnet), rag (Sonnet), cancellation (Sonnet), reschedule (Sonnet)
- **Database:** PostgreSQL on port 5433 (Docker), schema managed by SQLAlchemy `create_all` (no Alembic migrations in use)
- **Cache:** Redis on port 6379 (Docker), used for slot caching (10 min TTL), session state (1 hr), reminder dedup
- **Vector DB:** Pinecone index `booking-bot`, dimension=384, BAAI/bge-small-en-v1.5 embeddings via fastembed
- **Calendar:** Google Calendar API via OAuth2 (owner only), tokens stored in `oauth_tokens` table
- **Email:** Resend API for booking confirmations, cancellations, and 24-hr reminders (APScheduler, 30 min interval)
- **Auth:** JWT-based admin tokens (24hr), JWT cancel tokens (30-day), HMAC-SHA256 for VAPI webhook signatures

## Key Endpoints

- `GET /health` — liveness check
- `POST /chat/message` — web chat (LangGraph invoke)
- `GET /slots?date=&meeting_type=` — available booking slots (no auth)
- `GET /cancel/{token}` — cancel booking via signed JWT
- `POST /webhook/vapi/chat/completions` — VAPI Custom LLM (OpenAI-compatible)
- `GET /auth/google` → Google OAuth flow
- `GET /admin/bookings` — admin (JWT Bearer required)

## Services Status (as of 2026-06-14)

- Backend: RUNNING (local uvicorn with --reload)
- PostgreSQL: RUNNING (Docker, healthy, 9 bookings)
- Redis: RUNNING (Docker, healthy)
- Pinecone: CONNECTED (12 vectors = 10 seed + 2 blog)
- Production (Railway): RUNNING and healthy
- Google OAuth: Token refreshes successfully via refresh_token
- VAPI: Reachable (api.vapi.ai resolves, HTTP 200)
- Anthropic API: Reachable (api.anthropic.com resolves)

**Why:** Saves baseline for future diagnostic comparisons.
**How to apply:** Use this as the baseline when future diagnostics run — compare against these known-good values.
