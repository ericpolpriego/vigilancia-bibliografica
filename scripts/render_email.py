#!/usr/bin/env python3
"""Genera el email diario (data/email.html y data/email_subject.txt) con una plantilla fija.

Lee los ítems de docs/items.json cuyo `found` sea hoy (o --fecha AAAA-MM-DD) y los ordena:
resumen → Destacados (4-5) → Relevantes (3) → Para ojear (2) → Libros y tesis → Eventos → Noticias.
HTML con tablas y estilos en línea para que se vea bien en Gmail (web y móvil).
"""
import argparse
import datetime as dt
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = "https://ericpolpriego.github.io/vigilancia-bibliografica/"

C = {"ink": "#1d2321", "muted": "#5f6b66", "line": "#e3e1da", "bg": "#f7f6f2", "card": "#ffffff",
     "acc": "#1f6f50", "acc_soft": "#e2f0e9", "star": "#c08a16", "warn_soft": "#fdf3e1", "warn": "#8a5a00"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
TIPOS = {"article": "Artículo", "preprint": "Preprint", "thesis": "Tesis", "book": "Libro",
         "event": "Evento", "news": "Noticia"}
TEMAS = {"pedagogia_no_lineal": "Pedagogía no lineal / CLA", "sistemas_complejos": "Sistemas complejos",
         "futbol": "Fútbol", "aprendizaje_talento": "Aprendizaje y talento"}
FICHA = [("objective", "🎯 Objetivo"), ("design", "🧪 Diseño"), ("population", "👥 Muestra"),
         ("method", "⚙️ Método"), ("results", "📊 Resultados"), ("conclusions", "✅ Conclusiones"),
         ("limitations", "⚠️ Limitaciones"), ("why", "💡 Por qué te interesa"),
         ("practice", "⚽ Aplicación práctica")]


def e(s):
    return html.escape(str(s or ""), quote=True)


def fecha(s):
    """'2026-11-12' → '12 nov 2026'; '2026-11' → 'nov 2026'; '2026' → '2026'."""
    if not s:
        return ""
    p = str(s)[:10].split("-")
    try:
        if len(p) == 3:
            return f"{int(p[2])} {MESES[int(p[1]) - 1][:3]} {p[0]}"
        if len(p) == 2:
            return f"{MESES[int(p[1]) - 1][:3]} {p[0]}"
    except (ValueError, IndexError):
        pass
    return p[0]


def fecha_larga(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def autores(it):
    a = it.get("authors") or []
    return ", ".join(a[:3]) + (" et al." if len(a) > 3 else "")


def badge(txt, bg, fg):
    return (f'<span style="display:inline-block;background:{bg};color:{fg};font-size:12px;'
            f'font-weight:600;border-radius:10px;padding:2px 9px;margin:0 4px 4px 0">{e(txt)}</span>')


def botones(it):
    u = it.get("fulltext_url") or it.get("url") or ""
    if not u:
        return ""
    btn = ('<a href="{u}" style="display:inline-block;background:{bg};color:{fg};border:1px solid {bd};'
           'text-decoration:none;font-size:13px;font-weight:600;border-radius:8px;padding:7px 12px;'
           'margin:4px 6px 0 0">{t}</a>')
    t = it.get("type")
    if t in ("news", "event"):
        return btn.format(u=e(u), bg=C["acc"], fg="#fff", bd=C["acc"],
                          t="🌐 Ver evento" if t == "event" else "🌐 Leer noticia")
    if it.get("oa"):
        lab = "📄 Leer artículo completo" + (" (PDF)" if it.get("fulltext_kind") == "pdf" else "") + " · acceso abierto"
        return btn.format(u=e(u), bg=C["acc"], fg="#fff", bd=C["acc"], t=lab)
    out = btn.format(u=e(u), bg="#fff", fg=C["ink"], bd=C["line"], t="🔒 Texto completo en la editorial")
    if it.get("scholar_url"):
        out += btn.format(u=e(it["scholar_url"]), bg="#fff", fg=C["muted"], bd=C["line"], t="🔎 Buscar versión gratuita")
    return out


def cabecera_item(it):
    stars = "★" * int(it.get("relevance") or 0)
    b = f'<span style="color:{C["star"]};font-size:14px;margin-right:6px">{stars}</span>'
    b += badge(TIPOS.get(it.get("type"), it.get("type") or ""), C["acc_soft"], C["acc"])
    if it.get("type") not in ("news", "event"):
        b += badge("Acceso abierto" if it.get("oa") else "Suscripción",
                   C["acc_soft"] if it.get("oa") else C["warn_soft"], C["acc"] if it.get("oa") else C["warn"])
    for tp in it.get("topics") or []:
        b += badge(TEMAS.get(tp, tp), "#eef0ec", C["muted"])
    return b


def meta(it):
    partes = []
    if it.get("type") == "event" and it.get("event_date"):
        partes.append(f"📅 <b>Fecha del evento:</b> {fecha(it['event_date'])}"
                      + (f" · 📍 {e(it.get('location'))}" if it.get("location") else ""))
    else:
        f = fecha(it.get("date"))
        partes.append(f"📅 <b>Publicado:</b> {f}" if f else "📅 <b>Publicado:</b> fecha no disponible")
    linea2 = " · ".join(x for x in [e(autores(it)), f"<i>{e(it.get('venue'))}</i>" if it.get("venue") else ""] if x)
    return (f'<div style="font-size:13px;color:{C["ink"]};margin-top:6px">{partes[0]}</div>'
            + (f'<div style="font-size:13px;color:{C["muted"]};margin-top:2px">{linea2}</div>' if linea2 else ""))


def ficha(it):
    filas = ""
    for k, lab in FICHA:
        v = it.get(k)
        if not v or v == "—":
            continue
        filas += (f'<tr><td style="vertical-align:top;padding:5px 10px 5px 0;width:150px;font-size:13px;'
                  f'font-weight:600;color:{C["ink"]};white-space:nowrap">{lab}</td>'
                  f'<td style="vertical-align:top;padding:5px 0;font-size:14px;line-height:1.5;color:{C["ink"]}">{e(v)}</td></tr>')
    if not filas and it.get("summary"):
        filas = f'<tr><td colspan="2" style="font-size:14px;line-height:1.5;padding:5px 0">{e(it["summary"])}</td></tr>'
    src = it.get("analysis_source")
    nota = (f'<div style="font-size:12px;color:{C["muted"]};margin-top:6px">Análisis basado en: {e(src)}</div>'
            if src else "")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-top:1px solid {C["line"]};margin-top:10px;padding-top:4px">{filas}</table>{nota}')


def tarjeta(it, completa=True):
    titulo = (f'<a href="{e(it.get("url") or it.get("fulltext_url"))}" style="color:{C["ink"]};'
              f'text-decoration:none;font-size:17px;font-weight:700;line-height:1.35">{e(it.get("title"))}</a>')
    cuerpo = ficha(it) if completa else (
        f'<div style="font-size:14px;line-height:1.5;margin-top:8px">{e(it.get("summary"))}</div>'
        + (f'<div style="font-size:14px;line-height:1.5;margin-top:4px;color:{C["muted"]}"><b>💡</b> {e(it.get("why"))}</div>' if it.get("why") else ""))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{C["card"]};'
            f'border:1px solid {C["line"]};border-radius:12px;margin:0 0 14px"><tr><td style="padding:16px 18px">'
            f'<div>{cabecera_item(it)}</div><div style="margin-top:4px">{titulo}</div>{meta(it)}{cuerpo}'
            f'<div style="margin-top:10px">{botones(it)}</div></td></tr></table>')


def linea(it):
    u = it.get("fulltext_url") or it.get("url")
    f = fecha(it.get("event_date") if it.get("type") == "event" else it.get("date"))
    extra = " · ".join(x for x in [f, it.get("venue"), it.get("location") if it.get("type") == "event" else ""] if x)
    return (f'<tr><td style="padding:8px 0;border-bottom:1px solid {C["line"]}">'
            f'<span style="color:{C["star"]};font-size:12px">{"★" * int(it.get("relevance") or 0)}</span> '
            f'<a href="{e(u)}" style="color:{C["ink"]};font-weight:600;font-size:14px;text-decoration:none">{e(it.get("title"))}</a>'
            f'<div style="font-size:12px;color:{C["muted"]};margin-top:2px">{e(extra)}</div>'
            + (f'<div style="font-size:13px;color:{C["ink"]};margin-top:3px">{e(it.get("summary"))}</div>' if it.get("summary") else "")
            + '</td></tr>')


def seccion(titulo, sub, contenido):
    return (f'<h2 style="font-size:18px;color:{C["ink"]};margin:28px 0 4px">{titulo}</h2>'
            + (f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:12px">{sub}</div>' if sub else "")
            + contenido)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default=dt.datetime.utcnow().date().isoformat())
    ap.add_argument("--incidencias", default="")
    a = ap.parse_args()
    hoy = dt.date.fromisoformat(a.fecha)
    items = json.loads((ROOT / "docs" / "items.json").read_text(encoding="utf-8"))
    total = len(items)
    hoy_items = [x for x in items if x.get("found") == a.fecha]
    doc = [x for x in hoy_items if x.get("type") in ("article", "preprint")]
    rel = lambda x: -(x.get("relevance") or 0)
    dest = sorted([x for x in doc if (x.get("relevance") or 0) >= 4], key=rel)
    medio = [x for x in doc if (x.get("relevance") or 0) == 3]
    ojear = [x for x in doc if (x.get("relevance") or 0) <= 2]
    libros = sorted([x for x in hoy_items if x.get("type") in ("book", "thesis")], key=rel)
    eventos = sorted([x for x in hoy_items if x.get("type") == "event"], key=lambda x: x.get("event_date") or "9999")
    noticias = sorted([x for x in hoy_items if x.get("type") == "news"], key=rel)

    n = len(hoy_items)
    subject = (f"📚 Vigilancia científica · {fecha(a.fecha)} · {n} novedades ({len(dest)} destacadas)"
               if n else f"📚 Vigilancia científica · {fecha(a.fecha)} · sin novedades relevantes")

    # Resumen del día
    chips = "".join(
        f'<td style="padding:0 6px 0 0"><div style="background:{C["card"]};border:1px solid {C["line"]};border-radius:10px;'
        f'padding:8px 12px;text-align:center"><div style="font-size:20px;font-weight:700;color:{C["acc"]}">{v}</div>'
        f'<div style="font-size:11px;color:{C["muted"]}">{k}</div></div></td>'
        for k, v in [("Destacados", len(dest)), ("Relevantes", len(medio)), ("Para ojear", len(ojear)),
                     ("Libros/tesis", len(libros)), ("Eventos", len(eventos)), ("Noticias", len(noticias))] if v)
    indice = "".join(f'<li style="margin:2px 0">{e(x.get("title"))}</li>' for x in dest + medio)

    body = []
    if n:
        body.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0"><tr>{chips}</tr></table>')
        if indice:
            body.append(f'<div style="background:{C["acc_soft"]};border-radius:10px;padding:12px 16px;font-size:14px">'
                        f'<b>En este email</b><ol style="margin:6px 0 0 18px;padding:0">{indice}</ol></div>')
    else:
        body.append(f'<p style="font-size:15px">Sin novedades relevantes hoy.</p>')

    if dest:
        body.append(seccion("⭐ Destacados", "Relevancia alta para tu línea · ficha completa", "".join(tarjeta(x) for x in dest)))
    if medio:
        body.append(seccion("📌 Relevantes", "Relacionados con tus temas · ficha completa", "".join(tarjeta(x) for x in medio)))
    if ojear:
        body.append(seccion("👀 Para ojear", "Tangenciales pero potencialmente útiles",
                            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(linea(x) for x in ojear)}</table>'))
    if libros:
        body.append(seccion("📘 Libros y tesis", "", "".join(tarjeta(x) for x in libros)))
    if eventos:
        body.append(seccion("🗓️ Seminarios, congresos y calls", "Ordenados por fecha del evento",
                            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(linea(x) for x in eventos)}</table>'))
    if noticias:
        body.append(seccion("📰 Noticias y divulgación", "", "".join(tarjeta(x, completa=False) for x in noticias)))

    inc = (f'<div style="background:{C["warn_soft"]};color:{C["warn"]};border-radius:8px;padding:8px 12px;'
           f'font-size:12px;margin-top:10px"><b>Incidencias:</b> {e(a.incidencias)}</div>') if a.incidencias.strip() else ""
    pie = (f'<div style="border-top:1px solid {C["line"]};margin-top:28px;padding-top:12px;font-size:12px;color:{C["muted"]}">'
           f'🌐 <a href="{WEB}" style="color:{C["acc"]}">Biblioteca completa</a> ({total} ítems) · '
           f'<a href="{WEB}blog.html" style="color:{C["acc"]}">Blog semanal</a> · '
           f'<a href="{WEB}biblioteca.bib" style="color:{C["acc"]}">BibTeX para Zotero</a>'
           f'<div style="margin-top:6px">Las fichas son resúmenes propios generados a partir del texto completo o del abstract; '
           f'comprueba los datos en la fuente antes de citarlos.</div>{inc}</div>')

    out = (f'<div style="background:{C["bg"]};padding:20px 12px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{C["ink"]}">'
           f'<div style="max-width:680px;margin:0 auto">'
           f'<div style="font-size:12px;color:{C["muted"]};text-transform:uppercase;letter-spacing:.06em">Vigilancia científica</div>'
           f'<h1 style="font-size:24px;margin:4px 0 0;color:{C["ink"]}">Novedades del {fecha_larga(hoy)}</h1>'
           f'<div style="font-size:13px;color:{C["muted"]};margin-top:4px">Pedagogía no lineal · Sistemas complejos · Fútbol · Aprendizaje y talento</div>'
           + "".join(body) + pie + '</div></div>')

    (ROOT / "data" / "email.html").write_text(out, encoding="utf-8")
    (ROOT / "data" / "email_subject.txt").write_text(subject, encoding="utf-8")
    print(subject)
    print(f"data/email.html: {len(out)} caracteres, {n} ítems")


if __name__ == "__main__":
    main()
