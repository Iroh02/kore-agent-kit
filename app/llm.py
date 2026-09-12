"""OpenAI-compatible chat client on stdlib urllib. No SDK, no pip install.

chat(messages, tools) -> {"content": str|None, "tool_calls": [...]}
Falls back to a deterministic mock when no API key is set.
"""
import json
import time
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


def _post(url, payload, headers, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _live(messages, tools, temperature, model):
    payload = {
        "model": model or config.MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else config.TEMPERATURE,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.API_KEY}",
    }
    last = None
    for attempt in range(3):
        try:
            data = _post(
                f"{config.BASE_URL}/chat/completions", payload, headers, config.TIMEOUT
            )
            msg = data["choices"][0]["message"]
            return {
                "content": msg.get("content"),
                "tool_calls": msg.get("tool_calls") or [],
            }
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            last = LLMError(f"HTTP {e.code}: {body}")
            # 4xx other than rate limit will not fix itself
            if e.code not in (408, 409, 429) and e.code < 500:
                raise last
        except Exception as e:  # noqa: BLE001
            last = LLMError(str(e))
        time.sleep(1.5 * (attempt + 1))
    raise last


def _mock(messages, tools):
    """Deterministic stand-in. Turn 1: call search_docs with the user's
    question. Turn 2: answer from whatever the tool returned.

    Retrieval is genuinely running, so the demo shows real grounded content.
    """
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )
    if tools and not has_tool_result:
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "mock_1",
                    "type": "function",
                    "function": {
                        "name": "search_docs",
                        "arguments": json.dumps({"query": user, "k": 3}),
                    },
                }
            ],
        }
    evidence = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "tool"), ""
    )
    return {
        "content": (
            "[MOCK MODE - no API key set, so this answer is not model-generated. "
            "Retrieval below is real.]\n\n"
            f"Question: {user}\n\nTop retrieved evidence:\n{evidence[:1200]}"
        ),
        "tool_calls": [],
    }


def chat(messages, tools=None, temperature=None, model=None):
    if config.PROVIDER == "mock":
        return _mock(messages, tools)
    return _live(messages, tools, temperature, model)


def health():
    return {
        "provider": config.PROVIDER,
        "base_url": config.BASE_URL if config.PROVIDER == "live" else None,
        "model": config.MODEL if config.PROVIDER == "live" else "mock",
    }
