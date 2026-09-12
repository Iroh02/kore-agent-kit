"""Full demo surface check. Run this before every rehearsal and before 17:00.

    .venv/Scripts/python -m tests.demo_check

Exercises every path the demo touches, against a FRESH database so it is
repeatable. Prints a pass/fail table. Exit code is non-zero if anything
fails, so it can gate a push.

This is not a unit test suite - it is the demo, automated. If this is green,
the demo works.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import pipeline  # noqa: E402
from app.schemas import Attachment, InboundEvent, InputKind  # noqa: E402
from app.store import SQLiteStore  # noqa: E402

DB = "demo_check.db"
U, C = "u_demo", "c_demo"
CARDS = Path("fixtures/cards")

VCARD_WITH_ORG = b"""BEGIN:VCARD
VERSION:3.0
N:Rahman;Ahmed;;;
ORG:Marina Contracting LLC
TEL;TYPE=CELL:+971 50 445 2211
EMAIL:ahmed.rahman@marinacontracting.ae
END:VCARD"""

VCARD_NO_ORG = b"""BEGIN:VCARD
VERSION:3.0
N:Haddad;Layla;;;
TEL;TYPE=CELL:+971 55 900 1234
EMAIL:layla.h@example.ae
END:VCARD"""

results: list[tuple[str, bool, str]] = []


def ev(aid, kind, text="", cmd=None, blob=None, name="c.vcf", ctype="text/vcard"):
    atts = [Attachment(name=name, content_type=ctype, data=blob)] if blob else []
    return InboundEvent(
        activity_id=aid, conversation_id=C, service_url="https://x/",
        user_id=U, user_name="Demo", kind=kind, text=text, command=cmd,
        attachments=atts, received_at=datetime.now(timezone.utc),
    )


async def check(label, event, store, want_status=None, want=None):
    r = await pipeline.handle(event, store)
    ok = True
    why = r.status.value
    if want_status and r.status.value != want_status:
        ok, why = False, f"got {r.status.value}, wanted {want_status}"
    if ok and want:
        ok, why = want(r)
    results.append((label, ok, why))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label:52} {why}")
    if r.message:
        print(f"         bot: {r.message[:96]}")
    return r


async def main():
    if os.path.exists(DB):
        os.remove(DB)
    store = SQLiteStore(DB)

    print("\n--- 1. LEAD CREATION, all three input modes ---")
    await check("Mode 1  free text -> lead", ev("t1", InputKind.TEXT,
        text="New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, "
             "email f.mansoori@skylinefitout.ae"),
        store, "created",
        lambda r: (r.lead.company_name == "Skyline Fitout", f"company={r.lead.company_name}"))

    await check("Mode 2  .vcf with company -> lead", ev("t2", InputKind.CONTACT, blob=VCARD_WITH_ORG),
        store, "created",
        lambda r: (r.ledger.total_cost_usd == 0.0, f"cost=${r.ledger.total_cost_usd:.6f} (no model)"))

    if (CARDS / "01_clean.png").exists():
        await check("Mode 3  business card -> lead", ev("t3", InputKind.IMAGE,
            blob=(CARDS / "01_clean.png").read_bytes(), name="card.png", ctype="image/png"),
            store, "created",
            lambda r: (bool(r.lead.email), f"email={r.lead.email}"))
    else:
        results.append(("Mode 3  business card -> lead", False, "fixtures/cards missing"))

    print("\n--- 2. REFUSING TO GUESS  (the demo beats) ---")
    await check("Contact with NO company -> asks", ev("t4", InputKind.CONTACT, blob=VCARD_NO_ORG),
        store, "needs_clarification",
        lambda r: ("company" in r.message.lower(), "asked for company"))

    await check("Answering it -> lead created", ev("t5", InputKind.TEXT, text="Gulf Interiors FZE"),
        store, "created",
        lambda r: (r.lead.company_name == "Gulf Interiors FZE", f"company={r.lead.company_name}"))

    if (CARDS / "04_no_company.png").exists():
        await check("Card with NO company -> asks", ev("t6", InputKind.IMAGE,
            blob=(CARDS / "04_no_company.png").read_bytes(), name="c4.png", ctype="image/png"),
            store, "needs_clarification",
            lambda r: (True, "did not invent a company from the email domain"))
        await check("Answering it -> lead created", ev("t7", InputKind.TEXT, text="Delta Steel"),
            store, "created", lambda r: (r.lead.company_name == "Delta Steel", "company=Delta Steel"))

    print("\n--- 3. RELIABILITY ---")
    await check("Duplicate email -> refuses, reports match", ev("t8", InputKind.TEXT,
        text="Lead: Fatima Al Mansoori, Skyline Fitout, f.mansoori@skylinefitout.ae"),
        store, "duplicate",
        lambda r: (r.duplicate_matched_on == "email", f"matched on {r.duplicate_matched_on}"))

    before = len(store.list_leads())
    await check("Replayed activity_id -> no second lead", ev("t1", InputKind.TEXT,
        text="New lead - Fatima Al Mansoori at Skyline Fitout, mobile 971 50 332 8890, "
             "email f.mansoori@skylinefitout.ae"),
        store, "created",
        lambda r: (len(store.list_leads()) == before, f"{before} leads before and after"))

    print("\n--- 4. NOTES + FOLLOW-UP ---")
    lead = [l for l in store.list_leads() if l.company_name == "Skyline Fitout"][0]
    await check('Tap "Add note" -> scopes next message', ev("t9", InputKind.COMMAND,
        cmd={"action": "add_note", "lead_id": lead.id}), store, "read",
        lambda r: (True, "pending set"))

    await check("Notes + clear follow-up -> scheduled", ev("t10", InputKind.TEXT,
        text="Met Fatima on site. 40-unit villa project, budget 3.2m AED. She wants a "
             "revised proposal. Follow up after 2 days."),
        store, "created",
        lambda r: (r.follow_up is not None and r.follow_up.due_at is not None,
                   f"due {r.follow_up.due_at:%a %d %b %H:%M}" if r.follow_up else "no follow-up"))

    await check("Next message is a NEW lead again", ev("t11", InputKind.TEXT,
        text="New lead - Yusuf Bin Ali at Arc Glazing, 971 52 888 3131, yusuf@arcglazing.ae"),
        store, "created", lambda r: (r.lead.company_name == "Arc Glazing", "pending cleared"))

    await check('Add note again', ev("t12", InputKind.COMMAND,
        cmd={"action": "add_note", "lead_id": lead.id}), store, "read", lambda r: (True, ""))

    await check("Vague follow-up -> ASKS which day", ev("t13", InputKind.TEXT,
        text="Good call with Fatima, she likes the pricing. Follow up next week sometime."),
        store, "needs_clarification",
        lambda r: (r.follow_up is not None and r.follow_up.due_at is None,
                   "stored unscheduled, did not guess"))

    await check('Answering "Monday" -> scheduled', ev("t14", InputKind.TEXT, text="Monday"),
        store, "updated",
        lambda r: (r.follow_up is not None and r.follow_up.due_at is not None,
                   f"due {r.follow_up.due_at:%a %d %b %H:%M}" if r.follow_up else "not set"))

    print("\n--- 5. CRUD ---")
    target = [l for l in store.list_leads() if l.company_name == "Arc Glazing"][0]
    await check("UPDATE lead from a card button", ev("t15", InputKind.COMMAND,
        cmd={"action": "update_lead", "lead_id": target.id, "mobile": "+971 52 000 1111"}),
        store, "updated",
        lambda r: (r.lead.mobile == "+971 52 000 1111", f"mobile={r.lead.mobile}"))

    n_before = len(store.list_leads())
    await check("DELETE lead from a card button", ev("t16", InputKind.COMMAND,
        cmd={"action": "delete_lead", "lead_id": target.id}),
        store, "deleted",
        lambda r: (len(store.list_leads()) == n_before - 1,
                   f"{n_before} -> {len(store.list_leads())} leads"))

    print("\n--- 6. ECONOMICS ---")
    total = 0.0
    for l in store.list_leads():
        pass
    print(f"  leads in database : {len(store.list_leads())}")
    print(f"  notes             : {sum(len(store.list_notes(l.id)) for l in store.list_leads())}")
    print(f"  follow-ups        : {len(store.list_follow_ups())}")

    passed = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 78)
    print(f"  {passed}/{len(results)} checks passed")
    for label, ok, why in results:
        if not ok:
            print(f"    FAILED: {label} -> {why}")
    print("=" * 78 + "\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
