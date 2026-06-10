# Booking Bot

AI-powered appointment scheduling assistant for Oleg Polyakov. Built with LangGraph multi-agent orchestration, FastAPI, and a React frontend. Supports web chat and voice (Vapi).

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM orchestration | LangGraph + LangChain (Anthropic Claude) |
| Backend | FastAPI + SQLAlchemy (async) |
| Database | PostgreSQL (bookings + LangGraph checkpoints) |
| Cache | Redis (slot availability) |
| Vector search | Pinecone + fastembed |
| Calendar | Google Calendar API |
| Email | Resend |
| Voice | Vapi |
| Frontend | React + Vite + Tailwind |

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node 18+
- Docker + Docker Compose

### 1. Clone and enter the repo

```bash
git clone https://github.com/opolyo01/booking-bot.git
cd booking-bot
```

### 2. Create the backend `.env`

```bash
cp backend/.env.example backend/.env   # if it exists, otherwise create manually
```

Fill in every value — all are required:

```env
# App
SECRET_KEY=your-random-secret-key-here

# Database & cache (match docker-compose.yml defaults)
DATABASE_URL=postgresql+asyncpg://bookingbot:bookingbot@localhost:5433/bookingbot
REDIS_URL=redis://localhost:6379

# Anthropic (booking + RAG agents)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (text-embedding-3-small for knowledge base)
OPENAI_API_KEY=sk-...

# Google Calendar OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
GOOGLE_CALENDAR_ID=primary
GOOGLE_OWNER_EMAIL=your@email.com   # only this email gets admin access

# Pinecone (vector search)
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=booking-bot

# Email (Resend)
RESEND_API_KEY=re_...
FROM_EMAIL=onboarding@resend.dev    # use your verified domain in production

# Voice (Vapi) — leave blank to disable voice
VAPI_API_KEY=...
VAPI_WEBHOOK_SECRET=...

# URLs
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
```

### 3. Start Postgres and Redis

```bash
docker-compose up postgres redis -d
```

This starts:
- PostgreSQL on `localhost:5433` (note: 5433, not 5432, to avoid conflicts)
- Redis on `localhost:6379`

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Run database migrations

```bash
cd backend
alembic upgrade head
```

This creates all tables including LangGraph checkpoint tables.

### 6. Start the backend

```bash
uvicorn backend.main:app --reload
```

API is now running at `http://localhost:8000`.  
Swagger docs at `http://localhost:8000/docs`.

### 7. Connect Google Calendar (optional but recommended)

Visit `http://localhost:8000/auth/google` and complete the OAuth flow. This allows the bot to check your real calendar for conflicts and create events on booking.

### 8. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend is now running at `http://localhost:5173`.

---

## Quick Test (no frontend)

Send a chat message directly to the API:

```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-123",
    "message": "I would like to schedule a consulting call",
    "channel": "web",
    "timezone": "America/New_York"
  }'
```

---

## Deployment

### Option A — Railway (recommended, easiest)

1. Push your repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add a **PostgreSQL** plugin and a **Redis** plugin from the Railway dashboard
4. Set all environment variables from the `.env` template above (Railway injects `DATABASE_URL` and `REDIS_URL` automatically from plugins — update those to match Railway's format)
5. Railway uses the `Procfile` to start the server:
   ```
   web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
   ```
6. Deploy. Done.

> **Note:** Update `GOOGLE_REDIRECT_URI` and `FRONTEND_URL` / `BACKEND_URL` to your Railway domain after first deploy.

---

### Option B — Render

1. New Web Service → connect GitHub repo
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add a PostgreSQL database and Redis instance from Render's dashboard
5. Set all env vars in the Render environment tab

---

### Option C — Docker Compose (self-hosted)

The `docker-compose.yml` includes a `backend` service. To run the full stack:

```bash
# Build and start everything
docker-compose up --build

# Or in the background
docker-compose up --build -d
```

Backend: `http://localhost:8000`

For the frontend, either serve the built output:
```bash
cd frontend && npm install && npm run build
# then serve the dist/ folder with nginx or any static host
```

---

## Environment Variables Reference

| Variable | Description |
|---|---|
| `SECRET_KEY` | Random string for JWT signing |
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL (`redis://...`) |
| `ANTHROPIC_API_KEY` | Anthropic API key (Claude models) |
| `OPENAI_API_KEY` | OpenAI key (embeddings only) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | Must match the URI registered in Google Cloud Console |
| `GOOGLE_OWNER_EMAIL` | Your email — grants admin panel access |
| `PINECONE_API_KEY` | Pinecone API key |
| `PINECONE_INDEX_NAME` | Pinecone index name (default: `booking-bot`) |
| `RESEND_API_KEY` | Resend API key for confirmation emails |
| `FROM_EMAIL` | Sender address (use a verified domain in production) |
| `VAPI_API_KEY` | Vapi key for voice support (optional) |
| `VAPI_WEBHOOK_SECRET` | Vapi webhook signature secret (optional) |
| `FRONTEND_URL` | Full URL of the frontend (for CORS) |
| `BACKEND_URL` | Full URL of the backend |

---

## Architecture Overview

See [LANGGRAPH_TUTORIAL.md](LANGGRAPH_TUTORIAL.md) for a deep-dive into the LangGraph multi-agent design.

```
User (web or voice)
    │
    ▼
FastAPI  POST /chat/message
    │
    ▼
LangGraph StateGraph
    ├── orchestrator  (Haiku — intent routing)
    │       │
    │       ├── book   → booking_agent   (Sonnet — collects details, calls get_available_slots)
    │       ├── faq    → rag_agent       (Sonnet — Pinecone vector search)
    │       └── cancel → cancel_agent   (Sonnet — JWT token verification)
    │
    └── PostgreSQL checkpointer (persists full conversation state per session)
```
