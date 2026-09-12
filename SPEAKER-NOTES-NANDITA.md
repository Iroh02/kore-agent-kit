# NANDITA — SPEAKER NOTES
### Chat-to-Lead + Follow-up Automation · Intrakore AI Hackathon · 17:00

**Your three speaking slots:** 2:00 user flow (you open) → narration over Vishal's 7:00 demo → ~1:20 architecture in the final segment. Then Q&A.

---

## ⚠️ FOUR THINGS TO GET RIGHT BEFORE YOU WALK UP

**1. Do NOT say "we use tool-calling for CRUD."** The draft script says it; it is not built. `grep` for `tool_runner` / `tools=` across `app/`, `tests/`, `tools/` returns nothing. `DECISIONS.md` D4 describes it as a *decision*; `HANDOFF.md` lists it under "Open / not done." The deck is right — slide 12 puts it in WEEK TWO. Use the replacement line in §4.

**2. "Nineteen defects," never twenty-four.** The deck shows 12; `HANDOFF.md` lists 19 numbered entries (deck items 1–12 plus 7 found after the deck was built). Twenty-four has no source anywhere in the repo. Agreed line: *"Nineteen. The slide shows twelve — we found seven more after we built the deck."*

**3. The photo card is "about two cents," not the slide's one cent.** The JPEGs are bigger. And the *first* card of the session pays the prompt-cache write: **$0.021**, not $0.011.

**4. Project name and budget only appear if they were in the CAPTURE message.** `project_name` and `estimated_value` are written in exactly one place — `pipeline.py:468–470`, inside `_persist_lead`. The **notes** path never touches them. If Vishal's beat-1 message includes "40-unit villa project, budget 3.2m AED", you can say the closing line. If it doesn't, **skip it** — do not promise fields that will show as null on the projector.

---

## 1. WHAT YOU OWN — the primer

You own `schemas.py`, `extract.py`, `followup.py`, `store.py`, `ledger.py`, `pipeline.py`, `scheduler.py`, `transcribe.py`, `tests/`. Everything from `InboundEvent` inward. Vishal owns the transport.

### 1.1 The pipeline is a fixed ladder — `pipeline.handle()` → `_route()`

In order, and the order is the design:

