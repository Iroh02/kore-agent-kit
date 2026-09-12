"""Ten-line eval harness. Run: python3 -m app.evalkit

Almost no hackathon team shows evidence that their thing actually works.
A pass-rate table on one slide separates you from every demo that was
tested once, live, and prayed over.
"""
import json
import sys

from . import agent, config


def load_cases(path=None):
    path = path or config.ROOT / "tests" / "eval_cases.json"
    return json.loads(path.read_text())


def run(cases=None, verbose=True):
    cases = cases or load_cases()
    results, passed = [], 0
    for i, case in enumerate(cases, 1):
        out = agent.run(case["question"])
        answer = (out["answer"] or "").lower()
        missing = [k for k in case.get("must_include", []) if k.lower() not in answer]
        banned = [k for k in case.get("must_not_include", []) if k.lower() in answer]
        ok = not missing and not banned
        passed += ok
        results.append({**case, "ok": ok, "missing": missing, "banned": banned,
                        "elapsed_s": out["elapsed_s"], "tools": [t["tool"] for t in out["trace"]]})
        if verbose:
            mark = "PASS" if ok else "FAIL"
            print(f"[{mark}] {i}. {case['question'][:64]}  ({out['elapsed_s']}s)")
            if missing:
                print(f"        missing: {missing}")
            if banned:
                print(f"        should not have said: {banned}")
    rate = passed / len(cases) if cases else 0
    if verbose:
        print(f"\n{passed}/{len(cases)} passed  ({rate:.0%})")
    return {"passed": passed, "total": len(cases), "rate": rate, "results": results}


if __name__ == "__main__":
    sys.exit(0 if run()["rate"] == 1 else 1)
