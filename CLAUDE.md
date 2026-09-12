# kore-agent-kit

A grounded agent over a document corpus, with a visible tool-call trace. Built
for one-day builds where setup time is the enemy.

## Hard constraints, do not break these

- **Python standard library only.** No pip installs, no third-party imports in
  `app/`. `pypdf` is the single optional exception and its import is already
  wrapped in a try/except. If a task seems to need a dependency, say so and
  propose it rather than adding one.
- **The app must run with no API key.** `config.PROVIDER` falls back to `mock`,
  where retrieval is real and only the final answer is canned. Any change that
  makes a missing key fatal is a bug, because mock mode is the demo's fallback
  when the venue wifi dies.
- **No vector database, no agent framework.** The retrieval and the loop are
  hand-rolled on purpose: they are small enough to debug under time pressure.

## Run it

```bash
python3 -m tests.smoke     # full chain, ~10s, run this after any change
python3 -m app.server      # http://localhost:8000
python3 -m app.evalkit     # pass/fail against tests/eval_cases.json
```

On Windows use `python` if `python3` is not on PATH.

## Layout

| Path | Role |
|---|---|
| `app/config.py` | env loading, provider selection, paths |
| `app/llm.py` | OpenAI-compatible client on urllib, retries, mock provider |
| `app/rag.py` | heading-aware chunking, TF-IDF with stemming, cosine search |
| `app/tools.py` | tool registry: functions + JSON schemas |
| `app/agent.py` | tool-calling loop, system prompt, trace assembly |
| `app/server.py` | stdlib HTTP server, JSON API, serves the UI |
| `app/evalkit.py` | eval harness |
| `ui/index.html` | single-file chat UI with a live trace panel |
| `data/` | the corpus, swapped per problem |

## Conventions

- **Tools return strings**, and short ones. Long tool output makes the agent
  drift and burns the context the answer needs.
- **A tool's `description` is a prompt.** When an agent misuses a tool, fix the
  description before touching the loop.
- Adding a tool means three things: the function, an entry in `REGISTRY`, and a
  schema in `SCHEMAS`. **Append at the bottom of `tools.py`** and do not reorder
  what is there, so two people can add tools without conflicting.
- New behaviour needs a case in `tests/eval_cases.json`. Assertions are
  substring checks on the answer: cheap, and enough.
- Never commit `.env`. It is gitignored, keep it that way.

## Working here during a build

- Prefer the smallest change that makes one real question work end to end.
  Breadth is worth less than one flow that is solid.
- Do not add auth, a database, deployment, or a second data source. They are on
  the cut list in `WORKING-AGREEMENT.md` for a reason.
- If asked to swap TF-IDF for embeddings, ask what evidence says retrieval is
  the bottleneck first. Usually it is the chunking or the tool description.
- Two people work on `main` with `git pull --rebase`. See
  `WORKING-AGREEMENT.md` for the file ownership split.
