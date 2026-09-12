"""Persistence: a `Store` interface with a SQLite implementation.

Why an interface when there is only one implementation? Because the CRM
question was open until 11:00 and might reopen. `pipeline.py` depends on
`Store`, so swapping in an `IntrakoreStore` later is a new file, not a
rewrite. See DECISIONS.md D7.

Why plain `sqlite3` rather than an ORM: zero setup, zero version friction,
and nobody is grading the ORM. The typing lives in `schemas.py` where it
matters.

Everything here is CRUD-complete because the brief requires it explicitly:
"For all the use cases above make sure to cover Create, Read, Update &
Delete." Update and Delete are the ones teams skip - they are wired here
from the start so there is no excuse at 15:30.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.schemas import (
    FollowUp,
    FollowUpStatus,
    InputKind,
    Lead,
    LeadStatus,
    MeetingNote,
)

DB_PATH = Path(__file__).resolve().parent.parent / "kore.db"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_email(value: str | None) -> str | None:
    return value.strip().lower() or None if value else None


def normalize_mobile(value: str | None) -> str | None:
    """Strip everything that isn't a digit, keep the last 9.

    Last-9 matching means +971 50 123 4567, 00971501234567 and 050 123 4567
    all collide, which is the behaviour we want for dedupe in the GCC.
    """
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else (digits or None)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class Store(Protocol):
    # idempotency
    def seen_activity(self, activity_id: str) -> str | None: ...
    def mark_activity(self, activity_id: str, result_json: str) -> None: ...

    # pending-note state: what "Add note" sets, and the router reads
    def set_pending_note(self, user_id: str, conversation_id: str, lead_id: str) -> None: ...
    def get_pending_note(self, user_id: str, conversation_id: str) -> str | None: ...
    def clear_pending_note(self, user_id: str, conversation_id: str) -> None: ...

    # leads
    def create_lead(self, lead: Lead) -> Lead: ...
    def get_lead(self, lead_id: str) -> Lead | None: ...
    def list_leads(self, limit: int = 50) -> list[Lead]: ...
    def update_lead(self, lead_id: str, changes: dict) -> Lead | None: ...
    def delete_lead(self, lead_id: str) -> bool: ...
    def find_duplicate(
        self, email: str | None, mobile: str | None
    ) -> tuple[Lead, str] | None: ...

    # notes
    def create_note(self, note: MeetingNote) -> MeetingNote: ...
    def get_note(self, note_id: str) -> MeetingNote | None: ...
    def list_notes(self, lead_id: str) -> list[MeetingNote]: ...
    def update_note(self, note_id: str, changes: dict) -> MeetingNote | None: ...
    def delete_note(self, note_id: str) -> bool: ...

    # follow-ups
    def create_follow_up(self, fu: FollowUp) -> FollowUp: ...
    def get_follow_up(self, fu_id: str) -> FollowUp | None: ...
    def list_follow_ups(self, lead_id: str | None = None) -> list[FollowUp]: ...
    def due_follow_ups(self, now: datetime) -> list[FollowUp]: ...
    def update_follow_up(self, fu_id: str, changes: dict) -> FollowUp | None: ...
    def delete_follow_up(self, fu_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Set when the salesperson taps "Add note" on a lead card. The router reads
-- it to decide whether the NEXT message is a new lead or a note on this one.
-- Keyed per user per conversation so two people in the same chat don't
-- collide.
CREATE TABLE IF NOT EXISTS pending_notes (
    user_id         TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    lead_id         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, conversation_id)
);

-- Set when the bot ASKS a question, so the next message is read as the
-- ANSWER rather than as a new lead. Without this the clarification loops
-- dead-end: the bot asks "which company?", you type "Acme", and the system
-- files "Acme" as a brand new lead.
--
-- payload_json holds whatever the answer needs to complete:
--   kind='company'        -> the partial LeadExtraction, not yet written
--   kind='followup_date'  -> {"follow_up_id": ...}
-- attempts guards against an answer we still can't parse looping forever.
CREATE TABLE IF NOT EXISTS pending_clarifications (
    user_id         TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    kind            TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    question        TEXT NOT NULL DEFAULT '',
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, conversation_id)
);

CREATE TABLE IF NOT EXISTS leads (
    id              TEXT PRIMARY KEY,
    company_name    TEXT,
    first_name      TEXT,
    last_name       TEXT,
    mobile          TEXT,
    email           TEXT,
    project_name    TEXT,
    estimated_value REAL,
    enquiry_type    TEXT,
    status          TEXT NOT NULL,
    source_kind     TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 1.0,
    conversation_id TEXT,
    service_url     TEXT,
    owner_user_id   TEXT,
    email_key       TEXT,
    mobile_key      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_email  ON leads(email_key);
CREATE INDEX IF NOT EXISTS idx_leads_mobile ON leads(mobile_key);

CREATE TABLE IF NOT EXISTS notes (
    id                 TEXT PRIMARY KEY,
    lead_id            TEXT NOT NULL,
    summary            TEXT NOT NULL,
    key_points         TEXT NOT NULL DEFAULT '[]',
    action_items       TEXT NOT NULL DEFAULT '[]',
    original_kind      TEXT NOT NULL,
    original_text      TEXT NOT NULL DEFAULT '',
    original_media_ref TEXT,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id                     TEXT PRIMARY KEY,
    lead_id                TEXT NOT NULL,
    due_at                 TEXT,
    instruction            TEXT NOT NULL DEFAULT '',
    status                 TEXT NOT NULL,
    clarification_question TEXT,
    created_at             TEXT NOT NULL
);
"""


