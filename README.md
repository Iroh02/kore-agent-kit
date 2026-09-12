# kore-agent-kit — Chat-to-Lead + Follow-up Automation

A Microsoft Teams bot that turns a salesperson's messages into structured
leads, meeting notes and follow-ups — with the cost and latency of every
action broken down by component.

Built for **Intrakore AI Hackathon, Use Case 01**.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e .          # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn app.api:app --reload --port 8000
```

- `http://localhost:8000` — live dashboard: records and economics as they happen
- `http://localhost:8000/docs` — OpenAPI

It runs with **no API key**. Claude, Teams and speech-to-text each degrade to
a clearly-labelled mock rather than failing, and `/api/health` reports which
is which. Drop keys into `.env` (copy `.env.example`) to go live.

## What it does

| Input | How it arrives | Handling |
|---|---|---|
| Free-text details | Teams message | Claude structured extraction |
| Shared contact | `.vcf` attachment | Deterministic parse — no model, cannot hallucinate |
| Business card | Photo | Claude vision, one call, no separate OCR |
| Meeting notes | Text or voice note | Transcribed if voice; original always retained |
| Follow-up | "follow up after 2 days" | Resolved, or **asked about** if ambiguous |

Full CRUD on leads, notes and follow-ups — from Adaptive Card buttons in chat
and from the REST API.

## Three rules the code holds to

- **Never invent a field value.** Missing comes back as `null` and the bot
  asks. A hallucinated phone number is the worst thing this system can do.
- **Never silently guess a date.** `FollowUpParse` is tri-state:
  `RESOLVED | AMBIGUOUS | NONE`.
- **Nothing crashes in front of the salesperson.** Every external call
  degrades to a typed error the bot can say out loud.

## Layout

| Path | Role |
|---|---|
| `app/schemas.py` | The contract between the channel and pipeline halves |
| `app/pipeline.py` | Router — idempotency, dedupe, clarification |
| `app/extract.py` | Text, vCard, vision, transcript → validated models |
| `app/followup.py` | Tri-state date resolution |
| `app/store.py` | `Store` interface + SQLite, CRUD, dedupe |
| `app/ledger.py` | Cost + latency from real token usage |
| `app/transcribe.py` | Speech-to-text |
| `app/api.py` | FastAPI: webhook, REST CRUD, SSE feed |
| `app/channels/` | Teams transport and Adaptive Cards |
| `ui/dashboard.html` | Live projected dashboard |

## Architecture

A **deterministic pipeline, not an agent.** Input type is known and output
schema is known, so control flow is code — which is what makes the cost and
latency figures explainable. The one open-ended surface, free-text CRUD, uses
tool calling via the SDK's own tool runner. No agent framework.

## What is mocked

There is no Intrakore sandbox or credentials, so persistence is our own
SQLite store behind a `Store` interface, not the Intrakore CRM. The brief
permits *"a working backend application or data store"*. A production
integration would need auth and token refresh, field mapping, idempotency
keys, rate limits, an error taxonomy and a retry/DLQ path.

## Working here

[`DECISIONS.md`](DECISIONS.md) — every choice, what it rejected, what it costs.
[`WORK-SPLIT.md`](WORK-SPLIT.md) — who owns what, and the demo run of show.
[`CLAUDE.md`](CLAUDE.md) — hard constraints.
[`WORKING-AGREEMENT.md`](WORKING-AGREEMENT.md) — git discipline.
