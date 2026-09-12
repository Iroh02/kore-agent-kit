"""Extraction accuracy evals. Per-field, over labelled inputs.

    .venv/Scripts/python -m tests.evals

Every case has a known right answer. Each field scores 1 if the extraction
matches (or correctly returns None when the input has no value - abstaining
is a correct answer here, not a miss). Mobiles compare on digits only.

This is what turns "it works" into a number. It is also the prerequisite
for any honest model comparison: without it, "we tested Flash" is a claim.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import extract  # noqa: E402
from app.ledger import Ledger  # noqa: E402

CARDS = Path("fixtures/cards")
FIELDS = ["company_name", "first_name", "last_name", "mobile", "email"]

ALWASL = dict(company_name="AL WASL INTERIORS", first_name="Omar",
              last_name="Al Fardan", mobile="971507763312",
              email="o.alfardan@alwaslinteriors.ae")

CASES = [
    # --- free text: clean -------------------------------------------------
    ("text/clean",
     "New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, "
     "email f.mansoori@skylinefitout.ae",
     dict(company_name="Skyline Fitout", first_name="Fatima", last_name="Al Mansoori",
          mobile="971503328890", email="f.mansoori@skylinefitout.ae")),
    ("text/conversational",
     "met a guy called Yusuf Bin Ali today, he's with Arc Glazing, number is "
     "052 888 3131 and his email is yusuf@arcglazing.ae",
     dict(company_name="Arc Glazing", first_name="Yusuf", last_name="Bin Ali",
          mobile="0528883131", email="yusuf@arcglazing.ae")),
    ("text/messy-punctuation",
     "lead: Sara Nasser / Delta Steel LLC / +971-50-111-2222 / sara@deltasteel.ae",
     dict(company_name="Delta Steel LLC", first_name="Sara", last_name="Nasser",
          mobile="971501112222", email="sara@deltasteel.ae")),
    # --- free text: missing fields (correct answer is None) ---------------
    ("text/no-email",
     "Omar Hadi from Vertex Contracting, 971 50 777 8888",
     dict(company_name="Vertex Contracting", first_name="Omar", last_name="Hadi",
          mobile="971507778888", email=None)),
    ("text/no-mobile",
     "Add Hana Qasim at Vertex Joinery - hana@vertexjoinery.ae",
     dict(company_name="Vertex Joinery", first_name="Hana", last_name="Qasim",
          mobile=None, email="hana@vertexjoinery.ae")),
    ("text/name-only",
     "spoke to Layla Haddad, will send details later",
     dict(company_name=None, first_name="Layla", last_name="Haddad",
          mobile=None, email=None)),
    # --- the trap: a domain is NOT a company ------------------------------
    ("text/domain-is-not-company",
     "Reem Haddad, reem.haddad@outlook.com, 055 204 8871",
     dict(company_name=None, first_name="Reem", last_name="Haddad",
          mobile="0552048871", email="reem.haddad@outlook.com")),
    # --- noise: should not hallucinate a lead out of nothing ---------------
    ("text/no-lead-at-all",
     "thanks, see you at the site tomorrow",
     dict(company_name=None, first_name=None, last_name=None, mobile=None, email=None)),
    # --- business cards ----------------------------------------------------
    ("card/clean", CARDS / "01_clean.png", ALWASL),
    ("card/angled", CARDS / "02_angled.png", ALWASL),
    ("card/blurred", CARDS / "03_blurred.png", ALWASL),
    ("card/no-company", CARDS / "04_no_company.png",
     dict(company_name=None, first_name="Reem", last_name="Haddad",
          mobile="971552048871", email="reem.haddad@outlook.com")),
    # --- vCard: deterministic, should be perfect and free -------------------
    ("vcf/with-org",
     "BEGIN:VCARD\nN:Rahman;Ahmed;;;\nORG:Marina Contracting LLC\n"
     "TEL:+971 50 445 2211\nEMAIL:ahmed@marina.ae\nEND:VCARD",
     dict(company_name="Marina Contracting LLC", first_name="Ahmed", last_name="Rahman",
          mobile="971504452211", email="ahmed@marina.ae")),
    ("vcf/no-org",
     "BEGIN:VCARD\nN:Haddad;Layla;;;\nTEL:+971 55 900 1234\nEMAIL:layla@x.ae\nEND:VCARD",
     dict(company_name=None, first_name="Layla", last_name="Haddad",
          mobile="971559001234", email="layla@x.ae")),
]


def _digits(v):
    return "".join(c for c in (v or "") if c.isdigit()) or None


def _norm(field, v):
    if v is None:
        return None
    if field == "mobile":
        d = _digits(v)
        # tolerate a leading 0 vs 971: compare the last 9 digits
        return d[-9:] if d and len(d) >= 9 else d
    return str(v).strip().lower()


def run() -> int:
    per_field = {f: [0, 0] for f in FIELDS}  # correct, total
    rows = []
    total_cost = 0.0

    for label, inp, expected in CASES:
        led = Ledger("eval", label)
        try:
            if label.startswith("card/"):
                ex = extract.extract_lead_from_card(Path(inp).read_bytes(), "image/png", led)
            elif label.startswith("vcf/"):
                ex = extract.parse_vcard(inp)
            else:
                ex = extract.extract_lead_from_text(inp, led)
        except extract.ExtractionFailed as e:
            rows.append((label, "FAILED: " + str(e)[:60], 0, 0.0, 0.0))
            for f in FIELDS:
                per_field[f][1] += 1
            continue

        got_ok = 0
        misses = []
        for f in FIELDS:
            want, got = _norm(f, expected.get(f)), _norm(f, getattr(ex, f, None))
            per_field[f][1] += 1
            if want == got:
                per_field[f][0] += 1
                got_ok += 1
            else:
                misses.append(f"{f}: want {expected.get(f)!r} got {getattr(ex, f, None)!r}")

        fin = led.finish()
        total_cost += fin.total_cost_usd
        rows.append((label, "; ".join(misses) or "all fields correct",
                     got_ok, ex.confidence, fin.total_cost_usd))

    print()
    print(f"{'case':28} {'ok':>4} {'conf':>5} {'cost':>9}  detail")
    print("-" * 100)
    for label, detail, ok, conf, cost in rows:
        print(f"{label:28} {ok:>3}/5 {conf:5.2f} ${cost:8.5f}  {detail[:60]}")

    print("\n" + "=" * 100)
    print(f"{'field':16} {'correct':>8} {'of':>4} {'accuracy':>10}")
    print("-" * 100)
    overall_c = overall_t = 0
    for f in FIELDS:
        c, t = per_field[f]
        overall_c += c; overall_t += t
        print(f"{f:16} {c:>8} {t:>4} {c / t * 100:9.0f}%")
    print("-" * 100)
    print(f"{'OVERALL':16} {overall_c:>8} {overall_t:>4} {overall_c / overall_t * 100:9.0f}%")
    print(f"\n{len(CASES)} cases, total eval cost ${total_cost:.4f}")
    print("=" * 100 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
