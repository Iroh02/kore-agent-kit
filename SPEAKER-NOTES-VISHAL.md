# Speaker notes — Vishal

**You drive the 7-minute live demo. You take the channel (~1:10) and risks
(~1:30) in the architecture segment.**

Quoted lines are things to say out loud. Short sentences. Say them, don't
read them.

---

## 1. Your half, well enough to answer questions

You own **transport**: getting bytes in and out of the chat, and getting a
card back. Three files: `app/channels/teams.py`, `app/channels/cards.py`,
`app/api.py`.

**Three primitives, no SDK.** The Bot Framework is plain JSON over HTTPS, so
there's no `botbuilder` dependency anywhere:

- `get_token()` — client-credentials token, cached, refreshed 60s early
- `send_activity()` — POST an activity into a conversation
- `fetch_attachment()` — download one attachment's bytes

Roughly eighty lines. Everything downstream speaks `InboundEvent`, a plain
Python object, so the pipeline never knows it's Teams.

**Attachments arrive two different ways** and both are needed:

- Teams **files and voice notes** → `application/vnd.microsoft.teams.file.download.info`,
  whose `downloadUrl` is **pre-authenticated** — a plain GET works
- **Inline images and web-client uploads** → a `contentUrl` that needs the
  **bot's bearer token**

**Cards are the advantage.** Because replies are Adaptive Cards, the
salesperson gets create / edit / delete **inside the chat**. They never open
a CRM tab. `cards.py` renders four shapes: lead confirmation, clarification
question, duplicate warning, and plain text.

**The line between you and Nandita:** you move bytes, she interprets them.
`teams.py` returns raw attachment bytes and never looks inside them.

---

## 2. The live demo — beat by beat

> Web Chat left third, dashboard right two-thirds. Let the dashboard update
> in silence; the judges will watch rows appear on their own.

### A · Typed lead — 0:40

```
New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, email f.mansoori@skylinefitout.ae
```

> "That's how a salesperson actually types. Not a form. No fields."

→ card + dashboard row. **N quotes the cost line.**

### B · Notes and a follow-up — 0:50

**Tap "Add note" first.** Wait for the prompt.

```
Met Fatima on site. 40-unit villa project, budget 3.2m AED. She wants a revised proposal. Follow up in 2 minutes.
```

> "Two minutes so it fires while we're still standing here. In reality
> they'd say two days."

→ *"Notes saved. Follow-up set for …"*

### C · ⭐ Card with no company — 1:10 — **SLOW DOWN**

Paperclip → `fixtures/cards/04_no_company.png`

→ *"I've got Reem Haddad, but no company. Which company are they with?"*

> "Her email is reem-at-something. A system trying to look clever would
> infer the company from the domain."

***(pause — two full seconds. Let it land.)***

> "It asked instead."

```
Delta Steel
```

→ created.

### D · Photo of a card — 0:40

Paperclip → `fixtures/cards/05_photo_dark.jpg`

→ *"Lead created for Marina Gulf Contracting LLC."*

> "Photographed card, bad light, read straight off the image. No separate
> OCR step — it's one call."

**N quotes the vision cost.**

### E · Duplicate — 0:25

```
Lead: Fatima Al Mansoori, Skyline Fitout, f.mansoori@skylinefitout.ae
```

→ *"existing lead … matched on email"*, no new row.

> "It tells you which field matched. It doesn't merge anything behind your
> back."

### F · ⭐ Vague follow-up — 0:55 — **SLOW DOWN**

**Tap "Add note" on Skyline first.**

```
Good call with Fatima, she likes the pricing. Follow up next week sometime.
```

→ *"which day works?"*

> "'Next week sometime' isn't a date. It could have picked Monday and been
> right most of the time."

***(pause)***

> "Most of the time isn't good enough for something that books your diary."

```
Monday
```

→ *"follow-up set for Mon 14 Sep, 09:00"*

### G · The reminder fires — 0:15

It arrives on its own.

> "Nobody asked for that. That's the bot writing back into a conversation it
> stored two minutes ago."

🚫 **Do not type a reply.** The reminder is one-way.

### H · Voice note — 0:45

```bash
.venv/bin/python tools/send.py note <lead_id>
```
```bash
.venv/bin/python tools/send.py voice "<path to the .ogg>"
```

> "Real speech to text. And we keep the transcript next to the summary, so
> nothing is lost in the summarising."

### I · CRUD in the chat — 0:40

```
New lead - Yusuf Bin Ali at Arc Glazing, 971 52 888 3131, yusuf@arcglazing.ae
```

