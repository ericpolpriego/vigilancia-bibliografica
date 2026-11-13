#!/usr/bin/env python3
"""Añade a data/seen.json todos los candidatos evaluados hoy (API + web)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def norm_title(t):
    return re.sub(r"[^a-z0-9áéíóúàèòïüçñãõâêô]", "", (t or "").lower())[:120]


seen_path = DATA / "seen.json"
seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
before = len(seen)
for name in ("candidates.json", "web_candidates.json"):
    p = DATA / name
    if not p.exists():
        continue
    for it in json.loads(p.read_text(encoding="utf-8")):
        if it.get("id"):
            seen.add(it["id"])
        if it.get("title"):
            seen.add(f"t:{norm_title(it['title'])}")
        if it.get("url"):
            seen.add(f"u:{it['url']}")
seen_path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=0), encoding="utf-8")
print(f"seen.json: {before} -> {len(seen)}")
