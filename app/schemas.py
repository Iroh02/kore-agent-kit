"""Shared contracts between the channel layer and the pipeline layer.

This file is THE interface between the two halves of the build:

    Vishal  (channel)  produces InboundEvent, renders PipelineResult
    Nandita (pipeline) consumes InboundEvent, produces PipelineResult

Neither side needs to know how the other works. Changing a model here
changes both sides at once, so announce in chat before editing.

Everything is Pydantic. Extraction models are fed straight to Claude via
`client.messages.parse(output_format=...)`, so they must stay
strict-schema friendly: flat fields, no dict[str, X], no unions beyond
Optional.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Inbound - what the channel adapter produces
# ---------------------------------------------------------------------------


class InputKind(str, Enum):
    """How the salesperson sent the information.

    Maps to the brief's three lead-creation modes plus the two later stages.
    """

    TEXT = "text"          # mode 1: free-text client details, or meeting notes
    CONTACT = "contact"    # mode 2: .vcf attachment / forwarded contact
    IMAGE = "image"        # mode 3: business card photo
    AUDIO = "audio"        # voice note (meeting minutes)
    COMMAND = "command"    # Adaptive Card button, or a CRUD instruction


class Attachment(BaseModel):
    """A file that arrived with a chat message.

    Teams delivers attachments two different ways and they need different
    handling, hence `requires_auth`:

      * files / voice notes -> `application/vnd.microsoft.teams.file.download.info`
        with a SHORT-LIVED PRE-AUTHENTICATED download_url. Plain GET works.
      * inline images -> a contentUrl that needs the bot's bearer token.
    """

    name: str
    content_type: str
    download_url: str | None = None
    requires_auth: bool = False
    data: bytes | None = None  # populated once the channel has fetched it


class InboundEvent(BaseModel):
    """One chat message, normalized away from any platform's wire format."""

    # activity_id is the IDEMPOTENCY KEY. Teams retries deliveries; keying on
    # this is what stops one message becoming two leads.
    activity_id: str
    # conversation_id + service_url are stored on the Lead so a follow-up can
    # be delivered proactively into the same chat days later.
    conversation_id: str
    service_url: str
    user_id: str
    user_name: str = ""
    channel: str = "teams"
    kind: InputKind
    text: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    command: dict | None = None  # Adaptive Card Action.Submit payload
    received_at: datetime


# ---------------------------------------------------------------------------
# Extraction - what Claude returns, schema-validated
# ---------------------------------------------------------------------------


class LeadExtraction(BaseModel):
    """Claude's structured read of a lead, from text OR a business card.

    Fed to `messages.parse(output_format=LeadExtraction)`. The model cannot
    return prose we then regex - it returns this or the call fails validation
    and we retry once with the error, then abstain.

    Every field is Optional on purpose: a missing field must come back as
    None so the pipeline can ASK for it. An invented value is the single
    worst failure mode in this system.
    """

    company_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile: str | None = None
    email: str | None = None

    # Additive: only populated if the CTO confirms Intrakore's lead shape.
    # Harmless to leave None - nothing downstream requires them.
    project_name: str | None = None
    estimated_value: float | None = None
    enquiry_type: str | None = None

    confidence: float = Field(
        ge=0.0, le=1.0,
        description="0-1. Below 0.6 the pipeline flags the lead for review "
                    "instead of trusting it.",
    )
    uncertain_fields: list[str] = Field(
        default_factory=list,
        description="Field names the model was unsure about.",
    )
    source_quote: str = Field(
        default="",
        description="The span of input the extraction came from. Makes a "
                    "bad extraction debuggable without re-running it.",
    )


class MeetingNoteExtraction(BaseModel):
    """Claude's read of a meeting discussion (typed or transcribed)."""

    summary: str
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    # Raw follow-up instruction as the salesperson phrased it. Parsed
    # separately by followup.py - the model does NOT resolve dates here.
    follow_up_instruction: str = ""


