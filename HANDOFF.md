# HANDOFF — state of the build as at 15:55, 12 Sep 2026

Read this first in a fresh session. It is the complete state. `DECISIONS.md`
has the *why* for every choice; this file has the *what is true right now*.

Hard stop **16:00**. Presentations **17:00–18:00**, 20 min per team: 15 min
presentation + live demo, 5 min CXO Q&A, **both present**. Rehearse twice.

---

## Status in one line

**The whole pipeline works end to end and is tested. The demo runs in Azure
"Test in Web Chat" because Teams sideloading is blocked at tenant level.**
Demo machine is **Vishal's laptop**; Nandita opens his tunnel URL for the
dashboard on the projector.

## Verified working (all with real Claude, real Deepgram)

| Capability | Evidence |
|---|---|
| Mode 1 — free text → lead | `demo_check` + evals, Sonnet 5 low effort, ~$0.002, ~2.4–3s |
| Mode 2 — `.vcf` contact → lead | deterministic parse, **$0.000**, ~3ms; refuses when company missing |
| Mode 3 — business card → lead | Opus 5 vision, ~$0.011, ~4–5s; 4 cards 5/5 in evals |
| Voice note → transcript → notes/lead | **real Deepgram**, `stt $0.0015 + llm $0.002`; also works sent cold |
| Meeting notes: summary, key points, action items, **original retained** | `attach_note`, via "Add note" button |
| Follow-up tri-state (resolved / ambiguous → asks / none) | `followup.py`; spoken numbers ("two days") work |
| Both clarification loops (company, follow-up date) answerable by typing | `pending_clarifications`; expire 10 min; new-message guard (`@`, 2+ commas, >60 chars, >8 words re-routes; emoji / `?` re-asks) |
| `cancel` / `never mind` / `stop` escapes any pending state and says what was dropped | `_cancel_pending`; $0, no model call |
| Duplicate detection, reports which field matched | email then mobile, last-9 digits |
| Idempotency on `activity_id` | replay → no second lead |
| CRUD: create / read / update / delete, cascade on delete | REST + card buttons |
| Scheduler fires due follow-ups → dashboard always, chat when configured | `scheduler.py`, Vishal added the envelope |
| Cost + latency per component from real usage | `ledger.py`; rates verified against pricing pages |
| Live dashboard (SSE) with confidence column, follow-ups, component split | `ui/dashboard.html` |
| Adaptive Cards with Add note / Edit / Delete + cost line, rendering in Web Chat | Vishal |
| Typing indicator, concurrent with the pipeline | Vishal |
| `tests/demo_check.py` | **25/25** (8 pending-state guard checks added 15:10) |
| `tests/evals.py` | **70/70**, five fields, 14 labelled cases, $0.07/run |

## Measured numbers for the slides

| Mode | Model | Cost | Latency |
|---|---|---|---|
| Shared contact | none | **$0.000000** | ~3 ms |
| Free text | Sonnet 5 / low | $0.0019–0.0029 | 2.4–3.0 s |
| Business card | Opus 5 / default | $0.009–0.011 | 3.6–5 s |
| Voice note | Deepgram + Sonnet 5 | $0.0034 | ~6 s |

Tuning story: text path went **4965ms / $0.0097 → 2396ms / $0.0029** by
measuring four configs (effort + model) and selecting per path. Vision kept
on Opus at full effort deliberately. Haiku 4.5 rejected (400 on `effort`).

Confidence calibration (from evals): clean text 0.90, messy 0.95,
name-only **0.50**, "thanks see you tomorrow" **0.20**, email-domain-only
company → **null** at 0.80. Review threshold 0.6 does real work.

Sensitivity: 10/day $0.06 · 100/day $0.57 · 1,000/day $5.70 · 10,000/day $57.

Vendor (D16): Gemini 2.5 Flash is ~5× cheaper and has native audio — the
first week-two experiment, against the eval set. **Intrakore runs on AWS
(verified by DNS: EC2 us-east-1), not Azure** — the alignment line is
"Claude is native on Amazon Bedrock, inside your AWS account". Do NOT say
"same price".

