"""Speech-to-text for voice notes.  Owner: Nandita.

Claude has no audio input, so this is the one place a second vendor is
needed. DECISIONS.md D14: Deepgram Nova, picked for signup speed and because
it returns audio duration, which the cost ledger needs.

Degrades rather than raises, like everything else here: with no key the mock
returns a canned transcript so the voice path can still be demonstrated and
is clearly labelled as mocked.

The brief requires storing the ORIGINAL input as well as the processed
version, so the caller keeps the raw bytes / transcript on the MeetingNote.
"""

from __future__ import annotations

import httpx

from app.ledger import Ledger
from app.schemas import Component
from app.settings import settings

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"

# Teams voice notes are usually m4a/mp4; files people attach may be anything.
# Deepgram sniffs the container, so passing the bytes through is enough.
DEFAULT_PARAMS = {
    "model": "nova-3",
    "smart_format": "true",   # punctuation and capitalisation
    "punctuate": "true",
    "language": "en",
}

MOCK_TRANSCRIPT = (
    "[MOCK TRANSCRIPT - no speech-to-text key set] "
    "Met Ahmed at the Marina site today. They are tendering a forty unit "
    "villa project, budget around three point two million. He wants a "
    "revised proposal. Follow up after 2 days."
)


class TranscriptionFailed(Exception):
    """Could not transcribe. The pipeline asks for text instead."""


def transcribe(audio: bytes, content_type: str, ledger: Ledger) -> tuple[str, float]:
    """Return (transcript, seconds_of_audio).

    Seconds is what the ledger prices on, so it comes back even on the mock
    path - a zero-cost entry with a real duration is still honest accounting.
    """
    if not settings.stt_api_key or settings.stt_provider == "mock-stt":
        with ledger.span(Component.STT, "mock-stt", "transcribe") as span:
            span.record_stt(0.0)
        return MOCK_TRANSCRIPT, 0.0

    with ledger.span(Component.STT, settings.stt_provider, "transcribe") as span:
        try:
            resp = httpx.post(
                DEEPGRAM_URL,
                params=DEFAULT_PARAMS,
                content=audio,
                headers={
                    "Authorization": f"Token {settings.stt_api_key}",
                    "Content-Type": content_type or "audio/mp4",
                },
                timeout=60,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            raise TranscriptionFailed(
                f"HTTP {exc.response.status_code}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise TranscriptionFailed(f"speech-to-text unreachable: {exc}") from exc

        seconds = float(
            (payload.get("metadata") or {}).get("duration", 0.0)
        )
        span.record_stt(seconds)

        try:
            transcript = (
                payload["results"]["channels"][0]["alternatives"][0]["transcript"]
            )
        except (KeyError, IndexError) as exc:
            # A 200 with an unexpected envelope. Surface the shape, not a
            # bare KeyError - that is the worst debugging trap there is.
            raise TranscriptionFailed(
                f"unexpected response shape: {str(payload)[:300]}"
            ) from exc

    if not transcript.strip():
        raise TranscriptionFailed("empty transcript - audio may be silent")

    return transcript, seconds
