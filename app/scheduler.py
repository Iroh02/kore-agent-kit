"""Fires due follow-ups.  Owner: Nandita.

The brief asks us to "create the next action / meeting". Creating it is the
requirement; actually delivering it unprompted, days later, is what makes it
feel like a product rather than a form.

Design notes worth knowing before editing:

* It is a plain asyncio loop, not APScheduler. One dependency less, and the
  whole thing is 90 lines you can read. Cron-grade scheduling is a day-two
  problem; this polls.

* It ALWAYS publishes to the dashboard, and only ALSO sends to the chat when
  a channel is configured. That is deliberate: the demo beat where a reminder
  fires live in front of the room must work even if Teams sideloading is
  blocked. The dashboard is the fallback surface, not an afterthought.

* A follow-up is marked SENT whether or not delivery succeeded, with the
  outcome recorded. Retrying forever in a live demo is worse than one missed
  reminder, and a stuck row would fire on every single tick.

* Proactive delivery is possible at all because `Lead` stores the
  `conversation_id` and `service_url` from the message that created it. That
  is what those two fields are for.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from app.schemas import FollowUpStatus
from app.settings import settings
from app.store import Store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message(lead, fu) -> str:
    who = lead.company_name if lead else "a lead"
    name = " ".join(p for p in [getattr(lead, "first_name", None),
                                getattr(lead, "last_name", None)] if p)
    lines = [f"Follow-up due: {who}" + (f" ({name})" if name else "")]
    if fu.instruction:
        lines.append(f'You said: "{fu.instruction}"')
    if lead and lead.mobile:
        lines.append(f"Mobile: {lead.mobile}")
    return "\n".join(lines)


async def fire_due(store: Store, publish: Callable[[dict], None]) -> int:
    """One pass. Returns how many fired. Separated out so it is testable
    without waiting on the loop."""
    due = store.due_follow_ups(_now())
    for fu in due:
        lead = store.get_lead(fu.lead_id)
        text = _message(lead, fu)
        delivered = "dashboard only (no channel configured)"

        if settings.teams_enabled and lead and lead.conversation_id:
            # Imported lazily: scheduler must stay importable with no Teams
            # credentials, so tests and the dashboard-only demo still run.
            try:
                from app.channels.teams import send_activity

                # The connector rejects an activity with no Activity.From
                # (400 MissingProperty), and rejects one whose From is the
                # MS_APP_ID guid (403 Forbidden) - it wants the bot's own
                # CHANNEL account. A reply copies that off the inbound
                # activity; a proactive send has none, so channels.teams
                # caches it from inbound traffic. Measured against live Web
                # Chat: guid -> 403, channel account -> 200.
                from app.channels.teams import bot_account

                sender = bot_account()
                if not sender:
                    raise RuntimeError(
                        "no bot ChannelAccount seen yet - cannot address a "
                        "proactive send until the bot has received a message"
                    )

                proactive = {
                    "type": "message",
                    "text": text,
                    "conversation": {"id": lead.conversation_id},
                    "from": sender,
                }
                if lead.owner_user_id:
                    proactive["recipient"] = {"id": lead.owner_user_id}

                await send_activity(
                    lead.service_url, lead.conversation_id, proactive
                )
                delivered = "sent to chat"
            except Exception as exc:  # noqa: BLE001 - never kill the loop
                # Include the detail: "HTTPStatusError" alone hid a 403 for
                # an hour. The status code is what tells you what is wrong.
                delivered = f"send failed: {type(exc).__name__}: {exc}"[:200]

        store.update_follow_up(fu.id, {"status": FollowUpStatus.SENT})

        print(f"  [follow-up] {fu.id} -> {delivered}")
        publish({
            "type": "follow_up_fired",
            "follow_up_id": fu.id,
            "lead_id": fu.lead_id,
            "company": lead.company_name if lead else None,
            "text": text,
            "delivery": delivered,
            "fired_at": _now().isoformat(),
        })

    return len(due)


async def _loop(store: Store, publish: Callable[[dict], None], seconds: int) -> None:
    while True:
        try:
            await fire_due(store, publish)
        except Exception as exc:  # noqa: BLE001 - a bad row must not stop the loop
            print(f"  [scheduler] {type(exc).__name__}: {exc}")
        await asyncio.sleep(seconds)


def start(store: Store, publish: Callable[[dict], None]) -> asyncio.Task:
    """Start polling. Cancel the returned task to stop."""
    seconds = max(5, settings.scheduler_seconds)
    print(f"  scheduler: polling every {seconds}s for due follow-ups")
    return asyncio.create_task(_loop(store, publish, seconds))
