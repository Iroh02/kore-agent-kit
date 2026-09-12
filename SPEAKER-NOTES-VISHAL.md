# VISHAL — SPEAKER NOTES
### Chat-to-Lead, 17:00. You drive the demo; Nandita narrates the numbers.

**Your three speaking slots:** 7:00 live demo (you drive) → 1:10 the channel → 1:30 risks & what's mocked. Plus Q&A.

---

## 🔴 FIVE THINGS TO FIX BEFORE YOU WALK UP

1. **Say "a hundred and thirty lines," not "about eighty."** `PRESENTATION.md` line 240 says eighty. That's the aspiration in the file's own docstring. Measured: `app/channels/teams.py` is 252 lines, **130 of them code**; `app/channels/cards.py` is 178 lines, **118 code**. If a judge opens the file and counts, 130 is right and still startlingly small.
2. **Say "nineteen defects," not "twenty-four."** `PRESENTATION.md` line 285 says twenty-four; no list of twenty-four exists anywhere in the repo. The deck slide shows **12**, `HANDOFF.md` lists **19**. Your line: *"Nineteen. The slide shows twelve — we found seven more after we built the deck."*
3. **Add project and budget to the beat-1 typed lead** (exact text in the demo section). Without it, Nandita's closing line about "project name and estimated value" is false — those fields are written in one place only, `app/pipeline.py:468-470`, on the capture path. A note never writes them.
4. **Warm the prompt cache ~60 seconds before you start.** Send one typed lead and one business card through Web Chat, then `send.py reset` and reload the dashboard. Cold, the first text lead reads ~$0.0056 instead of $0.002 and the first card reads $0.021 instead of $0.011 — while Nandita says "two-tenths of a cent."
5. **Seed the 2-minute follow-up by TYPING IN WEB CHAT, never via `send.py`.** The scheduler can only push a reminder into the chat if the lead carries a real `conversation_id` and `service_url`. A lead created through `send.py` carries `https://smba.example/` — the reminder will say **"send failed"** and appear on the dashboard only.

Also: **do not restart the server** once the demo starts. The bot's channel account is an in-process global learned from inbound traffic; a restart clears it and proactive reminders stop reaching the chat.

---

# 1. WHAT YOU OWN — and what you must be able to answer

You own `app/api.py`, `app/channels/teams.py`, `app/channels/cards.py`, `fixtures/`, `manifest/`, and the Azure setup. Nandita owns everything downstream.

### The one-sentence framing
> "My half is transport. Bytes in and out of the chat, and a card back. Nothing in my half knows what a lead is."

### The three primitives — know these cold
`app/channels/teams.py` opens with its own design rule: *THREE PRIMITIVES ONLY. This file moves bytes; it never interprets them.*

| Primitive | What it does |
|---|---|
| `get_token()` | Client-credentials bearer token for the Bot Framework. Cached in-process, refreshed **60 s before expiry**. |
| `send_activity(service_url, conversation_id, activity)` | POSTs a message or card into a conversation. Used for replies **and** for proactive follow-ups. |
| `fetch_attachment(att)` | Raw bytes for one attachment. Two auth paths — below. |

There is a fourth function that isn't a primitive but earns its place: `to_inbound_event(activity)`, the normaliser that turns a Bot Framework Activity into the `InboundEvent` the pipeline eats. **It is the only place Teams vocabulary exists in the whole repo.**

Timeouts, if asked: token 15 s, send 20 s, attachment fetch 30 s.

### Why there is no Microsoft SDK
The protocol is two HTTP calls:
```
token:  POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
        grant_type=client_credentials  scope=https://api.botframework.com/.default
reply:  POST {serviceUrl}/v3/conversations/{conversationId}/activities
        Authorization: Bearer {token}
```
The SDK would have added a dependency, an async event-loop model to reconcile with FastAPI, and a layer between you and the exact JSON Microsoft was rejecting. **When the 400s started, we could read the wire format directly.** That's the payoff — say it if challenged.

### The two attachment doors (your most technically interesting fact)

| Path | How it arrives | Auth | Status |
|---|---|---|---|
| Teams file / voice note | `contentType: application/vnd.microsoft.teams.file.download.info` + `content.downloadUrl` | **Pre-authenticated** — plain GET, no token | Runs against our own server; **never against a live Teams tenant** |
| Web-client upload / Teams inline image | top-level `contentUrl` | **Needs the bot's bearer token** | Web Chat shape captured in fixtures |

