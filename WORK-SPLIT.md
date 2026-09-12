# Work split — Intrakore Hackathon, Use Case 01

Two people, 11:00–17:00, demo at 17:00. Split by file so we never edit the
same thing. The contract between us is `app/schemas.py`.

## The interface

Vishal produces an `InboundEvent` and renders a `PipelineResult`.
Nandita turns one into the other.

```python
from app.schemas import InboundEvent, PipelineResult
from app.pipeline import handle

result: PipelineResult = await handle(event)   # that's the whole contract
```

Both sides can be built against stubs from minute one.

## How the work is divided

Vishal owns **transport** — getting bytes in and out of Teams.
Nandita owns **everything that interprets bytes** — plus the two Teams pieces
that need the most judgment.

Vishal's half is the higher-*risk* half (Azure, tunnels, tenant permissions —
many small blockers, but documented). Nandita's is the higher-*judgment* half
(prompts, schemas, ambiguity, cost modelling — no blockers, but no recipe).

---

## Vishal — channel transport, cards, API surface

| File | What |
|---|---|
| `app/channels/teams.py` | Three primitives only: `get_token()`, `send_activity()`, `fetch_attachment()` |
| `app/channels/cards.py` | Adaptive Cards: lead confirmation, clarification prompt, CRUD buttons |
| `app/api.py` | FastAPI app, `POST /api/messages` webhook, REST CRUD endpoints over `store.py` |
| `fixtures/` | Real captured Teams payloads |
| Azure setup | Bot registration, dev tunnel, `manifest/` + icons, sideload |

**Order of work:**

1. **Azure Bot registration + dev tunnel + echo bot.** Nothing else until a
   Teams message round-trips. **If this isn't working by 12:00, say so out
   loud** — Nandita swaps in to help. A blocked channel is a dead demo, and
   it's the one risk worth both of us on it.
2. **Capture fixtures — the highest-leverage 15 minutes of the day.** Send the
   bot one of each and commit the raw Activity JSON to `fixtures/`:
   - plain text message
   - business card image (inline paste)
   - file attachment
   - shared contact / `.vcf`
   - Adaptive Card button press

   The moment those land, Nandita never needs the tunnel again.
3. `fetch_attachment()` — **two different paths, both needed:**
   - files and voice notes arrive as
     `application/vnd.microsoft.teams.file.download.info` with a
     **pre-authenticated** `downloadUrl` → plain GET
   - inline images arrive with a `contentUrl` that **needs the bot's bearer
     token**

   Return bytes. Don't interpret them — that's the pipeline's job.
4. Adaptive Cards. This is our Teams advantage: buttons give us **CRUD inside
   the chat**, which beats CRUD in a side dashboard.
5. REST CRUD in `api.py` over `store.py`, and the `/docs` page — that OpenAPI
   page is our architecture artifact in the demo.

**No SDK needed.** The Bot Framework protocol is plain JSON over HTTPS: get a
token from `login.microsoftonline.com/botframework.com/oauth2/v2.0/token`
(scope `https://api.botframework.com/.default`), then POST replies to
`{serviceUrl}/v3/conversations/{conversationId}/activities`. ~80 lines.

---

## Nandita — pipeline, extraction, judgment calls

| File | What |
|---|---|
| `app/schemas.py` | The contract — lands first |
| `app/extract.py` | Text / vCard / vision / transcript → `LeadExtraction` |
| `app/followup.py` | Tri-state date resolution — the hardest logic in the repo |
| `app/store.py` | Store interface, SQLite, dedupe, CRUD |
| `app/ledger.py` | Rate table, cost + latency accounting |
| `app/pipeline.py` | The router, retry/abstain policy, duplicate handling |
| `app/scheduler.py` | Follow-up firing + **proactive send** into a stored conversation |
| `app/transcribe.py` | Speech-to-text vendor call |
| `tests/` | Extraction evals with per-field precision/recall |

**Order of work:** schemas → store + ledger → text extraction → vision →
vCard → transcription → follow-up parsing → scheduler → evals.

