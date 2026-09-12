# DEMO SCRIPT — what Vishal types, in order

The typing-only view of `PRESENTATION.md`. Vishal drives, Nandita narrates.
Every string here has been run today. Copy them exactly.

**7 minutes.** Timings are cumulative from the start of the demo.

---

## BEFORE YOU START (do this at ~16:45)

```
git pull --rebase
```
Restart uvicorn. `extract.py`, `pipeline.py`, `followup.py` changed today.

```
.venv\Scripts\python -m tests.demo_check
```
Expect **25/25**. If anything is red, tell Nandita. Do not fix code.

**Warm the prompt cache** — send one typed lead and one business card, then:

```
.venv\Scripts\python tools\send.py reset
```

Reload the dashboard. Cold, the first lead reads $0.0056 instead of $0.002
and the first card reads $0.021 instead of $0.011, while Nandita is saying
"two-tenths of a cent".

**Screen:** Web Chat left third, dashboard right two-thirds, browser at 125%.
Deck on slide 4.

**Have ready:** the voice note `.ogg` on this machine, and the Skyline
`lead_id` (you will need it at 4:55 — get it from the dashboard or
`/docs` → GET `/api/leads`).

---

## 0:00 — Typed lead

Type into Web Chat:

```
New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, email f.mansoori@skylinefitout.ae. 40-unit villa project, budget 3.2m AED.
```

→ *"Lead created for Skyline Fitout."* Card with Add note / Edit / Delete
and a cost line. Row appears on the dashboard.

**You say:** "That's how a salesperson actually types. Not a form."

> The project and budget phrase is required — it is what puts
> `project_name` and `estimated_value` on the record for the 6:20 close.
> The notes path never writes those fields.

---

## 0:40 — Meeting notes and a follow-up

**Tap "Add note" on the Skyline card. Wait for the prompt.** Then type:

```
Met Fatima on site. She wants a revised proposal. Follow up in 2 minutes.
```

→ *"Notes saved. Follow-up set for …"* — the time must match the real wall
clock. If it shows UTC, the server was not restarted.

**You say:** "Two minutes is so it fires while we're still standing here.
In reality they'd say two days."

---

## 1:30 — ⭐ Business card with no company — KEY BEAT, SLOW DOWN

Paperclip → `fixtures\cards\04_no_company.png`

(or `.venv\Scripts\python tools\send.py card fixtures\cards\04_no_company.png`)

**Say nothing while it uploads.**

→ *"I've got Reem Haddad, but no company. Which company are they with?"*

**You say:** "Her email is an outlook.com address. A system that wanted to
look clever would infer the company from the domain. It asked instead."

**Pause. Let it land.** Then type:

```
Delta Steel
```

→ lead created.

---

## 2:40 — Photo of a card

Paperclip → `fixtures\cards\05_photo_dark.jpg`

→ *"Lead created for Marina Gulf Contracting LLC."* about 5 seconds.

---

## 3:20 — Duplicate

```
Lead: Fatima Al Mansoori, Skyline Fitout, f.mansoori@skylinefitout.ae
```

→ *"That looks like an existing lead — Skyline Fitout (matched on email)."*
**No new row on the dashboard.**

**You say:** "It tells you which field matched. It doesn't merge anything
behind your back."

---

## 3:45 — ⭐ Vague follow-up — KEY BEAT, SLOW DOWN

**Tap "Add note" on the Skyline card.** Then type:

```
Good call with Fatima, she likes the pricing. Follow up next week sometime.
```

→ *"You said next week — which day works? For example Monday or Wednesday."*

**You say:** "'Next week sometime' isn't a date. It could have picked Monday
and been right most of the time. Most of the time isn't good enough for
something that books your calendar."

Then type:

```
Monday
```

→ *"Got it — follow-up set for Mon 14 Sep, 09:00."*

---

## 4:40 — The reminder fires

The 2-minute follow-up from 0:40 lands unprompted, in the chat and on the
dashboard.

**Say nothing until it appears.** Then: "That arrived on its own. Nobody
asked for it."

🚫 **DO NOT TYPE A REPLY TO IT.** The reminder is one-way today. "Done"
gets the "I didn't spot lead details in that" message.

---

## 4:55 — Voice note

Two commands. The tool posts as its own user, so the Add-note tap must come
from the tool too.

```
.venv\Scripts\python tools\send.py note <lead_id>
```

```
.venv\Scripts\python tools\send.py voice "C:\path\to\voice.ogg"
```

→ *"Notes saved. Follow-up set for Mon 14 Sep, 09:00."* Summary, key points
and action items on the dashboard, with the raw transcript kept beside them.

**You say:** "Real speech-to-text, and the transcript is kept alongside the
summary — so nothing is lost in the summarising."

**If Deepgram mishears a word** (it renders "Fit Out" as two words and
"revised" as "revisit"): "That's the raw transcript, unedited, stored right
next to the summary — which is exactly why we keep the original."

---

## 5:40 — Create, edit, delete

```
New lead - Yusuf Bin Ali at Arc Glazing, 971 52 888 3131, yusuf@arcglazing.ae
```

- **Edit** on the card → change the mobile → Save → *"Updated mobile for Arc Glazing."*
- **Delete** on the card → *"Lead deleted."* → row disappears from the dashboard.

**You say:** "Create, edit and delete without leaving the conversation. They
never open a CRM tab. That's the whole point of doing this in chat."

---

## 6:20 — The numbers  *(Nandita takes over)*

Point at the economics tile. Then `/docs` → GET `/api/leads` → show
`project_name` and `estimated_value` on the Skyline record.

---

## IF SOMETHING GOES WRONG

**Anything feels stuck** — type:

```
cancel
```

Clears any pending question or Add-note scope, says what it dropped, costs
nothing, no model call. Use it freely between beats.

**A card or voice note fails to upload** — fall back to the tool:

```
.venv\Scripts\python tools\send.py card fixtures\cards\04_no_company.png
```

**The reminder is late** — say nothing. Never narrate a countdown.

**A beat misbehaves** — say what it did, move on. Do not retry more than once
and do not change code.

---

## NEVER DO THESE ON STAGE

- Answer the company question with `I don't know` — it files that as the company name
- Type a numeric date like `2026-09-31` — raises a generic error
- Reply to the fired reminder — it is one-way
- Send a PDF — declined politely, but it is a refusal, not a beat
- Send the same message twice expecting two cards — it is a replay, tagged
  "replay · not counted" on the dashboard
