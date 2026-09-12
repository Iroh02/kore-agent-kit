"""Dependency-free retrieval: chunk -> TF-IDF -> cosine.

Deliberately not a vector DB. It indexes a few hundred documents in under a
second, needs no network, and never fails to install. Swap in embeddings
later only if retrieval quality is actually your bottleneck.
"""
import csv
import json
import math
import re
from collections import Counter

from . import config

_STOP = set(
    """a an and are as at be by for from has have in is it its of on or that the to was were
will with this these those you your we our they their he she i""".split()
)

_INDEX = {"chunks": [], "df": {}, "n": 0}


# Crude suffix stemmer. Not linguistically correct, but it collapses
# escalate/escalates/escalated/escalation onto one key, which is most of what
# keyword retrieval needs. Longest suffix wins; never shorten below 3 chars.
_SUFFIXES = ("ational", "ization", "iveness", "fulness", "ousness", "ation",
             "ement", "ingly", "ing", "ies", "ied", "ion", "ers", "est",
             "ed", "es", "er", "ly", "s")


def stem(word):
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokenize(text):
    return [
        stem(t)
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if t not in _STOP and len(t) > 1
    ]


def _hard_split(text, size):
    """Last resort for a single oversized paragraph: split on sentence ends."""
    parts, buf = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(buf) + len(sentence) + 1 > size and buf:
            parts.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        parts.append(buf)
    return parts


def chunk_text(text, size=700, overlap_paras=1):
    """Markdown-heading aware. Sections first, then pack paragraphs up to
    `size` chars, carrying the last paragraph forward so a fact split across
    a boundary still appears whole in one chunk."""
    sections, current = [], []
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s", line) and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))

    chunks = []
    for section in sections:
        paras = [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]
        heading = paras[0] if paras and paras[0].lstrip().startswith("#") else ""
        buf = []
        for para in paras:
            for piece in ([para] if len(para) <= size else _hard_split(para, size)):
                if buf and sum(len(x) for x in buf) + len(piece) + 2 > size:
                    chunks.append("\n\n".join(buf))
                    tail = buf[-overlap_paras:] if overlap_paras else []
                    buf = ([heading] if heading and heading not in tail else []) + tail
                buf.append(piece)
        if buf:
            chunks.append("\n\n".join(buf))
    return chunks


def _read_file(path):
    """Return a list of (label, text) for one file."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            rows = []
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                for i, row in enumerate(csv.DictReader(f)):
                    body = "; ".join(f"{k}: {v}" for k, v in row.items() if v)
                    rows.append((f"{path.name}#row{i + 1}", body))
            return rows
        if suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return [(path.name, json.dumps(raw, indent=2))]
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader  # optional
            except ImportError:
                return []
            reader = PdfReader(str(path))
            return [
                (f"{path.name}#p{i + 1}", (pg.extract_text() or ""))
                for i, pg in enumerate(reader.pages)
            ]
        return [(path.name, path.read_text(encoding="utf-8", errors="replace"))]
    except Exception as e:  # noqa: BLE001
        print(f"[rag] skipped {path.name}: {e}")
        return []


def build_index(data_dir=None):
    data_dir = data_dir or config.DATA_DIR
    chunks = []
    exts = {".md", ".txt", ".csv", ".json", ".pdf", ".log", ".py", ".sql"}
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        for label, text in _read_file(path):
            for j, body in enumerate(chunk_text(text)):
                if len(body.strip()) < 20:
                    continue
                chunks.append(
                    {
                        "id": f"{label}::{j}",
                        "source": label,
                        "text": body,
                        "tf": Counter(tokenize(body)),
                    }
                )
    df = Counter()
    for c in chunks:
        df.update(c["tf"].keys())
    _INDEX.update({"chunks": chunks, "df": df, "n": len(chunks)})
    return {"files_indexed": len({c["source"].split("#")[0] for c in chunks}), "chunks": len(chunks)}


def _vec(tf, df, n):
    out = {}
    for term, count in tf.items():
        idf = math.log((n + 1) / (df.get(term, 0) + 1)) + 1.0
        out[term] = (1 + math.log(count)) * idf
    norm = math.sqrt(sum(v * v for v in out.values())) or 1.0
    return {k: v / norm for k, v in out.items()}


def search(query, k=4):
    if not _INDEX["chunks"]:
        build_index()
    if not _INDEX["chunks"]:
        return []
    n, df = _INDEX["n"], _INDEX["df"]
    qv = _vec(Counter(tokenize(query)), df, n)
    scored = []
    for c in _INDEX["chunks"]:
        cv = c.get("_vec")
        if cv is None:
            cv = c["_vec"] = _vec(c["tf"], df, n)
        score = sum(w * cv.get(t, 0.0) for t, w in qv.items())
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [
        {"source": c["source"], "text": c["text"], "score": round(s, 4)}
        for s, c in scored[:k]
    ]


def stats():
    if not _INDEX["chunks"]:
        build_index()
    return {
        "chunks": _INDEX["n"],
        "files": len({c["source"].split("#")[0] for c in _INDEX["chunks"]}),
    }