**The four genuinely hard pieces, in order of difficulty:**

1. **Tri-state follow-up parsing.** Relative dates ("after 2 days") against a
   stamped `now`, explicit dates, timezone handling, and — the hard part —
   *detecting* ambiguity rather than resolving it confidently. "Next week
   sometime" and "Tuesday" (which Tuesday?) must both come back as questions.
2. **The abstain policy.** Validation failure → one retry with the error fed
   back → then ask. Low confidence → flag for review, don't write. Getting
   this wrong is how the system invents phone numbers.
3. **Proactive send + scheduler.** Storing `conversation_id`/`service_url` at
   lead creation, then posting into that conversation days later unprompted.
   Trickiest Teams surface, but it's pure logic once Vishal's
   `send_activity()` exists.
4. **Evals.** Per-field precision/recall over labelled fixtures. "9/10 company,
   10/10 email, 7/10 mobile" is a far stronger slide than "it works."

---

## Timeline (organisers' actual schedule)

Build time is **5 hours, not 6** - lunch is a hard pause.

| Time | |
|---|---|
| 11:00-13:00 | **Sprint 1 - think + prove.** Problem, architecture, data flow, risks, and the thinnest end-to-end proof. Both must contribute. |
| **13:00** | **5-min check-in with judges.** Have something live to show. |
| 13:15-14:00 | Lunch. Build pauses, not scored. Think, don't code. |
| 14:00-17:00 | **Sprint 2 - build + test.** Integration, edge cases, reliability, prepare the live demo. Only 3 hours. |
| **14:30** | **Go/no-go on Teams.** Not round-tripping? Demo via /api/simulate and say so. Decide calmly now, not at 16:20. |
| **16:30** | Organisers' 30-min warning. **Freeze here.** Record the screen capture. |
| 16:30-17:00 | Rehearse. Demo-breaking fixes only. |
| 17:00-18:00 | **Presentations: 20 min per team** - 15 min presentation + live demo, 5 min CXO Q&A. **Both of us present and answer.** |

## Presentation split - 15 minutes, both speak

| Who | Minutes | What |
|---|---|---|
| Nandita | 2 | Problem framing, and why a pipeline rather than an agent |
| Vishal | 3 | System flow, Teams channel, data mapping |
| Both | 6 | **Live demo** - the run of show below |
| Nandita | 2 | Cost + latency per component, and the sensitivity table |
| Vishal | 2 | Risks, what's mocked, what production needs |
| Both | 5 | CXO Q&A |

Rehearse the handoffs. Each of us must be able to answer a question about
the other's half - the brief says both answer questions.

## Demo run of show

Build toward this, in this order:

1. **Seed a "follow up in 2 minutes" at the start** so it fires live, mid-demo
2. Type lead details in Teams → card confirms → show the record
3. Business card photo → extracted → confirmed
4. Shared contact → **company missing → bot asks → you answer → created**
5. Voice note → transcribed → notes stored, original retained
6. "Follow up after 2 days" → scheduled. Then **"next week sometime" → bot asks
   which day**
7. The seeded follow-up fires in the chat
8. Edit a lead from the card, delete another — CRUD shown, not claimed
9. Cost + latency panel, per action, split by component
10. Risks slide

Beats 4 and 6 are the ones to rehearse. A system visibly refusing to invent
data is worth more than one that guesses right.

## Rules

- `git pull --rebase` before every push. Push every 20–30 minutes.
- Don't edit the other person's column. If `schemas.py` needs a change, say so
  in chat first — it breaks both sides at once.
- Use **fake contacts** for everything. Real PII goes to third-party model APIs
  otherwise, and screenshots then need redacting.

## What's mocked, and we say so

No Intrakore sandbox or credentials. `store.py` is an interface with a SQLite
implementation. The brief permits this — *"a working backend application **or
data store**"* — as long as we identify it. The risks slide names the boundary
and what production needs: auth and token refresh, field mapping, idempotency,
rate limits, error taxonomy, retry/DLQ.

**Do not gold-plate the mock.** Thirty minutes, not two hours.
