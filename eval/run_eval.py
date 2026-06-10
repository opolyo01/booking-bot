"""
Booking Bot Eval Suite
Run: python eval/run_eval.py [--url https://booking-bot-production-b01f.up.railway.app]
"""

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

BASE_URL = "https://booking-bot-production-b01f.up.railway.app"
TIMEOUT = 30


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class Turn:
    user: str
    bot: str = ""
    ok: bool = True
    note: str = ""


@dataclass
class EvalResult:
    name: str
    category: str
    passed: bool
    turns: list[Turn] = field(default_factory=list)
    error: str = ""
    duration_ms: int = 0


# ── HTTP helper ───────────────────────────────────────────────────────────────

async def chat(client: httpx.AsyncClient, message: str, session_id: str) -> dict:
    r = await client.post(
        f"{BASE_URL}/chat/message",
        json={"message": message, "session_id": session_id},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Individual evals ──────────────────────────────────────────────────────────

async def eval_health(client: httpx.AsyncClient) -> EvalResult:
    r = await client.get(f"{BASE_URL}/health", timeout=10)
    ok = r.status_code == 200 and r.json().get("status") == "ok"
    return EvalResult("Health check", "infra", ok, turns=[
        Turn("GET /health", r.text, ok)
    ])


async def eval_faq_about_oleg(client: httpx.AsyncClient) -> EvalResult:
    sid = str(uuid.uuid4())
    turns = []
    queries = [
        ("Who is Oleg?", ["oleg", "engineer", "developer", "experience"]),
        ("What are his main skills?", ["python", "ai", "ml", "langchain", "langgraph", "machine"]),
        ("What meeting types does he offer?", ["consulting", "job", "training", "meetup"]),
    ]
    passed = True
    for msg, keywords in queries:
        resp = await chat(client, msg, sid)
        bot = resp["message"].lower()
        hit = any(k in bot for k in keywords)
        turns.append(Turn(msg, resp["message"], hit,
                          f"expected one of {keywords}"))
        if not hit:
            passed = False
    return EvalResult("FAQ — about Oleg", "faq", passed, turns)


async def eval_faq_skills(client: httpx.AsyncClient) -> EvalResult:
    sid = str(uuid.uuid4())
    resp = await chat(client, "Does Oleg know LangGraph?", sid)
    bot = resp["message"].lower()
    ok = "langgraph" in bot or "graph" in bot or "lang" in bot
    return EvalResult("FAQ — specific skill", "faq", ok, turns=[
        Turn("Does Oleg know LangGraph?", resp["message"], ok)
    ])


async def eval_faq_unknown(client: httpx.AsyncClient) -> EvalResult:
    sid = str(uuid.uuid4())
    resp = await chat(client, "What is Oleg's favorite pizza topping?", sid)
    bot = resp["message"].lower()
    # Should admit it doesn't know — any hedge/disclaimer counts
    ok = any(w in bot for w in ["don't know", "don't have", "not sure", "can't find",
                                 "information", "unable", "sorry", "no details",
                                 "not something", "not available", "not in"])
    return EvalResult("FAQ — unknown question (no hallucination)", "faq", ok, turns=[
        Turn("What is Oleg's favorite pizza topping?", resp["message"], ok,
             "should admit it doesn't know")
    ])


async def eval_booking_multiturn_consulting(client: httpx.AsyncClient) -> EvalResult:
    """Classic multi-turn: type → date → pick slot → details."""
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    # Turn 1: express intent
    r1 = await chat(client, "I'd like to book a meeting", sid)
    t1_ok = any(w in r1["message"].lower() for w in ["type", "kind", "what", "meeting"])
    turns.append(Turn("I'd like to book a meeting", r1["message"], t1_ok, "should ask meeting type"))
    if not t1_ok:
        passed = False

    # Turn 2: specify type
    r2 = await chat(client, "consulting", sid)
    t2_ok = any(w in r2["message"].lower() for w in ["date", "when", "time", "prefer"])
    turns.append(Turn("consulting", r2["message"], t2_ok, "should ask for date"))
    if not t2_ok:
        passed = False

    # Turn 3: give date
    r3 = await chat(client, "next Monday", sid)
    t3_ok = any(w in r3["message"].lower() for w in
                ["slot", "available", "time", "am", "pm", ":", "pick", "choose"])
    turns.append(Turn("next Monday", r3["message"], t3_ok, "should show slots"))
    if not t3_ok:
        passed = False

    # Turn 4: pick first slot-like option
    r4 = await chat(client, "Let's do 10am", sid)
    t4_ok = any(w in r4["message"].lower() for w in ["name", "email", "confirm", "detail"])
    turns.append(Turn("Let's do 10am", r4["message"], t4_ok, "should ask for name/email"))
    if not t4_ok:
        passed = False

    # Turn 5: provide details
    r5 = await chat(client, "My name is Test User and email is test@example.com", sid)
    t5_ok = any(w in r5["message"].lower() for w in
                ["confirm", "booked", "✅", "email", "calendar", "details"])
    turns.append(Turn("My name is Test User and email is test@example.com",
                      r5["message"], t5_ok, "should confirm booking"))
    if not t5_ok:
        passed = False

    return EvalResult("Booking — multi-turn consulting", "booking", passed, turns)


async def eval_booking_multiturn_job_offer(client: httpx.AsyncClient) -> EvalResult:
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    r1 = await chat(client, "I want to discuss a job opportunity with Oleg", sid)
    t1_ok = any(w in r1["message"].lower() for w in ["date", "when", "time", "type", "job"])
    turns.append(Turn("I want to discuss a job opportunity with Oleg", r1["message"], t1_ok))
    if not t1_ok:
        passed = False

    r2 = await chat(client, "How about this Thursday?", sid)
    t2_ok = any(w in r2["message"].lower() for w in ["slot", "available", "time", "am", "pm"])
    turns.append(Turn("How about this Thursday?", r2["message"], t2_ok, "should show slots"))
    if not t2_ok:
        passed = False

    r3 = await chat(client, "11am works for me", sid)
    t3_ok = any(w in r3["message"].lower() for w in ["name", "email", "confirm", "detail"])
    turns.append(Turn("11am works for me", r3["message"], t3_ok))
    if not t3_ok:
        passed = False

    r4 = await chat(client, "Jane Smith, jane@company.com, topic is Senior ML Engineer role", sid)
    t4_ok = any(w in r4["message"].lower() for w in ["confirm", "booked", "✅", "calendar"])
    turns.append(Turn("Jane Smith, jane@company.com", r4["message"], t4_ok))
    if not t4_ok:
        passed = False

    return EvalResult("Booking — multi-turn job offer", "booking", passed, turns)


async def eval_booking_multiturn_training(client: httpx.AsyncClient) -> EvalResult:
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    r1 = await chat(client, "I'm interested in a training session", sid)
    t1_ok = any(w in r1["message"].lower() for w in ["date", "when", "time", "topic"])
    turns.append(Turn("I'm interested in a training session", r1["message"], t1_ok))
    if not t1_ok:
        passed = False

    r2 = await chat(client, "Friday afternoon please", sid)
    t2_ok = any(w in r2["message"].lower() for w in ["slot", "available", "time", "pm", ":"])
    turns.append(Turn("Friday afternoon please", r2["message"], t2_ok))
    if not t2_ok:
        passed = False

    r3 = await chat(client, "2pm is perfect", sid)
    t3_ok = any(w in r3["message"].lower() for w in ["name", "email", "confirm"])
    turns.append(Turn("2pm is perfect", r3["message"], t3_ok))
    if not t3_ok:
        passed = False

    r4 = await chat(client, "Bob Chen, bob@startup.io", sid)
    t4_ok = any(w in r4["message"].lower() for w in ["confirm", "booked", "✅", "email"])
    turns.append(Turn("Bob Chen, bob@startup.io", r4["message"], t4_ok))
    if not t4_ok:
        passed = False

    return EvalResult("Booking — multi-turn training", "booking", passed, turns)


async def eval_booking_multiturn_meetup(client: httpx.AsyncClient) -> EvalResult:
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    r1 = await chat(client, "We're organizing a hackathon and want Oleg to participate", sid)
    t1_ok = any(w in r1["message"].lower() for w in ["date", "when", "time", "slot"])
    turns.append(Turn("We're organizing a hackathon", r1["message"], t1_ok))
    if not t1_ok:
        passed = False

    r2 = await chat(client, "Wednesday next week", sid)
    t2_ok = any(w in r2["message"].lower() for w in ["slot", "available", "time", "am", "pm"])
    turns.append(Turn("Wednesday next week", r2["message"], t2_ok))
    if not t2_ok:
        passed = False

    r3 = await chat(client, "10am", sid)
    # Bot may propose closest slot and ask "does that work?" — that's valid
    t3_ok = any(w in r3["message"].lower() for w in
                ["name", "email", "confirm", "work", "slot", "available", "closest"])
    turns.append(Turn("10am", r3["message"], t3_ok))
    if not t3_ok:
        passed = False

    r4 = await chat(client, "yes, and my name is Alex Rivera, alex@hackathon.org", sid)
    t4_ok = any(w in r4["message"].lower() for w in ["confirm", "booked", "✅", "name", "email"])
    turns.append(Turn("yes + Alex Rivera, alex@hackathon.org", r4["message"], t4_ok))
    if not t4_ok:
        passed = False

    return EvalResult("Booking — multi-turn meetup/hackathon", "booking", passed, turns)


async def eval_booking_preferred_time(client: httpx.AsyncClient) -> EvalResult:
    """User specifies a preferred time — bot should propose closest slot."""
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    r1 = await chat(client, "Book a consulting session for next Tuesday around 2pm", sid)
    bot = r1["message"].lower()
    t1_ok = any(w in bot for w in ["slot", "available", "closest", "pm", "2:", "14:"])
    turns.append(Turn("Book a consulting for next Tuesday around 2pm", r1["message"], t1_ok,
                      "should show slots near 2pm"))
    if not t1_ok:
        passed = False

    return EvalResult("Booking — preferred time hint", "booking", passed, turns)


async def eval_cancel_intent(client: httpx.AsyncClient) -> EvalResult:
    """User wants to cancel — bot should direct them to email link."""
    sid = str(uuid.uuid4())
    resp = await chat(client, "I need to cancel my booking", sid)
    bot = resp["message"].lower()
    ok = any(w in bot for w in ["email", "link", "cancel", "token", "confirmation"])
    return EvalResult("Cancel — intent detected", "cancel", ok, turns=[
        Turn("I need to cancel my booking", resp["message"], ok,
             "should mention cancellation link in email")
    ])


async def eval_cancel_with_bad_token(client: httpx.AsyncClient) -> EvalResult:
    """User provides a fake token — should handle gracefully."""
    sid = str(uuid.uuid4())
    resp = await chat(client, "Cancel my booking, token is abc123fake", sid)
    bot = resp["message"].lower()
    # Should either try and report failure, or ask for valid token
    ok = any(w in bot for w in ["invalid", "not found", "unable", "error", "token", "email",
                                  "couldn't", "could not", "cancel"])
    return EvalResult("Cancel — invalid token", "cancel", ok, turns=[
        Turn("Cancel my booking, token is abc123fake", resp["message"], ok,
             "should handle invalid token gracefully")
    ])


async def eval_slots_endpoint(client: httpx.AsyncClient) -> EvalResult:
    """Direct /slots API check."""
    from datetime import date as date_type, timedelta
    next_monday = date_type.today()
    while next_monday.weekday() != 0:
        next_monday += timedelta(days=1)

    r = await client.get(
        f"{BASE_URL}/slots",
        params={"date": next_monday.isoformat(), "meeting_type": "consulting"},
        timeout=TIMEOUT,
    )
    ok = r.status_code == 200
    data = r.json()
    # API returns {"slots": [...]} or a list directly
    slots = data.get("slots", data) if isinstance(data, dict) else data
    has_slots = isinstance(slots, list) and len(slots) > 0
    preview = json.dumps(slots[:3]) + ("..." if len(slots) > 3 else "")
    turns = [Turn(
        f"GET /slots?date={next_monday}&meeting_type=consulting",
        preview,
        ok and has_slots,
        f"got {len(slots)} slots"
    )]
    return EvalResult("Slots API — weekday", "api", ok and has_slots, turns)


async def eval_slots_weekend(client: httpx.AsyncClient) -> EvalResult:
    """Slots on a weekend should return empty."""
    from datetime import date, timedelta
    next_sat = date.today()
    while next_sat.weekday() != 5:
        next_sat += timedelta(days=1)

    r = await client.get(
        f"{BASE_URL}/slots",
        params={"date": next_sat.isoformat(), "meeting_type": "consulting"},
        timeout=TIMEOUT,
    )
    data = r.json()
    slots = data if isinstance(data, list) else data.get("slots", [])
    ok = len(slots) == 0
    turns = [Turn(
        f"GET /slots?date={next_sat} (Saturday)",
        json.dumps(data),
        ok,
        "Saturday should return no slots"
    )]
    return EvalResult("Slots API — weekend returns empty", "api", ok, turns)


async def eval_unknown_intent(client: httpx.AsyncClient) -> EvalResult:
    """Totally off-topic message — bot should handle gracefully."""
    sid = str(uuid.uuid4())
    resp = await chat(client, "What's the weather like today?", sid)
    bot = resp["message"].lower()
    # Should stay in context — not break or hallucinate unrelated stuff
    ok = len(bot) > 0 and not any(w in bot for w in ["traceback", "error", "exception", "500"])
    return EvalResult("Unknown intent — graceful handling", "robustness", ok, turns=[
        Turn("What's the weather like today?", resp["message"], ok,
             "should respond gracefully without crashing")
    ])


async def eval_empty_message(client: httpx.AsyncClient) -> EvalResult:
    """Empty message should not crash."""
    sid = str(uuid.uuid4())
    try:
        resp = await chat(client, " ", sid)
        ok = "message" in resp
        return EvalResult("Robustness — empty message", "robustness", ok, turns=[
            Turn("(empty/whitespace)", resp.get("message", ""), ok)
        ])
    except httpx.HTTPStatusError as e:
        ok = e.response.status_code == 422  # validation error is acceptable
        return EvalResult("Robustness — empty message", "robustness", ok, turns=[
            Turn("(empty)", f"HTTP {e.response.status_code}", ok,
                 "422 validation error is acceptable")
        ])


async def eval_session_isolation(client: httpx.AsyncClient) -> EvalResult:
    """Two different session IDs should not share state."""
    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())

    await chat(client, "I want a consulting session", sid_a)
    await chat(client, "consulting", sid_a)
    await chat(client, "next Monday", sid_a)

    # Session B starts fresh
    resp_b = await chat(client, "Hello, who are you?", sid_b)
    bot_b = resp_b["message"].lower()

    # Session B should NOT mention consulting or slots from A
    contaminated = "monday" in bot_b and "slot" in bot_b
    ok = not contaminated
    return EvalResult("Robustness — session isolation", "robustness", ok, turns=[
        Turn("(session A: booking flow started)",
             "(session B) Hello, who are you?", ok,
             "session B should not see session A's state"),
        Turn("session B response", resp_b["message"], ok),
    ])


