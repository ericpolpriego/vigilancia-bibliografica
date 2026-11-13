#!/usr/bin/env python3
"""Genera docs/biblioteca.bib (importable en Zotero/Mendeley) desde docs/items.json."""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
items = json.loads((ROOT / "docs" / "items.json").read_text(encoding="utf-8"))

KIND = {"article": "article", "preprint": "misc", "book": "book", "thesis": "phdthesis",
        "news": "misc", "event": "misc"}


def key(it, used):
    first = (it.get("authors") or ["anon"])[0].split()[-1] if it.get("authors") else "anon"
    first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode().lower()
    word = re.sub(r"[^a-z]", "", (it.get("title") or "x").split()[0].lower()) or "x"
    k = f"{re.sub(r'[^a-z]', '', first)}{(it.get('date') or '0000')[:4]}{word}"
    base, n = k, 1
    while k in used:
        n += 1
        k = f"{base}{n}"
    used.add(k)
    return k


def esc(s):
    return str(s or "").replace("{", "(").replace("}", ")")


used, out = set(), []
for it in items:
    if it.get("type") in ("news", "event"):
        continue
    f = {"title": "{" + esc(it.get("title")) + "}",
         "author": " and ".join(esc(a) for a in it.get("authors") or []),
         "year": (it.get("date") or "")[:4],
         "doi": it.get("doi"), "url": it.get("url"),
         "abstract": esc(it.get("abstract")),
         "keywords": ", ".join(it.get("topics") or []),
         "note": esc(it.get("summary"))}
    venue_field = {"article": "journal", "book": "publisher", "thesis": "school"}.get(it.get("type"), "howpublished")
    f[venue_field] = esc(it.get("venue"))
    body = ",\n".join(f"  {k} = {{{v}}}" if k != "title" else f"  {k} = {{{v}}}"
                      for k, v in f.items() if v)
    out.append(f"@{KIND.get(it.get('type'), 'misc')}{{{key(it, used)},\n{body}\n}}")

(ROOT / "docs" / "biblioteca.bib").write_text("\n\n".join(out) + "\n", encoding="utf-8")
print(f"biblioteca.bib: {len(out)} entradas")
