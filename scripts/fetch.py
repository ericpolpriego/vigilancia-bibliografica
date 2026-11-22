#!/usr/bin/env python3
"""Recolector diario de candidatos bibliográficos.

Consulta APIs abiertas (OpenAlex, Crossref, PubMed, arXiv, OSF/SportRxiv,
Google News RSS y feeds RSS), deduplica contra data/seen.json y escribe
data/candidates.json para que el agente los puntúe y resuma.

Solo usa la biblioteca estándar de Python 3.
Uso: python3 scripts/fetch.py [--days N]
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
UA = "vigilancia-bibliografica/1.0 (research digest bot)"

stats = {}
errors = []


def get(url, timeout=30, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code != 429:
                errors.append(f"{url[:120]} -> {e}")
                return None
            if isinstance(e, urllib.error.HTTPError) and e.code == 429 and 'openalex' in url:
                errors.append(f"{url[:120]} -> {e}")
                return None
            if attempt == retries:
                errors.append(f"{url[:120]} -> {e}")
                return None
            time.sleep(2 * (attempt + 1))


def get_json(url, **kw):
    txt = get(url, **kw)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        errors.append(f"JSON inválido: {url[:120]}")
        return None


def clean(s):
    if not s:
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s)))
    return re.sub(r"\s+", " ", s).strip()


def norm_title(t):
    return re.sub(r"[^a-z0-9áéíóúàèòïüçñãõâêô]", "", (t or "").lower())[:120]


def item(source, title, url, date="", authors=None, venue="", abstract="", doi="",
         kind="article", lang="", hint=""):
    doi = (doi or "").lower().replace("https://doi.org/", "").strip()
    return {
        "id": f"doi:{doi}" if doi else f"t:{norm_title(title)}",
        "source": source,
        "type": kind,
        "title": clean(title),
        "authors": [clean(a) for a in (authors or []) if a][:12],
        "venue": clean(venue),
        "date": (date or "")[:10],
        "doi": doi,
        "url": url or (f"https://doi.org/{doi}" if doi else ""),
        "abstract": clean(abstract)[:1800],
        "lang": {"eng": "en", "spa": "es", "por": "pt", "cat": "ca"}.get((lang or "").lower(), (lang or "").lower()[:2]),
        "hint": hint,
    }


# ---------------------------------------------------------------- OpenAlex
def oa_abstract(inv):
    if not inv:
        return ""
    pos = []
    for w, idx in inv.items():
        for i in idx:
            pos.append((i, w))
    return " ".join(w for _, w in sorted(pos))


def oa_item(w, hint):
    loc = (w.get("primary_location") or {})
    src = (loc.get("source") or {})
    t = w.get("type") or "article"
    kind = {"preprint": "preprint", "dissertation": "thesis", "book": "book",
            "book-chapter": "book"}.get(t, "article")
    it = item("OpenAlex", w.get("title") or w.get("display_name"),
                loc.get("landing_page_url") or w.get("id"),
                w.get("publication_date"),
                [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
                src.get("display_name", ""), oa_abstract(w.get("abstract_inverted_index")),
                w.get("doi") or "", kind, w.get("language") or "", hint)
    it["oa_url"] = (w.get("open_access") or {}).get("oa_url") or ""
    return it


def relevant(text):
    """Filtro local: concepto del área + contexto deportivo."""
    t = text.lower()
    return (any(c in t for c in CONFIG["concept_terms"]) and any(x in t for x in CONFIG["sport_terms"]))


def openalex(since):
    """Pocas llamadas (OR agrupados): el presupuesto gratuito de OpenAlex es limitado.
    Con OPENALEX_API_KEY en el entorno se usa la cuota propia (gratuita) del usuario."""
    out = []
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    langs = "|".join(CONFIG["languages"])
    base = "https://api.openalex.org/works"
    sel = "id,doi,title,display_name,publication_date,type,language,primary_location,authorships,abstract_inverted_index,open_access"

    def call(flt, hint, per=100, check=False):
        params = {"filter": flt, "per-page": str(per), "select": sel}
        if key:
            params["api_key"] = key
        js = get_json(base + "?" + urllib.parse.urlencode(params))
        if js is None and "api_key" in params:
            # clave rechazada (401) o fallo puntual: reintenta sin clave con el cupo gratuito
            params.pop("api_key")
            js = get_json(base + "?" + urllib.parse.urlencode(params))
            if js is not None:
                errors.append("OpenAlex: la clave OPENALEX_API_KEY fue rechazada; se usó el acceso sin clave")
        n = 0
        for w in (js or {}).get("results", []):
            it = oa_item(w, hint)
            if check and not relevant(it["title"] + " " + it["abstract"] + " " + it["venue"]):
                continue
            out.append(it); n += 1
        time.sleep(0.3)

    for tkey, topic in CONFIG["topics"].items():
        qs = topic["queries"]
        for i in range(0, len(qs), 8):  # 8 términos por llamada
            q = " OR ".join(f"({x})" for x in qs[i:i + 8])
            call(f"title_and_abstract.search:{q},from_publication_date:{since},language:{langs}", f"tema:{tkey}")
    # Bloque específico en español, portugués y catalán: búsqueda amplia por deporte y filtro local
    # por conceptos (OpenAlex indexa SciELO, Dialnet, Redalyc y repositorios de la península).
    iber = CONFIG.get("iberian_queries", [])
    for i in range(0, len(iber), 10):
        q = " OR ".join(f"({x})" for x in iber[i:i + 10])
        call(f"title_and_abstract.search:{q},from_publication_date:{since},language:es|pt|ca",
             "es/pt/ca", per=200, check=True)
    names = CONFIG["authors"]
    for i in range(0, len(names), 10):
        call(f"raw_author_name.search:{'|'.join(names[i:i + 10])},from_publication_date:{since}",
             "autor seguido", per=200, check=True)
    stats["openalex"] = len(out)
    return out


def fondo(_since):
    """Lecturas de fondo: cada día un tema y una consulta distintos (rotación), sin límite de fecha,
    ordenados por citas. Los ya vistos se descartan después, así que cada día salen trabajos nuevos."""
    out = []
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    topics = list(CONFIG["topics"].items())
    day = dt.date.today().toordinal()
    tkey, topic = topics[day % len(topics)]
    qs = topic["queries"]
    q = qs[(day // len(topics)) % len(qs)]
    params = {"filter": f"title_and_abstract.search:{q},language:{'|'.join(CONFIG['languages'])},type:article|review|book|book-chapter|dissertation",
              "sort": "cited_by_count:desc", "per-page": str(CONFIG.get("fondo_por_dia", 25)),
              "select": "id,doi,title,display_name,publication_date,type,language,primary_location,authorships,abstract_inverted_index,open_access,cited_by_count"}
    if key:
        params["api_key"] = key
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    js = get_json(url)
    if js is None and key:
        params.pop("api_key")
        js = get_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
    for w in (js or {}).get("results", []):
        it = oa_item(w, f"fondo:{tkey}:{q}")
        it["background"] = True
        it["cited_by"] = w.get("cited_by_count") or 0
        out.append(it)
    stats["fondo"] = f"{len(out)} ({topic['label']}: {q})"
    return out


# ---------------------------------------------------------------- Crossref
def crossref(since):
    jobs = [(j, issn) for j, issns in CONFIG["journals"].items() for issn in issns]

    def one(job):
        jname, issn = job
        res = []
        params = {"filter": f"issn:{issn},from-created-date:{since}", "rows": "300",
                  "select": "DOI,title,author,container-title,abstract,published,published-online,created,URL,type"}
        js = get_json("https://api.crossref.org/works?" + urllib.parse.urlencode(params), timeout=45)
        for w in ((js or {}).get("message") or {}).get("items", []):
            title = " ".join(w.get("title") or [])
            abstract = w.get("abstract", "")
            if not relevant(title + " " + abstract + " " + jname):
                continue
            src_date = w.get("published-online") or w.get("created") or w.get("published") or {}
            parts = (src_date.get("date-parts") or [[None]])[0]
            date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p)
            authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in w.get("author", [])]
            res.append(item("Crossref", title, w.get("URL"), date, authors, jname, abstract,
                            w.get("DOI"), "article", "", f"revista:{jname}"))
        return res

    out = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        for r in ex.map(one, jobs):
            out += r
    stats["crossref"] = len(out)
    return out


# ---------------------------------------------------------------- PubMed
def pubmed(days):
    q = ('("nonlinear pedagogy" OR "constraints-led" OR "ecological dynamics" OR "representative learning design" '
         'OR "small-sided games" OR "tactical periodization" OR "skill acquisition" OR "dynamical systems" '
         'OR "complex systems" OR "interpersonal coordination" OR "talent development" OR "motor learning") '
         'AND (football OR soccer OR sport OR "team sports" OR athletes OR coaching)')
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    es = get_json(base + "esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": q, "reldate": str(days), "datetype": "edat", "retmax": "200", "retmode": "json"}))
    ids = ((es or {}).get("esearchresult") or {}).get("idlist", [])
    out = []
    if ids:
        xml = get(base + "efetch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}), timeout=60)
        if xml:
            root = ET.fromstring(xml)
            for art in root.iter("PubmedArticle"):
                a = art.find(".//Article")
                if a is None:
                    continue
                title = "".join(a.find("ArticleTitle").itertext()) if a.find("ArticleTitle") is not None else ""
                abstract = " ".join("".join(x.itertext()) for x in a.findall(".//AbstractText"))
                authors = [f"{x.findtext('ForeName', '')} {x.findtext('LastName', '')}".strip()
                           for x in a.findall(".//Author")]
                doi = next((x.text for x in art.findall(".//ArticleId") if x.get("IdType") == "doi"), "")
                pmid = art.findtext(".//PMID")
                ad = a.find(".//ArticleDate")
                date = (f"{ad.findtext('Year')}-{ad.findtext('Month')}-{ad.findtext('Day')}" if ad is not None
                        else dt.date.today().isoformat())
                out.append(item("PubMed", title, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", date, authors,
                                a.findtext(".//Journal/Title", ""), abstract, doi, "article",
                                a.findtext("Language", ""), "pubmed"))
    stats["pubmed"] = len(out)
    return out


# ---------------------------------------------------------------- arXiv
def arxiv(since):
    q = ('(all:football OR all:soccer OR all:"team sports") AND (all:"complex systems" OR all:network '
         'OR all:"dynamical" OR all:coordination OR all:tactical OR all:"collective behaviour")')
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": "40"})
    xml = get(url, timeout=60)
    out = []
    if xml:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in ET.fromstring(xml).findall("a:entry", ns):
            date = e.findtext("a:published", "", ns)[:10]
            if date < since:
                continue
            out.append(item("arXiv", e.findtext("a:title", "", ns), e.findtext("a:id", "", ns), date,
                            [x.findtext("a:name", "", ns) for x in e.findall("a:author", ns)],
                            "arXiv", e.findtext("a:summary", "", ns), "", "preprint", "en", "arxiv"))
    stats["arxiv"] = len(out)
    return out


# ---------------------------------------------------------------- SportRxiv (OPS)
def sportrxiv(since):
    out = []
    xml = get("https://sportrxiv.org/index.php/server/gateway/plugin/WebFeedGatewayPlugin/rss2", timeout=60)
    if xml:
        for it in parse_rss(xml, "SportRxiv", "preprint", since, "sportrxiv"):
            if relevant(it["title"] + " " + it["abstract"]):
                it["venue"] = "SportRxiv"
                out.append(it)
    stats["sportrxiv"] = len(out)
    return out


# ---------------------------------------------------------------- RSS / noticias
def parse_rss(xml, source, kind, since, hint):
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        errors.append(f"RSS inválido: {source}")
        return out
    for it in root.iter("item"):
        pub = it.findtext("pubDate", "")
        try:
            date = dt.datetime.strptime(pub[:25].strip(), "%a, %d %b %Y %H:%M:%S").date().isoformat()
        except ValueError:
            date = ""
        if date and date < since:
            continue
        src = it.findtext("source", "") or source
        out.append(item(source, it.findtext("title", ""), it.findtext("link", ""), date, [], src,
                        it.findtext("description", ""), "", kind, "", hint))
    return out


def news(since):
    out = []
    locales = [("es", "ES", "ES:es"), ("en", "US", "US:en"), ("pt-PT", "PT", "PT:pt-150")]
    for q in CONFIG["news_queries"]:
        for hl, gl, ceid in locales:
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
                {"q": f"{q} when:{CONFIG['lookback_days']}d", "hl": hl, "gl": gl, "ceid": ceid})
            xml = get(url)
            if xml:
                out += parse_rss(xml, "Google News", "news", since, f"noticias:{q}")
            time.sleep(0.3)
    for name, url in CONFIG.get("rss_feeds", {}).items():
        xml = get(url)
        if xml:
            out += parse_rss(xml, name, "news", since, "rss")
    stats["news"] = len(out)
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=CONFIG["lookback_days"])
    args = ap.parse_args()
    since = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()

    seen_path = DATA / "seen.json"
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()

    collected = []
    for fn, arg in [(openalex, since), (fondo, since), (crossref, since), (pubmed, args.days), (arxiv, since),
                    (sportrxiv, since), (news, since)]:
        try:
            collected += fn(arg)
        except Exception as e:  # una fuente caída no debe tumbar el resto
            errors.append(f"{fn.__name__}: {e!r}")

    limite = (dt.date.today() - dt.timedelta(days=CONFIG.get("novelty_days", 60))).isoformat()
    descartados_antiguos = 0
    merged, index = {}, {}
    for it in collected:
        if not it["title"]:
            continue
        if it["type"] in ("article", "preprint", "thesis") and len(it["date"]) >= 4 and it["date"][:len(limite)] < limite[:len(it["date"])]:
            it["background"] = True  # anterior: no es novedad, pero puede ser una lectura de fondo valiosa
            descartados_antiguos += 1
        keys = {it["id"], f"t:{norm_title(it['title'])}"}
        if (keys | {f"u:{it['url']}"}) & seen:
            continue
        k = next((index[x] for x in keys if x in index), it["id"])
        for x in keys:
            index[x] = k
        if k in merged:
            m = merged[k]
            m["hint"] = ", ".join(sorted(set((m["hint"] + ", " + it["hint"]).split(", "))))
            if len(it["abstract"]) > len(m["abstract"]):
                m["abstract"] = it["abstract"]
            if not m["doi"] and it["doi"]:
                m["doi"] = it["doi"]
        else:
            merged[k] = it

    cands = list(merged.values())
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fulltext import enrich
    cands = enrich(cands)
    (DATA / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    stats["anteriores_marcados_de_fondo"] = descartados_antiguos
    print(json.dumps({"since": since, "por_fuente": stats, "candidatos_nuevos": len(cands),
                      "errores": errors[:20]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