**Edit** → change the mobile → Save → *"Updated mobile for Arc Glazing."*
**Delete** → *"Lead deleted."* → row disappears.

> "Create, edit and delete without leaving the conversation. That's the
> whole reason to do this in chat."

⚠️ Change a field before saving — blank now returns *"Nothing to update."*

### L · Hand to Nandita for the numbers — 0:40

---

## 3. Your architecture lines (~1:10)

> "My half is transport. Bytes in and out of the chat, and a card back."

> "There's no Microsoft SDK in this. The Bot Framework is just JSON over
> HTTPS, so we wrote it ourselves — about eighty lines. Get a token, post a
> message, download a file."

> "After that, everything is a plain Python object. The chat app is an
> adapter, not the architecture. If Teams had died at midday, the rest of
> this would still have been finished on time."

### The war story — 40 seconds, keep it fast

> "Two bugs ate our morning. Both are worth thirty seconds, because they're
> the real cost of standing up a new channel."

> "First: the bot couldn't get a security pass at all. Microsoft kept saying
> 'application not found in directory.'"

> "Our bot is registered to our directory. We were asking Microsoft's
> directory for the pass. Wrong front desk. The fix was one word in one URL."

> "Second: it could read every message perfectly and couldn't reply. Every
> reply came back rejected — missing property."

> "A reply has to say who it's *from*. We'd filled in who it was *to*. And
> the sender is sitting right there on the incoming message — the bot is
> whoever the message was addressed to. Swap two fields, send it back."

> "Neither of those is in a tutorial. That's why we spent the first hour
> proving the channel before writing a line of AI code."

---

## 4. Risks and what's mocked (~1:30)

> Say these before you're asked. Naming a limit reads as judgement.

> "Three things are deliberately not production, and I'd rather tell you
> than have you find them."

> "**The datastore is ours, not Intrakore's CRM.** We had no sandbox and no
> credentials. The brief allows a working data store, and this is one. For
> production you'd need field mapping, auth and token refresh, idempotency
> keys, rate limits, an error taxonomy and a retry queue. I can name all six
> because I know exactly where the boundary sits."

> "**We're in Microsoft's Web Chat, not the Teams client.** Installing a
> custom app needs a work tenant with app upload enabled. We had a personal
> account, and the university tenant only offers 'submit to your IT admin' —
> that's days, not hours. It's the same bot registration, the same protocol,
> the same card renderer. The only thing we lose is Teams-native file
> attachments, which are built to Microsoft's documented contract but not
> verified against a live tenant."

> "**No authentication on the webhook, no rate limiting.** Deliberate
> one-day cuts."

> "And the follow-up reminder is one-way today. Closing it from the chat
> needs a state machine on the follow-up, not a keyword. That's day two."

---

## 5. If something misbehaves live

| What happens | What you say |
|---|---|
| A beat returns the wrong thing | "That's not the branch I wanted — let me show you it properly." Redo it once. Don't debug on stage. |
| The bot asks a question you didn't expect | Type `cancel`, then carry on. "There's a question open — I'll clear it." |
| Nothing comes back at all | "Give it a second, that's a live model call." Wait. If still nothing, move to the next beat and come back. |
| A card shows a duplicate instead of a creation | "That one's already in there from rehearsal — which is duplicate detection doing its job." **Turn it into a feature.** |
| Everything falls over | "We have a recording of the full flow, let me show you that." |

**Never** debug, apologise twice, or say "it worked earlier."

---

## 6. Questions likely to come to you

**"Why not use the Bot Framework SDK?"**
> "It's JSON over HTTPS. The SDK is a wrapper over about eighty lines. At
> hour five we wanted stack traces through our own code, not through someone
> else's abstraction."

**"Why isn't this in real Teams?"**
> "Tenant permission. Custom app upload needs a work tenant with that policy
> enabled — we had a personal account. Same bot, same protocol, same
> renderer; only the window differs."

**"What happens if the tunnel drops mid-demo?"**
> "The bot stops receiving. Nothing is lost — the messages queue at
> Microsoft's end and the store is untouched. In production this is a
> deployed endpoint, not a tunnel."

**"Can it handle a PDF / a spreadsheet?"**
> "Not today. It classifies images, audio and contact cards. Anything else
> is downloaded but not interpreted — and it says so rather than guessing."

**"How do you know the attachment paths work?"**
> "The inline image and contact-card paths I've run end to end. The
> Teams-native file path is built to the documented contract but never run
> against a live tenant, because we couldn't install into Teams. I'd rather
> say that than claim it."
