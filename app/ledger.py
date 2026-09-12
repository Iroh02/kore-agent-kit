"""Cost and latency accounting.

The brief asks for: "total cost, model / service used and end-to-end latency,
with a component-level breakdown (for example OCR / speech-to-text / LLM /
API / database)."

This is a quarter of what gets demoed at 17:00 and it CANNOT be reconstructed
afterwards. Every pipeline step opens a span; the span records real usage.

Two rules:
  1. Cost comes from `response.usage`, never from an estimate.
  2. Steps with no cost (DB, channel API) still record latency.

Usage:

    led = Ledger(trace_id=..., activity_id=...)

    with led.span(Component.LLM, "claude-opus-5") as s:
        resp = client.messages.parse(...)
        s.record_claude(resp.usage)

    with led.span(Component.DB, "sqlite"):
        store.create_lead(lead)

    result_ledger = led.finish()
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.schemas import ActivityLedger, Component, CostEntry

# ---------------------------------------------------------------------------
# Rate table - the ONLY place prices live
# ---------------------------------------------------------------------------
#
# USD per million tokens, Anthropic first-party API rates.
# Verify against https://www.anthropic.com/pricing before quoting on a slide.

CLAUDE_RATES: dict[str, tuple[float, float]] = {
    # model id            (input $/MTok, output $/MTok)
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Prompt-caching multipliers against the base input rate.
# NOTE: verify these against current pricing docs before putting them on a
# slide - they are the standard multipliers, not a quoted per-model figure.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

# Speech-to-text, USD per minute of audio. Set whichever vendor we picked.
STT_RATES: dict[str, float] = {
    "deepgram-nova-3": 0.0043,
    "azure-speech-standard": 0.0167,
    "mock-stt": 0.0,
}


def claude_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Price one Claude call from its real token usage."""
    rate_in, rate_out = CLAUDE_RATES.get(model, (0.0, 0.0))
    per_token_in = rate_in / 1_000_000
    per_token_out = rate_out / 1_000_000
    return (
        input_tokens * per_token_in
        + output_tokens * per_token_out
        + cache_read_tokens * per_token_in * CACHE_READ_MULTIPLIER
        + cache_write_tokens * per_token_in * CACHE_WRITE_MULTIPLIER
    )


def stt_cost(service: str, seconds: float) -> float:
    return STT_RATES.get(service, 0.0) * (seconds / 60.0)


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------


@dataclass
class Span:
    """One timed step. Call a `record_*` method to attach cost."""

    component: Component
    service: str
    detail: str = ""
    input_units: float = 0.0
    output_units: float = 0.0
    cached_input_units: float = 0.0
    unit_label: str = "tokens"
    cost_usd: float = 0.0
    _started: float = field(default_factory=time.perf_counter)
    latency_ms: float = 0.0

    def record_claude(self, usage) -> None:
        """Attach real token usage from an Anthropic response.

        `usage` is the SDK's usage object. Cache fields are absent on some
        responses, hence the getattr defaults.
        """
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

        self.input_units = input_tokens
        self.output_units = output_tokens
        self.cached_input_units = cache_read
        self.unit_label = "tokens"
        self.cost_usd = claude_cost(
            self.service, input_tokens, output_tokens, cache_read, cache_write
        )

    def record_stt(self, seconds: float) -> None:
        self.input_units = seconds
        self.unit_label = "seconds"
        self.cost_usd = stt_cost(self.service, seconds)

    def to_entry(self) -> CostEntry:
        return CostEntry(
            component=self.component,
            service=self.service,
            input_units=self.input_units,
            output_units=self.output_units,
            cached_input_units=self.cached_input_units,
            unit_label=self.unit_label,
            cost_usd=round(self.cost_usd, 6),
            latency_ms=round(self.latency_ms, 2),
            detail=self.detail,
        )


class Ledger:
    """Accumulates spans for one processed activity."""

    def __init__(self, trace_id: str, activity_id: str) -> None:
        self.trace_id = trace_id
        self.activity_id = activity_id
        self._spans: list[Span] = []
        self._started = time.perf_counter()

    @contextmanager
    def span(self, component: Component, service: str, detail: str = ""):
        """Time a step. Records latency even if the step raises.

        A failed step is still a cost and still a latency - dropping it would
        make the economics panel lie about failures.
        """
        s = Span(component=component, service=service, detail=detail)
        try:
            yield s
        finally:
            s.latency_ms = (time.perf_counter() - s._started) * 1000
            self._spans.append(s)

    def finish(self) -> ActivityLedger:
        entries = [s.to_entry() for s in self._spans]
        return ActivityLedger(
            trace_id=self.trace_id,
            activity_id=self.activity_id,
            entries=entries,
            total_cost_usd=round(sum(e.cost_usd for e in entries), 6),
            # Wall clock, not the sum of spans - concurrent steps would
            # otherwise inflate it. This is the "end-to-end latency" the
            # brief asks for; per-span figures give the breakdown.
            total_latency_ms=round((time.perf_counter() - self._started) * 1000, 2),
        )