async def eval_repeated_booking_blocked(client: httpx.AsyncClient) -> EvalResult:
    """Once booking confirmed, same session should block a second booking."""
    sid = str(uuid.uuid4())

    # Build up a proper multi-turn booking first (more reliable than one-shot)
    await chat(client, "I want to book a consulting session", sid)
    await chat(client, "next Monday", sid)
    r_slots = await chat(client, "first available slot please", sid)
    await chat(client, "yes that works", sid)
    r_confirm = await chat(client, "John Doe, john@evaltest.com", sid)
    # Bot may show summary and ask "confirm?" — give it one more turn
    if not r_confirm.get("booking_confirmed"):
        r_confirm = await chat(client, "yes, confirm", sid)

    confirmed = r_confirm.get("booking_confirmed", False) or any(
        w in r_confirm["message"].lower() for w in ["confirmed", "✅", "booked", "calendar", "confirmation email"]
    )

    r2 = await chat(client, "I want to book another consulting session", sid)
    bot = r2["message"].lower()
    blocked = any(w in bot for w in ["already", "confirmed", "new conversation", "session"])

    ok = confirmed and blocked
    return EvalResult("Robustness — double booking blocked", "robustness", ok, turns=[
        Turn("(multi-turn booking)", r_confirm["message"], confirmed,
             "first booking should confirm"),
        Turn("I want to book another consulting session", r2["message"], blocked,
             "should block second booking in same session"),
    ])