One sentence for a judge: *"Teams hands the bot a short-lived pre-signed link — the permission is baked into the URL. The web client hands you a plain resource URL and expects the bot to prove who it is at fetch time. Same word 'attachment', two security models."*

Anything carrying bytes is classified by content type, then by filename suffix, most specific first — nothing is dropped silently. That fix was bug 5.

### Why buttons in the chat, not a dashboard
`cards.py` calls this "our Teams advantage" and it's a **product** argument, not a technical one:
> "The whole premise is that the salesperson never opens a CRM tab. If the confirmation lands in a side dashboard, you have re-created the CRM tab. CRUD inside the chat is the only version that keeps the premise intact."

It also does double duty: the brief requires *"confirm back what was created, or ask for what's missing"* — **the card is that confirmation.**

Mechanics: an `Action.Submit` press posts back a normal `message` Activity with a top-level `value` payload (**not** an `invoke` — confirmed in `fixtures/webchat/message_cardbutton_*.json`). `to_inbound_event` sees `value`, sets `kind=COMMAND`, `pipeline._handle_command` dispatches on the `action` string. Adaptive Card schema **version 1.5**. Four card types: lead confirmation, clarification, duplicate, plain text.

Two choices worth naming if asked:
- **Every card carries a cost line** — `$0.0029 · 2396 ms · llm + db` — rendered from the ledger. Economics in every screenshot, not one slide.
- **The clarification card deliberately has no button.** The pipeline holds `lead=None` until the company arrives, so any button there would carry `lead_id=""`. Typing the answer is the correct path.
- **Edit exposes Mobile and Email only** (`cards.py` lines 104-118). Don't offer to edit a company name live.

---

# 2. THE LIVE DEMO — 7:00, beat by beat

**Screen:** Web Chat left third, dashboard right two-thirds. Let the dashboard update in silence — judges will watch rows appear on their own.

**Before you start:** warm-up send → `send.py reset` → **reload the dashboard** (its counters are client-side and will otherwise carry rehearsal numbers into the demo).

---

### BEAT 1 — 0:00–0:40 · Typed lead
**Type into Web Chat, exactly this (note the added project and budget):**
```
New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, email f.mansoori@skylinefitout.ae. 40-unit villa project, budget 3.2m AED.
```
**Expect:** confirmation card with Add note / Edit / Delete, a cost line at the bottom, and a new row on the dashboard.

**You say:** *"That's how a salesperson actually types. Not a form."*

**Nandita:** "Two-tenths of a cent. About two and a half seconds. Bottom of the card."

> ⚠️ Do **not** put a follow-up phrase in this message. `_persist_lead` ignores follow-ups on the capture path — a follow-up only parses through "Add note."

---

### BEAT 2 — 0:40–1:30 · Meeting notes + the seeded reminder
Tap **Add note** on the Skyline card. Wait for the prompt. Then type:
```
Met Fatima on site. She wants a revised proposal. Follow up in 2 minutes.
```
**Expect:** *"Notes saved. Follow-up set for …"*

**You say:** *"Two minutes is so it fires while we're still standing here. In reality they'd say two days."*

> 🕐 **Timing truth the script gets wrong.** The script parks the reminder at 4:40. It will actually land about **two and a half minutes after you send this** — roughly during the photo-card or duplicate beat — and the scheduler polls every 30 s so it can be up to half a minute later than that. **Don't fight it.** When it lands mid-sentence, finish your sentence, then point at it. An interruption you didn't schedule is better proof it's unprompted than one you did.

---

### ⭐ BEAT 3 — 1:30–2:40 · BUSINESS CARD WITH NO COMPANY — **KEY BEAT, SLOW DOWN**

Paperclip → `/Users/candyswaris/Documents/kore-agent-kit/fixtures/cards/04_no_company.png`

**Expect:** *"I've got Reem Haddad, but no company. Which company are they with?"*

**You say:** *"Her email is reem-at-outlook. A system that wanted to look clever would infer the company from the domain. It asked instead."*

### ⏸ **PAUSE HERE. Three full seconds. Say nothing. Look at the card.**
This is the single best moment in the presentation. Let the room finish the thought for you.

**Then type exactly two words:**
```
Delta Steel
```
**Expect:** lead created.

