# Decision record

Intrakore AI Hackathon, Use Case 01 — Chat-to-Lead + Follow-up Automation.
Decided 2026-09-12, before the 11:00 build window.

Each entry: what we chose, why, what we rejected, and what it costs us.
If you disagree with one of these mid-build, change it here first so the
other person and both our Claudes see the same rules.

---

## D1 — Microsoft Teams is the platform

**Decision:** Teams. Assigned to us; not a choice.

**Consequence:** Teams is the heaviest of the three options — Azure AD app
registration, Bot Framework, a public HTTPS callback, a manifest, and tenant
permission to sideload. Telegram would have been ten minutes. So the first
45 minutes of the build go to proving the channel works, before any pipeline
work. If the echo bot isn't replying by 12:00 we escalate rather than debug
alone.

---

## D2 — The channel is an adapter, not the architecture

**Decision:** Teams-specific code lives only in `channels/teams.py` and
`channels/cards.py`. Everything downstream speaks `InboundEvent`.

**Why:** it lets the pipeline be built and tested without the tunnel up, and
it means a platform problem can never take the whole build down.

**How it pays off immediately:** Vishal captures five real Teams payloads into
`fixtures/` in the first half hour, and Nandita then works against real data
all day without needing Teams at all. That's the single highest-leverage
15 minutes of the day.

---

## D3 — Deterministic pipeline, not an agent

**Decision:** input type is known, output schema is known, so control flow is
code. One structured Claude call per step. No agent loop for ingestion.

**Why:** the brief scores *"total cost, model/service used and end-to-end
latency, with a component-level breakdown."* An agent decides its own number
of calls, which makes those numbers variable and unexplainable. A pipeline
can be priced exactly. Reliability is also testable — a deterministic branch
can carry an assertion; "the model decided" cannot.

**Rejected:** an agent loop over the whole flow.

---

## D4 — Tool use for chat CRUD, but no agent framework

**Decision:** the one genuinely open-ended surface — *"change the mobile for
the Acme lead", "delete Jillian's lead", "push the Acme follow-up to
Tuesday"* — uses tool use via the SDK's own
`client.beta.messages.tool_runner`, with `strict: true` on each tool.

**Why an agent here:** which record, which field, which operation cannot be
enumerated at design time. That is the actual test for when an agent earns
its place, and this surface passes it.

**Why not LangChain / CrewAI / AutoGen:** they are an abstraction over an API
that already ships the loop. They rewrite prompts we didn't author, which
makes token attribution — a scored requirement — into archaeology. And at
hour five we want stack traces through our own code.

**Superseded:** an earlier "no agent anywhere" position. Too absolute; the
CRUD surface is genuinely agent-shaped.

---

## D5 — Claude Opus 5 for extraction *and* vision. No separate OCR.

**Decision:** `claude-opus-5` for text extraction, business-card vision, and
note summarisation. Business cards are an image content block on the same
call.

**Why:** one vendor, one cost line, one failure mode. A Tesseract-then-LLM
pipeline is two things to debug and two things to price for no accuracy gain
on a photographed card.

**Rates** (per MTok, in `ledger.py` and nowhere else): Opus 5 $5 / $25.
Alternatives if we ever need them: Sonnet 5 $2 / $10, Haiku 4.5 $1 / $5.

**Illustrative cost per activity:** text lead ≈ $0.006, business card ≈
$0.014, notes summarisation ≈ $0.018. Real figures come from
`response.usage`, not from this table.

---

## D6 — Schema-validated extraction, never parsed prose

**Decision:** `client.messages.parse(output_format=LeadExtraction)`. On
validation failure, one retry with the error fed back, then abstain and ask
the salesperson.

**Why:** regexing model prose is the most common way these prototypes produce
confident garbage. A schema makes a bad extraction a caught error rather than
a wrong record.

**Consequence:** `schemas.py` must stay strict-schema friendly — flat fields,
`Optional`, no `dict[str, X]`. Every field is Optional so a missing value
comes back as `None` and gets asked for, rather than invented.

---

## D7 — SQLite behind a `Store` interface. No Intrakore integration.

**Decision:** our own datastore. `store.py` is an interface with a SQLite
implementation. No live CRM integration.

**Why:** we have no Intrakore sandbox and no credentials, and the brief says
*"persisted record in a working backend application **or data store**."* Our
own store is fully compliant.

**Rejected:** an elaborate fake Intrakore client. With no credentials it
proves nothing and can eat two hours.

**Consequence:** the risks slide names the boundary explicitly and states
what production would need — auth and token refresh, field mapping,
idempotency keys, rate limits, an error taxonomy, retry/DLQ. Naming the gap
reads as competence; hiding it gets dismantled in Q&A.

**Corrected assumption:** we initially treated CRM integration as required
because Intrakore is a construction ERP whose CRM module is exactly this
workflow's destination. Re-reading the brief, it isn't required. That freed
up the afternoon.

---

## D8 — The cost ledger exists from the first commit

**Decision:** every pipeline step appends a `CostEntry` — component, service,
units, cost, latency — including DB and channel steps where cost is zero but
latency isn't.

**Why:** it cannot be reconstructed at 16:00. Either it goes in with the first
step or it doesn't happen. It is also a full quarter of what gets demoed at
17:00.

**Extra credit:** prompt caching on the stable system prompt, verified via
`usage.cache_read_input_tokens`, then show the cached-vs-uncached delta in the
demo.

---

## D9 — Follow-up parsing is tri-state