async def eval_faq_then_book(client: httpx.AsyncClient) -> EvalResult:
    """Mix: FAQ then booking in same session."""
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    r1 = await chat(client, "What does Oleg specialize in?", sid)
    t1_ok = len(r1["message"]) > 20
    turns.append(Turn("What does Oleg specialize in?", r1["message"], t1_ok))

    r2 = await chat(client, "Great, I'd like to book a consulting session", sid)
    t2_ok = any(w in r2["message"].lower() for w in ["date", "when", "type", "meeting"])
    turns.append(Turn("Great, I'd like to book a consulting session", r2["message"], t2_ok,
                      "should transition to booking flow"))
    if not t2_ok:
        passed = False

    return EvalResult("Flow — FAQ then booking transition", "flow", passed, turns)


async def eval_booking_then_faq(client: httpx.AsyncClient) -> EvalResult:
    """Mid-booking user asks an FAQ — should answer then return to booking."""
    sid = str(uuid.uuid4())
    turns = []
    passed = True

    r1 = await chat(client, "I want to book a meeting", sid)
    turns.append(Turn("I want to book a meeting", r1["message"], True))

    r2 = await chat(client, "Actually wait — what's the difference between consulting and training?", sid)
    t2_ok = any(w in r2["message"].lower() for w in ["consult", "train", "differ", "workshop"])
    turns.append(Turn("What's the difference between consulting and training?",
                      r2["message"], t2_ok, "should answer FAQ"))
    if not t2_ok:
        passed = False

    return EvalResult("Flow — FAQ interruption mid-booking", "flow", passed, turns)


