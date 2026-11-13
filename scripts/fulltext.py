#!/usr/bin/env python3
"""Añade a cada ítem el mejor enlace para leer el texto completo.

Campos que añade:
  fulltext_url   enlace directo al texto completo (PDF o HTML en acceso abierto) o,
                 si no existe versión abierta, la página del artículo en la editorial
  fulltext_kind  "pdf" | "html" (acceso abierto) | "publisher" (puede requerir suscripción)
  oa             True si hay versión gratuita legal
  oa_status      gold / green / hybrid / bronze / diamond / closed (según Unpaywall)
  scholar_url    búsqueda en Google Scholar ("Todas las versiones" suele dar PDF del autor)

Uso standalone:  python3 scripts/fulltext.py docs/items.json data/web_candidates.json
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "vigilancia-bibliografica/1.0 (research digest bot)"
UNPAYWALL_EMAIL = "vigilancia-bibliografica@users.noreply.github.com"


def _get_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _scholar(it):
    q = it.get("doi") or f'"{it.get("title", "")}"'
    return "https://scholar.google.com/scholar?" + urllib.parse.urlencode({"q": q})


OA_JOURNALS = ["journal of human kinetics", "sports medicine - open", "sports medicine – open", "frontiers in",
               "plos one", "retos", "apunts", "ricyde", "cultura, ciencia y deporte", "cultura ciencia y deporte",
               "motricidade", "biology of sport", "e-balonmano", "journal of sport science and medicine",
               "journal of sports science and medicine", "scientific reports", "bmc ", "peerj", "revista brasileira",
               "movimento", "revista de psicología del deporte", "cuadernos de psicología del deporte",
               "journal of physical education and sport", "international journal of environmental research and public health",
               "sports (basel)", "applied sciences", "healthcare", "children", "behavioral sciences"]


def _known_open(it):
    """Fuentes cuyo enlace ya es el texto completo."""
    url = it.get("url") or ""
    venue = (it.get("venue") or "").lower()
    if it.get("doi") and any(venue.startswith(j) or j in venue for j in OA_JOURNALS):
        return f"https://doi.org/{it['doi']}", "html"
    if "arxiv.org/abs/" in url:
        return url.replace("/abs/", "/pdf/"), "pdf"
    if "sportrxiv.org" in url or "osf.io" in url:
        return url, "html"
    if it.get("type") in ("news", "event"):
        return url, "html"
    return None, None


def enrich_one(it):
    if it.get("fulltext_url") and it.get("fulltext_kind"):
        return it
    it["scholar_url"] = _scholar(it)
    url, kind = _known_open(it)
    if url:
        it.update(fulltext_url=url, fulltext_kind=kind, oa=True, oa_status="open")
        return it
    doi = (it.get("doi") or "").strip()
    if doi:
        js = _get_json(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={UNPAYWALL_EMAIL}")
        best = (js or {}).get("best_oa_location") or {}
        oa_url = it.get("oa_url") or best.get("url_for_pdf") or best.get("url_for_landing_page") or best.get("url")
        if js and js.get("is_oa") and oa_url:
            is_pdf = bool(best.get("url_for_pdf")) or oa_url.lower().endswith(".pdf") or "/pdf" in oa_url
            it.update(fulltext_url=oa_url, fulltext_kind="pdf" if is_pdf else "html",
                      oa=True, oa_status=js.get("oa_status") or "open")
            return it
        it.update(fulltext_url=f"https://doi.org/{doi}", fulltext_kind="publisher", oa=False,
                  oa_status=(js or {}).get("oa_status") or "closed")
        return it
    if it.get("oa_url"):
        it.update(fulltext_url=it["oa_url"], fulltext_kind="pdf" if re.search(r"pdf", it["oa_url"], re.I) else "html",
                  oa=True, oa_status="open")
        return it
    it.update(fulltext_url=it.get("url") or it["scholar_url"], fulltext_kind="publisher", oa=False,
              oa_status="unknown")
    return it


def enrich(items, workers=6):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(enrich_one, items))


if __name__ == "__main__":
    for path in sys.argv[1:] or ["docs/items.json"]:
        p = Path(path)
        if not p.exists():
            continue
        data = enrich(json.loads(p.read_text(encoding="utf-8")))
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        n_oa = sum(1 for x in data if x.get("oa"))
        print(f"{path}: {len(data)} ítems, {n_oa} con texto completo abierto")
