"""Tool-calling loop with a visible trace.

The trace is the demo. Judges cannot see your architecture diagram from the
back of a room, but they can see the agent decide to call a tool, get a
result, and cite it.
"""
import json
import time

from . import config, llm, tools

SYSTEM = """You are a grounded analyst agent.

Rules:
1. For any factual claim about the user's data, call search_docs first. Never answer from memory.
2. Cite sources inline as [source=<filename>] for every claim drawn from a document.
3. Use calculate for arithmetic and table_query for aggregations. Do not compute numbers yourself.
4. If the first search comes back weak or off-topic, search again with different wording: synonyms, the industry term, the exact column or field name. Two cheap searches beat one confident guess.
5. If the retrieved passages do not answer the question, say exactly what is missing. Do not fill gaps with plausible text.
6. Be concise. Lead with the answer, then the evidence."""


def _run_tool(name, raw_args):
    fn = tools.REGISTRY.get(name)
    if not fn:
        return f"Unknown tool '{name}'. Available: {list(tools.REGISTRY)}"
    try:
        kwargs = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else {}
    except json.JSONDecodeError:
        return f"Arguments were not valid JSON: {raw_args!r}"
    try:
        return str(fn(**kwargs))
    except TypeError as e:
        return f"Bad arguments for {name}: {e}"
    except Exception as e:  # noqa: BLE001
        return f"{name} failed: {e}"


def run(question, history=None, max_steps=None, system=SYSTEM):
    """Returns {"answer", "trace", "sources", "steps", "elapsed_s"}."""
    max_steps = max_steps or config.MAX_STEPS
    messages = [{"role": "system", "content": system}]
    for turn in history or []:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    trace, sources, started = [], [], time.time()

    for step in range(max_steps):
        reply = llm.chat(messages, tools=tools.SCHEMAS)
        calls = reply.get("tool_calls") or []

        if not calls:
            answer = reply.get("content") or "(empty response)"
            return {
                "answer": answer,
                "trace": trace,
                "sources": sorted(set(sources)),
                "steps": step + 1,
                "elapsed_s": round(time.time() - started, 2),
            }

        messages.append(
            {"role": "assistant", "content": reply.get("content"), "tool_calls": calls}
        )
        for call in calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments", "{}")
            result = _run_tool(name, args)
            trace.append(
                {
                    "step": step + 1,
                    "tool": name,
                    "args": args,
                    "result_preview": result[:400] + ("..." if len(result) > 400 else ""),
                }
            )
            if name == "search_docs":
                sources += [
                    ln.split("source=")[1].split(" ")[0]
                    for ln in result.splitlines()
                    if "source=" in ln
                ]
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id", name), "content": result}
            )

    return {
        "answer": "Hit the step limit without a final answer. Narrow the question.",
        "trace": trace,
        "sources": sorted(set(sources)),
        "steps": max_steps,
        "elapsed_s": round(time.time() - started, 2),
    }
