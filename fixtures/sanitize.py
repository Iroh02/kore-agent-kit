"""Strip credentials out of captured Activities so they can be committed.

Raw captures land in fixtures/raw/ (gitignored) and carry live secrets:

  * attachment contentUrl has a ~1kB JWT in its `t=` query parameter
  * recipient.id embeds an Azure-issued key - it contains the JQQJ99 marker
    Microsoft's own secret scanners look for
  * assorted eyJ... bearer tokens

This repo is public, so nothing from raw/ is committed directly. Run:

    python fixtures/sanitize.py

and the redacted copies land next to it for commit. Structure is preserved
exactly - only secret VALUES are replaced - so to_inbound_event can still be
written against the real Activity shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "webchat"

JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]*\.?[A-Za-z0-9_\-]*")


def _scrub_url(url: str) -> str:
    parts = urlparse(url)
    if not parts.query:
        return url
    return urlunparse(parts._replace(query=urlencode({"t": "<REDACTED_JWT>"})))


def scrub(node):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "id" and isinstance(value, str) and "@" in value:
                out[key] = value.split("@", 1)[0] + "@<REDACTED_BOT_ID>"
            elif key in ("contentUrl", "downloadUrl") and isinstance(value, str):
                out[key] = _scrub_url(value)
            elif key == "thumbnailUrl" and isinstance(value, str):
                # Base64 of the sender's actual photo. Public repo: drop it.
                out[key] = "<REDACTED_INLINE_IMAGE_DATA>"
            else:
                out[key] = scrub(value)
        return out
    if isinstance(node, list):
        return [scrub(v) for v in node]
    if isinstance(node, str):
        return JWT.sub("<REDACTED_JWT>", node)
    return node


def main() -> None:
    if not RAW.exists():
        print("no fixtures/raw/ - send the bot a message first")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for src in sorted(RAW.glob("*.json")):
        clean = scrub(json.loads(src.read_text(encoding="utf-8")))
        (OUT / src.name).write_text(
            json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  {src.name}")
    print(f"\n{len(list(OUT.glob('*.json')))} sanitized -> {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
