"""FastAPI app: Teams webhook, REST CRUD, and the live demo dashboard.

Owner: Vishal (routes, webhook, cards). The pipeline half is imported, not
edited here.

Three surfaces:
  POST /api/messages   Teams Bot Framework webhook
  /api/leads|notes|follow-ups   REST CRUD - the brief requires full CRUD
  GET /                the live dashboard, projected during the demo

/docs is the OpenAPI page - use it as the architecture artifact at 17:00.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from app import pipeline
from app.schemas import (
    Component,
    CostEntry,
    InboundEvent,
    InputKind,
    PipelineResult,
)
from app.settings import settings
from app.store import SQLiteStore

store = SQLiteStore(settings.db_path)

# Live feed for the dashboard. Every processed activity is pushed here so
# judges watch records appear as they message the bot.
_subscribers: list[asyncio.Queue] = []


def publish(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO(Nandita): start the follow-up scheduler here.
    #   from app.scheduler import start; task = start(store, publish)
    yield


app = FastAPI(title="Chat-to-Lead", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Teams webhook  [Vishal]
# ---------------------------------------------------------------------------


async def _post_reply(event: InboundEvent, result: PipelineResult) -> None:
    """Render the result as a card and post it into the conversation.

    Bot Framework ignores this webhook's HTTP response body, so a reply only
    reaches the chat by POSTing back to {serviceUrl}. Failures here are
    swallowed on purpose: a non-200 makes Bot Framework redeliver, and a
    redelivered activity is how one message becomes two leads.
    """
    from app.channels import cards  # local: avoid import cycle
    from app.channels.teams import send_activity

    if not (settings.teams_enabled and event.service_url and event.conversation_id):
        result.ledger.entries.append(
            CostEntry(
                component=Component.CHANNEL_API,
                service="teams.send_activity",
                unit_label="calls",
                detail="skipped: channel not configured",
            )
        )
        return

    reply = cards.render(result)
    reply["replyToId"] = event.activity_id

    started = time.perf_counter()
    detail = "sent"
    try:
        await send_activity(event.service_url, event.conversation_id, reply)
    except Exception as exc:  # noqa: BLE001 - never crash in front of the user
        detail = f"send failed: {type(exc).__name__}: {exc}"

    latency_ms = (time.perf_counter() - started) * 1000
    result.ledger.entries.append(
        CostEntry(
            component=Component.CHANNEL_API,
            service="teams.send_activity",
            input_units=1.0,
            unit_label="calls",
            latency_ms=latency_ms,
            detail=detail,
        )
    )
    result.ledger.total_latency_ms += latency_ms


@app.post("/api/messages")
async def messages(request: Request):
    """Bot Framework posts every Teams activity here.

    TODO(Vishal): validate the inbound JWT against Bot Framework's OpenID
    keys. Skipped in the prototype - name it on the risks slide.
    """
    activity = await request.json()

    from app.channels.teams import to_inbound_event  # local: avoid import cycle

    event = await to_inbound_event(activity)
    result = await pipeline.handle(event, store)

    await _post_reply(event, result)

    publish({"type": "activity", "result": json.loads(result.model_dump_json())})

    # Body is ignored by Bot Framework; the reply went out via send_activity.
    return Response(status_code=200)


@app.post("/api/simulate")
async def simulate(event: InboundEvent):
    """Same pipeline, no Teams. Lets the pipeline half be developed and
    demoed while the tunnel is down. Clearly a dev fixture, not the demo."""
    result = await pipeline.handle(event, store)
    publish({"type": "activity", "result": json.loads(result.model_dump_json())})
    return result


# ---------------------------------------------------------------------------
# REST CRUD  - the brief requires Create, Read, Update, Delete on everything
# ---------------------------------------------------------------------------


@app.get("/api/leads")
def list_leads(limit: int = 50):
    return store.list_leads(limit)


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: str):
    lead = store.get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    return lead


@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: str, changes: dict):
    lead = store.update_lead(lead_id, changes)
    if not lead:
        raise HTTPException(404, "lead not found")
    publish({"type": "lead_updated", "lead_id": lead_id})
    return lead


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: str):
    if not store.delete_lead(lead_id):
        raise HTTPException(404, "lead not found")
    publish({"type": "lead_deleted", "lead_id": lead_id})
    return {"deleted": lead_id}


@app.get("/api/leads/{lead_id}/notes")
def list_notes(lead_id: str):
    return store.list_notes(lead_id)


@app.patch("/api/notes/{note_id}")
def update_note(note_id: str, changes: dict):
    note = store.update_note(note_id, changes)
    if not note:
        raise HTTPException(404, "note not found")
    return note


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str):
    if not store.delete_note(note_id):
        raise HTTPException(404, "note not found")
    return {"deleted": note_id}


@app.get("/api/follow-ups")
def list_follow_ups(lead_id: str | None = None):
    return store.list_follow_ups(lead_id)


@app.patch("/api/follow-ups/{fu_id}")
def update_follow_up(fu_id: str, changes: dict):
    fu = store.update_follow_up(fu_id, changes)
    if not fu:
        raise HTTPException(404, "follow-up not found")
    return fu


@app.delete("/api/follow-ups/{fu_id}")
def delete_follow_up(fu_id: str):
    if not store.delete_follow_up(fu_id):
        raise HTTPException(404, "follow-up not found")
    return {"deleted": fu_id}


# ---------------------------------------------------------------------------
# Live dashboard
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    """What is live and what is mocked. Honest by construction."""
    return {
        "ok": True,
        "claude": "live" if settings.claude_enabled else "MOCKED (no API key)",
        "teams": "live" if settings.teams_enabled else "MOCKED (no bot creds)",
        "stt": settings.stt_provider,
        "store": "sqlite (our own datastore, not Intrakore CRM)",
        "model": settings.extraction_model,
        "leads": len(store.list_leads(limit=1000)),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/stream")
async def stream():
    """Server-sent events. The dashboard subscribes; every processed
    activity pushes a frame so records appear live during the demo."""

    async def gen():
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        _subscribers.append(q)
        try:
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if q in _subscribers:
                _subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


DASHBOARD = Path(__file__).resolve().parent.parent / "ui" / "dashboard.html"


@app.get("/", response_class=HTMLResponse)
def dashboard():
    if not DASHBOARD.exists():
        return HTMLResponse("<h1>dashboard.html missing</h1>", status_code=404)
    return HTMLResponse(DASHBOARD.read_text(encoding="utf-8"))
