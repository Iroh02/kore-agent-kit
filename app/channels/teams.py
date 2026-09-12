"""Microsoft Teams transport.  Owner: Vishal.

THREE PRIMITIVES ONLY. This file moves bytes; it never interprets them.
Anything that decides what bytes *mean* belongs in the pipeline.

    get_token()          -> bearer token for the Bot Framework
    send_activity(...)   -> post a message (or card) into a conversation
    fetch_attachment(...)-> return raw bytes for one attachment

No Bot Framework SDK. The protocol is plain JSON over HTTPS:

  token:  POST https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token
          grant_type=client_credentials
          client_id={MS_APP_ID}  client_secret={MS_APP_PASSWORD}
          scope=https://api.botframework.com/.default

  reply:  POST {serviceUrl}/v3/conversations/{conversationId}/activities
          Authorization: Bearer {token}

Roughly 80 lines when finished.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.schemas import Attachment, InboundEvent, InputKind
from app.settings import settings

TOKEN_URL = (
    "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
)
SCOPE = "https://api.botframework.com/.default"

# Teams sends files (and voice notes) with this contentType. The downloadUrl
# on it is PRE-AUTHENTICATED - a plain GET works, no bearer token.
FILE_DOWNLOAD_INFO = "application/vnd.microsoft.teams.file.download.info"

_token: str | None = None
_token_expires: float = 0.0


async def get_token() -> str:
    """Cached client-credentials token. Refreshes 60s before expiry."""
    global _token, _token_expires
    if _token and time.time() < _token_expires - 60:
        return _token
    if not settings.teams_enabled:
        raise RuntimeError("Teams credentials not configured (MS_APP_ID/PASSWORD)")

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.ms_app_id,
                "client_secret": settings.ms_app_password,
                "scope": SCOPE,
            },
        )
        resp.raise_for_status()
        payload = resp.json()

    _token = payload["access_token"]
    _token_expires = time.time() + int(payload.get("expires_in", 3600))
    return _token


async def send_activity(service_url: str, conversation_id: str, activity: dict) -> dict:
    """Post an activity into a conversation.

    Used for replies AND for proactive follow-ups days later - which is why
    conversation_id and service_url are stored on every Lead.
    """
    token = await get_token()
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    async with httpx.AsyncClient(timeout=20) as http:
        resp = await http.post(
            url, json=activity, headers={"Authorization": f"Bearer {token}"}
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}


async def fetch_attachment(att: Attachment) -> bytes:
    """Download one attachment. TWO PATHS, both needed.

    * files / voice notes: pre-authenticated downloadUrl -> plain GET
    * inline images: contentUrl -> needs the bot's bearer token
    """
    if not att.download_url:
        raise ValueError(f"attachment {att.name!r} has no download url")

    headers = {}
    if att.requires_auth:
        headers["Authorization"] = f"Bearer {await get_token()}"

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        resp = await http.get(att.download_url, headers=headers)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Activity -> InboundEvent
# ---------------------------------------------------------------------------


async def to_inbound_event(activity: dict) -> InboundEvent:
    """Normalize a Bot Framework Activity.

    TODO(Vishal): finish this against the REAL fixtures in fixtures/ rather
    than against this guess. Capture one of each first - text, inline image,
    file, .vcf, card button - then make this match what actually arrives.
    """
    raw_attachments = activity.get("attachments") or []
    attachments: list[Attachment] = []
    kind = InputKind.TEXT

    for raw in raw_attachments:
        content_type = raw.get("contentType", "")
        if content_type == FILE_DOWNLOAD_INFO:
            info = raw.get("content") or {}
            name = raw.get("name", "file")
            att = Attachment(
                name=name,
                content_type=info.get("fileType", "application/octet-stream"),
                download_url=info.get("downloadUrl"),
                requires_auth=False,  # pre-authenticated
            )
            lowered = name.lower()
            if lowered.endswith(".vcf"):
                kind = InputKind.CONTACT
            elif lowered.endswith((".m4a", ".mp3", ".wav", ".ogg", ".mp4")):
                kind = InputKind.AUDIO
        elif content_type.startswith("image/"):
            att = Attachment(
                name=raw.get("name", "image"),
                content_type=content_type,
                download_url=raw.get("contentUrl"),
                requires_auth=True,  # inline images need the bot token
            )
            kind = InputKind.IMAGE
        else:
            continue

        try:
            att.data = await fetch_attachment(att)
        except Exception:
            # Leave data unset; the pipeline turns that into a question
            # rather than a crash.
            pass
        attachments.append(att)

    value = activity.get("value")
    if value:
        kind = InputKind.COMMAND

    return InboundEvent(
        activity_id=activity.get("id", ""),
        conversation_id=(activity.get("conversation") or {}).get("id", ""),
        service_url=activity.get("serviceUrl", ""),
        user_id=(activity.get("from") or {}).get("id", ""),
        user_name=(activity.get("from") or {}).get("name", ""),
        channel="teams",
        kind=kind,
        text=(activity.get("text") or "").strip(),
        attachments=attachments,
        command=value,
        received_at=datetime.now(timezone.utc),
    )
