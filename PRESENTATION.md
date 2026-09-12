# Chat-to-Lead — 13 minute run of show

2:00 user flow · 7:00 live demo · 4:00 architecture & code · ~2:00 Q&A buffer

**V** = Vishal · **N** = Nandita
Screen: Web Chat left third, dashboard right two-thirds. Deck on slide 7.

---

# PART 1 — USER FLOW (2:00)   · N speaks · deck on screen

### 0:00–0:30 — The problem

"A salesperson meets a lead. The details are on a business card in their
pocket, or in a voice note they recorded walking to the car."

"By the time anyone types that into a CRM — if anyone ever does — it's three
days old and half of it is missing. That's the gap. Not lead generation.
Lead *capture*."

### 0:30–1:15 — What the salesperson actually does

"So we put it where they already are: a chat window."

"They send whatever they have. Typed details. A photo of a card. A shared
contact. A voice note walking out of the meeting."

"The bot reads it, confirms back what it captured, and — this is the part
that matters — **asks when it isn't sure, instead of guessing.**"

"Then they say when to follow up, in their own words. 'After two days.'
'Next week sometime.' And it schedules it, or it asks which day."

### 1:15–2:00 — Why it's trustworthy

"Three design decisions you'll see in the demo."

"**It never invents a value.** A missing company comes back as a question,
not a plausible guess from the email domain."

"**It never silently guesses a date.** Vague timing gets a question back."

"**Every single action is priced and timed** — in real money, from real
usage, per component. You'll see that panel on the right throughout."

**Hand to V:** "Vishal's going to run it live."

---

# PART 2 — LIVE DEMO (7:00)   · V drives · N narrates the numbers

> Both panes visible the whole time. Let the dashboard update in silence —
> the judges will watch rows appear on their own.

### 0:00–0:40 — Typed lead  *(V)*

```
New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, email f.mansoori@skylinefitout.ae
```

**V:** "That's how a salesperson actually types. Not a form."

→ card appears, row appears on the dashboard

**N:** "Two-tenths of a cent. Two and a half seconds. Bottom of the card."

---

### 0:40–1:30 — Meeting notes + follow-up  *(V)*

Tap **Add note**, wait for the prompt, then:

```
Met Fatima on site. 40-unit villa project, budget 3.2m AED. She wants a revised proposal. Follow up in 2 minutes.
```

**V:** "Two minutes is so it fires while we're still standing here. In
reality they'd say two days."

→ *"Notes saved. Follow-up set for …"*

**N:** "It also pulled the project and the budget out of that sentence —
we'll show those fields at the end."

---

### 1:30–2:40 — ⭐ Business card with no company  *(V)*   **KEY BEAT — slow down**

Paperclip → `fixtures/cards/04_no_company.png`

→ *"I've got Reem Haddad, but no company. Which company are they with?"*

**V:** "Her email is reem@ — a system that wanted to look clever would
infer the company from the domain. It asked instead."

*(pause — let that land)*

```
Delta Steel
```

→ lead created

**N:** "That question cost nothing. Refusing to guess is cheaper than
guessing wrong."

---

### 2:40–3:20 — Photo of a card  *(V)*

Paperclip → `fixtures/cards/05_photo_dark.jpg`

→ *"Lead created for Marina Gulf Contracting LLC."*

**N:** "Two cents, about five seconds. Six times the text path — that's the
vision call, and it's the single most expensive thing we do. Which is
exactly why we measure per component rather than quoting one average."

---

### 3:20–3:45 — Duplicate  *(V)*

```
Lead: Fatima Al Mansoori, Skyline Fitout, f.mansoori@skylinefitout.ae
```

→ *"existing lead … matched on email"*, **no new row**

**V:** "It tells you which field matched. It doesn't merge anything behind
your back."

---

### 3:45–4:40 — ⭐ Vague follow-up  *(V)*   **KEY BEAT — slow down**

Tap **Add note** on Skyline, then:

```
Good call with Fatima, she likes the pricing. Follow up next week sometime.
```

→ *"which day works?"*

**V:** "'Next week sometime' isn't a date. It could have picked Monday and
been right most of the time. Most of the time isn't good enough for
something that books your calendar."

```
Monday
```

→ *"follow-up set for Mon 14 Sep, 09:00"*

---

### 4:40–4:55 — The reminder fires  *(V — say nothing, let it happen)*

The 2-minute follow-up lands unprompted in the chat and on the dashboard.

**V:** "That arrived on its own. Nobody asked it. That's the bot writing
back into a conversation it stored two minutes ago."

🚫 **Do not type a reply.**

---

### 4:55–5:40 — Voice note  *(V)*

```bash
.venv/bin/python tools/send.py note <lead_id>
```
```bash
.venv/bin/python tools/send.py voice "<path to the .ogg>"
```

→ *"Notes saved. Follow-up set for Mon 14 Sep, 09:00."*