**Nandita:** "That question cost nothing. Refusing to guess is cheaper than guessing wrong."

> ⚠️ **Type exactly `Delta Steel`.** A wordy answer — one containing `@`, or two commas, or over 60 characters, or over 8 words — is treated as a new message, and the parked extraction (Reem's name, email and mobile) is **dropped without notice**. Recovery line is in section 5.

---

### BEAT 4 — 2:40–3:20 · Photo of a card
Paperclip → `/Users/candyswaris/Documents/kore-agent-kit/fixtures/cards/05_photo_dark.jpg`

**Expect:** *"Lead created for Marina Gulf Contracting LLC."*

**You say nothing.** Let Nandita take it — this beat is hers.

**Nandita:** "About two cents, roughly five seconds. Six to ten times the text path. That's the vision call, and it's the single most expensive thing we do — which is exactly why we price per component instead of quoting one average."

---

### BEAT 5 — 3:20–3:45 · Duplicate
```
Lead: Fatima Al Mansoori, Skyline Fitout, f.mansoori@skylinefitout.ae
```
**Expect:** *"existing lead … matched on email"*, **no new row on the dashboard.**

**You say:** *"It tells you which field matched. It doesn't merge anything behind your back."*

---

### ⭐ BEAT 6 — 3:45–4:40 · VAGUE FOLLOW-UP — **KEY BEAT, SLOW DOWN**

Tap **Add note** on the Skyline card first. Wait for the prompt. Then:
```
Good call with Fatima, she likes the pricing. Follow up next week sometime.
```
**Expect:** *"…which day works?"*

**You say:** *"'Next week sometime' isn't a date. It could have picked Monday and been right most of the time."*

### ⏸ **PAUSE. Two seconds.**

*"Most of the time isn't good enough for something that books your calendar."*

**Then type:**
```
Monday
```
**Expect:** *"follow-up set for Mon 14 Sep, 09:00."*

> ⚠️ Type `Monday`, not `next Monday` — "next Monday" resolves nine days out, to Mon 21 Sep. And never type a raw ISO date: `2026-09-31` raises a ValueError and you get the generic error message.

---

### BEAT 7 — whenever it lands · The reminder fires
The seeded follow-up drops into the chat unprompted, and onto the dashboard.

**You say:** *"That arrived on its own. Nobody asked it. That's the bot writing back into a conversation it stored two minutes ago."*

> 🚫 **Do not type a reply to it.** It's one-way. "Done" hits the chit-chat path and you get "I didn't spot lead details in that."

---

### BEAT 8 — 4:55–5:40 · Voice note
```bash
.venv/bin/python tools/send.py leads
.venv/bin/python tools/send.py note <lead_id>
.venv/bin/python tools/send.py voice fixtures/audio/real_speech.wav
```
**Expect:** *"Notes saved…"* plus the transcript printed alongside the summary.

**You say:** *"Real speech-to-text, and the raw transcript is kept alongside the summary — so nothing is lost in the summarising."*

**Nandita:** "Deepgram, priced by the second, on its own line in the ledger."

> ⚠️ This beat runs on the CLI and lands on the dashboard, not in the chat. Say so in half a sentence if anyone looks puzzled: *"That one's through our own CLI onto the dashboard — same pipeline, different door."*

---

### BEAT 9 — 5:40–6:20 · CRUD inside the chat
```
New lead - Yusuf Bin Ali at Arc Glazing, 971 52 888 3131, yusuf@arcglazing.ae
```
- Tap **Edit** → change the **mobile** → **Save** → *"Updated mobile for Arc Glazing."*
- Tap **Delete** → *"Lead deleted."* → the row disappears from the dashboard.

**You say:** *"Create, edit and delete without leaving the conversation. They never open a CRM tab. That's the whole point of doing this in chat."*

> ⚠️ Change the mobile, not the email, and don't blank a field — a lone space used to wipe a stored mobile and its dedupe key. That's fixed, but don't go looking for it.

---

### BEAT 10 — 6:20–7:00 · Hand over
Open the economics tile, then `/docs → GET /api/leads` on the projector. **Nandita talks.** You stand back.

---

# 3. YOUR ARCHITECTURE LINES — 1:10, spoken

> Four short blocks. Block 3 is the one people remember. Do not rush it and do not add a third war story on stage.

**Block 1 — what your half is (20 sec)**

> "My half is transport. Bytes in and out of the chat, and a card back. Nothing in my half knows what a lead is."
>
> "There's **no Microsoft SDK**. The Bot Framework turns out to be plain JSON over HTTPS, so we wrote it ourselves — **a hundred and thirty lines, three functions. Get a token. Post an activity. Download an attachment.** That's the entire channel."
>
> "Everything downstream speaks a plain Python object. The chat app is an adapter, not the architecture — which is why Nandita built and tested the whole pipeline all day with the channel completely down."

**Block 2 — cards (15 sec)**

> "And the reply is a card with real buttons. Add note, Edit, Delete — inside the chat. That's deliberate. The moment you put the confirmation in a side dashboard, you've re-invented the CRM tab the salesperson was already refusing to open."
>
> "Every card also carries what that action cost and how long it took. The economics are in every screenshot, not just on one slide."

**Block 3 — the war story (35 sec). Keep it fast, don't editorialise.**

> "Two bugs ate our morning, and they're the real cost of standing up a new channel."
>
> "**One — the bot couldn't get a security pass at all.** 'Application not found in directory.' Our bot is registered to *our* directory; we were asking Microsoft's, because that's what the documentation shows. Wrong front desk. One word, in one URL."
>
> "**Two — then it could read every message perfectly and could not reply.** Every single reply rejected: four hundred, missing property. A reply has to say who it's *from* — and the sender is sitting right there on the incoming message, because the bot is who the message was addressed *to*. Swap two fields, send it back."
>
> "Neither of those is in a tutorial. That's the argument for proving the channel before writing a line of AI code."

**If you find yourself 20 seconds ahead, this is your best bug — otherwise save it for Q&A:**

> "There's a third one that would have wrecked this demo. Teams doesn't just send you messages — it sends you 'chat opened' and 'user is typing', to the same webhook. We were running the full pipeline on those. So about two and a half seconds after you open the chat, before you've typed a word, the bot asks 'which company?' about nothing — and then eats your first real message as the answer to that question. **The demo broke before it started.**"

**Error codes, in order, if anyone wants them:** `AADSTS700016` → `400 MissingProperty` → `403 → 200`.

---

# 4. YOUR RISKS / WHAT'S-MOCKED LINES — 1:30

> Say these before anyone asks. Volunteering your worst vulnerability, precisely, is the strongest credibility move available to you.

**The datastore (20 sec)**
> "The datastore is ours, not Intrakore's CRM. No sandbox, no credentials — and an elaborate fake CRM client proves nothing and eats two hours. The brief allows a working data store and this is one. Production needs six things: field mapping, auth and token refresh, idempotency keys, rate limits, an error taxonomy, and a retry queue. We can name all six because we know exactly where the boundary is."

**Security — lead with the specific one (30 sec)**
> "No inbound JWT validation on the webhook, and no auth on the REST layer. Deliberate one-day cuts, and I'll tell you exactly what they cost. The `serviceUrl` — the address we post replies to — arrives on that unauthenticated payload, and we send the bot's bearer token to it. So an unauthenticated POST to our webhook could point us at an attacker's server and leak that token. **That's why validating the Bot Framework JWT is the first line of the production list and not the fifth.** It's also why our handover says, in capital letters, do not deploy this."

Two honest mitigations you can add if it lands hard: the dashboard HTML-escapes everything the model produces (`ui/dashboard.html`), and `update_lead` allow-lists column names before building SQL — so the dynamic SQL isn't injectable.

**Web Chat, not the Teams client (20 sec) — flat, no apology, then move on**
> "We're in Microsoft's Azure Web Chat, not the Teams client. Sideloading a custom app needs a work or school tenant with custom app upload enabled. We had a personal account, and the university tenant only offers 'submit to your IT admin' — that's days, not hours."
>
> "Same bot registration. Same Bot Framework protocol. Same Adaptive Card renderer. What we lose is Teams-native file attachments, which are built to the documented contract and have never met a live tenant."

*Backup if pressed:* the Teams app package is built and sitting in the repo — `manifest/manifest.json`, `chat-to-lead.zip`, manifest version 1.16, bot scope `personal`, `supportsFiles: true`. **The package exists; the permission doesn't.**

**Volunteer the specific unverified thing (15 sec) — this is what makes the rest credible**
> "And a specific gap inside that: in our own captures, Teams reports a file's type sometimes as a MIME type and sometimes as a bare extension. We only ever saw the audio and vCard variants, so a Teams-client *image* would very likely misclassify. That's a lookup table and thirty minutes with a real tenant — and it's exactly the kind of thing you cannot know without the real client."

**One-way reminders (10 sec)**
> "The follow-up reminder fires into the chat unprompted — that's the part that makes it a product rather than a form. Closing the loop from the chat needs a state machine on the follow-up object, not a keyword, because 'done' has to mean done-for-this-follow-up and not done-for-the-lead. Done and Snooze buttons on the reminder card is the day-two shape."

**The defect count (10 sec)**
> "We found and fixed **nineteen** defects today — the slide shows twelve, and we found seven more after we built it. Nearly all of them came from **running the demo against ourselves**, including one that would have frozen the whole process for thirty minutes on a bad network."

---

# 5. RECOVERY LINES — what to say when a beat misbehaves

**The attachment doesn't come through / console prints `[attachment fetch failed]`**
> "That's our web-client attachment path asking for a token it didn't get — the diagnostic line is there precisely so that's a ten-second call, not a guess. Here it is through our own CLI."

Then immediately:
```bash
.venv/bin/python tools/send.py card fixtures/cards/04_no_company.png
```
Have that command typed and waiting in a second terminal before you start.

**The first card shows ~$0.021 instead of a cent**
> "That's the first call of the session paying to write the prompt cache — sixteen hundred tokens of schema. Every card after it reads the same prefix at a tenth of the price. Watch the next one drop."

Then point at the next card dropping to ~$0.011. That turns a discrepancy into a demonstration.

**Same thing on the first typed lead (~$0.0056)** — identical line, "fifteen hundred tokens of schema."

**The company answer gets swallowed and the parked lead vanishes**
> "That guard is there because a whole lead line with an email in it used to get filed as a company name — it cost us the parked contact. Send the card again and answer with just the company."

**A short chatty answer files "she's with Delta Steel LLC in Dubai" as the company**
> "One Edit tap fixes it — and the card showing you exactly what was captured is the whole point."

**Anything feels stuck / a question is hanging**
Type `cancel`. It clears any pending state, costs nothing, no model call, and tells you what it dropped. Use it freely between beats — it's the cheapest safety net you have.

**The reminder says "send failed" on the dashboard**
> "The proactive send needs the bot's own channel account, which it learns from inbound traffic — and this one was seeded through our CLI rather than the chat, so it lands on the dashboard. Same event, one surface instead of two."

**Deepgram mishears the voice note**
> "That's the transcript, unedited, stored next to the summary — which is exactly why we keep the original. The summariser reads what the transcriber heard, and you can see both."
A mis-transcription you can point at is a better answer than a clean one you can't audit.

**The bot doesn't reply at all**
Don't debug on stage. Move to the CLI (`send.py text "…"`), say *"I'll take that to the terminal — the pipeline is the same either side"*, and keep going.

**Everything hangs for ~10 seconds**
> "One worker, one message at a time — extraction runs synchronously, which is why these latency numbers are clean and uncontended. Production is a queue between the webhook and the pipeline."

---

# 6. QUESTIONS MOST LIKELY TO COME TO YOU

**"Why not use the Bot Framework SDK?"**
> "Because the protocol is two HTTP calls, and we'd have inherited a dependency and an async event-loop model to reconcile with FastAPI. And when Microsoft started rejecting our replies with a four hundred, we could read the exact JSON on the wire. With the SDK there'd have been a layer between us and the thing that was wrong."

**"How much work to move this to WhatsApp or Telegram?"**
> "Two files. `channels/teams.py` and `channels/cards.py` — a hundred and thirty lines and a hundred and eighteen. Everything downstream speaks our own object. The pipeline was built and tested all day with the channel completely down, which is the proof that boundary is real."

**"How do you stop a retried message creating two leads?"**
> "Idempotency on the Bot Framework activity id — it's the primary key of our activities table. A repeat is a no-op that returns the original result, the original trace id, the original ledger. And send failures on our side are swallowed deliberately: a non-200 back to Bot Framework makes it redeliver, and a redelivered activity is exactly how one message becomes two leads."
*(If pressed further, be honest: "There's no lock. The write happens after the work, so two simultaneous deliveries would both pass the check. In practice the single event loop serialises them — that's luck with a good outcome, not design.")*

**"Is the webhook secure?"**
> "No, and it's named on the slide. No inbound JWT validation against Bot Framework's OpenID keys, no rate limiting, and no auth on the REST layer. It's the first thing I'd add — it's an afternoon, not a redesign. And the specific reason it matters is the `serviceUrl` token path I mentioned."

**"Is the channel tested?"**
> "Not by automated tests — zero. Our twenty-five out of twenty-five is the pipeline; those tests construct our internal event object directly and never touch the channel code. The channel was verified by live Web Chat traffic and by replaying our own captured payloads. I'd rather tell you that than let a green number cover it."
**Never let 25/25 imply channel coverage.** This is the answer that costs you least if you give it first.

**"The attachment URLs in your repo — isn't that a leak?"**
> "Caught and fixed. Raw captures carry about a kilobyte of JWT in each attachment URL, an Azure-issued key in the recipient id containing the marker Microsoft's own secret scanners look for, and the sender's photo inlined as base64. The repo is public. The raw directory is gitignored and a sanitiser strips all three while preserving the structure exactly — only the twelve sanitised fixtures are committed."

**"Why is the typing indicator interesting?"**
> "It isn't, technically — it's cosmetic. We fire a typing indicator so the wait isn't silent, and it's deliberately kept out of the latency total."
*Do not say "concurrently" — the task is scheduled but nothing yields before the pipeline completes, so it actually fires after. Cosmetically identical, factually wrong.*

**"What happens when twenty salespeople message at once?"**
> "One worker, and extraction runs synchronously in the event loop, so we process one message at a time. For today that's a feature — it's why the latency numbers on that panel are clean and uncontended. For production it's a queue between the webhook and the pipeline, plus load testing we haven't done. I know the shape of the fix; I haven't measured it, so I won't quote you a throughput number."

**"Could a business card contain a prompt injection?"**
> "Not hardened, and the blast radius is deliberately small — the model has no tools and can't act. It fills a fixed form and hands it back to code that decides what happens. Worst case is a bad field value on a confirmation card a human is already reading. Real hardening is input fencing and an output allow-list — an item, not a claim."

**"Why cards in chat rather than a proper UI?"**
> "Because the premise is that the salesperson never opens a CRM tab. The moment the confirmation lands in a side dashboard, you've re-created the tab they were already refusing to open. The dashboard we do have is for you, not for them."

---

# 7. THIRTY-SECOND PRE-STAGE CHECKLIST

- [ ] Warm-up send done, then `send.py reset`, then **dashboard reloaded**
- [ ] Second terminal open with `send.py card fixtures/cards/04_no_company.png` typed and waiting
- [ ] Server **not** restarted since the warm-up
- [ ] Beat 1 text includes **"40-unit villa project, budget 3.2m AED"**
- [ ] Say **"a hundred and thirty lines"**, not "about eighty"
- [ ] Say **"nineteen defects"**, not "twenty-four"
- [ ] Beat 3: pause **three seconds** before typing `Delta Steel` — exactly two words
- [ ] Beat 6: type `Monday`, not "next Monday". Never a raw ISO date.
- [ ] Do **not** reply to the reminder when it fires
- [ ] Never let **25/25** imply the channel is tested
- [ ] Volunteer the webhook JWT + `serviceUrl` token path as "what I'd fix first"
- [ ] `cancel` is your reset button between beats — free, instant, says what it dropped

---

## FILES, IF YOU NEED TO OPEN ONE LIVE
- `/Users/candyswaris/Documents/kore-agent-kit/app/channels/teams.py` — the three primitives; `to_inbound_event` at the bottom
- `/Users/candyswaris/Documents/kore-agent-kit/app/channels/cards.py` — `_cost_line()` at line 53, the Edit ShowCard at 104
- `/Users/candyswaris/Documents/kore-agent-kit/app/api.py` — `/api/messages` webhook, `_envelope()`, the `TODO` marking the missing JWT check
- `/Users/candyswaris/Documents/kore-agent-kit/app/scheduler.py` — the proactive-send comment block explaining 403 → 200
- `/Users/candyswaris/Documents/kore-agent-kit/manifest/manifest.json` — the Teams package that exists but can't be sideloaded
