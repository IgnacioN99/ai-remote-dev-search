# Computrabajo Argentina URL Reference

Public, unauthenticated pages on https://ar.computrabajo.com. Postings are in Spanish;
market is Argentina. Server-rendered HTML (not a client-side SPA) — the search page
returns a full `<title>` and ~300KB of markup.

> Personal use only — robots.txt disallows several internal paths (below) and automated
> access may be against the portal's terms; keep volume low.

## Search

```
GET https://ar.computrabajo.com/trabajo-de-<slug>
```

`<slug>` is the query lowercased, with accents stripped and spaces/punctuation
collapsed to hyphens:

| Input | Slug | URL |
|-------|------|-----|
| `desarrollador` | `desarrollador` | `/trabajo-de-desarrollador` |
| `desarrollador backend` | `desarrollador-backend` | `/trabajo-de-desarrollador-backend` |
| `ruby on rails` | `ruby-on-rails` | `/trabajo-de-ruby-on-rails` |
| `administración` | `administracion` | `/trabajo-de-administracion` (accented form 301-redirects here) |

Query params:

| Param | Meaning | Example |
|-------|---------|---------|
| `p` | Page number (1-indexed, 20 results/page) | `?p=2` |
| `pubdate` | Only postings published in the last N days | `?pubdate=7` |

Note: robots.txt disallows `pubdate=`-style filter combos on the `/ofertas-de-trabajo/*`
path; the `/trabajo-de-<query>` search path itself is not disallowed.

### Search-results markup (the file to update if the portal changes)

Each posting is an `<article class="box_offer ..." data-id='<32-hex-ID>'>`. Field anchors:

| Field | Anchor |
|-------|--------|
| Job ID | `data-id='<32-hex>'` on the `<article>` (fallback: 32-hex suffix of the offer URL) |
| Title | `<a class="js-o-link fc_base" href="...">` inside `<h2 class="fs18 fwB prB">` |
| Offer URL | that anchor's `href`, relative: `/ofertas-de-trabajo/oferta-de-trabajo-de-<slug>-<ID>#lc=...` (strip `#lc` fragment, prefix with site origin) |
| Company | `<p class="dFlex vm_fs fs16 fc_base mt5">` — either `<a class="fc_base t_ellipsis" href="...">Company</a>` or plain text (anonymous employers) |
| Location | `<p class="fs16 fc_base mt5"><span class="mr10">Location</span></p>` |
| Date | `<p class="fs13 fc_aux mt15">Hace …</p>` (relative Spanish: `Hace 2 horas`, `Hace 3 días`) |
| Modality (optional) | `<div class="fs13 mt15">…` (`Presencial`, `Remoto`, `Presencial y remoto`) |

The page embeds an `application/ld+json` graph, but its `ListItem` entries carry only
URLs (no title/company/date), so parsing the card markup is the reliable path.

An empty results page (e.g. a phrase with no postings) returns HTTP 200 with zero
`<article class="box_offer">` elements — the parser returns `[]`.

## Detail

```
GET https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-<slug>-<id>
```

A posting's canonical URL is echoed in `<link rel="canonical" href="...">`.

| Field | Anchor |
|-------|--------|
| Title | `<h1 class="fwB fs24 mb5 box_detail w100_m">` |
| Company + location | `<p class="fs16">Company - City, Province</p>` (split on the last `" - "`) |
| Description block | `<div class="mb40 pb40 bb1" div-link="oferta">` |
| Salary / contract / schedule / modality | `<span class="tag base mb10">…</span>` ×4 (order: salary, contract type, schedule, modality) |
| Full description | `<p class="mbB">…</p>` inside the block, lines separated by `<br />` (convert to newlines) |
| Requirements | `<p class="fwB fs18 mtB mb10">Requerimientos</p>` + `<ul class="disc mbB"><li …>` |
| Keywords | `<p class="fc_aux fs13 mbB mtB">Palabras clave: …</p>` |
| Date | `<p class="fc_aux fs13">Hace … (actualizada)</p>` |
| Apply URL | `data-href-offer-apply="…"` (or `data-href-access="…"`) on the Postularme anchor → `candidato.ar.computrabajo.com/match/?oi=<id>…` |

A non-existent job ID returns a 404 (the CLI reports `NOT_FOUND`).

## robots.txt (https://ar.computrabajo.com/robots.txt)

Disallowed: `/hojas-de-vida/*`, `/curriculums/*`, several filtered-search combos on
`/ofertas-de-trabajo/*` (e.g. `*pubdate=`, `*sal=`, `*by=`, `*emp=`), `/empresas/*city=`,
`/ofertas-de-trabajo/Detail/Print.aspx`, `/Ajax/*`, `/_services/*`, `/go/*`.
The `/trabajo-de-<query>` search path used by this skill is **not** disallowed.

## Notes

- No authentication required; `fetch` follows the accent-stripping 301 redirects.
- Respect rate limits — the CLI backs off with exponential backoff + jitter on 429/5xx.
- `--jobage <days>` maps to `pubdate=<days>`.
