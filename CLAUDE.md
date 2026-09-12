# kore-agent-kit — Chat-to-Lead + Follow-up Automation

Intrakore AI Hackathon, Use Case 01. Build window 11:00–17:00, demo at 17:00.
Two people, one day.

**What it does:** a salesperson in Microsoft Teams sends lead details, meeting
notes and follow-up instructions to a bot. The bot extracts structured data,
persists it, confirms back what it created or asks for what's missing, and
schedules the follow-up. Every action is priced and timed.

> This repo previously held a RAG kit. That is gone. Files under `app/` that
> aren't in the layout table below are dead and pending deletion — do not
> import them, do not fix them.

## Hard constraints

- **Nothing crashes in front of the salesperson.** Every external call — Claude,
  speech-to-text, Teams — degrades to a typed error the bot can say out loud.
  A failed extraction asks a question. It never 500s into silence.
- **Never invent a field value.** A missing field comes back as `None` and the
  bot asks for it. Hallucinating a phone number is worse than admitting we
  didn't get one. This is the single most important rule in the repo.
- **Never silently guess a date.** `FollowUpParse` is tri-state:
  `RESOLVED | AMBIGUOUS | NONE`. "Follow up after 2 days" resolves.
  "Next week sometime" must return a question. The brief scores this.
- **Every LLM call is priced from real usage.** `response.usage`, real
  per-MTok rates, into the ledger. Never estimated, never skipped, never
  bolted on afterwards.
- **Idempotency on `activity_id`.** Teams retries deliveries. One message must
  never become two leads.

## Architecture

This is a **deterministic pipeline, not an agent.** Input type is known,
output schema is known, so control flow is code, not model-decided. That's
what makes cost and latency explainable — a scored requirement.

```
Teams ──> channels/teams.py ──> InboundEvent ──> pipeline.handle() ──> PipelineResult ──> Adaptive Card
                                                      │
                                   ┌──────────────────┼──────────────────┐
                                   │                  │                  │
                              extract.py         followup.py         store.py
                          (messages.parse)    (tri-state dates)   (interface + sqlite)
                                   │                  │                  │
                                   └──────── ledger.py (cost + latency) ─┘
```

**The one exception:** chat CRUD ("change the mobile for the Acme lead")
*is* open-ended, so it uses tool use via the SDK's own tool runner —
`client.beta.messages.tool_runner` with `strict: true` on each tool.
No agent framework. The SDK already has the loop; a framework would add an
abstraction over prompts we didn't write and make token attribution
impossible.

## Layout and ownership

Split by file. Do not edit someone else's column.

| Path | Role | Owner |
|---|---|---|
| `app/schemas.py` | **The contract.** Pydantic models both sides import | Nandita — announce before editing |
| `app/extract.py` | Claude extraction: text, vCard, vision, transcript | Nandita |
| `app/followup.py` | Date parsing, tri-state ambiguity | Nandita |
| `app/store.py` | `Store` interface + SQLite implementation + CRUD | Nandita |
| `app/ledger.py` | Cost + latency accounting, rate table | Nandita |
| `app/pipeline.py` | Router, retry/abstain policy, duplicate handling | Nandita |
| `app/scheduler.py` | Follow-up firing + proactive send | Nandita |
| `app/transcribe.py` | Speech-to-text vendor call | Nandita |
| `tests/` | Extraction evals against labelled fixtures | Nandita |
| `app/api.py` | FastAPI app, `/api/messages` webhook, REST CRUD | Vishal |
| `app/channels/teams.py` | Transport only: `get_token`, `send_activity`, `fetch_attachment` | Vishal |
| `app/channels/cards.py` | Adaptive Cards + button payloads | Vishal |
| `fixtures/` | Captured real Teams payloads | Vishal |

The line: **Vishal moves bytes, Nandita interprets them.** `teams.py` returns
raw attachment bytes and never inspects them; everything that decides what
bytes *mean* lives in the pipeline.

## Conventions

- **`schemas.py` is strict-schema friendly.** Flat fields, `Optional`, no
  `dict[str, X]`, no unions beyond `Optional`. These models go straight to
  `messages.parse(output_format=...)` and a clever type breaks the call.
- **Extraction returns a model or raises.** One retry with the validation
  error fed back, then abstain and ask. Never regex over model prose.
- **Model:** `claude-opus-5` for extraction and vision. Model IDs and rates
  live in `ledger.py` — one place, nowhere else.
- **Prompt caching:** stable system prompt behind a `cache_control`
  breakpoint, volatile content after it. Verify with
  `usage.cache_read_input_tokens` — a zero means something is invalidating it.
- **Every pipeline step appends a `CostEntry`**, including DB and channel
  calls where cost is 0 but latency isn't.
- **Anything mocked is labelled in the code and on the risks slide.** The
  brief scores transparency and punishes hidden gaps.

## Run it

```bash
uv sync
uv run uvicorn app.api:app --reload --port 8000
```

`/docs` gives the live OpenAPI page — use it as the architecture artifact in
the demo.

## Git

Both work on `main`. No branches, no PRs. `git pull --rebase` before every
push, push every 20–30 minutes. See `WORKING-AGREEMENT.md`.

Freeze at **16:15** — record the screen capture, then only demo-breaking
fixes. See `DECISIONS.md` for why every choice above was made.