## Bugs found today by exercising the demo (say this on stage)

1. `conversationUpdate` ran the pipeline → unprompted "which company?" card
   that ate the first real lead (Vishal)
2. Replies silently 400'd — `Activity.From` missing (Vishal)
3. Single Tenant token authority (Vishal)
4. Buttons claiming writes they never made — `provide_company` removed (both)
5. Base64 attachments utf-8-encoded into bytes → every image/audio via the
   API was corrupt; vCards passed by accident and hid it
6. Stale unanswered question hijacked the next message — notes became a
   30-word "company name"
7. Spoken numbers ("two days") unparsed → every voice follow-up ambiguous
8. Bare voice note (no Add-note tap) failed outright
9. `.env` pinned `EXTRACTION_MODEL=opus` and silently overrode the tuning
10. Raw Web Chat captures contained live JWTs — repo is public (Vishal)
11. Open "which company?" accepted a whole lead line with an email in it as
    the company name, under the 8-word guard (Vishal reproduced live)
12. No way out of a pending state — a mistaken "Add note" tap or an unwanted
    question stuck until the 10-minute expiry
13. Anthropic client had SDK default timeouts (600 s × 3): a hung connection
    froze the single-worker process ~30 min. Now 25 s × 2 (~51 s worst case)
14. Card Edit saved with blank fields replied "Updated  for X" having written
    nothing; a lone space wiped a stored mobile and its dedupe key
15. Answering a date question after the lead was deleted said "follow-up set"
    for a row that no longer existed
16. A `.vcf` whose download failed parsed as an all-None lead at confidence
    1.0 and the bot said "I've got this contact"
17. A photo or `.vcf` arriving while a question / Add-note was open left it
    armed, so the next typed sentence became that lead's company name
18. Follow-up times were UTC: "in 2 minutes" printed a clock 4 h off the
    wall, and the dashboard (browser-local) disagreed with the card. Now
    parsed in Asia/Dubai (`followup.LOCAL_TZ`), stored UTC, shown local

## How to run

```
.venv\Scripts\python -m uvicorn app.api:app --port 8000     # server
http://localhost:8000                                        # dashboard
.venv\Scripts\python -m tests.demo_check                     # 25/25
.venv\Scripts\python -m tests.evals                          # 70/70
.venv\Scripts\python tools\send.py demo                      # run of show, one beat per keypress
.venv\Scripts\python tools\send.py reset                     # wipe leads before a rehearsal
.venv\Scripts\python tools\send.py voice <file.m4a>          # test a voice note
```

`.env` needs `ANTHROPIC_API_KEY` and `STT_API_KEY` (Deepgram). Models are
set in `settings.py`, not `.env`. `uv` was not on Nandita's machine; plain
venv + `pip install -e .` works. Vishal uses `uv sync` — both fine.

## Gotchas that will bite during the demo

- **Don't run scripts against `kore.db` directly** while the server runs —
  stale-read. `send.py` is safe (goes via HTTP). `demo_check`/`evals` use
  their own DBs.
- **`send.py reset` then reload the dashboard** before each rehearsal and
  before 17:00 — the dashboard counters are client-side.
- **Dashboard averages (fixed 15:35):** a Teams retry returns the original
  result with the same `trace_id` and the webhook publishes it again, so
  the dashboard was counting cost and latency twice. It now dedupes on
  `trace_id` and tags the entry "replay · not counted". The latency tile
  shows two figures: all activities (button taps and `.vcf` parses at ~3 ms
  included) and model calls only. Quote the second one against the slide
  table. Still not in the total on the Teams path: attachment download
  (happens before the ledger starts) — Vishal's column.
- An unanswered bot question stays live 10 min. Tapping "Add note" clears it.
  Typing `cancel` or `never mind` clears any pending state and says so. Any
  photo / `.vcf` that isn't claimed as an answer also clears it (15:50).
- **A follow-up typed in the same message as a new lead is ignored.** Only
  `attach_note` parses follow-ups. Beat 6: tap "Add note" first, then type.
