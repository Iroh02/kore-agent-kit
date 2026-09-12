# THE SHARED PROTOTYPE REFERENCE
### Chat-to-Lead + Follow-up Automation — Intrakore AI Hackathon, Use Case 01
**Read this before 17:00. Both of you. It is the one document where your two halves agree.**

Ground rule for the next 45 minutes: if a number or a claim is not in this document, do not say it on stage. Everything here is traced to code, to `HANDOFF.md`, to `DECISIONS.md`, or to the real `demo_check` ledger captured at 16:01–16:02 today. Anything unverifiable is flagged in red text, not quietly omitted — because the thing that loses points is a judge finding a gap you didn't name.

---

## 0. THE SIX THINGS NEITHER OF YOU SAYS

These are wrong or unsupported in the current drafts. Fix them in your head now.

| Don't say | Say instead | Why |
|---|---|---|
| "twenty-four defects" | **"nineteen — the slide shows twelve, we found seven more after we built it"** | 24 appears only in `PRESENTATION.md:285`. No list of 24 exists anywhere. |
| "about eighty lines we wrote ourselves" | **"the Teams transport is a hundred and thirty lines of code, the cards another hundred and eighteen"** | 80 is the aspiration in the file's own docstring. Measured: 130 code lines in `teams.py`, 118 in `cards.py`. |
| "we use tool use for chat CRUD" | **"free-text CRUD is the one surface that would earn an agent — that's our test, and it's the next thing we build. Today CRUD is card buttons."** | `tool_runner` / `tools=` appear nowhere in the repo. `CLAUDE.md` and D4 both describe it in the present tense; the *deck* is correct (week two). |
| "it pulled the project and budget out of the spoken note" | Only true if project + budget are in the **beat-1 typed lead message**. The notes path cannot write those fields. | `project_name` / `estimated_value` are written in exactly one place: `pipeline.py:468–470`, inside `_persist_lead`. |
| "the typing indicator runs concurrently" | **"we fire a typing indicator so the wait isn't silent"** | `asyncio.create_task` schedules it, but nothing yields before `await pipeline.handle(...)`, so it fires after. Cosmetically identical, factually wrong. |
| "17/17" (if anyone opens D16 on stage) | **25/25** | `DECISIONS.md:250` is stale. |

**One more, agreed between you:** the first business card of the session costs **about two cents**, not the slide's one cent, because it pays the prompt-cache write. Nandita narrates this. Vishal does not contradict it. See §4.3.

---

## 1. WHAT THE PRODUCT IS — one paragraph

A salesperson meets someone. The details are on a business card in their pocket, in a shared contact, or in a voice note recorded walking back to the car — and by the time anyone types them into a CRM, if ever, they are three days old and half of them are gone. This system closes that gap without asking the salesperson to change what they do: they send whatever they have into the Microsoft Teams chat window that is already open — typed text, a `.vcf` contact, a photographed business card, a voice note — then meeting notes, then a follow-up instruction in their own words. A deterministic pipeline extracts structured fields, checks for duplicates, persists a record, and replies **in the chat** with an Adaptive Card that either confirms exactly what was created or asks for precisely what is missing, with Add-note / Edit / Delete buttons on it so CRUD never leaves the conversation. Follow-ups are parsed tri-state and fire back into the same chat unprompted at the scheduled time. Every single action is priced and timed from real API usage and shown per component. The product is **lead capture, not lead generation**, and its defining behaviour is that it refuses to invent: a missing company becomes a question, an ambiguous date becomes a question, and refusing to guess is measurably free.

---

## 2. WHAT HAPPENS TO ONE MESSAGE — end to end

This is the walkthrough both of you should be able to give. The handover point between your halves is marked. Station names are real function names — if a judge asks "where does that happen", you can name the file.

### Inbound — Vishal's half

**1. `POST /api/messages`** (`app/api.py`). Bot Framework posts every activity here over the dev tunnel. There is **no JWT validation** — `TODO(Vishal)` in the code, named on the risks slide.

