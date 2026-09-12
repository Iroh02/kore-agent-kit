# kore-agent-kit

A grounded agent over your own documents, with a visible tool-call trace.
No pip install, no vector database, no framework: Python 3.9+ and the
standard library. Built so that hour one of a hackathon goes on the problem
instead of on dependency resolution.

```bash
git clone <this repo> && cd kore-agent-kit
python3 -m tests.smoke      # 10 seconds, proves the whole chain works
python3 -m app.server       # http://localhost:8000
```

If both of those pass, you are set up. There is no step three.

**Working with someone else on this?** Read
[WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) first. It is short, and it is
the difference between shipping and spending the last hour on merge
conflicts.

It runs with **no API key**. Retrieval is real; only the final wording is
canned. The moment you get a key, drop it in `.env` and the same code path
goes live. Nothing about your demo can be broken by a missing credential or
a dead wifi connection.

## Wiring up a real model

```bash
cp .env.example .env      # then set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
```

Any OpenAI-compatible endpoint works: OpenAI, Azure, Groq, Together,
Fireworks, OpenRouter, vLLM, Ollama. `.env.example` lists the exact two
lines to change for each.

## What is in the box

| File | What it does | Where you will actually edit |
|---|---|---|
| `app/rag.py` | chunk, index, retrieve (TF-IDF + stemming) | chunk size, file types |
| `app/tools.py` | the tool registry | **add your tools here** |
| `app/agent.py` | tool-calling loop + trace | the system prompt |
| `app/llm.py` | provider client, retries, mock | rarely |
| `app/server.py` | stdlib HTTP + JSON API | add endpoints |
| `ui/index.html` | chat UI with a live agent trace | branding |
| `app/evalkit.py` | pass/fail harness | run it before you present |
| `data/` | the knowledge base | **replace entirely** |

## The three things to do first, in order

**1. Swap the corpus.** Delete everything in `data/`, drop in the
organisers' files, hit Reindex in the UI. Supported: `.md .txt .csv .json
.pdf .log .py .sql`. CSVs index one row per chunk, so row-level questions
retrieve cleanly.

**2. Add one tool that is specific to the problem.** This is the whole
game. A generic RAG chatbot is what every other team will build. A tool
that does the domain's actual arithmetic is what gets remembered. Pattern:

```python
def check_margin(item_code: str) -> str:          # app/tools.py
    ...
    return "B-201 blockwork: budget 290000, actual 318000, overrun 9.7%"

REGISTRY["check_margin"] = check_margin
SCHEMAS.append({"type": "function", "function": {
    "name": "check_margin",
    "description": "Compare budget against actual cost for one BOQ item.",
    "parameters": {"type": "object",
                   "properties": {"item_code": {"type": "string"}},
                   "required": ["item_code"]}}})
```

Three rules for tools: return a **string**, keep it **short** (long dumps
make the agent wander), and write a description a stranger could follow,
because the description *is* the prompt.

**3. Write three eval cases before you write the demo script.** Edit
`tests/eval_cases.json`, then `python3 -m app.evalkit`. A pass-rate on a
slide is the single cheapest way to look like an engineer rather than a
demo-builder.

## Known limits, and the honest answer to each

These are real weaknesses. Judges who know the field will find them, so say
them first, in your own words. It reads as judgement, not as gaps.

- **Keyword retrieval misses synonyms.** "Retention" will not match
  "retained". Fix: let the agent search twice with different wording (the
  system prompt already tells it to), or swap `rag.search` for embeddings
  once you have the key. The interface stays identical.
- **The forecast is a straight line.** Eight data points do not support
  anything more. The tool reports its own residual spread; when that band is
  wide, that *is* the finding.
- **No auth, no rate limits, no persistence.** Correct for a one-day build.
  Name it as a deliberate cut, not an oversight.
- **The trace is truncated to 400 chars per step.** Enough to demo, not
  enough to audit. Real logging is a day-two problem.

## API

```
GET  /api/health   -> provider, model, chunk and file counts
POST /api/ingest   -> reindex data/
POST /api/chat     {"message": "...", "history": [...]}
                   -> {answer, trace[], sources[], steps, elapsed_s}
```

## If something breaks on the day

| Symptom | Cause | Fix |
|---|---|---|
| "No matching passages found" | corpus not indexed | POST `/api/ingest`, check `data/` is not empty |
| `HTTP 401` | bad key | check `.env`, no quotes, no trailing spaces |
| `HTTP 404` on chat completions | wrong base URL | must end in `/v1`, no trailing slash |
| Agent loops to the step limit | tool description is vague | rewrite the description, raise `AGENT_MAX_STEPS` |
| PDF indexes as nothing | `pypdf` missing | `pip install pypdf`, or convert to text |
| Everything is on fire, 10 min to demo | — | unset `LLM_API_KEY`. Mock mode always runs. |