- `demo_check` prints `due … 05:00` — that is UTC storage; the bot's
  message says 09:00 local. Both correct.
- Web Chat: **file and `.vcf` attachments are unvalidated** (need a real
  Teams client). Mode 2 demos via `send.py vcf` landing on the dashboard —
  say so plainly.
- Deepgram heard synthetic TTS "Skyline Fitout" as "skyline feet out".
  Record a real human voice note before the demo; keep a typed lead as backup.
- Only ONE machine can be the bot's messaging endpoint. It's Vishal's.

## Run of show (17:00)

1. Seed "follow up in 2 minutes" — fires live on the dashboard mid-demo
2. Business card **with no company** → bot refuses to guess, asks → answer → created  ← strongest beat
3. Free-text lead → card with buttons
4. Duplicate → refused, "matched on email"
5. Voice note → transcribed → notes stored, original retained (the one that gets caught as a duplicate on mobile is the best version)
6. "Follow up next week sometime" → bot asks which day → "Monday" → scheduled
7. The seeded reminder fires
8. Edit and Delete from the card
9. Economics panel: per action, component split
10. Risks / what's mocked

## Presentation split (15 min + 5 Q&A)

| Who | Min | What |
|---|---|---|
| Nandita | 2 | Problem: "the lead discussed in Teams that never reaches the CRM" — Intrakore's own margin-in-the-gaps thesis |
| Nandita | 2 | Architecture: deterministic pipeline not an agent; model in 2 files; why costs are explainable |
| Vishal | 3 | Teams channel, Web Chat, the token/envelope war stories, data mapping |
| Both | 5 | Live demo |
| Nandita | 2 | Cost table, tuning story, confidence table, evals |
| Vishal | 1 | Risks + what's mocked: SQLite not Intrakore CRM; no JWT validation; PII to third-party APIs; sideloading |
| Both | 5 | Q&A |

CXO answers ready: Bedrock (not Foundry — they're AWS); sensitivity table;
two-file vendor swap; null-not-guess; PII needs DPA + redaction in prod.

## What NOT to do

- **Do not deploy.** Tunnel is a public URL; Web Chat is a real channel;
  Bedrock is the production answer on a slide.
- **Do not switch models.** Measured, tested, 25/25. Gemini is a week-two
  experiment.
- **No new features.** Every bug today came from running the demo, not
  adding to it.

## Open / not done (all cuttable)

- Free-text CRUD via tool use ("change the mobile for Acme") — D4, not built
- Adversarial card set hard enough to lower confidence
- Gemini comparison against the eval set
- Inbound JWT validation (named on risks slide)
- From the 15:30 edge-case audit (`handover-nandita-edgecases.md`), NOT done:
  invalid / past ISO dates in `followup.py` crash to the generic error or
  schedule in the past (only reachable by typing `2026-09-31`); "I don't
  know" filed as a company name; two contacts in one message drops the
  second silently; `_persist_lead` ignores a follow-up in a one-message
  lead — so **beat 6 must be "tap Add note, then type"**.
- Vishal's latency note (`for-nandita-latency-and-bugs.md`, 15:05): the text
  path is 99.9% Claude output tokens at ~50–70 tok/s; `source_quote` is
  ~15–25 of the ~147. Dropping it is a `schemas.py` contract change plus an
  eval rerun — week two, not before the demo.

## Repo / people

- github.com/Iroh02/kore-agent-kit — Nandita is `Iroh02`, Vishal is `Vishal4507`
- Ownership: Nandita = schemas, extract, followup, store, ledger, pipeline,
  scheduler, transcribe, tests, tools; Vishal = api, channels/, fixtures,
  manifest. `ui/dashboard.html` was written by Nandita's side.
- Both on `main`, `git pull --rebase` before push. Docs: CLAUDE.md,
  DECISIONS.md (D1–D16), WORK-SPLIT.md, this file.
- Build board artifact: https://claude.ai/code/artifact/3a4ce2ae-6473-434c-8eb0-b22eada3a0e0