1. **Idempotency** — `store.seen_activity(activity_id)`. Seen before? Return the *original* `PipelineResult`, original `trace_id`, original ledger. No second lead, no second charge.
2. **Card buttons (COMMAND)** — explicit instructions always win.
3. **Cancel words** — `cancel` / `never mind` / `stop` escapes any pending state, says what it dropped, costs $0.
4. **Pending clarification** — if we just *asked* something, this message is the *answer*, not a new lead. TTL 600 s; expired questions are cleared, not honoured.
5. **Pending note** — set by the "Add note" button. We do not classify "is this a note?" — a classifier can misfire live; a button cannot.
6. **Clear stale state** — a photo or `.vcf` sails past 4 and 5, so any armed flag is dropped here. (This was a real bug — the next typed sentence became that lead's company name.)
7. **Capture** — the input *kind* selects the extractor.

The docstring says it outright: *"the model is only ever asked to fill a schema, never to choose what happens next."*

### 1.2 Extraction — `extract.py`

- `client.messages.parse(output_format=LeadExtraction)`. The model returns an object or the call fails validation. **We never regex model prose.**
- `_parse_lead`: validation failure on attempt 0 → the actual error is fed back as a user turn → **one** retry. Still invalid → `ExtractionFailed` → the bot asks for the details as text.
- `anthropic.APIError` is **not** retried here — the SDK already retried. Straight to abstain.
- Client pinned `timeout=25.0, max_retries=1` (~51 s worst case). This replaced SDK defaults of 600 s × 3 after a hung connection froze our single-worker process for ~30 minutes. That's HANDOFF bug 13.
- **Weak spot, know it:** `extract_meeting_note` has no retry wrapper. A failure there falls to `handle()`'s catch-all: *"Something went wrong processing that. Nothing was saved."* Honest, not silent.

### 1.3 The schema — why every field is Optional

`LeadExtraction`: `company_name`, `first_name`, `last_name`, `mobile`, `email`, plus `project_name`, `estimated_value`, `enquiry_type` — all `| None = None`. Only `confidence` is required. There's also `source_quote` — the span of input the fields were read from, so a human can audit without re-running.

- `REQUIRED = ["company_name"]` → blocks creation, asks.
- `NICE_TO_HAVE = first/last/mobile/email` → lead is created, reply names what's missing.
- Prompt reinforces it: *if the only evidence is an email domain, return null — a domain is not a company name.*
- `confidence < 0.6` → status `NEEDS_REVIEW`, and the bot says which fields it was unsure about.
- Nothing extracted at all ("thanks", "hi") → read-only reply, **nothing parked.**
- **The extraction is parked, not discarded.** `_answer_company` rehydrates the payload from `pending_clarifications`. That's why answering a question costs **$0.000000**.

### 1.4 Follow-up parsing — `followup.py`, tri-state

`RESOLVED | AMBIGUOUS | NONE`, from `parse_follow_up(instruction, now)`. `now` is always injected — never read from the clock inside a resolver. That's what makes it testable.

- **The ambiguity gate runs first**, but it stands down if the phrase pins an actual day. So "next week" asks; "next week on Tuesday" resolves.
- Offsets and explicit dates are resolved **by regex, not by the model**. *A regex cannot hallucinate a Tuesday.*
- Word numbers parse ("two days", "a couple of weeks") — Deepgram writes small numbers as words, so every voice follow-up was ambiguous until that landed.
- `answering=True` changes meaning: a bare "Tuesday" volunteered in a note is ambiguous; "Tuesday" in reply to "which day?" plainly means the coming one.
- `MAX_CLARIFY_ATTEMPTS = 2` — ask twice, then leave it unscheduled rather than loop or guess.
- Times parsed in Asia/Dubai (UTC+4), **stored UTC**, displayed local. Bare dates default to 09:00.
- ⚠️ **Never type a raw ISO date on stage.** `2026-09-31` raises a ValueError → generic error. Month names ("15 September") and slash dates don't parse either — they ask.

### 1.5 Dedupe — `store.find_duplicate(email, mobile)`

Email first, then mobile; returns the lead **and** which field matched. `normalize_email` = strip + lowercase. `normalize_mobile` = digits only, **keep the last 9** — so `+971 50 123 4567`, `00971501234567` and `050 123 4567` all collide, which is what you want in the GCC. **Nothing is merged.** Status `DUPLICATE`, no row written, offer to update the existing one. `update_lead` recomputes `email_key`/`mobile_key` so the keys stay in step.

**Do not claim fuzzy company-name matching.** D12 describes it; the code does email-then-mobile only. Say: *"company-name matching is deliberately not automatic — a near-match is exactly the case a human should see."*

### 1.6 The ledger — `ledger.py`

`led.span(component, service, detail)` wraps **every** step. `span.record_claude(resp.usage)` prices it from **real** `response.usage`, never an estimate. Components: `llm | vision | stt | db | channel_api`. DB and channel spans record **$0 with real latency** — deliberate, and why the dashboard shows two latency figures (all activities vs model calls only; **quote the second** against the slide table). `finish()` reports **wall-clock** end-to-end latency, not the sum of spans. The span records latency even if the step raises — a failed step is still a cost and still a latency. Rates live in exactly one place: `CLAUDE_RATES`.

### 1.7 The evals — what the number is and isn't

**70/70 = 14 labelled cases × 5 fields** (`company_name, first_name, last_name, mobile, email`), scored per field. Composition: 8 free-text, **4 business cards** (01_clean, 02_angled, 03_blurred, 04_no_company), 2 vCards. The two **photo** cards (05, 06) are **not** in the eval set — verified by hand. Mobiles compare on digits only, last 9. **Abstaining scores as correct** — a case whose right answer is `None` earns a point for returning `None`. Two deliberate traps: `reem.haddad@outlook.com` must **not** yield a company; "thanks, see you at the site tomorrow" must give five nulls. Run cost $0.07.

Separately: `tests/demo_check.py` is **25/25** — the demo itself, automated, against a fresh DB. ⚠️ That covers the **pipeline**, not the channel. Don't let 25/25 imply Vishal's layer is tested — it isn't.

---

## 2. THE USER FLOW — 2:00, spoken

> Deck on the problem slide. You own the room. Slow. Don't rush to the demo.

### 0:00–0:30 — The gap

"A salesperson meets a lead. The details are on a business card in their pocket, or in a voice note they recorded walking to the car."

"By the time anyone types that into a CRM — if anyone ever does — it's three days old and half of it is missing."

"That's the gap. This isn't lead *generation*. It's lead **capture**."

### 0:30–1:15 — What they actually do

"So we put it where they already are. A chat window."

"They send whatever they have. Typed details. A photo of a card. A shared contact. A voice note walking out of the meeting."

"The bot reads it, confirms back exactly what it captured — and this is the part that matters — **asks when it isn't sure, instead of guessing.**"

"Then they say when to follow up, in their own words. 'After two days.' 'Next week sometime.' And it schedules it, or it asks which day."

### 1:15–1:50 — Why it's trustworthy

"Three design decisions, and you'll watch every one of them happen."

"**It never invents a value.** A missing company comes back as a question — not a plausible guess off the email domain."

"**It never silently guesses a date.** Vague timing gets a question back."

"**Every single action is priced and timed** — in real money, from real usage, broken down per component. That panel on the right is live the whole way through."

### 1:50–2:00 — Handover

"Vishal's going to run it live. I'll call the numbers as they land."

---

## 3. DEMO NARRATION — short lines, said OVER his actions

> **Rule: one sentence, then stop.** He's driving. Let the dashboard fill in silence — judges watch rows appear on their own. Never talk over a card rendering.

### Beat 1 — Typed lead
> **"Two-tenths of a cent. About three seconds. It's on the bottom of the card."**

Measured today: $0.0020 / 2.6–4.2 s (four text activities, Sonnet 5 at low effort).

**If it reads ~$0.0056 instead** — that's a cold prompt cache, and it's a *better* moment than the clean one:
> "That's the first call of the session paying to write the prompt cache — fifteen hundred tokens of schema. Every call after it reads that at a tenth of the price. Watch the next one drop."

### Beat 2 — Business card with no company ⭐
*(say nothing while the card uploads)*

After the bot asks "which company?":
> **"That question cost nothing. The extraction is parked, not re-run — refusing to guess is cheaper than guessing wrong."**

Verified: $0.000000, 1–3 ms.

### Beat 3 — Photo of a card
> **"About two cents, five seconds. That's the vision call — six to ten times the text path, and the single most expensive thing we do. Which is exactly why we report per component instead of quoting one average."**

Say "two cents." Do not say "one cent" — the slide's figure is the flat PNG, warm.

### Beat 4 — Shared contact (`.vcf`)
> **"Zero. Not rounded — zero. No model was called at all. A vCard is already structured, so we parse it. One millisecond."**

This is your strongest single number. Land it and stop.

### Beat 5 — Duplicate
> **"No new row, and it names the field that matched. Nothing gets merged behind your back."**

### Beat 6 — "Follow up next week sometime" ⭐
*(let Vishal deliver the line about most-of-the-time not being good enough)*

After "Monday" resolves:
> **"The date was resolved by a regex, not by the model. A regex cannot hallucinate a Tuesday."**

### Beat 7 — The reminder fires
> **Say nothing.** Let it arrive. Silence is the point.

### Beat 8 — Voice note
> **"Deepgram, priced by the second, on its own line in the ledger. Speech-to-text a tenth of a cent, the extraction two-tenths — three and a half tenths of a cent for the whole thing."**

($0.0034 = STT $0.0015 + LLM $0.0019. Latency: say "about five or six seconds," never a decimal — there's no voice case in demo_check.)

**If Deepgram mishears:**
> "That's the raw transcript, unedited, stored right next to the summary — which is exactly why we keep the original. The summariser reads what the transcriber heard, and you can see both."

### Beat 9 — Edit / Delete from the card
> **"Zero, and about a millisecond. A button press is deterministic — there's no model in that path at all."**

### Beat 10 — The economics panel (your close, ~40 s)
> "Everything you just watched: total activities, total cost, average latency — and the latency is split two ways, all activities versus model calls only, because the database and the chat API cost nothing but still take time."

> "A thousand leads a day is five dollars and seventy cents."

**Only if project/budget were in the beat-1 capture message:**
> "And here's the Skyline record — project name and estimated value, in structured fields."

---

## 4. ARCHITECTURE — ~1:20 spoken

> Architecture slide up. This is an argument, not a tour. Don't list files.

"It's a **fixed pipeline, not an agent.** We know what comes in and what has to come out, so the control flow is code. The model does one job at one station: read fields out of text, a photo, or a transcript."

"That isn't an aesthetic preference. The brief scores cost, model used, and end-to-end latency with a component breakdown. An agent decides its own number of calls — so those numbers become variable and unexplainable. A pipeline can be priced exactly, and a deterministic branch can carry an assertion. 'The model decided' cannot."

"The model **fills a form. It never writes prose we then parse.** Output is schema-validated on the way back. Invalid output retries once with the validation error fed back, then abstains and asks the salesperson. That's the difference between a caught error and a wrong record — and regexing model prose is the single most common way prototypes like this produce confident garbage."

"Every field on that schema is Optional on purpose, so a missing value comes back as null and gets asked for rather than invented."

**Where an agent would earn its place — say it exactly like this:**

"There is one surface in this system that would genuinely earn an agent, and it's free-text CRUD — 'change the mobile on the Acme lead.' Which record, which field, which operation genuinely can't be enumerated at design time. That's our test for when an agent is justified, and it's the first thing we'd build next. Today CRUD runs off card buttons, which are deterministic — and that's what you just watched."

"Underneath: dedupe on normalised email then mobile, and the card tells you which field matched — we never auto-merge. Idempotency on the chat platform's activity ID, because Teams retries deliveries and one message must never become two leads. And a cost ledger that every step writes to — including the database and channel steps, where the cost is zero but the latency isn't."

"The model lives in two files, `extract.py` and `transcribe.py`, behind the pipeline. Swapping vendors is a file change, not an architecture change."

**Point at the diagram (one line, in `CLAUDE.md`):**
`Teams → channels/teams.py → InboundEvent → pipeline.handle() → PipelineResult → Adaptive Card`

---

## 5. QUESTIONS THAT COME TO YOU

**"Is this just ChatGPT in a wrapper?"**
> "No. The flow is deterministic code. The model does one job — reading fields — and its output is schema-validated, so a bad read is a caught error, not a wrong record. The interesting engineering is the code around the model that decides what to do when it abstains. That's also why we can quote you a fixed cost per lead instead of a range."

**"How accurate is it, really? Fourteen cases you wrote yourselves."**
> "Seventy out of seventy across fourteen labelled cases, five fields each — and I'll tell you exactly what that number is and isn't. It's not a benchmark; it's a regression harness, built so that 'we tried Gemini Flash' can become a measurement instead of a claim. Fourteen cases we wrote is enough to catch a regression and nowhere near enough to quote an accuracy rate to a customer. Week one of production is a hundred labelled cases from your actual salespeople, run three times, with the variance reported."
>
> *(If pressed to re-run live: offer `demo_check` — 25/25, faster, deterministic in structure. If you run the evals, say before you hit enter: "live run against a live model, a field may move — which is precisely why we keep the set.")*

**"Does it hallucinate?"**
> "The failure mode we designed against is inventing a field, and the defence is structural, not a prompt instruction. Every field in the schema is Optional, so a missing value comes back as null, and null becomes a question. The eval case that proves it is a contact whose only company evidence is an outlook.com address — the clever-looking answer is 'Outlook' and the correct answer is to ask. Where it *can* still go wrong is inside a field it did extract — a digit off a blurry card. That's why every value goes back on a confirmation card a human reads, and why low confidence writes the record as NEEDS_REVIEW instead of NEW."

**"Confidence is the model grading its own homework."**
> "It is, and you've found the evidence — messy text scores higher than clean, which no calibrated model would do. It's a self-report, not a calibrated probability. We use it as a triage signal: below 0.6 the record is written for review and the bot names which fields it was unsure about. It does real work at the extremes. Calibrating it properly needs a labelled set and a reliability curve — that's week two, not a hackathon."
>
> *(Don't promise a specific confidence number before a live run. Today's real run: clean text 0.90, cards 0.95 and 0.88, vCards 1.00.)*

**"Why Claude, and why this model?"**
> "Measured, not assumed, and selected per path. The text path went from just under five seconds and a cent, to about two-point-four seconds and three-tenths of a cent, by moving to Sonnet 5 at low effort — because output tokens *are* the latency, they're generated serially, and field extraction from a sentence isn't a task that rewards deliberation. Vision stayed on Opus at full effort deliberately: a photographed card is the genuinely hard input, and we won't trade its accuracy for three hundred milliseconds. Haiku 4.5 was rejected outright — the API four-hundreds on the effort parameter, so we have no measurement for it. Three configurations produced numbers, not four."

**"Could you make it cheaper?"**
> "Yes, and we know roughly by how much. Gemini 2.5 Flash is about four to six times cheaper per text lead on our token counts, and takes audio natively — which would remove our speech vendor entirely. That's a real simplification and it's our first week-two experiment. We didn't switch at half-past three with no eval run to prove accuracy held across all three input modes. Build the eval set, run Flash against it, then decide — and we built the eval set. The one thing that counts against it for your stack is that it has no Bedrock path."

**"What happens when the model is down?"**
> "Nothing five-hundreds. The client is bounded at twenty-five seconds with one retry — fifty-one seconds worst case — and an API error becomes an abstain: the bot says it couldn't read the details and asks for them as text. Two honest caveats. That message is weak when the model itself is down, because the text path is the same model; the right degraded behaviour is 'I've kept your message and I'll process it when we're back', and we don't do that yet. And the one path that works with no model at all is the shared contact — a vCard is parsed deterministically, zero cost, one millisecond, and it cannot hallucinate. That timeout bound came from a real incident today: SDK defaults are ten minutes times three, and a hung connection froze our single-worker process for half an hour."

**"What about concurrency? Twenty salespeople at once?"**
> "One worker, and extraction runs synchronously in the event loop — so we process one message at a time. For today that's a feature: it's why the latency numbers on that panel are clean and uncontended. For production it's a queue between the webhook and the pipeline, plus load testing we haven't done. I know the shape of the fix; I haven't measured it, so I won't quote you a throughput number."

**"Your dedupe only checks email and mobile."**
> "Exact match on normalised email, then mobile — last nine digits, so every GCC phone format collides the way you'd want. Deterministic and explainable, and the card tells you which field matched, so it's never a black box. Fuzzy company matching was on the design list and didn't get built — I'd rather tell you that than describe it as if it ran. And note two people at the same company *should* be two leads, so company matching is a surfacing problem, not a merging one."

**"What about a forwarded thread with three contacts?"**
> "One lead per message, by schema — and a second contact in the same message is dropped silently, which is the wrong behaviour. It should say 'I found two, which one?'. The fix is a list-typed extraction, which is a contract change and an eval rerun, not a prompt tweak."

**"$57 a day at ten thousand leads — at what mix?"**
> "Blended, at the mix we measured. The honest range is about twenty-two dollars a day if every lead is typed, and about a hundred and ten if every one is a photographed card. The reason I can give you a range rather than one number is that we price per component instead of quoting an average. Which end you land on is a product question — cards are roughly five times text."
>
> ⚠️ The $0.0057 blend is internally consistent but documented nowhere. **Don't invent a mix** — give the bounds.

**"Prompt injection in a business card?"**
> "Not hardened, and the blast radius is deliberately small. The model has no tools and can't act — it fills a fixed form and hands it back to code that decides what happens. Worst case is a bad field value on a confirmation card a human is already reading. Our dashboard HTML-escapes everything the model produces. Real hardening is input fencing and an output allow-list — it's an item, not a claim."

**"Why not fine-tune?"**
> "Three reasons. Fourteen labelled cases is a regression harness, not a training set. The behaviour we actually care about is abstention, which is a schema and prompt property, not something you'd teach by example without a lot of negatives. And fine-tuning welds us to one vendor — right now the model lives in two files and swapping it is a file change. The thing you'd fine-tune *for* is cost, and prompt caching already took a fifteen-hundred-token prefix down to a tenth of price per call."

**"Where does our data go?"**
> "Names, phones, emails and voice audio go to Anthropic and Deepgram over the API today. No DPA, no redaction — that's on the risks slide because it's the first question your legal team asks. The answer for you specifically is that Claude runs natively on Amazon Bedrock and you're on AWS — verified by DNS, your app, portal, login and api subdomains resolve to EC2 in us-east-1 — so the same model and the same code run inside your own account and data boundary. Pointing our two model files at Bedrock is a client change. I'd quote you Bedrock pricing rather than assume it: AWS sets it, same range, not identical."

---

## 6. THE EXTRA-CREDIT NUMBER — use it if the room is technical

You have cold *and* warm cache measured in the same run, and both reconcile to the cent:

| Vision call | Input | Output | Cache | Cost | Latency |
|---|---|---|---|---|---|
| Cold (first card) | 854 tok | 272 tok | writes 1,586 @ 1.25× | **$0.020983** | 5,217 ms |
| Warm (next card) | 854 tok | 234 tok | reads 1,586 @ 0.10× | **$0.010913** | 4,452 ms |

> "The system prompt is cached. Writing that cache costs a cent, once. Every card after it reads the same prefix for eight hundredths of a cent — about nine-tenths of a cent saved on every card after the first. And I can show you the `cache_read_input_tokens` that proves it."

**Honest footnote if pressed:** the meeting-notes prompt shows `cache_read = 0` and no write premium — that prefix is below the minimum cacheable length, and the ledger reports that as zero rather than pretending.

---

## 7. THIRTY-SECOND PRE-STAGE CHECKLIST

- [ ] **Nineteen** defects, never twenty-four
- [ ] Tool-use CRUD is the **criterion and the next build**, not something we shipped
- [ ] Photo card = **"about two cents"**
- [ ] `.vcf` = **"zero, not rounded — zero"**
- [ ] Cold-cache recovery line ready for beat 1
- [ ] Project/budget close **only** if it was in the beat-1 capture message
- [ ] Four cards in the evals, two more checked by hand — never "six"
- [ ] 25/25 is the **pipeline**; it does not cover the channel
- [ ] Quote the **model-calls-only** latency figure against the slide table
- [ ] Never quote D5's cost table (superseded); never quote D16's "17/17" (stale)

---

## 8. IF SOMETHING BREAKS MID-DEMO

- **Anything feels stuck** → have Vishal type `cancel`. Clears any pending state, costs nothing, says what it dropped.
- **A pending question eats a message** → "That guard exists because a whole lead line with an email in it used to get filed as a company name. Send it again and answer with just the company."
- **A date doesn't parse and it asks** → "It asks rather than guesses. A date format we haven't taught it is the safest possible failure."
- **"Next Monday" resolves nine days out** → "'Next Monday' is genuinely contested — half this room means the 14th and half means the 21st. We resolve it one way and print the resolved date straight back so you can see it. The one thing we won't do is book it silently."
- **The reminder is late** → say nothing; never narrate a countdown.

**Do not offer to open** `handover-nandita-edgecases.md` or `for-nandita-latency-and-bugs.md`. HANDOFF cites both; neither exists in the repo or in any commit.