# ── Runner ────────────────────────────────────────────────────────────────────

ALL_EVALS = [
    eval_health,
    eval_faq_about_oleg,
    eval_faq_skills,
    eval_faq_unknown,
    eval_slots_endpoint,
    eval_slots_weekend,
    eval_booking_preferred_time,
    eval_booking_multiturn_consulting,
    eval_booking_multiturn_job_offer,
    eval_booking_multiturn_training,
    eval_booking_multiturn_meetup,
    eval_cancel_intent,
    eval_cancel_with_bad_token,
    eval_unknown_intent,
    eval_empty_message,
    eval_session_isolation,
    eval_repeated_booking_blocked,
    eval_faq_then_book,
    eval_booking_then_faq,
]


async def run_all(url: str) -> None:
    global BASE_URL
    BASE_URL = url.rstrip("/")

    print(f"\n{'='*70}")
    print(f"  Booking Bot Eval Suite  →  {BASE_URL}")
    print(f"{'='*70}\n")

    results: list[EvalResult] = []

    async with httpx.AsyncClient() as client:
        for fn in ALL_EVALS:
            t0 = time.monotonic()
            try:
                result = await fn(client)
            except Exception as e:
                result = EvalResult(fn.__name__, "error", False, error=str(e))
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            results.append(result)

            icon = "✅" if result.passed else "❌"
            print(f"{icon}  [{result.category:12s}]  {result.name}  ({result.duration_ms}ms)")
            if not result.passed:
                for t in result.turns:
                    if not t.ok:
                        print(f"      ↳ USER: {t.user[:80]}")
                        print(f"        BOT:  {t.bot[:120]}")
                        if t.note:
                            print(f"        NOTE: {t.note}")
            if result.error:
                print(f"      ↳ ERROR: {result.error}")

    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    pct = int(passed / total * 100)

    by_category: dict[str, list[EvalResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    print(f"\n{'='*70}")
    print(f"  RESULTS: {passed}/{total} passed  ({pct}%)")
    print(f"{'='*70}")

    for cat, cat_results in by_category.items():
        cp = sum(1 for r in cat_results if r.passed)
        ct = len(cat_results)
        bar = "█" * cp + "░" * (ct - cp)
        print(f"  {cat:14s}  {bar}  {cp}/{ct}")

    print()

    if passed < total:
        print("FAILED:")
        for r in results:
            if not r.passed:
                print(f"  ❌  {r.name}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://booking-bot-production-b01f.up.railway.app")
    args = parser.parse_args()
    asyncio.run(run_all(args.url))