**2. `_capture_activity()`** writes the raw JSON to `fixtures/raw/` (gitignored; sanitized copies are what's committed). This is why the pipeline could be built all day against real payloads with the channel down.

**3. Type gate.** `if activity.get("type") != "message": return 200`. Bot Framework delivers `conversationUpdate` (chat opened) and `typing` to the same webhook. Acting on those was defect #1 — a spurious "which company?" card ~2.6 s after the chat opened, which then ate the first real lead. Captured, never acted on.

**4. `to_inbound_event(activity)`** (`app/channels/teams.py`) — the only place Teams vocabulary exists. It normalises the Bot Framework Activity into an `InboundEvent`, downloads any attachment via `fetch_attachment()`, and classifies it (content type first, filename suffix second, most specific first). Attachment download is **timed here and folded into the ledger as a `CHANNEL_API` span**, because it happens before the pipeline opens its ledger and was otherwise invisible in the economics panel.

**5. Replay check.** `store.seen_activity(...)` — used here to decide whether to re-publish to the dashboard and re-count the cost. A redelivered activity must still get a reply, but must not be counted twice.

**6. Typing indicator** is scheduled as a task, then the pipeline is awaited.

> **⟶ HANDOVER.** Everything past this point receives a plain Python `InboundEvent` and knows nothing about Teams. *"That's where my half ends and Nandita's begins."* / *"That's where Vishal hands me an InboundEvent."*

### The pipeline — Nandita's half

**7. `pipeline.handle(event, store)`** mints a `trace_id` and opens a `Ledger`. First real action: **idempotency**. `store.seen_activity(activity_id)` — if seen, return the **original** `PipelineResult`, original trace_id, original ledger. Costs nothing, creates nothing (D10).

**8. `_route()` — the fixed ladder.** No model is asked what to do next:
   - `COMMAND` (an Adaptive Card button press) always wins — dispatched by `action` string.
   - `TEXT`: `cancel` / `never mind` / `stop` first, so it can never be swallowed as an answer → then a pending clarification (expired after **600 s** is cleared as stale) → this message is the *answer*, not a new lead.
   - `TEXT` or `AUDIO`: a pending "Add note" scope → this is a note on that lead.
   - Nothing claimed it → clear any stale pending state (a photo or `.vcf` used to sail past and leave the flag armed) → **capture**.

**9. `_extract_for(kind)`** picks the extractor by input kind:

| Kind | Path | Model | Effort |
|---|---|---|---|
| TEXT | `extract_lead_from_text` | `claude-sonnet-5` | low |
| IMAGE | `extract_lead_from_image` | `claude-opus-5` | default |
| CONTACT | `parse_vcard` | **none — deterministic** | — |
| AUDIO | `transcribe` → text path | Deepgram Nova-3 + Sonnet 5 | low |

**10. Schema-validated extraction (D6).** `client.messages.parse(output_format=LeadExtraction)`. The model **fills a form; it never writes prose we then parse**. Validation failure → one retry with the actual validation error appended as a user turn → still invalid → `ExtractionFailed` → abstain and ask for the details as text. An `APIError` skips the retry (the SDK already retried) and goes straight to abstain. Client is bounded at **25 s × 2 retries (~51 s worst case)**.

**11. Every field is `Optional`.** `company_name` is `REQUIRED`; `first_name / last_name / mobile / email` are `NICE_TO_HAVE`. A missing company **parks the whole extraction** in `pending_clarifications` and asks — it is not discarded, which is why answering the question later costs **$0.000000**. Missing nice-to-haves still create the lead, and the card names what's still missing. `confidence < 0.6` → `LeadStatus.NEEDS_REVIEW`. Nothing extracted at all → "I didn't spot lead details in that…" and **nothing parked**.

**12. Dedupe (D12).** `store.find_duplicate(email, mobile)` — normalised email first, then normalised mobile (digits only, **last 9 kept**, so `+971 50 123 4567`, `00971501234567` and `050 123 4567` all collide). Returns which field matched. **Nothing is merged**: status `DUPLICATE`, no row written, and the bot offers to update the existing lead.

**13. Persist**, then `led.finish()` records **wall-clock** end-to-end latency, not the sum of spans, so concurrent steps don't inflate it. Every step wrote a span — including DB and channel steps at **$0 cost with real latency**.

**14. `store.mark_activity(activity_id, result_json)`** — the idempotency record, storing the full result so a replay can return it verbatim.

### Outbound — Vishal's half again

**15. `cards.render(result)`** (`app/channels/cards.py`) — Adaptive Card **schema 1.5**. Four types: lead confirmation (Add note / Edit / Delete), clarification question, duplicate notice, plain text. Every card carries a cost line: `$0.0029 · 2396 ms · llm + db`.

**16. `_envelope()`** adds `Activity.From` — **the bot is the inbound activity's `recipient`, the user is its `from`**. Without it the connector returns `400 MissingProperty` on every reply (defect #2).

**17. `teams.send_activity(serviceUrl, conversationId, reply)`** — the reply reaches the chat *only* this way; Bot Framework ignores the webhook's HTTP response body. Send failures are **swallowed deliberately**: a non-200 back to Bot Framework triggers redelivery, and redelivery is exactly how one message becomes two leads.

**18. `publish()`** pushes the result over SSE to the live dashboard (`ui/dashboard.html`), which dedupes on `trace_id` and tags replays "replay · not counted".

**19. `return 200`.**

### Later — the follow-up

**20. `scheduler.py`** polls every **30 s** for due follow-ups and posts a proactive reminder into the stored conversation. A proactive send has no inbound activity to copy addressing from, so `teams.py` caches the **bot's own ChannelAccount** learned from inbound traffic. Using the `MS_APP_ID` GUID instead returns **403**; the channel account returns **200** (measured live, same conversation). The reminder always lands on the dashboard; it lands in the chat when the channel is configured **and the bot has seen at least one inbound message since the last server restart**.

---

## 3. THE DESIGN DECISIONS — D1 to D16

Each with the reasoning, because the reasoning is what gets scored.

**D1 — Microsoft Teams is the platform.** Assigned, not chosen. Teams is the heaviest of the three options: Azure AD registration, Bot Framework, a public HTTPS callback, a manifest, and tenant permission to sideload — Telegram would have been ten minutes. So the first 45 minutes went to proving the channel before any pipeline work, with an explicit escalation trigger if the echo bot wasn't replying by 12:00.

**D2 — The channel is an adapter, not the architecture.** Teams-specific code lives only in `channels/teams.py` and `channels/cards.py`; everything downstream speaks a plain `InboundEvent`. This meant a platform problem could never take the whole build down — and it paid off literally: Vishal captured real payloads in the first half hour and Nandita built and tested the entire pipeline all day without the tunnel. *This is also the answer to "how hard is Telegram or WhatsApp": two files.*

**D3 — Deterministic pipeline, not an agent.** The input type is known and the output schema is known, so control flow is code, with one structured Claude call per step. The brief scores total cost, model used and end-to-end latency with a component breakdown — an agent decides its own number of calls, which makes those numbers variable and unexplainable. A deterministic branch can also carry an assertion; "the model decided" cannot.

**D4 — Tool use for chat CRUD, but never an agent framework.** The test for when an agent earns its place is whether the space of operations can be enumerated at design time. Ingestion can — three input kinds, one output schema. Free-text CRUD ("change the mobile for the Acme lead") cannot, so that surface is genuinely agent-shaped. **Status: designed, scoped, NOT built** — say it as the criterion and the next build, never in the present tense. Frameworks were rejected because they wrap an API that already ships the loop, they rewrite prompts we didn't author (turning token attribution — a scored requirement — into archaeology), and at hour five you want stack traces through your own code.

**D5 — One vendor for text and vision, no separate OCR.** One vendor means one cost line and one failure mode; a Tesseract-then-LLM pipeline is two things to debug and two things to price for no accuracy gain on a photographed card. ⚠️ **D5's model assignment and its cost table are superseded by D16 and by measurement** — D5 says Opus 5 for text, and labels its own costs "illustrative". Do not quote them.

**D6 — Schema-validated extraction, never parsed prose.** `messages.parse(output_format=...)`, one retry with the validation error fed back, then abstain. Regexing model prose is the single most common way prototypes like this produce confident garbage; a schema turns a bad extraction into a *caught error* rather than a *wrong record*. The consequence is a convention: `schemas.py` stays flat and Optional, because a clever type breaks strict-schema parsing.

**D7 — SQLite behind a `Store` interface, no Intrakore integration.** No sandbox and no credentials, and the brief permits "a working backend application **or data store**". An elaborate fake CRM client proves nothing and eats two hours. What it bought was the whole afternoon on the clarification loops, which is where the product value actually is. The corrected assumption is worth saying: the team initially treated CRM integration as required, re-read the brief, and found it wasn't.

**D8 — The cost ledger exists from the first commit.** Every step appends a `CostEntry` — component, service, units, cost, latency — including DB and channel steps where cost is zero but latency isn't. The reasoning is brutal and correct: this cannot be reconstructed at 16:00. Either it goes in with the first step or it never happens. It is also roughly a quarter of what gets demoed.

**D9 — Follow-up parsing is tri-state.** `RESOLVED | AMBIGUOUS | NONE`. The brief says "do not silently guess if timing is ambiguous", which is a scored requirement and cheap to get right. **Demoing the system refusing to guess is worth more than demoing it guessing correctly.**

**D10 — Idempotency on the `activity_id`.** It is the PRIMARY KEY of the `activities` table, checked on the first line of `handle()`. Teams retries deliveries; without this one check a retried message becomes a second lead, and duplicate handling is explicitly scored.

**D11 — "Shared contact" means a `.vcf` attachment.** Teams has no structured contact-share message the way Telegram does, so `.vcf` is the faithful equivalent, with a pasted contact block as fallback. **The real point of mode 2 is the clarification loop, not the transport** — the brief attaches "company information is mandatory" to this mode alone, precisely because a phone contact rarely carries a company. Parse, notice the company is missing, ask, then create. That is what makes it a distinct mode rather than mode 1 in disguise.

**D12 — Dedupe on normalised email, then mobile.** Deterministic and explainable beats clever, and the card always says *which field matched*. ⚠️ D12 also describes a fuzzy company-name match, surfaced but never auto-merged — **that part was designed and not built**. Say so. (And note two people at the same company *should* be two leads, so company-level matching is a surfacing problem, not a merging one.)

**D13 — Stdlib-only is dead; the instinct behind it is not.** FastAPI, Pydantic v2, the Anthropic SDK, SQLModel, APScheduler. What survives from the stdlib-only instinct is the rule that matters: **no key, no crash** — every external call degrades to a typed error the bot can say out loud.

**D14 — Pick a speech-to-text vendor and don't revisit it.** Claude has no audio input, so *a* vendor is needed and nobody is grading which. Deepgram Nova-3, ten minutes, done. The decision is shallow on purpose: not deciding was the only wrong answer.

**D15 — One question to the CTO, not eight.** Asked only what a Lead looks like in Intrakore's CRM — field names, which are required, the initial pipeline stage — because that is the only thing the team could not answer for itself. A list of eight questions at 11:00 reads as not building. It was explicitly not a blocker: build the five fields the brief names; anything that comes back is additive optional fields on the same model.

**D16 — Model vendor, measured against the alternative.** Stay on Claude today: **Sonnet 5 at low effort for text, Opus 5 at default effort for vision, Deepgram Nova-3 for speech.** Per-path tuning took the text path from 4,965 ms / $0.0097 to 2,396 ms / $0.0029 — output tokens generate serially, so output tokens *are* the latency, and field extraction from a sentence does not reward deliberation. Vision deliberately stayed at default effort: a photographed card is the genuinely hard input and card accuracy is not traded for 300 ms. The honest alternative is named rather than dismissed — **Gemini 2.5 Flash is roughly 4–6× cheaper per text lead on our token counts and takes audio natively**, which would remove Deepgram as a vendor entirely. It wasn't switched for timing and risk, not quality: switching at 15:30 means an untested path on all three modes with no eval run to prove accuracy held. Correct sequence is build the eval set, run Flash against it, then decide — and the eval set exists. **Intrakore runs on AWS, verified by DNS (app/portal/login/api subdomains resolve to EC2 in us-east-1, AS14618), not Azure** — an earlier draft assumed Azure from Teams usage and would have been wrong in front of their COO. Claude is native on **Amazon Bedrock**, inside their existing AWS account; Gemini has no Bedrock path. **Never say "same price"** — Bedrock pricing is AWS's, same range, not identical.

---

## 4. THE NUMBERS — the single authoritative set

### 4.1 Cost and latency per activity

Measured from the real `demo_check` ledger captured at 16:01–16:02 today unless marked otherwise. Every Claude figure re-derives exactly from the rate table in `ledger.py`.

| What | Model / service | **Say this cost** | **Say this latency** | Grade |
|---|---|---|---|---|
| Shared contact (`.vcf`) | **none — deterministic parse** | **$0.000000** | **~1–3 ms** | measured |
| Free-text lead | Sonnet 5, effort low | **$0.002** ("two-tenths of a cent") | **~3 s** | measured ×4 today |
| Meeting-note summarisation | Sonnet 5, effort low | **$0.0027** | **~2.5 s** | measured ×2 today |
| Business card, flat PNG, **warm** | Opus 5, default effort | **$0.011** | **~4.5 s** | measured today |
| Business card, **first of the session** | Opus 5 | **$0.021** ("two cents") | **~5.2 s** | measured today |
| Business card, **phone photo (the demo JPEG)** | Opus 5 | **~$0.02** ("two cents") | ~5 s | ⚠️ HANDOFF only |
| Voice note | Deepgram + Sonnet 5 | **$0.0034** (stt $0.0015 + llm $0.0019) | "five or six seconds" | ⚠️ STT arithmetic-verified; latency HANDOFF only |
| Answering a clarification | none — extraction rehydrated | **$0.000000** | ~1–3 ms | measured |
| Card button / `cancel` | none | **$0.000000** | **~1 ms** | measured, 11 activities |
| Replayed `activity_id` | none | **$0.000000** | ~0 ms | measured |
| Chit-chat ("thanks", "hi") | Sonnet 5 | "roughly a tenth of a cent" | ~2 s | ⚠️ HANDOFF only |

**Rates — `ledger.py` is the only place prices live:** Sonnet 5 **$2 / $10** per MTok · Opus 5 **$5 / $25** · Haiku 4.5 $1 / $5 (rejected: 400s on the `effort` param) · Deepgram Nova-3 **$0.0043/min**. Cache multipliers: write **1.25×** input, read **0.10×** input.

### 4.2 Tests, evals, totals

| Figure | What it actually is |
|---|---|
| **`demo_check` 25/25** | 25 assertions over the demo surface — 3 input modes, 2 refuse-to-guess beats, duplicate + idempotency, notes + follow-up (clear and vague), 8 pending-state guards, update + delete. Produced 24 stored activities (one is a deliberate replay). **Pipeline only — it touches no channel code.** |
| **`evals` 70/70** | 14 labelled cases × 5 fields (`company_name, first_name, last_name, mobile, email`), scored per field. |
| Eval composition | 8 free-text · **4 business cards (01–04)** · 2 vCards. Photo cards 05/06 are **not** in the set — verified by hand. |
| Eval run cost | **$0.07** (independently reconstructed as $0.0713) |
| **Whole `demo_check` run: $0.0458** | Summed from 24 stored ledgers. *"Four and a half cents to prove the entire surface."* |
| Review threshold | **0.6** — routes to `NEEDS_REVIEW` |

### 4.3 Prompt caching — the best extra-credit number you have

Both states captured in the same run, both reconcile to the cent:

| Vision call | Input | Output | Cache | Cost | Latency |
|---|---|---|---|---|---|
| **Cold** (first card, `t3`) | 854 tok | 272 tok | **writes** 1,586 @ 1.25× | **$0.020983** | 5,215 ms |
| **Warm** (`t6`) | 854 tok | 234 tok | **reads** 1,586 @ 0.10× | **$0.010913** | 4,450 ms |

The write premium isolates exactly: 1,586 × $5/MTok × 1.25 = **$0.009913**, which is precisely the gap. Warm reads cost $0.000793. **Saving per card after the first: $0.0091.** On the text path, 1,510 cached tokens are read for $0.000302 of a $0.002028 call — with no caching at all that call would be ~$0.0047, so **caching more than halves it**.

Honest footnote if pressed: the **meeting-notes** prompt shows `cache_read = 0` and no write premium — that prefix is below the minimum cacheable length, and the ledger reports zero rather than pretending.

> ### ⚠️ THE #1 STAGE TRAP — agree this now
> Slide 8's business-card figure ($0.009–0.011) is the **warm, flat-PNG** number. The demo's first card is the first vision call of the session, so unless a card was sent within the cache TTL (~5 min) it will read **≈ $0.021**. Same for the first typed lead if the text cache is cold: **~$0.0056**, not $0.002 (measured cold today: $0.005621).
>
> **Mitigation:** send one throwaway text lead **and** one card ~60 seconds before you start, then `send.py reset` and reload the dashboard. The cache lives at Anthropic and survives the reset.
>
> **If it happens anyway, Nandita's line — and it is a better beat than the clean number:** *"That's the first call of the session paying to write the prompt cache — fifteen hundred tokens of schema. Every call after it reads that at a tenth of the price. Watch the next one drop."* Then point at it dropping.

### 4.4 The tuning story — three configurations measured, a fourth rejected

| Config | Latency | Output tok | Cost |
|---|---|---|---|
| Opus 5, default effort | 4,965 ms | 346 | $0.0097 |
| Opus 5, effort low | 3,254 ms | 185 | $0.0057 |
| **Sonnet 5, effort low ← shipped** | **2,396 ms** | — | **$0.0029** |
| Haiku 4.5 | — | — | — (400 on the `effort` parameter — **no measurement**) |

Headline: **4,965 ms / $0.0097 → 2,396 ms / $0.0029** — ~52% faster, ~70% cheaper, same extraction. ⚠️ The deck says "four configurations measured"; only three produced numbers. Say **"three measured, a fourth rejected outright."**

### 4.5 Scale sensitivity

**10/day $0.06 · 100/day $0.57 · 1,000/day $5.70 · 10,000/day $57.** Internally consistent at a blended **$0.0057 per activity**.

⚠️ **That blend is documented nowhere.** If a CXO asks for the mix, do not invent one. Answer with the measured bounds: *"All-typed is about twenty-nine dollars a day at ten thousand; all-photographed-card about a hundred and ten. Fifty-seven is the mix we measured — and the reason I can give you a range rather than one number is that we price per component instead of quoting an average."* Note also these are **per activity**, and a complete lead is usually two or three activities.

### 4.6 Confidence

Today's real run: clean text **0.90** and 0.90 · card (Al Wasl) **0.95** · card (no-company) **0.88** · vCard **1.00** (deterministic). Deck slide 9 shows 0.90 / 0.95 / 0.50 / 0.20 / 0.80 — those are **model outputs from one eval run and will move between runs.** ⚠️ **Never promise a specific confidence number before a live call.** Safe framing: *"name-only input lands below our 0.6 review threshold; a pleasantry lands far below it."*

If a judge notices that *messy* text (0.95) scores higher than *clean* (0.90), that is a fair hit and the honest answer is strong: *"It's a self-report, not a calibrated probability, and you've found the evidence. We use it as a triage signal — below 0.6 the record is written NEEDS_REVIEW and the bot names which fields it was unsure about. Calibrating it properly needs a labelled set and a reliability curve. Week two."*

### 4.7 ⚠️ THE DEFECT COUNT — settled

Three numbers are in circulation. Here is what each is:

| Source | Count | What it really is |
|---|---|---|
| Deck slide 10 | **12** | 12 named entries, committed 14:49. **Exactly HANDOFF items 1–12.** |
| `HANDOFF.md` lines 68–101 | **19** | 19 numbered entries, 1–19, no gaps, no duplicates (18 and 19 are printed out of order — cosmetic). Items 13–19 were found *after* the deck was built. |
| `PRESENTATION.md:285` | **24** | ❌ **Unsupported.** No list of 24 exists in the repo or in any commit. |

**12 + 7 found after the deck = 19.** Auditable line by line.

**Both of you say, word for word:** *"Nineteen. The slide shows twelve — we found seven more after we built the deck."*

**Vishal's channel half is exactly 6** — items 1, 2, 3, 10, 11 marked *(Vishal)* plus item 4 marked *(both)*. "Six of the nineteen were the channel" is exact.

**Provenance matters and the deck already says it right:** nearly all of them came from **running the demo against ourselves**, not from an audit tool. Do not read `PRESENTATION.md:285`'s "most of them from automated adversarial passes" aloud — it contradicts both the deck header and HANDOFF's own header.

### 4.8 🚩 BANNED NUMBERS — quoted somewhere, wrong or unverifiable

1. "twenty-four defects" — say **nineteen**.
2. "17/17" (D16:250) — stale, it is **25/25**.
3. D5's illustrative costs (text $0.006, card $0.014, notes $0.018) — the doc labels them illustrative itself. Superseded.
4. D5's "Opus 5 for extraction *and* vision" — **text runs on Sonnet 5.** If challenged: *"D5 was the 11:00 decision; D16 and settings.py are the measured outcome."*
5. "business card $0.009–0.011" **unqualified** — true only warm and flat.
6. "~3 ms" for `.vcf` — measured **1 ms**. Say "one to three milliseconds" or "effectively instant".
7. Gemini's $0.30 / $2.50 / $1.00 rates — external pricing page, not in `ledger.py`, not verified today. Use D16's own hedge: **"roughly 4–6× cheaper per text lead on our token counts."**
8. "four configurations measured" — **three**.
9. Voice "~6 s" — no voice case exists in `demo_check`. Say "about five or six seconds", never a decimal.
10. "six business cards in the evals" — **four** are in the eval set, two were checked by hand.
11. **Do not offer to open `handover-nandita-edgecases.md` or `for-nandita-latency-and-bugs.md`.** HANDOFF cites both; **neither exists in the repo or in any commit.**

---

## 5. REAL vs MOCKED vs UNVERIFIED

| Thing | Status | Say this if asked |
|---|---|---|
| Claude extraction — text, vision, notes | **REAL** | Real API, real `response.usage`, real money. |
| Deepgram Nova-3 speech-to-text | **REAL** and keyed | Was mocked earlier today; `/api/health` used to paint a green "live" pill while a canned transcript ran — defect, fixed, it now reports what actually runs. |
| `.vcf` / vCard parsing | **REAL, deterministic** | No model call at all. $0.000000. It cannot hallucinate. |
| Datastore | **MOCKED — ours, not Intrakore's CRM** | No sandbox, no credentials. The brief allows a working data store and this is one. Production needs six things: field mapping, auth + token refresh, idempotency keys, rate limits, an error taxonomy, retry/DLQ. |
| Free-text CRUD by tool use (D4) | **NOT BUILT** | Scoped, criterion stated, week two. The deck has it in week two correctly. |
| Fuzzy company-name dedupe (D12) | **NOT BUILT** | Email then mobile only. Design position, not implemented. |
| Teams client (sideloaded app) | **NOT USED — Azure Web Chat instead** | Sideloading needs a tenant with custom app upload enabled; personal account + a university tenant that only offers "submit to your IT admin" = days, not hours. Same bot registration, same protocol, same card renderer. The manifest and `chat-to-lead.zip` are built and in the repo. |
| Teams-native file attachments (`FILE_DOWNLOAD_INFO`) | **UNVERIFIED against a live tenant** | Built to the documented contract; runs correctly against a local server. All 5 such captures are locally synthesized. **All 192 real captures are `channelId: "webchat"` — there is not one `msteams` payload in the repo.** |
| The bearer-token branch of `fetch_attachment` | **UNVERIFIED** | A live Web Chat URL carries its own `?t=` JWT *and* gets a bearer header. That combination has never met Microsoft's server. Degrades to a question, never a crash; there is a specific diagnostic log line for it. |
| Teams `fileType` handling for images | **KNOWN GAP** | Our own captures show `fileType` as both a MIME type (`audio/mp4`) and a bare extension (`vcf`). `_classify` only has a suffix fallback for audio, so a Teams-file **image** would likely fall through to TEXT. Thirty minutes with a real tenant. |
| Inbound JWT validation on `/api/messages` | **NOT DONE — deliberate** | **This is the one to volunteer as "what I'd fix first."** See the sharp version below. |
| REST CRUD auth / rate limiting | **NONE** | `GET /api/leads` returns every lead; `PATCH`/`DELETE` take anything. On a public tunnel during the demo. |
| Automated tests over the channel layer | **ZERO** | `demo_check` constructs `InboundEvent` objects directly and never touches `to_inbound_event`, `cards.render`, or any `api.py` route. **Never let 25/25 imply channel coverage.** |
| Concurrency | **ONE** | `pipeline.handle` is async but `_route` contains no `await`; the SDK call and the Deepgram POST are synchronous. One message at a time. |
| Prompt-injection hardening | **NOT HARDENED** | Blast radius is small by design — the model fills a fixed form, has no tools, cannot act. |
| PII handling | **NO DPA, NO REDACTION** | Names, phones, emails and audio go to Anthropic and Deepgram today. Every inbound payload is also captured to disk for debugging — off in production. |

**The sharpest security fact, and Vishal should say it before a judge finds it:** `serviceUrl` arrives on the **unauthenticated** inbound payload, and `send_activity` posts the bot's **bearer token** to it. So an unauthenticated POST to `/api/messages` naming an attacker's server would leak that token. *That* is why validating the Bot Framework JWT is the first line of the production list and not the fifth — and why `HANDOFF.md` says **do not deploy** in capital letters. Two honest mitigations you can also cite: the dashboard HTML-escapes everything the model produces, and `update_lead` allow-lists column names before building SQL.

---

## 6. DIVISION OF LABOUR — so you can hand over cleanly

**The line, memorised:** *"Vishal moves bytes. Nandita interprets them."* The contract between the halves is one function call:

```python
result: PipelineResult = await handle(event, store)
```

| Vishal owns | Nandita owns |
|---|---|
| `app/api.py` — FastAPI, `/api/messages` webhook, REST CRUD, `/docs` | `app/schemas.py` — **the contract**, announce before editing |
| `app/channels/teams.py` — three primitives + `to_inbound_event` | `app/extract.py` — text / vCard / vision / transcript |
| `app/channels/cards.py` — Adaptive Cards + button payloads | `app/followup.py` — tri-state date resolution |
| `fixtures/` — captured payloads + `sanitize.py` | `app/store.py` — Store interface, SQLite, dedupe, CRUD |
| `manifest/` + Azure Bot registration, dev tunnel | `app/ledger.py` — rate table, cost + latency |
| | `app/pipeline.py` — router, retry/abstain, duplicates |
| | `app/scheduler.py`, `app/transcribe.py`, `tests/`, `tools/`, `ui/dashboard.html` |

**Speaking split (15 min):** Nandita 2 min user flow → both 7 min live demo (Vishal drives, Nandita narrates numbers) → Nandita architecture then Vishal channel + risks, 4 min → ~2 min Q&A. Both answer questions; the brief requires it.

**Clean handover lines to rehearse:**

- Nandita → Vishal: *"That's the pipeline. The reason any of it reaches a chat window at all is Vishal's half — over to him."*
- Vishal → Nandita: *"Everything past this point receives a plain Python object and has never heard of Teams. Nandita."*
- Either, on the other's territory: *"That's Vishal's half — he'll take it"* / *"That's the pipeline, Nandita owns that."* **Do not guess into the other's half.** Hand it over; it reads as a team, not a gap.

**What each must be able to say about the other's half (one sentence, no more):**
- **Vishal on the pipeline:** *"It's a fixed pipeline, not an agent — the model only ever fills a schema, every field is Optional so a missing value becomes a question, and every call is priced from real usage."*
- **Nandita on the channel:** *"Three primitives — get a token, post an activity, download an attachment — a hundred and thirty lines, no Microsoft SDK, and the reply is an Adaptive Card with real buttons so CRUD never leaves the chat."*

---

## 7. GLOSSARY — plain language, so nobody fumbles a definition

**Bot Framework** — Microsoft's chat plumbing behind Teams. In practice it is plain JSON over HTTPS: get a bearer token, POST a message to a URL. That is why there is no Microsoft SDK in this build.

**Activity** — Bot Framework's word for one event in a conversation. Not just messages: `conversationUpdate` (chat opened) and `typing` arrive at the same webhook, which is why the code filters on `type == "message"`.

**`serviceUrl`** — the address Bot Framework tells you to post replies back to. The webhook's own HTTP response body is ignored; a reply only reaches the chat by POSTing there.

**Azure Web Chat** — Microsoft's own browser chat client for testing a bot. Same bot registration, same protocol, same card renderer as the Teams client; what you lose is Teams-native file attachments.

**Sideloading** — installing a custom app into a Teams tenant. Requires an admin to enable custom app upload. Blocked for us at tenant level, which is a Microsoft administration fact, not a gap in the work.

**Adaptive Card** — a JSON-described rich card that renders natively inside Teams or Web Chat, with buttons. Ours are schema 1.5 and carry Add note / Edit / Delete plus a cost line. **Why it matters as a product argument:** the whole premise is that the salesperson never opens a CRM tab — if the confirmation lands in a side dashboard, you have re-invented the CRM tab.

**`Action.Submit`** — an Adaptive Card button press. It comes back as a normal `message` activity with a `value` payload (not an `invoke`), which the normaliser turns into a `COMMAND` event.

**`InboundEvent` / `PipelineResult`** — the two plain Python objects that are the entire contract between the two halves. Nothing downstream of `InboundEvent` knows what Teams is.

**Idempotency** — making a repeat do nothing. Teams retries deliveries, so each message's `activity_id` is a primary key: a repeat returns the *original* stored result, same trace_id, same ledger, creating nothing and costing nothing.

**Prompt caching** — the stable part of a prompt (schema + system instructions) is stored server-side behind a `cache_control` breakpoint. **The first call pays a write premium of 1.25× the input rate; every later call reads it at 0.10×.** Ours is 1,510 tokens on the text path, 1,586 on vision. Verified via `usage.cache_read_input_tokens` — a zero means something is invalidating the prefix. It expires after about five minutes of silence, which is why the first call after a quiet walk-up costs more.

**Effort** — a knob on the model controlling how much it reasons before answering. Low effort produces fewer output tokens; **output tokens generate serially, so output tokens are the latency.** Text and notes run at low effort; vision deliberately does not.

**Structured output / `messages.parse`** — asking the model to fill a typed form rather than write prose you then parse. Invalid output is a caught error, not a wrong record.

**Abstain policy** — what happens when extraction fails. Validation failure → one retry with the actual error fed back → still invalid → stop and ask the salesperson for the details as text. An API error skips the retry because the SDK already retried. **It never invents a value to fill a gap.**

**Tri-state parsing** — the follow-up parser returns one of three things: `RESOLVED` (a real datetime), `AMBIGUOUS` (a question back to the user), or `NONE` (no follow-up mentioned). "After 2 days" resolves; "next week sometime" asks. The ambiguity gate runs *first*, so "next week" asks but "next week on Tuesday" resolves. Relative offsets and explicit dates are resolved **by regex, not by the model — a regex cannot hallucinate a Tuesday.** Times parse in Asia/Dubai, store UTC, display local; bare dates default to 09:00; it asks at most twice, then leaves it unscheduled rather than looping.

**Clarification / pending state** — when a required field is missing, the whole extraction is **parked**, not discarded, and a question goes out. The next typed message is treated as the answer and the parked extraction is rehydrated — which is why answering costs **$0.000000**. Parked questions expire after 10 minutes, `cancel` clears any pending state, and a message that looks like a new message (contains `@`, 2+ commas, >60 characters, or >8 words) is re-routed rather than filed as an answer.

**Dedupe key** — a normalised form used for matching: email is trimmed and lowercased; mobile is digits-only with the **last 9 kept**, so `+971 50 123 4567`, `00971501234567` and `050 123 4567` all collide. Email is checked first, then mobile, and the card says which one matched. **Nothing is ever auto-merged.**

**`NEEDS_REVIEW`** — the status written instead of `NEW` when the model's self-reported confidence is below **0.6**. The bot also names which fields it was unsure about.

**Ledger / span / component** — every step of the pipeline is wrapped in a timed `span` that records cost, latency, tokens and cache reads under a component: `llm | vision | stt | db | channel_api`. DB and channel spans record **$0 with real latency** — deliberately, because latency you didn't pay for is still latency. The total is **wall-clock**, not the sum of spans, so concurrent work doesn't inflate it. A span records its latency **even if the step raises** — a failed step is still a cost and still a wait.

**Dev tunnel** — a public HTTPS URL pointing at a laptop, so Microsoft's servers can reach the bot. Only one machine can be the bot's endpoint; today it is Vishal's.

**SSE dashboard** — the live economics panel. It streams results over Server-Sent Events, dedupes on `trace_id` (tagging replays "replay · not counted"), and shows two latency figures: all activities, and model calls only. **Quote the second against the slide table.** Its totals tile is client-side — describe it as "this session", not "today's spend".

---

## 8. THIRTY-SECOND PRE-STAGE CHECKLIST

- [ ] **Nineteen** defects, not twenty-four — "the slide shows twelve, we found seven more after we built it"
- [ ] **A hundred and thirty lines** of transport, not "about eighty"
- [ ] Tool-use CRUD is the **criterion and the next build**, never the present tense
- [ ] Project + budget go in the **beat-1 typed message**, or don't claim they were extracted
- [ ] Warm the cache: one text lead **and** one card, then `send.py reset` and **reload the dashboard**
- [ ] Beat 2 answer is exactly **`Delta Steel`** — nothing chatty, no email, under 8 words
- [ ] Beat 6 is **tap "Add note" first, then type** the follow-up
- [ ] Never type a raw ISO date, a month name, or "on the 15th" on stage
- [ ] Don't reply to the fired reminder — it's one-way
- [ ] **25/25 never implies the channel is tested.** It is not.
- [ ] Volunteer the webhook JWT — and the `serviceUrl` token-leak path — as "what I'd fix first"
- [ ] Error codes in order: **AADSTS700016 → 400 MissingProperty → 403 → 200**
- [ ] `cancel` is free, clears anything, and says what it dropped. Use it between beats if anything feels stuck.
