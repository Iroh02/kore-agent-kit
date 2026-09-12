"""Run this the moment you clone: python3 -m tests.smoke"""
import sys

from app import agent, llm, rag, tools


def main():
    print("1. indexing...")
    info = rag.build_index()
    assert info["chunks"] > 0, "no chunks indexed - is data/ empty?"
    print(f"   {info}")

    print("2. retrieval...")
    hits = rag.search("retention release defects liability", k=2)
    assert hits, "retrieval returned nothing"
    assert "retention" in hits[0]["text"].lower(), hits[0]["text"][:120]
    print(f"   top source: {hits[0]['source']} score={hits[0]['score']}")

    print("3. tools...")
    assert abs(float(tools.calculate("1480000 * 0.1")) - 148000) < 1e-6
    out = tools.table_query("variations.csv", "value_aed", "status", "sum")
    assert "approved" in out, out
    print(f"   {out.splitlines()[1]}")
    fc = tools.forecast("monthly_cost.csv", "period", "cost_incurred_aed", 2)
    assert "+1:" in fc, fc
    print(f"   {fc.splitlines()[1]}")

    print("4. llm...")
    print(f"   {llm.health()}")

    print("5. agent...")
    res = agent.run("How much retention is deducted from each interim payment?")
    assert res["answer"], "agent produced no answer"
    print(f"   tools used: {[t['tool'] for t in res['trace']]}")
    print(f"   sources: {res['sources']}")
    print(f"   answer: {res['answer'][:220]}")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
