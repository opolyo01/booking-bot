---
name: project-known-issues
description: Discovered bugs, misconfigurations, and eval failures in the Booking Bot VoIP system
metadata:
  type: project
---

Issues discovered during E2E diagnostic on 2026-06-14. See [[project-voip-system]] for system context.

## 1. VAPI Webhook Signature Bypass (Security, Medium)

**File:** `backend/routers/vapi_webhook.py`, line ~21  
**Problem:** `_verify_signature()` is only called when `sig` is truthy (`if sig and not _verify_signature(...)`). A request with no `x-vapi-secret` header silently bypasses authentication.  
**Impact:** Any unauthenticated caller can POST to the webhook endpoint and invoke the LangGraph agent.  
**Fix:** Always verify the signature; return 401 if the header is absent.

## 2. Eval Keyword Gap — FAQ Hallucination Test (Low, False Failure)

**File:** `eval/run_eval.py`, `eval_faq_unknown()`  
**Problem:** The bot correctly admits ignorance ("Oleg's knowledge base doesn't cover his pizza preferences") but none of the hardcoded keywords match that phrasing. The eval returns a false negative (FAIL despite correct behavior).  
**Current keywords:** `["don't know", "don't have", "not sure", "can't find", "information", "unable", "sorry", "no details", "not something", "not available", "not in"]`  
**Missing keywords:** `"doesn't cover"`, `"knowledge base doesn't"`, `"not cover"`, `"focused on"`  
**Fix:** Add those phrases to the keyword list. Eval score is actually 19/19 behaviorally.

## 3. Pinecone Knowledge Base Under-Populated (Low)

**Current state:** 12 vectors (10 seed + 2 blog chunks). The commit log shows 114 Pinecone chunks were created from blog scraping, but only 2 blog-origin vectors exist in the index.  
**Impact:** RAG quality is limited; queries about blog posts may return low-relevance results. Scores are acceptable (0.75+) for profile queries but may degrade for technical topic questions.  
**Fix:** Re-run the blog scrape via `POST /admin/knowledge-base/scrape-blog` (requires admin JWT).

## 4. Frontend Port Conflict (Low, Local Dev Only)

**Problem:** `backend/.env` sets `FRONTEND_URL=http://localhost:5173` for CORS, but port 5173 is occupied by `plumber-app-client` Docker container. The booking-bot frontend isn't running locally.  
**Impact:** CORS headers point to the wrong origin. Web chat (`/chat/message`) will be blocked in browser for direct local dev.  
**Fix:** Run `npm run dev` in `frontend/` on a different port (e.g., 5174) and update `FRONTEND_URL` accordingly, or stop the plumber container.

## 5. Alembic Not Wired (Low)

**Problem:** `alembic.ini` contains `sqlalchemy.url = driver://user:pass@localhost/dbname` (placeholder). Schema is managed via `Base.metadata.create_all` in `init_db.py`. No migration versions exist.  
**Impact:** Schema changes require manual intervention or a full DB recreate. Not a current blocker since schema is stable.  
**Fix:** Run `alembic init` with correct DB URL if future schema migrations are needed.

## 6. Two uvicorn Processes on Port 8000 (Low)

**Problem:** `lsof -i :8000` shows two PIDs (96129 parent + 42576 child). The child is a multiprocessing worker spawned by APScheduler or uvicorn's reload mechanism. This is normal for `--reload` mode but appears as two processes.  
**Impact:** None — this is expected behavior for uvicorn `--reload`.
