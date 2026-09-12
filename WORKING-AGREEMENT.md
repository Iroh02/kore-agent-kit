# Working agreement

Two people, one day. Read this before the first commit; it takes 90 seconds and
saves the hour that teams normally lose to merge conflicts at 4pm.

## Git, for a one-day build

**Work on `main`. No branches, no pull requests.** Branch protection and code
review are correct for a product and wrong for eight hours. The whole point is
that both of you see the same code all day.

```bash
git pull --rebase        # before you push, every single time
git push
```

`--rebase` keeps the history linear and avoids the merge commits that make a
one-day log unreadable. If a rebase conflicts, fix it immediately and ask the
other person what they meant. Do not stash it and carry on.

**Push every 20 to 30 minutes.** Small commits, present tense, one idea each.
An unpushed hour of work is an hour that can vanish with a laptop.

## Split by file, not by feature

Merge conflicts come from two people editing the same file, so divide the
files up front and stick to it. A workable split:

| Owner | Files |
|---|---|
| Person A | `app/agent.py`, `app/tools.py`, `tests/` |
| Person B | `app/server.py`, `ui/index.html`, `data/` |
| Either, announce first | `app/rag.py`, `app/config.py`, `README.md` |

`app/tools.py` is the file you will both want. If you both have to touch it,
**append new tools at the bottom** and never reorder what is already there.
Appends merge cleanly; reordering does not.

## Secrets

`.env` is gitignored and must stay that way. Send keys to each other over chat,
never in a commit. If a key does get committed, say so out loud immediately and
rotate it. Do not quietly force-push over it.

## Checkpoints

Agree these at the start and treat them as real:

- **Mid-build:** stop, demo to each other out loud, cut anything that is not
  working. Cutting early is judgement; cutting late is panic.
- **Freeze, 90 minutes before presenting:** no new code, at all. Record a
  screen capture of the working flow. That recording is your insurance.
- After the freeze, the only commits are to `README.md`.

## If you disagree

Whoever is writing most of that part decides. Spend the argument budget on
scope, which is what you will actually be judged on, not on stack choices,
which nobody will ask about.