# ---------------------------------------------------------------------------
# Follow-up - tri-state, because the brief forbids silent guessing
# ---------------------------------------------------------------------------


class FollowUpResolution(str, Enum):
    RESOLVED = "resolved"      # we have a concrete datetime
    AMBIGUOUS = "ambiguous"    # we must ask before scheduling
    NONE = "none"              # no follow-up was requested


class FollowUpParse(BaseModel):
    """Result of reading a follow-up instruction.

    The brief: "Do not silently guess if timing is ambiguous."
    So AMBIGUOUS is a first-class outcome, not an error. "Follow up after
    2 days" resolves; "next week sometime" must come back as a question.
    """

    resolution: FollowUpResolution
    due_at: datetime | None = None
    clarification_question: str | None = None
    raw_instruction: str = ""
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Domain records - what gets persisted
# ---------------------------------------------------------------------------


class LeadStatus(str, Enum):
    NEW = "new"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_REVIEW = "needs_review"  # low-confidence extraction
    ACTIVE = "active"


class Lead(BaseModel):
    id: str
    company_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile: str | None = None
    email: str | None = None
    project_name: str | None = None
    estimated_value: float | None = None
    enquiry_type: str | None = None

    status: LeadStatus = LeadStatus.NEW
    source_kind: InputKind = InputKind.TEXT
    confidence: float = 1.0

    # Needed to message the salesperson later, unprompted.
    conversation_id: str = ""
    service_url: str = ""
    owner_user_id: str = ""

    created_at: datetime
    updated_at: datetime


class MeetingNote(BaseModel):
    id: str
    lead_id: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    # The brief requires storing the ORIGINAL input, not just the processed
    # version - transcript for voice, raw message for text.
    original_kind: InputKind = InputKind.TEXT
    original_text: str = ""
    original_media_ref: str | None = None
    created_at: datetime


class FollowUpStatus(str, Enum):
    SCHEDULED = "scheduled"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    SENT = "sent"
    CANCELLED = "cancelled"


class FollowUp(BaseModel):
    id: str
    lead_id: str
    due_at: datetime | None = None
    instruction: str = ""
    status: FollowUpStatus = FollowUpStatus.SCHEDULED
    clarification_question: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Ledger - the brief's "solution economics" requirement
# ---------------------------------------------------------------------------


class Component(str, Enum):
    """Component-level split the brief asks for explicitly."""

    LLM = "llm"
    VISION = "vision"
    STT = "stt"
    DB = "db"
    CHANNEL_API = "channel_api"


class CostEntry(BaseModel):
    """One priced, timed step. Never estimated - always from real usage.

    For Claude calls, input/output_units come from `response.usage`.
    For speech-to-text, units are seconds of audio.
    For DB and channel calls, cost is 0 but latency still counts.
    """

    component: Component
    service: str  # e.g. "claude-opus-5", "deepgram-nova-3", "sqlite"
    input_units: float = 0.0
    output_units: float = 0.0
    cached_input_units: float = 0.0
    unit_label: str = "tokens"
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    detail: str = ""


class ActivityLedger(BaseModel):
    """Every cost and latency for one processed activity."""

    trace_id: str
    activity_id: str
    entries: list[CostEntry] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Outbound - what the channel renders
# ---------------------------------------------------------------------------


class ResultStatus(str, Enum):
    CREATED = "created"
    READ = "read"
    UPDATED = "updated"
    DELETED = "deleted"
    NEEDS_CLARIFICATION = "needs_clarification"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class PipelineResult(BaseModel):
    """The pipeline's answer. The channel turns this into an Adaptive Card.

    `message` is always populated and always safe to say out loud, including
    on failure. Nothing in this system should ever leave the salesperson
    without a reply.
    """

    trace_id: str
    status: ResultStatus
    message: str

    lead: Lead | None = None
    note: MeetingNote | None = None
    follow_up: FollowUp | None = None

    clarification_question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    duplicate_of: str | None = None
    duplicate_matched_on: str | None = None

    ledger: ActivityLedger
