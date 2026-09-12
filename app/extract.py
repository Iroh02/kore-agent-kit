"""Extraction: text, business card image, vCard, and meeting notes.

Everything here returns a validated Pydantic model or raises. There is no
path where model prose gets regexed - see DECISIONS.md D6.

The abstain policy, which is the whole point of this file:

    parse -> validation error -> retry ONCE with the error fed back
          -> still failing -> raise ExtractionFailed, and the pipeline ASKS

A missing field comes back as None so the bot can ask for it. Inventing a
phone number is the worst thing this system can do.
"""

from __future__ import annotations

import base64
import re

import anthropic

from app.ledger import Ledger
from app.schemas import Component, LeadExtraction, MeetingNoteExtraction
from app.settings import settings


class ExtractionFailed(Exception):
    """Extraction could not produce a valid result. Ask the user instead."""


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # `or None` lets the SDK resolve from env or an `ant auth login`
        # profile; an explicit empty string would block that resolution.
        # SDK defaults are read=600s x 3 attempts: a connection that opens
        # and then hangs freezes this single-worker process for ~30 min,
        # dashboard and scheduler included. 25s x 2 attempts bounds it at
        # ~51s, after which the APIError path below asks a question instead.
        # transcribe.py already bounds its httpx call at 60s.
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key or None,
            timeout=25.0,
            max_retries=1,
        )
    return _client


# ---------------------------------------------------------------------------
# Prompts
#
# Kept as module constants and placed FIRST in the request so they sit behind
# a cache_control breakpoint. Volatile content (the actual message) goes after.
# Verify caching is working via usage.cache_read_input_tokens - a zero there
# means something is invalidating the prefix.
# ---------------------------------------------------------------------------

LEAD_SYSTEM = """You extract sales lead details for a construction ERP.

Return ONLY what is actually present in the input. Rules:

1. If a field is not present, return null. Never guess, never infer, never
   complete a partial value. A null we can ask about is far better than a
   plausible wrong value we cannot detect.
2. mobile: keep the country code if present, digits and + only.
3. company_name: the organisation, not a job title and not a domain name.
   If the only evidence is an email domain, return null - a domain is not a
   company name.
4. confidence: your honest 0-1 read of the WHOLE extraction. Use below 0.6
   when the input is messy, partial, or the image is hard to read.
5. uncertain_fields: name any field you guessed at or read with difficulty.
6. source_quote: the span of input the details came from, so a human can
   check without re-running this. Keep it under 12 words - it is a debugging
   aid, and every token here is latency the salesperson waits through."""

CARD_SYSTEM = LEAD_SYSTEM + """

This input is a photograph of a business card. Read every visible field.
If the card is blurred, cropped, or partly unreadable, say so through a low
confidence and list the affected fields in uncertain_fields rather than
guessing at characters."""

NOTES_SYSTEM = """You turn a salesperson's meeting account into usable notes.

Return:
- summary: 2-4 sentences, factual, no invented outcomes.
- key_points: what was actually discussed.
- action_items: commitments made, one per item.
- follow_up_instruction: the raw phrase indicating when to follow up, copied
  VERBATIM from the input (e.g. "follow up after 2 days", "call me next
  Tuesday"). Empty string if none. Do NOT resolve it into a date - a separate
  component does that, and it must see the original wording to detect
  ambiguity."""


