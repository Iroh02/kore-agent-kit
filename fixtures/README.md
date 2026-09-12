# Captured Activity fixtures

Real payloads, so `to_inbound_event` can be written against what actually
arrives rather than against a guess.

## Read this before trusting a fixture

**These are Web Chat, not Teams.** Web Chat is the real Bot Framework and the
real Adaptive Card renderer, so it proves the protocol. It does **not** shape
attachments the way Teams does. Specifically:

| Path | Validated by these fixtures? | Why |
|---|---|---|
| plain text | **yes** | identical shape on both channels |
| Adaptive Card button press | **yes** | `Action.Submit` posts back a top-level `value` on both |
| inline image | **partly** | Web Chat gives `contentUrl` + a `t=` JWT. Teams gives a `contentUrl` needing the *bot's bearer token*. Auth model differs. |
| file attachment | **no** | Teams sends `application/vnd.microsoft.teams.file.download.info` with a pre-authenticated `downloadUrl`. Web Chat has no equivalent. |
| `.vcf` contact | **no** | arrives via the Teams file path above |

So the two `fetch_attachment` branches in `channels/teams.py` are **not**
covered here. They need a real Teams client to confirm.

## What's here

`webchat/` — sanitized, committed, safe to read.

- `message_text_*` — plain text lead details
- `message_cardbutton_*` — `Action.Submit` press. Note `value` is top-level
  and `type` is still `message` (not `invoke`), which is why
  `to_inbound_event` keys on `activity.get("value")`
- `message_jpeg_*` — inline image, Web Chat flavour
- `typing_*`, `conversationUpdate_*` — the noise a real client also sends;
  worth knowing the webhook receives these, not just messages

`raw/` — gitignored, never committed. See below.

## Why raw/ is gitignored

This repo is public and raw captures carry live credentials:

- `attachments[].contentUrl` has a ~1kB JWT in its `t=` query parameter
- `recipient.id` embeds an Azure-issued key containing the `JQQJ99` marker
  that Microsoft's secret scanners look for
- `thumbnailUrl` inlines the sender's actual photo as base64

`sanitize.py` strips all of that while preserving structure exactly. After
capturing new payloads:

```bash
python fixtures/sanitize.py
```

then commit `webchat/` only. Never commit `raw/`.
