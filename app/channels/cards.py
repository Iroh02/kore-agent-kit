"""Adaptive Cards.  Owner: Vishal.

This is our Teams advantage. Buttons give us CRUD INSIDE the chat, which is
a stronger demo than CRUD in a side dashboard - and it doubles as the
"confirm back what was created or what needs clarification" requirement.

Button presses come back as an Activity with a `value` payload, which
`to_inbound_event` turns into InputKind.COMMAND and pipeline._handle_command
dispatches on. Keep the `action` strings in sync with that function:

    delete_lead | update_lead | provide_company

Schema reference: https://adaptivecards.io/explorer/
"""

from __future__ import annotations

from app.schemas import PipelineResult, ResultStatus


def render(result: PipelineResult) -> dict:
    """PipelineResult -> a Teams message activity carrying one card."""
    if result.status is ResultStatus.NEEDS_CLARIFICATION:
        card = _clarification_card(result)
    elif result.status is ResultStatus.DUPLICATE:
        card = _duplicate_card(result)
    elif result.lead is not None:
        card = _lead_card(result)
    else:
        card = _text_card(result.message)

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


def _base(body: list, actions: list | None = None) -> dict:
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": body,
        "actions": actions or [],
    }


def _cost_line(result: PipelineResult) -> dict:
    """Every card shows what the action cost and how long it took.

    Putting it on the card - not just the dashboard - means the economics
    requirement is visible in every single screenshot.
    """
    led = result.ledger
    return {
        "type": "TextBlock",
        "isSubtle": True,
        "wrap": True,
        "spacing": "Small",
        "text": (
            f"${led.total_cost_usd:.4f} · {led.total_latency_ms:.0f} ms · "
            + " + ".join(f"{e.component.value}" for e in led.entries)
        ),
    }


def _lead_card(result: PipelineResult) -> dict:
    lead = result.lead
    facts = [
        {"title": k, "value": v}
        for k, v in [
            ("Company", lead.company_name),
            ("Name", " ".join(p for p in [lead.first_name, lead.last_name] if p)),
            ("Mobile", lead.mobile),
            ("Email", lead.email),
            ("Status", lead.status.value),
        ]
        if v
    ]
    return _base(
        body=[
            {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
             "text": result.message, "wrap": True},
            {"type": "FactSet", "facts": facts},
            _cost_line(result),
        ],
        actions=[
            # TODO(Vishal): Action.ShowCard with Input.Text fields for edit.
            {"type": "Action.Submit", "title": "Edit",
             "data": {"action": "update_lead", "lead_id": lead.id}},
            {"type": "Action.Submit", "title": "Delete",
             "data": {"action": "delete_lead", "lead_id": lead.id}},
        ],
    )


def _clarification_card(result: PipelineResult) -> dict:
    """The mode-2 demo beat: company missing, so we ask instead of inventing."""
    lead_id = result.lead.id if result.lead else ""
    return _base(
        body=[
            {"type": "TextBlock", "weight": "Bolder", "wrap": True,
             "text": result.clarification_question or result.message},
            {"type": "Input.Text", "id": "company_name",
             "placeholder": "Company name"},
            _cost_line(result),
        ],
        actions=[
            {"type": "Action.Submit", "title": "Create lead",
             "data": {"action": "provide_company", "lead_id": lead_id}},
        ],
    )


def _duplicate_card(result: PipelineResult) -> dict:
    return _base(
        body=[
            {"type": "TextBlock", "weight": "Bolder", "wrap": True,
             "text": result.message},
            {"type": "TextBlock", "isSubtle": True, "wrap": True,
             "text": f"Matched on {result.duplicate_matched_on}."},
            _cost_line(result),
        ],
        actions=[
            {"type": "Action.Submit", "title": "Update existing",
             "data": {"action": "update_lead", "lead_id": result.duplicate_of}},
        ],
    )


def _text_card(message: str) -> dict:
    return _base(body=[{"type": "TextBlock", "wrap": True, "text": message}])