**V:** "Real speech-to-text, real transcript kept alongside the summary —
so nothing is lost in the summarising."

**N:** "Deepgram, priced by the second, on its own line in the ledger."

---

### 5:40–6:20 — CRUD inside the chat  *(V)*

```
New lead - Yusuf Bin Ali at Arc Glazing, 971 52 888 3131, yusuf@arcglazing.ae
```

- **Edit** → change the mobile → Save → *"Updated mobile for Arc Glazing."*
- **Delete** → *"Lead deleted."* → row disappears

**V:** "Create, edit and delete without leaving the conversation. They never
open a CRM tab. That's the whole point of doing this in chat."

---

### 6:20–7:00 — The numbers  *(N)*

Point at the economics tile, then `/docs → GET /api/leads`.

**N:** "Everything you just watched: total activities, total cost, average
latency — split into all calls versus model calls, because the database and
the chat API cost nothing but still take time."

"And here's the Skyline record — project name and estimated value, pulled
out of a spoken sentence, sitting in structured fields."

---

# PART 3 — ARCHITECTURE & CODE (4:00)

### 0:00–1:20 — The shape of it  *(N)*   · architecture slide

"It's a **fixed pipeline, not an agent.**"

"We know what comes in and what has to come out, so the steps are code. The
model does one job at one station: reading fields out of text, a photo or a
transcript."

"That's why we can tell you it costs two-tenths of a cent and takes two and
a half seconds. An agent picks its own number of calls, and then you can't
quote a number at all."

"The model fills a form — it never writes prose we then parse. Output is
schema-validated; invalid output retries once with the error fed back, then
abstains and asks. That's the difference between a caught error and a wrong
record."

"The one place we *do* use tool-calling is chat CRUD — 'change the mobile
for Acme' — because which record, which field, which operation genuinely
can't be enumerated up front. That's the test for when an agent earns its
place."

### 1:20–2:30 — The channel  *(V)*

"My half is transport. Bytes in and out of the chat, and a card back."

"No Microsoft SDK. The Bot Framework is JSON over HTTPS — about a hundred and thirty lines we wrote ourselves. Get a token, post an activity, download an attachment."

"Everything downstream speaks a plain Python object. The chat app is an
adapter, not the architecture — which is why the pipeline was built and
tested all day without the channel being up."

**The war story — 40 seconds, keep it fast:**

"Two bugs ate our morning, and they're the real cost of a new channel."

"The bot couldn't get a security pass at all — 'application not found in
directory.' Our bot is registered to *our* directory; we were asking
Microsoft's. Wrong front desk. One word in one URL."

"Then it could read every message perfectly and couldn't reply. Every reply
rejected — missing property. A reply has to say who it's *from*, and the
sender is sitting on the incoming message: the bot is who the message was
addressed to. Swap two fields, send it back."

"Neither is in a tutorial. That's why we proved the channel before writing
a line of AI code."

### 2:30–4:00 — Risks and what's mocked  *(V)*   · risks slide

> Say these before anyone asks. It reads as judgement, not gaps.

"**The datastore is ours, not Intrakore's CRM.** No sandbox, no credentials.
The brief allows a working data store, and this is one. Production needs
field mapping, auth and token refresh, idempotency keys, rate limits, an
error taxonomy and a retry queue. We can name all six because we know
exactly where the boundary is."

"**We're in Microsoft's Web Chat, not the Teams client.** Installing a
custom app needs a work tenant with upload enabled; we had a personal
account, and the university tenant only offers 'submit to your IT admin' —
days, not hours. Same bot registration, same protocol, same card renderer.
What we lose is Teams-native file attachments, which are built to the
documented contract but unverified on a live tenant."

"**No auth on the webhook, no rate limiting.** Deliberate one-day cuts."

"**The follow-up reminder is one-way.** Closing it from the chat needs a
state machine on the follow-up, not a keyword. Day two."

"We found and fixed nineteen defects today, most of them from automated
adversarial passes over our own code — including one that would have frozen
the whole process for thirty minutes on a bad network."

---

## Q&A — have these ready

**"Is this just ChatGPT in a wrapper?"**
"No. The flow is deterministic code. The model does one job — reading fields
— and its output is schema-validated, so a bad read is a caught error, not a
wrong record. That's why we can quote you a fixed cost per lead."

**"How accurate is it?"**
"Seventy out of seventy on per-field evals across fourteen labelled cases.
And more importantly it's built to abstain — you saw it ask twice."

**"What happens with messy input?"**
*(reproduce it live)* "It flags low confidence, names which fields it's
unsure about, and marks the record for review rather than pretending."

**"How long to production?"**
"The CRM integration is the main piece — mapping our fields to Intrakore's
lead object, plus auth and retries. The chat layer and the extraction are
done."

**"Prompt injection in a business card?"**
"Not hardened, and the blast radius is small — the model fills a fixed form,
it has no tools and can't act. Worst case is a bad field value the human
sees on the confirmation card. Real hardening is a production item."
