# BEFORE AND AFTER — Nandita's card

What happens either side of the seven live minutes. `DEMO-SCRIPT.md` is
Vishal's typing card; this one is yours.

---

# BEFORE

## 16:30 — Vishal's machine (he does this, you watch it happen)

```
git pull --rebase
```
Restart uvicorn. Three pipeline files changed today.

```
.venv\Scripts\python -m tests.demo_check
```
**25/25.** Anything red and you stop and decide together. Nobody edits code.

## 16:45 — Warm the cache, then wipe

Send one typed lead and one business card through Web Chat. This pays the
prompt-cache write so the first *real* lead prices correctly. Then:

```
.venv\Scripts\python tools\send.py reset
```

**Reload the dashboard.** The counters are client-side; a stale tab shows
yesterday's totals on the projector.

## 16:50 — The screen

- Web Chat left third, dashboard right two-thirds, browser at **125%**
- Deck open in **presenter view** on your laptop, slide 4 up
- Tabs ready but not shown: `/docs`, and a terminal holding the 25/25 output
- The voice note `.ogg` is on **Vishal's** machine, not yours
- Only one machine can be the bot's endpoint. It is his.

## 16:55 — In your head, not on a slide

| | |
|---|---|
| Typed lead | two-tenths of a cent, ~2.5 s |
| Photo card | **about two cents**, ~5 s |
| Shared contact | **zero, not rounded** — no model at all |
| Voice note | ~a third of a cent, ~5 s |
| At 1,000/day | $5.70 |
| Evals | 70/70, fourteen cases, five fields |
| Demo checks | 25/25 — **pipeline only, not the channel** |

## The four corrections, one last time

1. **"Nineteen defects."** Never twenty-four. "The slide shows twelve, we
   found seven more after we built the deck."
2. **Never say tool-use CRUD is built.** It is the criterion and the next
   build. Card buttons are what they just watched.
3. **"About two cents"** for the card. Never one cent.
4. **Never say Bedrock is "the same price."** Same range, AWS sets it.

## Your opening line

> "Two-tenths of a cent, and two and a half seconds. That's what it costs to
> turn a message in a chat window into a lead with a scheduled follow-up."

Then the problem. Slow. Don't rush to the demo.

## Set expectations before the first message

> "Everything you're about to see runs live against the real models. The
> store is ours, not your CRM, and it's Web Chat rather than the Teams
> client because sideloading is blocked in the tenant. Those two are the
> only substitutions, and both are on the risks slide."

Saying it first turns two gaps into evidence of judgement.

---

# AFTER

## The moment the demo ends — your transition

Do not let it trail off. Take the room back with one sentence:

> "Everything you just watched was priced and timed as it happened. Here's
> why it can be."

Then slide 6, architecture. That is your 1:20.

## During Q&A — which slide answers what

| They ask | Go to |
|---|---|
| "Does it hallucinate?" | **Slide 11** — the six rules |
| "How accurate is it really?" | **Slide 12** — tuning and calibration |
| "How do you know it's reliable?" | **Slide 13** — the bug list |
| "What does it cost at scale?" | **Slide 5** — economics |
| "Where does our data go?" | **Slide 8** — risks, then Bedrock |

Appendix slides are behind the Q&A slide. Arrow right, don't hunt.

## The three answers you will almost certainly give

**"Is this just ChatGPT in a wrapper?"**
> "No. The flow is deterministic code. The model does one job — reading
> fields — and its output is schema-validated, so a bad read is a caught
> error, not a wrong record. That's why we can quote a fixed cost per lead."

**"How long to production?"**
> "The CRM integration is the main piece — mapping our fields to Intrakore's
> lead object, plus auth and retries. Our store is already an interface, so
> that's an implementation, not a rewrite. The chat layer and the extraction
> are done."

**"Can we have it in Teams?"**
> "Enable custom app upload for one pilot team and it's in Teams the same
> day. The manifest is built, the bot is registered, and Web Chat is the
> same bot on the same endpoint."

## If the demo went badly

Say it plainly and move on. Do not apologise twice.

> "That's a real failure and you just watched it. What it did *not* do is
> invent a value or silently schedule something — which is the behaviour
> we actually designed for."

Then go to the bug slide and use it: nineteen found, every one from running
it rather than adding to it.

## After the session

- **Do not deploy anything.** The tunnel is a public URL and Web Chat is a
  live channel. Bedrock is the production answer on a slide, not tonight.
- **Stop the tunnel** when you leave. It points at Vishal's laptop.
- **The screen recording is the insurance.** Keep it even if the live demo
  went fine.
- **Write down the questions you couldn't answer** before you forget them.
  Those are week two's backlog, and they're worth more than any feature you
  could have added today.
- If the COO asks for a follow-up, the ask is **one pilot team with custom
  app upload enabled**, and **their CRM's lead field names**. Nothing else.

## What week two actually starts with

In order, and all of it is written down already:

1. A hundred labelled cases from their salespeople, run three times, variance
   reported. Everything else depends on this.
2. Gemini 2.5 Flash against that eval set. Four to six times cheaper, native
   audio, no Bedrock path.
3. Chat CRUD by tool use — the one surface that genuinely earns an agent.
4. The CRM behind the `Store` interface.
5. Actionable reminders: Done, Snooze, Reschedule on the proactive card.
