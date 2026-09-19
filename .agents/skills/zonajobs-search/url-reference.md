# ZonaJobs Argentina URL Reference

Public, unauthenticated JSON API behind ZonaJobs Argentina's SPA
(www.zonajobs.com.ar). Bumeran (www.bumeran.com.ar) uses the **same backend**
with a different `x-site-id` (`BMAR`). The HTML pages are a client-rendered
React shell and carry **no** listings — the API is the only source of job data.

> Personal use only — keep volume low; the site may rate-limit.

## Common request headers

Both endpoints require a browser User-Agent and the `x-site-id` header
(`ZJAR` for ZonaJobs Argentina). Sending `Origin`/`Referer` matching the site
avoids Cloudflare friction.

```
x-site-id: ZJAR
Content-Type: application/json   (search only)
Accept: application/json
```

## Search

```
POST https://www.zonajobs.com.ar/api/avisos/searchV2?pageSize=<n>&page=<p>
```

Query params:

| Param | Meaning | Example |
|-------|---------|---------|
| `pageSize` | Results per page (default 20) | `20` |
| `page` | Page, **0-indexed** | `0`, `1`, `2`, … |

JSON body:

| Field | Meaning | Example |
|-------|---------|---------|
| `query` | Free-text keyword search | `"desarrollador"` |
| `filtros` | Array of `{ id, value }` filters | see below |
| `internacional` | International listings flag | `false` |

Filters:

| `id` | `value` | Meaning |
|------|---------|---------|
| `provincia` | Semantic province id, e.g. `argentina\|buenos-aires` | Location |
| `dias_fecha_publicacion` | `publicacion-menor-a-7-dias` (buckets: 2,3,4,5,6,7,15,31 days, plus `publicacion-menor-a-1-mes`) | Posting age |

### Response shape

```json
{
  "number": 0,
  "size": 20,
  "total": 95,
  "content": [
    {
      "id": 2188012,
      "titulo": "Analista Programador",
      "detalle": "<description, HTML-encoded>",
      "empresa": "Ferrovias S.A.C.",
      "confidencial": false,
      "localizacion": "Capital Federal, Buenos Aires",
      "fechaPublicacion": "13-08-2026",
      "fechaHoraPublicacion": "13-08-2026 09:00:00",
      "modalidadTrabajo": "Híbrido",
      "tipoTrabajo": "Full-time"
    }
  ],
  "filters": [ { "type": "provincia", "facets": [ { "id": "29", "idSemantico": "argentina|buenos-aires", "name": "Buenos Aires", "quantity": 80 } ] } ],
  "filtersApplied": [ { "type": "dias_fecha_publicacion", "id": "now-7d/d", "idSemantico": "publicacion-menor-a-7-dias", "name": "Menor a 1 semana" }, { "id": "query", "value": "desarrollador" } ]
}
```

Field mapping used by the CLI: `id`→id, `titulo`→title, `empresa`→company
(null when `confidencial` is true), `localizacion`→location,
`fechaPublicacion`→date (DD-MM-YYYY).

### Job URL

The listing URL is not returned by search; reconstruct it as
`/empleos/<slugified-title>[-<slugified-company>]-<id>.html` (company segment
omitted when confidential), e.g.
`https://www.zonajobs.com.ar/empleos/analista-programador-ferrovias-s.a.c.-2188012.html`.
`seoFriendlyUrl` in the detail response is authoritative.

## Detail

```
GET https://www.zonajobs.com.ar/api/candidates/fichaAvisoNormalizada/<id>
```

Additional header: `Cache-Control: no-cache, no-store, must-revalidate`.

### Response shape

```json
{
  "aviso": {
    "id": 2188012,
    "titulo": "Analista Programador",
    "empresa": { "denominacion": "Ferrovias S.A.C.", "confidencial": false },
    "localizacion": { "detalle": "Capital Federal, Buenos Aires, Argentina" },
    "fechaPublicacion": "13-08-2026",
    "fechaHoraPublicacion": "13-08-2026 09:00:00",
    "modalidadTrabajo": { "id": 3, "nombre": "Híbrido", "idSemantico": "hibrido" },
    "tipoTrabajo": { "id": 2, "nombre": "Full-time", "idSemantico": "full-time" },
    "tipoContratacion": { "id": 1, "nombre": "Indeterminado" },
    "nivelLaboral": { "id": 1, "nombre": "Senior / Semi-Senior" },
    "descripcion": "<p>…HTML…</p>",
    "descripcionSimple": "…",
    "requisitos": { "edad": null, "salario": { "salarioMinimo": null } },
    "seoFriendlyUrl": "/empleos/analista-programador-ferrovias-s.a.c.-2188012.html"
  },
  "avisosSimilares": [ ],
  "productoLookAndFeel": { }
}
```

The `descripcion` field is HTML; the CLI converts it to plain text with
paragraph breaks preserved.

## Location reference

Province filter values come from `GET https://www.zonajobs.com.ar/api/provincias/1`
(23 Argentine provinces; `idSemantico` is the filter value). The CLI bakes a
static copy of this map plus aliases (`Capital Federal`, `CABA`, `GBA` →
`argentina|buenos-aires`). City-level localidad ids exist but are not exposed
here.

## Notes

- Page is 0-indexed in the API, 1-indexed in the CLI.
- A `404` from the search endpoint is treated as an error (endpoint moved/blocked),
  while a `404` from detail means "job not found".
- Robots.txt does not disallow the `/api/` paths.
- When the site changes this SPA, re-discover the endpoints from
  `https://www.zonajobs.com.ar/candidate/static/js/main.<hash>.js` — the API
  paths and the `x-site-id` default (`ZJAR`) live in the webpack bundle.
