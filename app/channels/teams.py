"""Microsoft Teams transport.  Owner: Vishal.

THREE PRIMITIVES ONLY. This file moves bytes; it never interprets them.
Anything that decides what bytes *mean* belongs in the pipeline.

    get_token()          -> bearer token for the Bot Framework
    send_activity(...)   -> post a message (or card) into a conversation
    fetch_attachment(...)-> return raw bytes for one attachment

No Bot Framework SDK. The protocol is plain JSON over HTTPS:

  token:  POST https://login.microsoftonline.com/{authority}/oauth2/v2.0/token
          grant_type=client_credentials
          client_id={MS_APP_ID}  client_secret={MS_APP_PASSWORD}
          scope=https://api.botframework.com/.default

          {authority} is the TENANT ID for a Single Tenant bot, and the
          literal "botframework.com" for a Multi Tenant one. Using
          botframework.com against a single-tenant registration fails with
          AADSTS700016 "application not found in directory" - the app lives
          in our tenant, not Microsoft's. Our Azure Bot is Single Tenant.

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

SCOPE = "https://api.botframework.com/.default"


def _token_url() -> str:
    """Single Tenant bots authenticate against their own tenant, not Microsoft's."""
    authority = settings.ms_tenant_id or "botframework.com"
    return f"https://login.microsoftonline.com/{authority}/oauth2/v2.0/token"

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
            _token_url(),
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


AUDIO_SUFFIXES = (".m4a", ".mp3", ".wav", ".ogg", ".mp4", ".aac", ".webm")

# The bot's own ChannelAccount, learned from inbound traffic.
#
# A proactive send (the follow-up scheduler) has no inbound activity to copy
# addressing from, and the connector is strict about who the sender is:
# from.id = the MS_APP_ID guid is rejected 403, while the bot's channel
# account id is accepted. Every inbound activity addresses the bot as its
# `recipient`, so that is where this comes from - no hardcoded handle, and it
# stays correct per channel.
_bot_account: dict | None = None


def bot_account() -> dict | None:
    """The bot's ChannelAccount, or None if no inbound activity seen yet."""
    return _bot_account


def remember_bot_account(activity: dict) -> None:
    global _bot_account
    recipient = activity.get("recipient")
    if isinstance(recipient, dict) and recipient.get("id"):
        _bot_account = recipient


def _classify(name: str, content_type: str) -> InputKind | None:
    """What KIND of input an attachment represents, by type then by suffix."""
    lowered = (name or "").lower()
    if content_type.startswith("image/"):
        return InputKind.IMAGE
    if content_type.startswith("audio/") or lowered.endswith(AUDIO_SUFFIXES):
        return InputKind.AUDIO
    if content_type in ("text/vcard", "text/x-vcard") or lowered.endswith(".vcf"):
        return InputKind.CONTACT
    return None


async def to_inbound_event(activity: dict) -> InboundEvent:
    """Normalize a Bot Framework Activity. Written against the real payloads
    in fixtures/webchat/, not against a guess at the shape.

    Attachments arrive two ways and BOTH are handled:

      * Teams files and voice notes -> FILE_DOWNLOAD_INFO, whose downloadUrl
        is pre-authenticated, so a plain GET works.
      * anything uploaded through a web client (and Teams inline images) ->
        a contentUrl that needs the bot's bearer token.

    Everything that is not a card button is attached and classified. An
    earlier version matched only FILE_DOWNLOAD_INFO and image/*, and dropped
    the rest on an `else: continue` - which was worse than it sounds: a
    dropped attachment left kind=TEXT with empty text, so the pipeline ran
    lead extraction on "", got nothing back, and parked a clarification that
    then swallowed the user's NEXT message as its answer. Same failure shape
    as running the pipeline on conversationUpdate. Classify, never drop.
    """
    remember_bot_account(activity)

    raw_attachments = activity.get("attachments") or []
    attachments: list[Attachment] = []
    kinds: list[InputKind] = []

    for raw in raw_attachments:
        content_type = raw.get("contentType", "") or ""

        if content_type == FILE_DOWNLOAD_INFO:
            info = raw.get("content") or {}
            name = raw.get("name", "file")
            att = Attachment(
                name=name,
                content_type=info.get("fileType", "application/octet-stream"),
                download_url=info.get("downloadUrl"),
                requires_auth=False,  # pre-authenticated
            )
        else:
            url = raw.get("contentUrl")
            if not url:
                # Cards and other inline content carry no bytes to fetch.
                continue
            att = Attachment(
                name=raw.get("name", "attachment"),
                content_type=content_type or "application/octet-stream",
                download_url=url,
                requires_auth=True,  # web-client uploads need the bot token
            )

        found = _classify(att.name, att.content_type)
        if found:
            kinds.append(found)

        try:
            att.data = await fetch_attachment(att)
        except Exception as exc:  # noqa: BLE001 - a dead download is a question, not a crash
            # Leave data unset; the pipeline turns that into a question
            # rather than a crash. But say so on the console: this is the
            # only place a dead download is otherwise invisible, and the
            # auth story here is genuinely untested - a live Web Chat
            # attachment URL carries its own ?t= JWT AND gets a bearer
            # header, a combination that has never run against Microsoft's
            # server. If that 401s, this line is the difference between
            # diagnosing it in ten seconds and guessing.
            print(
                f"  [attachment fetch failed] {att.name} "
                f"({att.content_type}, auth={att.requires_auth}): "
                f"{type(exc).__name__}: {exc}"
            )
        attachments.append(att)

    # Most specific wins, so a caption plus a card photo is still an IMAGE.
    kind = InputKind.TEXT
    for candidate in (InputKind.CONTACT, InputKind.AUDIO, InputKind.IMAGE):
        if candidate in kinds:
            kind = candidate
            break

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
