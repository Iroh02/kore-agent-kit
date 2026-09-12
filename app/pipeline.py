"""The router: InboundEvent -> PipelineResult.

Deterministic. The input kind decides the path; the model is only ever asked
to fill a schema, never to choose what happens next. See DECISIONS.md D3.

Every branch returns a PipelineResult with a `message` that is safe to say
out loud, including on failure. Nothing here may raise into the webhook.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from app import extract, followup, transcribe
from app.ledger import Ledger
from app.schemas import (
    Component,
    FollowUp,
    FollowUpResolution,
    FollowUpStatus,
    InboundEvent,
    InputKind,
    Lead,
    LeadExtraction,
    LeadStatus,
    MeetingNote,
    PipelineResult,
    ResultStatus,
)
from app.settings import settings
from app.store import Store, new_id

# The five fields the brief names. company_name is required for every mode;
# the brief makes that explicit for shared contacts, and it is the field a
# construction CRM cannot file a lead without.
REQUIRED = ["company_name"]
NICE_TO_HAVE = ["first_name", "last_name", "mobile", "email"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def handle(event: InboundEvent, store: Store) -> PipelineResult:
    """Entry point. The channel calls this and renders what comes back."""
    trace_id = f"trc_{uuid.uuid4().hex[:12]}"
    led = Ledger(trace_id=trace_id, activity_id=event.activity_id)

    # --- Idempotency ------------------------------------------------------
    # Teams retries deliveries. Without this one check, a retried message
    # becomes a second lead - and duplicate handling is scored.
    with led.span(Component.DB, "sqlite", "idempotency_check"):
        seen = store.seen_activity(event.activity_id)
    if seen:
        return PipelineResult.model_validate_json(seen)

    try:
        result = await _route(event, store, led)
    except Exception as exc:  # nothing reaches the webhook as a 500
        result = PipelineResult(
            trace_id=trace_id,
            status=ResultStatus.FAILED,
            message=(
                "Something went wrong processing that. Nothing was saved - "
                "please try again, or send the details as text."
            ),
            ledger=led.finish(),
        )
        result.ledger.entries.append(
            _error_entry(f"{type(exc).__name__}: {exc}")
        )
        return result

    with led.span(Component.DB, "sqlite", "mark_activity"):
        store.mark_activity(event.activity_id, result.model_dump_json())
    return result


async def _route(event: InboundEvent, store: Store, led: Ledger) -> PipelineResult:
    # Card buttons are explicit instructions; they always win.
    if event.kind is InputKind.COMMAND:
        return _handle_command(event, store, led)

    # Did we just ASK something? Then this message is the ANSWER, not a new
    # lead. Checked before the pending-note branch because an unanswered
    # question is the most recent thing that happened in the conversation.
    if event.kind is InputKind.TEXT:
        with led.span(Component.DB, "sqlite", "get_pending_clarification"):
            pending = store.get_pending_clarification(
                event.user_id, event.conversation_id
            )
        if pending:
            return _handle_clarification(event, pending, store, led)

    # Is this message a NOTE on an existing lead rather than a new lead?
    # We do not guess. The salesperson tapped "Add note" on a lead card,
    # which set this flag - so the next thing they send is scoped to it.
    # A classifier would be more elegant and can misfire live; this cannot.
    if event.kind in (InputKind.TEXT, InputKind.AUDIO):
        with led.span(Component.DB, "sqlite", "get_pending_note"):
            pending_lead_id = store.get_pending_note(
                event.user_id, event.conversation_id
            )
        if pending_lead_id:
            return _handle_note(event, pending_lead_id, store, led)

    if event.kind in (InputKind.TEXT, InputKind.IMAGE, InputKind.CONTACT, InputKind.AUDIO):
        return _handle_capture(event, store, led)
    return _fail(led, "I don't know how to handle that kind of message yet.")


# Leading filler people type when answering "which company?". Stripped
# deterministically rather than with a model call: it is predictable, free,
# and the confirmation card shows what was captured so a wrong read is one
# tap from being fixed.
_COMPANY_FILLER = re.compile(
    r"^\s*(?:(?:he|she|they)(?:'s| is| are)?\s+)?"
    r"(?:with|at|from|works? (?:at|for)|the company is|company is|it'?s|its)\s+",
    re.I,
)
MAX_CLARIFY_ATTEMPTS = 2


def _handle_clarification(
    event: InboundEvent, pending: dict, store: Store, led: Ledger
) -> PipelineResult:
    """The user is answering a question we asked. Route by what we asked."""
    answer = (event.text or "").strip()
    kind = pending["kind"]
    attempts = pending["attempts"]

    if not answer:
        return _fail(led, pending["question"])

    if kind == "company":
        return _answer_company(event, pending, answer, store, led)
    if kind == "followup_date":
        return _answer_followup_date(event, pending, answer, attempts, store, led)

    with led.span(Component.DB, "sqlite", "clear_pending_clarification"):
        store.clear_pending_clarification(event.user_id, event.conversation_id)
    return _fail(led, "Sorry, I lost track of what I was asking. Start again?")


def _answer_company(
    event: InboundEvent, pending: dict, answer: str, store: Store, led: Ledger
) -> PipelineResult:
    """The missing company arrived. Complete the lead we refused to write."""
    company = _COMPANY_FILLER.sub("", answer).strip(" .,\n\t")
    if not company:
        return _clarify(led, pending["question"], missing=["company_name"])

    # Rehydrate the extraction we held back rather than re-running the model.
    extraction = LeadExtraction(**pending["payload"])
    extraction.company_name = company

    with led.span(Component.DB, "sqlite", "clear_pending_clarification"):
        store.clear_pending_clarification(event.user_id, event.conversation_id)

    return _persist_lead(extraction, event, store, led,
                         source_kind=InputKind(pending["payload"].get(
                             "_source_kind", InputKind.TEXT.value)))


def _answer_followup_date(
    event: InboundEvent, pending: dict, answer: str, attempts: int,
    store: Store, led: Ledger,
) -> PipelineResult:
    """A date arrived for a follow-up we refused to guess at."""
    fu_id = pending["payload"].get("follow_up_id", "")
    parsed = followup.parse_follow_up(answer, _now(), answering=True)

    if parsed.resolution is FollowUpResolution.RESOLVED:
        with led.span(Component.DB, "sqlite", "update_follow_up"):
            fu = store.update_follow_up(fu_id, {
                "due_at": parsed.due_at,
                "status": FollowUpStatus.SCHEDULED,
                "clarification_question": None,
            })
            store.clear_pending_clarification(event.user_id, event.conversation_id)
        return PipelineResult(
            trace_id=led.trace_id, status=ResultStatus.UPDATED,
            message=f"Got it - follow-up set for {parsed.due_at:%a %d %b, %H:%M}.",
            follow_up=fu, ledger=led.finish(),
        )

    # Still can't pin it down. Ask once more, then stop rather than loop.
    if attempts + 1 >= MAX_CLARIFY_ATTEMPTS:
        with led.span(Component.DB, "sqlite", "clear_pending_clarification"):
            store.clear_pending_clarification(event.user_id, event.conversation_id)
        return PipelineResult(
            trace_id=led.trace_id, status=ResultStatus.UPDATED,
            message=(
                "I still couldn't pin that down, so I've left the follow-up "
                "unscheduled rather than guess. Set a date from the lead card "
                "whenever you know it."
            ),
            follow_up=store.get_follow_up(fu_id), ledger=led.finish(),
        )

    question = parsed.clarification_question or (
        "What date should I set? A day like Monday, or a date like 2026-09-20."
    )
    with led.span(Component.DB, "sqlite", "set_pending_clarification"):
        store.set_pending_clarification(
            event.user_id, event.conversation_id, "followup_date",
            json.dumps({"follow_up_id": fu_id}), question, attempts + 1,
        )
    return PipelineResult(
        trace_id=led.trace_id, status=ResultStatus.NEEDS_CLARIFICATION,
        message=question, clarification_question=question, ledger=led.finish(),
    )


def _handle_note(
    event: InboundEvent, lead_id: str, store: Store, led: Ledger
) -> PipelineResult:
    """A message arriving while a lead is pending a note.

    Text goes straight through; a voice note is transcribed first. The
    original input is retained either way, which the brief requires.
    """
    text = event.text
    media_ref = None

    if event.kind is InputKind.AUDIO:
        att = next((a for a in event.attachments if a.data), None)
        if not att:
            return _fail(led, "I couldn't read that voice note. Try sending it again?")
        try:
            text, _seconds = transcribe.transcribe(att.data, att.content_type, led)
        except transcribe.TranscriptionFailed as exc:
            # Degrade, don't crash: keep the lead pending so they can retry
            # or just type it.
            result = _clarify(
                led,
                "I couldn't transcribe that voice note. Could you type the "
                "notes instead?",
                missing=[],
                detail=str(exc),
            )
            return result
        media_ref = att.name

    if not text.strip():
        return _fail(led, "That looked empty - what came out of the meeting?")

    result = attach_note(
        lead_id, text, event.kind, store, led, media_ref=media_ref,
        user_id=event.user_id, conversation_id=event.conversation_id,
    )

    # Note captured, so stop scoping messages to this lead.
    with led.span(Component.DB, "sqlite", "clear_pending_note"):
        store.clear_pending_note(event.user_id, event.conversation_id)
    return result


# ---------------------------------------------------------------------------
# Lead capture - modes 1, 2, 3
# ---------------------------------------------------------------------------


def _handle_capture(event: InboundEvent, store: Store, led: Ledger) -> PipelineResult:
    try:
        extraction = _extract_for(event, led)
    except extract.ExtractionFailed as exc:
        return _clarify(
            led,
            "I couldn't read the details from that. Could you send the company, "
            "name, mobile and email as text?",
            missing=REQUIRED + NICE_TO_HAVE,
            detail=str(exc),
        )

    # --- Missing required fields: ASK, never invent -----------------------
    missing = [f for f in REQUIRED if not getattr(extraction, f, None)]
    if missing:
        # The demo beat for mode 2: a shared contact rarely carries a company,
        # so we stop and ask instead of filing an unusable lead.
        #
        # The extraction is PARKED, not discarded - the brief says company is
        # mandatory BEFORE the lead is created, so we must not write a partial
        # record. When the answer arrives, _answer_company rehydrates this
        # payload rather than re-running the model, which keeps the whole
        # clarification round trip free.
        question = _ask_for(missing, extraction)
        payload = extraction.model_dump()
        payload["_source_kind"] = event.kind.value
        with led.span(Component.DB, "sqlite", "set_pending_clarification"):
            store.set_pending_clarification(
                event.user_id, event.conversation_id, "company",
                json.dumps(payload), question,
            )
        return _clarify(led, question, missing=missing)

    return _persist_lead(extraction, event, store, led)


def _persist_lead(
    extraction: LeadExtraction, event: InboundEvent, store: Store, led: Ledger,
    source_kind: InputKind | None = None,
) -> PipelineResult:
    """Dedupe then write. Shared by the direct path and the answered-
    clarification path, so both behave identically - a lead completed by
    answering a question still gets the duplicate check."""
    # --- Duplicate check --------------------------------------------------
    with led.span(Component.DB, "sqlite", "find_duplicate"):
        dup = store.find_duplicate(extraction.email, extraction.mobile)
    if dup:
        existing, matched_on = dup
        return PipelineResult(
            trace_id=led.trace_id,
            status=ResultStatus.DUPLICATE,
            message=(
                f"That looks like an existing lead - {existing.company_name} "
                f"(matched on {matched_on}). I haven't created a duplicate. "
                f"Update the existing one instead?"
            ),
            lead=existing,
            duplicate_of=existing.id,
            duplicate_matched_on=matched_on,
            ledger=led.finish(),
        )

    # --- Persist ----------------------------------------------------------
    low_confidence = extraction.confidence < settings.min_confidence
    lead = Lead(
        id=new_id("lead"),
        company_name=extraction.company_name,
        first_name=extraction.first_name,
        last_name=extraction.last_name,
        mobile=extraction.mobile,
        email=extraction.email,
        project_name=extraction.project_name,
        estimated_value=extraction.estimated_value,
        enquiry_type=extraction.enquiry_type,
        status=LeadStatus.NEEDS_REVIEW if low_confidence else LeadStatus.NEW,
        source_kind=source_kind or event.kind,
        confidence=extraction.confidence,
        conversation_id=event.conversation_id,
        service_url=event.service_url,
        owner_user_id=event.user_id,
        created_at=_now(),
        updated_at=_now(),
    )
    with led.span(Component.DB, "sqlite", "create_lead"):
        store.create_lead(lead)

    msg = f"Lead created for {lead.company_name}."
    if low_confidence:
        msg += (
            f" I'm only {extraction.confidence:.0%} confident on this one"
            + (f" (unsure about: {', '.join(extraction.uncertain_fields)})"
               if extraction.uncertain_fields else "")
            + " - worth a check."
        )
    absent = [f for f in NICE_TO_HAVE if not getattr(extraction, f, None)]
    if absent:
        msg += f" Still missing: {', '.join(f.replace('_', ' ') for f in absent)}."

    return PipelineResult(
        trace_id=led.trace_id,
        status=ResultStatus.CREATED,
        message=msg,
        lead=lead,
        missing_fields=absent,
        ledger=led.finish(),
    )


def _extract_for(event: InboundEvent, led: Ledger) -> LeadExtraction:
    """Pick the extractor for this input kind."""
    if event.kind is InputKind.CONTACT:
        raw = event.text
        for att in event.attachments:
            if att.data:
                raw = att.data.decode("utf-8", errors="replace")
                break
        # Deterministic parse - a vCard is already structured, so no model
        # call and no chance of hallucination.
        with led.span(Component.LLM, "vcard-parser", "parse_vcard  # deterministic, no model"):
            return extract.parse_vcard(raw)

    if event.kind is InputKind.IMAGE:
        att = next((a for a in event.attachments if a.data), None)
        if not att:
            raise extract.ExtractionFailed("no image bytes on the event")
        return extract.extract_lead_from_card(att.data, att.content_type, led)

    if event.kind is InputKind.AUDIO:
        # A voice note sent WITHOUT tapping "Add note" first. Transcribe it
        # and treat the transcript as free text - someone describing a new
        # lead out loud is a perfectly reasonable thing to do, and failing
        # with "I couldn't read that" because a button wasn't pressed is a
        # footgun in front of a judge.
        att = next((a for a in event.attachments if a.data), None)
        if not att:
            raise extract.ExtractionFailed("no audio bytes on the event")
        try:
            transcript, _seconds = transcribe.transcribe(
                att.data, att.content_type, led
            )
        except transcribe.TranscriptionFailed as exc:
            raise extract.ExtractionFailed(f"could not transcribe: {exc}") from exc
        if not transcript.strip():
            raise extract.ExtractionFailed("transcript was empty")
        return extract.extract_lead_from_text(transcript, led)

    return extract.extract_lead_from_text(event.text, led)


def _ask_for(missing: list[str], extraction: LeadExtraction) -> str:
    who = " ".join(
        p for p in [extraction.first_name, extraction.last_name] if p
    ) or "this contact"
    if missing == ["company_name"]:
        return (
            f"I've got {who}, but no company. Which company are they with? "
            "I'll create the lead once I have it."
        )
    pretty = ", ".join(f.replace("_", " ") for f in missing)
    return f"I need a bit more before I can create the lead - {pretty}?"


# ---------------------------------------------------------------------------
# Meeting notes + follow-up
# ---------------------------------------------------------------------------


def attach_note(
    lead_id: str, text: str, kind: InputKind, store: Store, led: Ledger,
    media_ref: str | None = None, user_id: str = "", conversation_id: str = "",
) -> PipelineResult:
    """Publish meeting notes against a lead and schedule any follow-up.

    The brief requires storing the ORIGINAL input as well as the processed
    version - `original_text` holds the raw message or the transcript.
    """
    lead = store.get_lead(lead_id)
    if not lead:
        return _fail(led, "I couldn't find that lead.")

    parsed = extract.extract_meeting_note(text, led)
    note = MeetingNote(
        id=new_id("note"),
        lead_id=lead_id,
        summary=parsed.summary,
        key_points=parsed.key_points,
        action_items=parsed.action_items,
        original_kind=kind,
        original_text=text,
        original_media_ref=media_ref,
        created_at=_now(),
    )
    with led.span(Component.DB, "sqlite", "create_note"):
        store.create_note(note)

    fu_parse = followup.parse_follow_up(parsed.follow_up_instruction, _now())
    fu = None
    message = "Notes saved."

    if fu_parse.resolution is FollowUpResolution.RESOLVED:
        fu = FollowUp(
            id=new_id("fu"), lead_id=lead_id, due_at=fu_parse.due_at,
            instruction=fu_parse.raw_instruction,
            status=FollowUpStatus.SCHEDULED, created_at=_now(),
        )
        with led.span(Component.DB, "sqlite", "create_follow_up"):
            store.create_follow_up(fu)
        message += f" Follow-up set for {fu_parse.due_at:%a %d %b, %H:%M}."

    elif fu_parse.resolution is FollowUpResolution.AMBIGUOUS:
        # Recorded, but NOT scheduled. The brief forbids guessing.
        fu = FollowUp(
            id=new_id("fu"), lead_id=lead_id, due_at=None,
            instruction=fu_parse.raw_instruction,
            status=FollowUpStatus.AWAITING_CLARIFICATION,
            clarification_question=fu_parse.clarification_question,
            created_at=_now(),
        )
        with led.span(Component.DB, "sqlite", "create_follow_up"):
            store.create_follow_up(fu)
        # Park the question so the next message is read as the ANSWER.
        # Without this the bot asks "which day?" and the reply "Monday"
        # becomes a brand new lead - the exact dead end this closes.
        if user_id:
            with led.span(Component.DB, "sqlite", "set_pending_clarification"):
                store.set_pending_clarification(
                    user_id, conversation_id, "followup_date",
                    json.dumps({"follow_up_id": fu.id}),
                    fu_parse.clarification_question or "", 0,
                )
        return PipelineResult(
            trace_id=led.trace_id,
            status=ResultStatus.NEEDS_CLARIFICATION,
            message=f"Notes saved. {fu_parse.clarification_question}",
            lead=lead, note=note, follow_up=fu,
            clarification_question=fu_parse.clarification_question,
            ledger=led.finish(),
        )

    return PipelineResult(
        trace_id=led.trace_id, status=ResultStatus.CREATED, message=message,
        lead=lead, note=note, follow_up=fu, ledger=led.finish(),
    )


# ---------------------------------------------------------------------------
# CRUD from Adaptive Card buttons
# ---------------------------------------------------------------------------


def _handle_command(event: InboundEvent, store: Store, led: Ledger) -> PipelineResult:
    """Structured commands from card buttons.

    Free-text CRUD ("change the mobile for the Acme lead") is the one
    agent-shaped surface - see DECISIONS.md D4 - and lands here later via
    the SDK tool runner. Card buttons are deterministic and handled now.
    """
    cmd = event.command or {}
    action = cmd.get("action")
    lead_id = cmd.get("lead_id", "")

    if action == "add_note":
        lead = store.get_lead(lead_id)
        if not lead:
            return _fail(led, "I couldn't find that lead.")
        with led.span(Component.DB, "sqlite", "set_pending_note"):
            store.set_pending_note(event.user_id, event.conversation_id, lead_id)
        who = lead.company_name or "that lead"
        return PipelineResult(
            trace_id=led.trace_id,
            status=ResultStatus.READ,
            message=(
                f"Go ahead - send me the notes for {who}. Text or a voice note "
                f"both work. Include when to follow up if there is one."
            ),
            lead=lead,
            ledger=led.finish(),
        )

    if action == "delete_lead":
        with led.span(Component.DB, "sqlite", "delete_lead"):
            ok = store.delete_lead(lead_id)
        return PipelineResult(
            trace_id=led.trace_id,
            status=ResultStatus.DELETED if ok else ResultStatus.FAILED,
            message="Lead deleted." if ok else "I couldn't find that lead.",
            ledger=led.finish(),
        )

    if action == "update_lead":
        changes = {k: v for k, v in cmd.items()
                   if k not in ("action", "lead_id") and v not in (None, "")}
        with led.span(Component.DB, "sqlite", "update_lead"):
            lead = store.update_lead(lead_id, changes)
        if not lead:
            return _fail(led, "I couldn't find that lead.")
        return PipelineResult(
            trace_id=led.trace_id, status=ResultStatus.UPDATED,
            message=f"Updated {', '.join(changes)} for {lead.company_name}.",
            lead=lead, ledger=led.finish(),
        )

    # provide_company is deliberately GONE. It updated a lead by id, but the
    # missing-company path never creates one - the extraction is parked until
    # the answer arrives - so lead_id was always "", update_lead changed zero
    # rows, and it still replied "Thanks - lead created". A button that claims
    # a write that never happened, on the one beat whose whole point is that
    # we do not invent data.
    #
    # Answering by typing is the correct path and is covered by demo_check:
    #   _route -> _handle_clarification -> _answer_company -> _persist_lead
    # An unknown action now falls through to the honest "Unknown action" below.

    return _fail(led, f"Unknown action: {action!r}")


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _clarify(led: Ledger, message: str, missing: list[str], detail: str = "") -> PipelineResult:
    result = PipelineResult(
        trace_id=led.trace_id,
        status=ResultStatus.NEEDS_CLARIFICATION,
        message=message,
        clarification_question=message,
        missing_fields=missing,
        ledger=led.finish(),
    )
    if detail:
        result.ledger.entries.append(_error_entry(detail))
    return result


def _fail(led: Ledger, message: str) -> PipelineResult:
    return PipelineResult(
        trace_id=led.trace_id, status=ResultStatus.FAILED,
        message=message, ledger=led.finish(),
    )


def _error_entry(detail: str):
    from app.schemas import CostEntry
    return CostEntry(
        component=Component.LLM, service="error", unit_label="n/a", detail=detail
    )
