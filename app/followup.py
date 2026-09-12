"""Follow-up scheduling from a natural-language instruction.

The brief: "Create the next action / meeting using an instruction such as
'follow up after 2 days' or the client-requested date and time. Do not
silently guess if timing is ambiguous."

So this is TRI-STATE, and AMBIGUOUS is a success, not a failure:

    RESOLVED  -> we have a concrete datetime, schedule it
    AMBIGUOUS -> we must ask before scheduling
    NONE      -> no follow-up was requested

Design note: relative offsets and explicit dates are resolved by regex, not
by the model. A regex cannot hallucinate a Tuesday. The model is only called
for phrasings the patterns don't cover, and it is instructed to prefer
AMBIGUOUS over a confident guess.

`now` is always passed in, never read from the clock inside a resolver -
that is what makes this testable.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.schemas import FollowUpParse, FollowUpResolution

# Business-hours default for a bare date. Stated, not hidden: if the user
# says "Tuesday" we still ask, but if they say "3 March" we schedule 09:00.
DEFAULT_HOUR = 9

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# "after 2 days", "in 3 weeks", "in a week", "in 2 minutes"
# Minutes exist for the demo: "follow up in 2 minutes" lets a scheduled
# reminder fire live in front of the room.
# Voice notes say "two days", not "2 days" - Deepgram writes small numbers
# as words, so the parser has to read them. "a couple of weeks" too.
_WORD_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
              "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "couple": 2, "few": 3}
_RELATIVE = re.compile(
    r"\b(?:after|in)\s+(?:a\s+)?(?P<n>\d+|" + "|".join(_WORD_NUMS) + r")"
    r"(?:\s+of)?\s+(?P<unit>min|mins|minute|hour|day|week|month)s?\b",
    re.I,
)
# "tomorrow", "next week"
_TOMORROW = re.compile(r"\btomorrow\b", re.I)
# "on 3 March", "on 03/03", "on 2026-03-03"
_ISO_DATE = re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b")
# explicit time "at 3pm", "at 15:00"
_TIME = re.compile(r"\bat\s+(?P<h>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ampm>am|pm)?\b", re.I)

# Phrasings that are DELIBERATELY treated as ambiguous. Each of these has
# more than one reasonable resolution, so we ask.
_AMBIGUOUS_HINTS = [
    (re.compile(r"\bnext week\b", re.I),
     "You said next week - which day works? For example Monday or Wednesday."),
    (re.compile(r"\bnext month\b", re.I),
     "You said next month - which date should I set?"),
    (re.compile(r"\b(sometime|soon|later|shortly|in a bit|asap)\b", re.I),
     "That timing is open-ended - what date and time should I set?"),
    (re.compile(r"\bend of (the )?(week|month)\b", re.I),
     "Which exact day did you mean by end of week/month?"),
    (re.compile(r"\bafter the (holidays|weekend|eid|break)\b", re.I),
     "Which date should I use for that?"),
]


def parse_follow_up(
    instruction: str, now: datetime, answering: bool = False
) -> FollowUpParse:
    """Resolve a follow-up instruction against `now`.

    Order matters: ambiguity is checked FIRST. "next week on Tuesday" would
    otherwise resolve on the weekday branch, but a bare "next week" must ask.

    `answering=True` means the user is replying to a question we just asked.
    That changes what the SAME words mean: a bare "Tuesday" volunteered in a
    meeting note is ambiguous (this week or next?), but "Tuesday" typed in
    answer to "which day works?" plainly means the coming Tuesday. Without
    this distinction the clarification loop asks the same question forever.
    """
    text = (instruction or "").strip()
    if not text:
        return FollowUpParse(
            resolution=FollowUpResolution.NONE, raw_instruction=instruction or ""
        )

    has_weekday = any(d in text.lower() for d in _WEEKDAYS)
    has_explicit_date = bool(_ISO_DATE.search(text))

    # 1. Ambiguity gate - unless the phrase also pins an actual day.
    for pattern, question in _AMBIGUOUS_HINTS:
        if pattern.search(text) and not (has_weekday or has_explicit_date):
            return FollowUpParse(
                resolution=FollowUpResolution.AMBIGUOUS,
                clarification_question=question,
                raw_instruction=instruction,
                reasoning=f"matched ambiguous phrasing: {pattern.pattern}",
            )

    hour, minute = _extract_time(text)

    # 2. Relative offset: "after 2 days", "in 3 weeks"
    m = _RELATIVE.search(text)
    if m:
        raw_n = m.group("n").lower()
        n = int(raw_n) if raw_n.isdigit() else _WORD_NUMS[raw_n]
        unit = m.group("unit").lower()
        delta = {
            # Minutes exist for the demo: "follow up in 2 minutes" lets a
            # scheduled reminder fire live in front of the room.
            "min": timedelta(minutes=n),
            "mins": timedelta(minutes=n),
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
        }[unit]
        due = now + delta
        if unit not in ("min", "mins", "minute", "hour"):
            due = due.replace(
                hour=hour if hour is not None else DEFAULT_HOUR,
                minute=minute or 0, second=0, microsecond=0,
            )
        return FollowUpParse(
            resolution=FollowUpResolution.RESOLVED,
            due_at=due,
            raw_instruction=instruction,
            reasoning=f"relative offset: {n} {unit}(s) from now",
        )

    # 3. Explicit ISO date
    m = _ISO_DATE.search(text)
    if m:
        due = datetime(
            int(m.group("y")), int(m.group("m")), int(m.group("d")),
            hour if hour is not None else DEFAULT_HOUR, minute or 0,
            tzinfo=now.tzinfo,
        )
        return FollowUpParse(
            resolution=FollowUpResolution.RESOLVED,
            due_at=due,
            raw_instruction=instruction,
            reasoning="explicit date",
        )

    # 4. "tomorrow"
    if _TOMORROW.search(text):
        due = (now + timedelta(days=1)).replace(
            hour=hour if hour is not None else DEFAULT_HOUR,
            minute=minute or 0, second=0, microsecond=0,
        )
        return FollowUpParse(
            resolution=FollowUpResolution.RESOLVED,
            due_at=due,
            raw_instruction=instruction,
            reasoning="tomorrow",
        )

    # 5. Bare weekday. "Tuesday" is ambiguous unless qualified by next/this -
    #    it could be in 1 day or in 8. This is the case most systems get
    #    silently wrong, and the brief calls it out.
    for name, idx in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text, re.I):
            qualified = re.search(rf"\b(next|this|coming)\s+{name}\b", text, re.I)
            if not qualified and not answering:
                return FollowUpParse(
                    resolution=FollowUpResolution.AMBIGUOUS,
                    clarification_question=(
                        f"Did you mean this coming {name.capitalize()}, or the "
                        f"{name.capitalize()} after?"
                    ),
                    raw_instruction=instruction,
                    reasoning="bare weekday - could be either week",
                )
            days_ahead = (idx - now.weekday()) % 7 or 7
            if qualified and qualified.group(1).lower() == "next":
                days_ahead += 7 if days_ahead <= 7 else 0
            due = (now + timedelta(days=days_ahead)).replace(
                hour=hour if hour is not None else DEFAULT_HOUR,
                minute=minute or 0, second=0, microsecond=0,
            )
            return FollowUpParse(
                resolution=FollowUpResolution.RESOLVED,
                due_at=due,
                raw_instruction=instruction,
                reasoning=(
                    f"qualified weekday: {qualified.group(0)}" if qualified
                    else f"bare weekday '{name}' resolved because we asked"
                ),
            )

    # 6. Something was said about following up, but nothing we can pin down.
    #    Ask rather than default to a week.
    if re.search(r"\bfollow[\s-]?up\b|\bcall\b|\bmeet\b|\bremind\b", text, re.I):
        return FollowUpParse(
            resolution=FollowUpResolution.AMBIGUOUS,
            clarification_question=(
                "I couldn't work out when to schedule that. What date and time?"
            ),
            raw_instruction=instruction,
            reasoning="follow-up intent detected, no parseable timing",
        )

    return FollowUpParse(
        resolution=FollowUpResolution.NONE, raw_instruction=instruction
    )


def _extract_time(text: str) -> tuple[int | None, int | None]:
    m = _TIME.search(text)
    if not m:
        return None, None
    hour = int(m.group("h"))
    minute = int(m.group("min") or 0)
    ampm = (m.group("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return (hour if 0 <= hour <= 23 else None), minute
