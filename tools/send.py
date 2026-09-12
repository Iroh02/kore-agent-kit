"""Fire any input at the running server. Test tool and demo driver.

    .venv/Scripts/python tools/send.py text  "New lead - Sara at Delta Steel, 971 50 111 2222, sara@delta.ae"
    .venv/Scripts/python tools/send.py card  fixtures/cards/01_clean.png
    .venv/Scripts/python tools/send.py vcf   fixtures/contacts/layla.vcf
    .venv/Scripts/python tools/send.py voice recording.m4a
    .venv/Scripts/python tools/send.py note  <lead_id>        # taps "Add note"
    .venv/Scripts/python tools/send.py leads                  # list ids
    .venv/Scripts/python tools/send.py demo                   # scripted run of show
    .venv/Scripts/python tools/send.py reset                  # wipe every lead (and its notes/follow-ups)

Everything goes through POST /api/simulate, which is the same pipeline the
Teams webhook calls - so a green result here means the pipeline is right and
anything still broken is in the channel.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

BASE = "http://localhost:8000"
CONV, USER = "conv_demo", "user_demo"


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def _event(kind: str, text: str = "", attachment: dict | None = None,
           command: dict | None = None) -> dict:
    return {
        "activity_id": f"cli_{int(time.time() * 1000)}",
        "conversation_id": CONV, "service_url": "https://smba.example/",
        "user_id": USER, "user_name": "Demo", "kind": kind, "text": text,
        "attachments": [attachment] if attachment else [],
        "command": command,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def _file_attachment(path: str, content_type: str) -> dict:
    raw = open(path, "rb").read()
    # Pydantic decodes base64 into the bytes field.
    return {"name": path.split("/")[-1].split("\\")[-1],
            "content_type": content_type,
            "data": base64.b64encode(raw).decode()}


def _show(r: dict) -> dict:
    led = r.get("ledger") or {}
    print(f"\n  {r['status'].upper()}")
    print(f"  bot: {r['message']}")
    if r.get("lead"):
        l = r["lead"]
        print(f"  lead: {l['company_name']} | "
              f"{' '.join(x for x in [l.get('first_name'), l.get('last_name')] if x)} | "
              f"{l.get('mobile')} | {l.get('email')}")
        print(f"  id  : {l['id']}")
    if r.get("note"):
        print(f"  note: {r['note']['summary'][:100]}")
        if r["note"].get("original_kind") == "audio":
            print(f"  transcript: {r['note']['original_text'][:90]}")
    if r.get("follow_up"):
        f = r["follow_up"]
        print(f"  follow-up: {f['status']}  due={f.get('due_at')}")
    for e in led.get("entries", []):
        if e.get("cost_usd") or e["component"] in ("stt", "llm", "vision"):
            print(f"    {e['component']:12} {e['service']:18} "
                  f"{e['latency_ms']:7.0f}ms  ${e['cost_usd']:.6f}")
    print(f"  TOTAL ${led.get('total_cost_usd', 0):.6f}  "
          f"{led.get('total_latency_ms', 0):.0f} ms")
    return r


AUDIO_TYPES = {"m4a": "audio/mp4", "mp3": "audio/mpeg", "wav": "audio/wav",
               "ogg": "audio/ogg", "mp4": "audio/mp4", "webm": "audio/webm"}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]

    if cmd == "reset":
        # Through the API, not the file: deleting a lead cascades its notes,
        # follow-ups and pending-note state, and the server's own connection
        # sees it immediately - no stale-read, no restart. Open questions
        # (pending_clarifications) are not lead-scoped; they expire in 10 min
        # and any new question overwrites them, so they cannot leak into a
        # fresh run. Reload the dashboard afterwards to zero its counters.
        leads = _get("/api/leads?limit=1000")
        for l in leads:
            urllib.request.urlopen(urllib.request.Request(
                f"{BASE}/api/leads/{l['id']}", method="DELETE"), timeout=30)
        print(f"  deleted {len(leads)} lead(s). Reload the dashboard to reset its counters.")
        return 0

    if cmd == "leads":
        for l in _get("/api/leads"):
            print(f"  {l['id']}  {l['company_name']}  [{l['source_kind']}]")
        return 0

    if cmd == "text":
        _show(_post("/api/simulate", _event("text", text=" ".join(rest))))
    elif cmd == "card":
        _show(_post("/api/simulate", _event(
            "image", attachment=_file_attachment(rest[0], "image/png"))))
    elif cmd == "vcf":
        _show(_post("/api/simulate", _event(
            "contact", attachment=_file_attachment(rest[0], "text/vcard"))))
    elif cmd == "voice":
        ext = rest[0].rsplit(".", 1)[-1].lower()
        _show(_post("/api/simulate", _event(
            "audio", attachment=_file_attachment(rest[0], AUDIO_TYPES.get(ext, "audio/mp4")))))
    elif cmd == "note":
        _show(_post("/api/simulate", _event(
            "command", command={"action": "add_note", "lead_id": rest[0]})))
    elif cmd == "delete":
        _show(_post("/api/simulate", _event(
            "command", command={"action": "delete_lead", "lead_id": rest[0]})))
    elif cmd == "demo":
        return run_of_show()
    else:
        print(__doc__)
        return 1
    return 0


def _pause(label: str) -> None:
    print(f"\n{'=' * 70}\n  {label}\n{'=' * 70}")
    try:
        input("  [enter to send] ")
    except EOFError:
        pass


def run_of_show() -> int:
    """The 17:00 run of show, one beat per keypress. Rehearse with this."""
    _pause("BEAT 0  seed a reminder that fires live, mid-demo")
    lead = _show(_post("/api/simulate", _event(
        "text", text="New lead - Omar Hadi at Vertex Contracting, "
                     "971 50 777 8888, omar@vertexcontracting.ae"))).get("lead")
    _post("/api/simulate", _event("command",
          command={"action": "add_note", "lead_id": lead["id"]}))
    _show(_post("/api/simulate", _event(
        "text", text="Quick site visit with Omar, all positive. "
                     "Follow up in 2 minutes.")))
    print("\n  ^ that reminder fires on the dashboard in ~2 minutes, unprompted.")

    _pause("BEAT 1  business card with NO company -> the bot refuses to guess")
    _show(_post("/api/simulate", _event(
        "image", attachment=_file_attachment(
            "fixtures/cards/04_no_company.png", "image/png"))))
    _pause("BEAT 2  answer it -> lead created")
    _show(_post("/api/simulate", _event("text", text="Falcon Interiors")))

    _pause("BEAT 3  free text lead")
    l2 = _show(_post("/api/simulate", _event(
        "text", text="New lead - Fatima Al Mansoori at Skyline Fitout, "
                     "971 50 332 8890, f.mansoori@skylinefitout.ae"))).get("lead")

    _pause("BEAT 4  duplicate -> refuses, and says which field matched")
    _show(_post("/api/simulate", _event(
        "text", text="Lead: Fatima Al Mansoori, Skyline Fitout, "
                     "f.mansoori@skylinefitout.ae")))

    _pause("BEAT 5  meeting notes with an AMBIGUOUS follow-up -> asks which day")
    _post("/api/simulate", _event("command",
          command={"action": "add_note", "lead_id": l2["id"]}))
    _show(_post("/api/simulate", _event(
        "text", text="Good call with Fatima, she likes the pricing. "
                     "Follow up next week sometime.")))
    _pause('BEAT 6  answer "Monday" -> scheduled')
    _show(_post("/api/simulate", _event("text", text="Monday")))

    _pause("BEAT 7  delete a lead -> CRUD demonstrated, not claimed")
    _show(_post("/api/simulate", _event(
        "command", command={"action": "delete_lead", "lead_id": l2["id"]})))

    print("\n  Done. The seeded reminder should fire on the dashboard shortly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