**Decision:** `RESOLVED | AMBIGUOUS | NONE`. "Follow up after 2 days"
resolves against a stamped `now`. "Next week sometime" returns a question.

**Why:** the brief says *"Do not silently guess if timing is ambiguous."*
This is a scored requirement and cheap to get right. Demoing the system
refusing to guess is worth more than demoing it guessing correctly.

---

## D10 — Idempotency on the Teams `activity_id`

**Decision:** every inbound event is keyed on its activity ID; a repeat is a
no-op returning the original result.

**Why:** Teams retries deliveries. Without this, one retried message becomes
two leads — and duplicate handling is explicitly scored.

---

## D11 — Shared contact means a `.vcf` attachment

**Decision:** mode 2 accepts a `.vcf`, with a pasted/forwarded contact block
as fallback. Both route to a parser distinct from the free-text extractor.

**Why:** Teams has no structured contact-share message the way Telegram does.
`.vcf` is the closest faithful equivalent.

**The real point of mode 2:** the brief attaches *"company information is
mandatory"* to this mode alone, because a phone contact rarely carries a
company. So mode 2's purpose is the **clarification loop**, not the
transport — parse, notice company is missing, ask, then create. That is what
makes it a genuinely distinct mode rather than mode 1 in disguise.

---

## D12 — Dedupe on normalized email, then mobile

**Decision:** exact match on normalized email first, then normalized mobile.
Fuzzy company-name match second, surfaced but never auto-merged. The
confirmation card shows **which field matched.**

**Why:** deterministic and explainable beats clever. Our call, not the CTO's —
making it is the job.

---

## D13 — Stdlib-only is dead; the instinct behind it is not

**Decision:** FastAPI, Pydantic v2, the Anthropic SDK, SQLModel, APScheduler,
`uv`. The brief grants *"freedom to build."*

**What survives:** *no key, no crash.* Every external call degrades to a typed
error the bot can speak. That was the point of the old repo's mock provider
and it carries over unchanged.

**Consequence:** the old RAG modules under `app/` are dead and pending
deletion. Don't import them, don't fix them.

---

## D14 — Speech-to-text vendor: pick one and don't revisit

**Decision:** Deepgram Nova or Azure Speech. Azure if we want one cloud and
one bill; Deepgram to be done in ten minutes.

**Why it's this shallow:** Claude has no audio input, so we need *a* vendor,
and nobody is grading which. Not deciding is the only wrong answer.

---

## D15 — One question to the CTO, not eight

**Asked:** what a Lead actually looks like in Intrakore's CRM — field names,
which are required, the initial pipeline stage.

**Why only this one:** it's the only thing we can't answer ourselves, and with
no credentials our data model matching theirs is the only evidence of
integration we can offer. Everything else — STT vendor, dedupe key, whether
mocking is acceptable — is ours to decide, and a list of eight questions at
11:00 reads as not building.

**Not a blocker.** We build the five fields the brief names; anything that
comes back is additive optional fields on the same model.

---

## Freeze

**16:15.** Record the screen capture, then demo-breaking fixes only. Per
`WORKING-AGREEMENT.md`, that recording is the insurance.

---

## D16 — Model vendor, measured against the alternative

**Decision:** stay on Claude for today. Sonnet 5 at low effort for text,
Opus 5 at default effort for business-card vision, Deepgram Nova-3 for
speech-to-text. All three measured, all three tested, 17/17.

**Verified prices (2026-09-12):**

| | Input / MTok | Output / MTok | Audio |
|---|---|---|---|
| Claude Sonnet 5 | $2.00 | $10.00 | not supported |
| Claude Opus 5 | $5.00 | $25.00 | not supported |
| Gemini 2.5 Flash | $0.30 | $2.50 | $1.00 / MTok native |
| Deepgram Nova-3 | — | — | $0.0043 / min |

**Measured per activity (ours):** contact $0.000, text ~$0.002, card ~$0.011,
voice ~$0.0034 (stt $0.0015 + llm $0.0019).

**The honest alternative:** Gemini 2.5 Flash is roughly 4–6× cheaper per
text lead on our token counts, and takes audio natively — a voice note
could go straight to extraction in one call, removing Deepgram as a vendor.
That is a real simplification, not a marginal one.

**Why we did not switch:** timing and risk, not quality. Switching at 15:30
means an untested path on all three modes, no eval set to prove accuracy
held, and a rewrite of the ledger's usage mapping — 90 minutes before
freeze. The right sequence is: build the eval set, then run Flash against
it, then decide. That is the first experiment for week two.

**Why a free tier is the wrong answer for this brief:** the brief scores
cost per activity. A free tier makes that "zero", which cannot be put on a
slide or extrapolated. Paid per-token pricing is what makes the
sensitivity table possible.

**The structural point that makes this low-stakes:** the model lives in two
files, `extract.py` and `transcribe.py`, behind the pipeline. Swapping it is
a file change, not an architecture change.

**Their cloud is AWS, not Azure - verified, not inferred.** Teams is their
collaboration tool; their app subdomains (app/portal/login/api.intrakore.com)
resolve to an EC2 instance in us-east-1 (AS14618, Amazon). An earlier draft
of this entry assumed Azure from Teams usage - that was wrong and would have
been wrong in front of their COO.

**The alignment line, corrected:** Claude is available natively on Amazon
Bedrock - same model, same code, inside their existing AWS account. Do NOT
say "same price": Bedrock pricing is set by AWS, in the same range but not
identical. Gemini has no Bedrock path, which makes it a worse fit for their
stack, not a better one.
