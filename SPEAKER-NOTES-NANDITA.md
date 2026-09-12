# Speaker notes — Nandita

**You open with the 2-minute user flow. You narrate the numbers over
Vishal's demo. You take the architecture argument (~1:20).**

Quoted lines are things to say out loud.

---

## 1. PART 1 — USER FLOW (2:00) · you own the room

### 0:00–0:30 · The problem

> "A salesperson meets a lead. The details are on a business card in their
> pocket, or in a voice note they recorded walking to the car."

> "By the time anyone types that into a CRM — if anyone ever does — it's
> three days old and half of it is missing."

> "That's the gap we went after. Not lead generation. Lead *capture*."

### 0:30–1:15 · What the salesperson actually does

> "So we put it where they already are — a chat window."

> "They send whatever they have. Typed details. A photo of a card. A shared
> contact. A voice note on the way out of the meeting."

> "The bot reads it, confirms back what it captured, and — this is the part
> that matters — it asks when it isn't sure, instead of guessing."

> "Then they say when to follow up, in their own words. 'After two days.'
> 'Next week sometime.' It either schedules it, or it asks which day."

### 1:15–2:00 · Why it can be trusted

> "Three decisions you'll see in the demo."

> "**It never invents a value.** A missing company comes back as a question,
> not a plausible guess from the email domain."

> "**It never silently guesses a date.** Vague timing gets a question back."

> "**Every action is priced and timed** — real money, from real usage, split
> by component. That's the panel on the right, and it fills up as we go."

**Handover:** "Vishal's going to run it live."

---

## 2. Your narration over the demo

Short lines said **over** his actions. Never compete with the screen.

| Beat | Say |
|---|---|
| A · typed lead | "Two-tenths of a cent. About two and a half seconds. It's printed on the card." |
| B · notes | "It also pulled the project and the budget out of that sentence — we'll show those fields at the end." |
| C · ⭐ no company | *(let his pause breathe, then)* "That question cost nothing. Refusing to guess is cheaper than guessing wrong." |
| D · photo card | "About two cents, five seconds. Six times the text path — that's the vision call. Which is exactly why we measure per component instead of quoting one average." |
| E · duplicate | "Normalised email first, then mobile. It surfaces the match, it never auto-merges." |
| F · ⭐ vague date | *(say nothing until he's answered)* "Three states, not two: resolved, ambiguous, or nothing at all." |
| G · reminder | "That's a proactive message — the bot writing into a conversation it stored earlier." |
| H · voice note | "Deepgram, priced by the second, on its own line in the ledger. And the raw transcript is kept next to the summary." |
| I · CRUD | "Create, read, update, delete — all from the card." |

---

## 3. PART 3 — Your architecture argument (~1:20)

> "It's a **fixed pipeline, not an agent.**"

> "We know what comes in and we know what has to come out, so the steps are
> code. The model does one job, at one station: reading fields out of text,
> a photo, or a transcript."

> "That's why we can tell you it costs two-tenths of a cent and takes two
> and a half seconds. An agent picks its own number of calls — and then you
> can't quote a number at all."

> "The model fills a form. It never writes prose that we then parse. The
> output is schema-validated — if it comes back malformed we retry once with
> the error fed back, and if it still fails we stop and ask. That's the
> difference between a caught error and a wrong record."

> "Every field is allowed to be empty, on purpose. Empty triggers a
> question. It can't invent."

> "The one place we *do* use tool-calling is chat CRUD — 'change the mobile
> for Acme.' Which record, which field, which operation genuinely can't be
> enumerated up front. That's the test for when an agent earns its place,
> and that surface passes it."

> "And the cost ledger went in with the first commit, not at the end. Every
> step records what it cost and how long it took — including the database
> and the chat calls, where the cost is zero but the time isn't. You can't
> reconstruct that at four in the afternoon."

---

## 4. Your half, well enough to answer questions

- **`schemas.py`** — the contract between both halves. Flat, `Optional`
  fields, strict-schema friendly so it can be handed straight to
  `messages.parse(output_format=...)`.
- **`extract.py`** — text, vCard, vision and transcript → `LeadExtraction`.
  Retry-once-with-the-error, then abstain.
- **`followup.py`** — tri-state: `RESOLVED | AMBIGUOUS | NONE`.
- **`store.py`** — `Store` interface + SQLite. Dedupe on normalised email,
  then mobile.
- **`ledger.py`** — per-component cost and latency, real usage only.
- **`pipeline.py`** — the router, the retry/abstain policy, duplicate
  handling, idempotency on `activity_id`.
- **`scheduler.py`** — polls for due follow-ups, fires proactively.
- **`tests/`** — `demo_check` (25 checks, the whole journey) and the
  extraction evals.

---

## 5. Questions likely to come to you

**"Is this just ChatGPT in a wrapper?"**
> "No. The control flow is deterministic code. The model does one job —
> reading fields — and its output is schema-validated, so a bad read is a
> caught error, not a wrong record. That's what lets us quote a fixed cost
> per lead."

**"How accurate is it?"**
> "We ran per-field evals across labelled cases — company, name, mobile,
> email and the rest. And more importantly it's built to abstain: you saw it
> ask twice rather than guess."

**"What about hallucination?"**
> "Every field is optional, so a missing value comes back as null and
> becomes a question. The failure mode we designed against is a confidently
> invented phone number — that's worse than an empty one."

**"Why Claude, and why two different models?"**
> "Sonnet for text at low reasoning effort — it's a field-extraction task,
> it doesn't need more. Opus for business cards, because reading a
> photographed card in bad light is genuinely harder. One vendor, one cost
> line, one failure mode — no separate OCR step to debug and price."

**"What happens when the model is down?"**
> "Every external call degrades to a typed error the bot says out loud. It
> asks the salesperson to resend rather than hanging or failing silently.
> The call is bounded by a timeout, so a hung connection can't freeze it."

**"How long to production?"**
> "The CRM integration is the main piece — mapping our fields onto
> Intrakore's lead object, plus auth, retries and a dead-letter path. The
> chat layer and the extraction are done."

**"Prompt injection — someone writes instructions on a business card?"**
> "Not hardened, and I'd rather say so. The blast radius is small: the model
> fills a fixed form, it has no tools and can't act. Worst case is a bad
> field value, which the human sees on the confirmation card before anything
> else happens. Real hardening is a production item."