def _system(text: str) -> list[dict]:
    """System prompt with a cache breakpoint. Stable content only."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


# ---------------------------------------------------------------------------
# Lead extraction
# ---------------------------------------------------------------------------


def extract_lead_from_text(text: str, ledger: Ledger) -> LeadExtraction:
    """Mode 1: free-text client details."""
    return _parse_lead(
        system=LEAD_SYSTEM,
        content=[{"type": "text", "text": f"Extract the lead from:\n\n{text}"}],
        ledger=ledger,
        component=Component.LLM,
        detail="lead_from_text",
        effort="low",
        model=settings.text_model,
    )


def extract_lead_from_card(
    image_bytes: bytes, media_type: str, ledger: Ledger
) -> LeadExtraction:
    """Mode 3: business card photo.

    One Claude call with an image block - no separate OCR service. See
    DECISIONS.md D5: one vendor, one cost line, one failure mode.
    """
    return _parse_lead(
        system=CARD_SYSTEM,
        content=[
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(image_bytes).decode(),
                },
            },
            {"type": "text", "text": "Extract the lead from this business card."},
        ],
        ledger=ledger,
        component=Component.VISION,
        detail="lead_from_card",
        model=settings.vision_model,
    )


def _parse_lead(
    system: str, content: list[dict], ledger: Ledger, component: Component,
    detail: str, effort: str | None = None, model: str | None = None,
) -> LeadExtraction:
    """One structured call, one retry on validation failure, then abstain.

    `effort` tunes how much the model thinks. MEASURED on this workload:

        default   4965ms  346 out tok  $0.0097
        low       3254ms  185 out tok  $0.0057   <- same extraction

    Output tokens ARE the latency - they are generated serially - so cutting
    reasoning the task doesn't need cuts the wait by a third. Field
    extraction from a sentence is not a task that rewards deliberation.

    Vision is deliberately left at default: reading a photographed card is
    the genuinely hard input, and that is where thinking earns its cost.
    """
    messages = [{"role": "user", "content": content}]

    for attempt in range(2):
        use_model = model or settings.extraction_model
        with ledger.span(component, use_model, detail) as span:
            try:
                kwargs = dict(
                    model=use_model,
                    max_tokens=2048,
                    system=_system(system),
                    messages=messages,
                    output_format=LeadExtraction,
                )
                if effort:
                    kwargs["output_config"] = {"effort": effort}
                resp = client().messages.parse(**kwargs)
                span.record_claude(resp.usage)
                return resp.parsed_output
            except anthropic.APIError as exc:
                # Transport/API failures are not retried here - the SDK
                # already retries those. Surface as an abstain.
                raise ExtractionFailed(f"Claude call failed: {exc}") from exc
            except Exception as exc:  # validation failure
                if attempt == 1:
                    raise ExtractionFailed(
                        f"Could not produce a valid extraction: {exc}"
                    ) from exc
                # Feed the error back and let the model correct itself once.
                messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            f"That response failed schema validation: {exc}. "
                            "Return a valid object. Use null for anything not "
                            "present in the input."
                        ),
                    }
                ]

    raise ExtractionFailed("unreachable")


# ---------------------------------------------------------------------------
# Meeting notes
# ---------------------------------------------------------------------------


def extract_meeting_note(text: str, ledger: Ledger) -> MeetingNoteExtraction:
    with ledger.span(
        Component.LLM, settings.extraction_model, "meeting_note"
    ) as span:
        resp = client().messages.parse(
            model=settings.extraction_model,
            max_tokens=2048,
            system=_system(NOTES_SYSTEM),
            messages=[{"role": "user", "content": text}],
            output_format=MeetingNoteExtraction,
            output_config={"effort": "low"},
        )
        span.record_claude(resp.usage)
        return resp.parsed_output


# ---------------------------------------------------------------------------
# vCard - mode 2, no LLM needed
#
# A .vcf is structured already. Parsing it deterministically is faster,
# free, and cannot hallucinate. The LLM is for unstructured input only.
# ---------------------------------------------------------------------------

_VCARD_LINE = re.compile(r"^(?P<key>[A-Za-z]+)(?P<params>;[^:]*)?:(?P<value>.*)$")


def parse_vcard(raw: str) -> LeadExtraction:
    """Mode 2: shared contact.

    Company is very often absent from a personal contact - which is exactly
    why the brief makes it mandatory for this mode. Absent means None here,
    and the pipeline turns that into a clarification question.
    """
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        m = _VCARD_LINE.match(line.strip())
        if not m:
            continue
        key = m.group("key").upper()
        value = m.group("value").strip()
        if not value:
            continue
        fields.setdefault(key, value)

    first = last = None
    if "N" in fields:
        # N is  Family;Given;Middle;Prefix;Suffix
        parts = fields["N"].split(";")
        last = (parts[0] or "").strip() or None
        first = (parts[1] if len(parts) > 1 else "").strip() or None
    if not (first or last) and "FN" in fields:
        bits = fields["FN"].split()
        first = bits[0] if bits else None
        last = " ".join(bits[1:]) or None if len(bits) > 1 else None

    return LeadExtraction(
        company_name=fields.get("ORG", "").split(";")[0].strip() or None,
        first_name=first,
        last_name=last,
        mobile=fields.get("TEL") or None,
        email=fields.get("EMAIL") or None,
        confidence=1.0,  # deterministic parse - nothing was inferred
        uncertain_fields=[],
        source_quote=raw[:300],
    )
