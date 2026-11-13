# Vigilancia bibliográfica diaria

Rutina de Claude en la nube que cada mañana busca novedades sobre **pedagogía no lineal / CLA /
dinámica ecológica**, **sistemas complejos en el deporte**, **fútbol** y **aprendizaje motor y
talento** (EN/ES/PT/CA), las puntúa y resume, envía un email por Gmail y actualiza la web acumulativa.

| Fichero | Qué hace |
|---|---|
| `config.json` | Términos de búsqueda por tema, autores y revistas seguidas, filtros. **Edítalo para afinar.** |
| `AGENTE.md` | Instrucciones que sigue el agente cada día (criterios de relevancia, formato del email). |
| `scripts/fetch.py` | Consulta OpenAlex, Crossref (26 revistas), PubMed, arXiv, SportRxiv, Google News y RSS. |
| `scripts/mark_seen.py` | Registra lo ya evaluado en `data/seen.json` para no repetir. |
| `scripts/export_bib.py` | Genera `docs/biblioteca.bib` para importar en Zotero/Mendeley. |
| `docs/` | Web acumulativa (GitHub Pages): `index.html` + `items.json`. |

Prueba local: `python3 scripts/fetch.py --days 7` (opcional: `OPENALEX_API_KEY=... python3 scripts/fetch.py`).