class SQLiteStore:
    """The store we demo on. Identified as our own datastore, not a CRM."""

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # -- idempotency --------------------------------------------------------

    def seen_activity(self, activity_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT result_json FROM activities WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return row["result_json"] if row else None

    def mark_activity(self, activity_id: str, result_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO activities VALUES (?, ?, ?)",
            (activity_id, result_json, _now().isoformat()),
        )
        self._conn.commit()

    # -- pending note state -------------------------------------------------

    def set_pending_note(self, user_id: str, conversation_id: str, lead_id: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO pending_notes VALUES (?, ?, ?, ?)",
            (user_id, conversation_id, lead_id, _now().isoformat()),
        )
        self._conn.commit()

    def get_pending_note(self, user_id: str, conversation_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT lead_id FROM pending_notes WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        ).fetchone()
        return row["lead_id"] if row else None

    def clear_pending_note(self, user_id: str, conversation_id: str) -> None:
        self._conn.execute(
            "DELETE FROM pending_notes WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        )
        self._conn.commit()

    # -- pending clarification state ----------------------------------------

    def set_pending_clarification(
        self, user_id: str, conversation_id: str, kind: str,
        payload_json: str, question: str, attempts: int = 0,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO pending_clarifications "
            "(user_id, conversation_id, kind, payload_json, question, attempts, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, conversation_id, kind, payload_json, question,
             attempts, _now().isoformat()),
        )
        self._conn.commit()

    def get_pending_clarification(
        self, user_id: str, conversation_id: str
    ) -> dict | None:
        row = self._conn.execute(
            "SELECT kind, payload_json, question, attempts FROM pending_clarifications "
            "WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        ).fetchone()
        if not row:
            return None
        return {
            "kind": row["kind"],
            "payload": json.loads(row["payload_json"]),
            "question": row["question"],
            "attempts": row["attempts"],
        }

    def clear_pending_clarification(self, user_id: str, conversation_id: str) -> None:
        self._conn.execute(
            "DELETE FROM pending_clarifications WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        )
        self._conn.commit()

    # -- leads --------------------------------------------------------------

    def create_lead(self, lead: Lead) -> Lead:
        self._conn.execute(
            """INSERT INTO leads (id, company_name, first_name, last_name, mobile,
               email, project_name, estimated_value, enquiry_type, status,
               source_kind, confidence, conversation_id, service_url,
               owner_user_id, email_key, mobile_key, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lead.id, lead.company_name, lead.first_name, lead.last_name,
                lead.mobile, lead.email, lead.project_name, lead.estimated_value,
                lead.enquiry_type, lead.status.value, lead.source_kind.value,
                lead.confidence, lead.conversation_id, lead.service_url,
                lead.owner_user_id, normalize_email(lead.email),
                normalize_mobile(lead.mobile),
                lead.created_at.isoformat(), lead.updated_at.isoformat(),
            ),
        )
        self._conn.commit()
        return lead

    def get_lead(self, lead_id: str) -> Lead | None:
        row = self._conn.execute(
            "SELECT * FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        return _row_to_lead(row) if row else None

    def list_leads(self, limit: int = 50) -> list[Lead]:
        rows = self._conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_lead(r) for r in rows]

    def update_lead(self, lead_id: str, changes: dict) -> Lead | None:
        allowed = {
            "company_name", "first_name", "last_name", "mobile", "email",
            "project_name", "estimated_value", "enquiry_type", "status",
            "confidence",
        }
        sets = {k: v for k, v in changes.items() if k in allowed}
        if not sets:
            return self.get_lead(lead_id)
        if "status" in sets and hasattr(sets["status"], "value"):
            sets["status"] = sets["status"].value
        # Keep the dedupe keys in step with the values they derive from.
        if "email" in sets:
            sets["email_key"] = normalize_email(sets["email"])
        if "mobile" in sets:
            sets["mobile_key"] = normalize_mobile(sets["mobile"])
        sets["updated_at"] = _now().isoformat()
        clause = ", ".join(f"{k} = ?" for k in sets)
        self._conn.execute(
            f"UPDATE leads SET {clause} WHERE id = ?",
            (*sets.values(), lead_id),
        )
        self._conn.commit()
        return self.get_lead(lead_id)

    def delete_lead(self, lead_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        # Cascade by hand - a lead's notes and follow-ups are meaningless
        # without it, and leaving orphans makes the CRUD demo look sloppy.
        self._conn.execute("DELETE FROM notes WHERE lead_id = ?", (lead_id,))
        self._conn.execute("DELETE FROM follow_ups WHERE lead_id = ?", (lead_id,))
        # A deleted lead must not stay pending, or the next message would
        # attach a note to a lead that no longer exists.
        self._conn.execute("DELETE FROM pending_notes WHERE lead_id = ?", (lead_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def find_duplicate(
        self, email: str | None, mobile: str | None
    ) -> tuple[Lead, str] | None:
        """Email first, then mobile. Returns the lead AND the field that
        matched, so the confirmation card can say *why* it's a duplicate."""
        ek = normalize_email(email)
        if ek:
            row = self._conn.execute(
                "SELECT * FROM leads WHERE email_key = ? LIMIT 1", (ek,)
            ).fetchone()
            if row:
                return _row_to_lead(row), "email"
        mk = normalize_mobile(mobile)
        if mk:
            row = self._conn.execute(
                "SELECT * FROM leads WHERE mobile_key = ? LIMIT 1", (mk,)
            ).fetchone()
            if row:
                return _row_to_lead(row), "mobile"
        return None

    # -- notes --------------------------------------------------------------

    def create_note(self, note: MeetingNote) -> MeetingNote:
        self._conn.execute(
            "INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?)",
            (
                note.id, note.lead_id, note.summary,
                json.dumps(note.key_points), json.dumps(note.action_items),
                note.original_kind.value, note.original_text,
                note.original_media_ref, note.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return note

    def get_note(self, note_id: str) -> MeetingNote | None:
        row = self._conn.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        return _row_to_note(row) if row else None

    def list_notes(self, lead_id: str) -> list[MeetingNote]:
        rows = self._conn.execute(
            "SELECT * FROM notes WHERE lead_id = ? ORDER BY created_at DESC",
            (lead_id,),
        ).fetchall()
        return [_row_to_note(r) for r in rows]

    def update_note(self, note_id: str, changes: dict) -> MeetingNote | None:
        allowed = {"summary", "key_points", "action_items"}
        sets = {k: v for k, v in changes.items() if k in allowed}
        if not sets:
            return self.get_note(note_id)
        for k in ("key_points", "action_items"):
            if k in sets:
                sets[k] = json.dumps(sets[k])
        clause = ", ".join(f"{k} = ?" for k in sets)
        self._conn.execute(
            f"UPDATE notes SET {clause} WHERE id = ?", (*sets.values(), note_id)
        )
        self._conn.commit()
        return self.get_note(note_id)

    def delete_note(self, note_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # -- follow-ups ---------------------------------------------------------

    def create_follow_up(self, fu: FollowUp) -> FollowUp:
        self._conn.execute(
            "INSERT INTO follow_ups VALUES (?,?,?,?,?,?,?)",
            (
                fu.id, fu.lead_id,
                fu.due_at.isoformat() if fu.due_at else None,
                fu.instruction, fu.status.value, fu.clarification_question,
                fu.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return fu

    def get_follow_up(self, fu_id: str) -> FollowUp | None:
        row = self._conn.execute(
            "SELECT * FROM follow_ups WHERE id = ?", (fu_id,)
        ).fetchone()
        return _row_to_follow_up(row) if row else None

    def list_follow_ups(self, lead_id: str | None = None) -> list[FollowUp]:
        if lead_id:
            rows = self._conn.execute(
                "SELECT * FROM follow_ups WHERE lead_id = ? ORDER BY due_at",
                (lead_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM follow_ups ORDER BY due_at"
            ).fetchall()
        return [_row_to_follow_up(r) for r in rows]

    def due_follow_ups(self, now: datetime) -> list[FollowUp]:
        """Scheduled and past due. The scheduler polls this."""
        rows = self._conn.execute(
            """SELECT * FROM follow_ups
               WHERE status = ? AND due_at IS NOT NULL AND due_at <= ?
               ORDER BY due_at""",
            (FollowUpStatus.SCHEDULED.value, now.isoformat()),
        ).fetchall()
        return [_row_to_follow_up(r) for r in rows]

    def update_follow_up(self, fu_id: str, changes: dict) -> FollowUp | None:
        allowed = {"due_at", "instruction", "status", "clarification_question"}
        sets = {k: v for k, v in changes.items() if k in allowed}
        if not sets:
            return self.get_follow_up(fu_id)
        if "status" in sets and hasattr(sets["status"], "value"):
            sets["status"] = sets["status"].value
        if "due_at" in sets and isinstance(sets["due_at"], datetime):
            sets["due_at"] = sets["due_at"].isoformat()
        clause = ", ".join(f"{k} = ?" for k in sets)
        self._conn.execute(
            f"UPDATE follow_ups SET {clause} WHERE id = ?",
            (*sets.values(), fu_id),
        )
        self._conn.commit()
        return self.get_follow_up(fu_id)

    def delete_follow_up(self, fu_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM follow_ups WHERE id = ?", (fu_id,))
        self._conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_lead(row: sqlite3.Row) -> Lead:
    return Lead(
        id=row["id"],
        company_name=row["company_name"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        mobile=row["mobile"],
        email=row["email"],
        project_name=row["project_name"],
        estimated_value=row["estimated_value"],
        enquiry_type=row["enquiry_type"],
        status=LeadStatus(row["status"]),
        source_kind=InputKind(row["source_kind"]),
        confidence=row["confidence"],
        conversation_id=row["conversation_id"] or "",
        service_url=row["service_url"] or "",
        owner_user_id=row["owner_user_id"] or "",
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _row_to_note(row: sqlite3.Row) -> MeetingNote:
    return MeetingNote(
        id=row["id"],
        lead_id=row["lead_id"],
        summary=row["summary"],
        key_points=json.loads(row["key_points"]),
        action_items=json.loads(row["action_items"]),
        original_kind=InputKind(row["original_kind"]),
        original_text=row["original_text"],
        original_media_ref=row["original_media_ref"],
        created_at=_dt(row["created_at"]),
    )


def _row_to_follow_up(row: sqlite3.Row) -> FollowUp:
    return FollowUp(
        id=row["id"],
        lead_id=row["lead_id"],
        due_at=_dt(row["due_at"]),
        instruction=row["instruction"],
        status=FollowUpStatus(row["status"]),
        clarification_question=row["clarification_question"],
        created_at=_dt(row["created_at"]),
    )
