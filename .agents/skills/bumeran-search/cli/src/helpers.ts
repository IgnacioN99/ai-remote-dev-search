// Data source: the public JSON API behind Bumeran Argentina's SPA
// (www.bumeran.com.ar). The SPA shell is a client-rendered React app, so the
// HTML page carries no listings — everything comes from these endpoints:
//
//   search: POST /api/avisos/searchV2
//   detail: GET  /api/candidates/fichaAvisoNormalizada/<id>
//
// Both require the "x-site-id" header ("BMAR" = Bumeran Argentina; ZonaJobs
// uses "ZJAR" against the same backend). No authentication, no API key.

export const SITE = "https://www.bumeran.com.ar"
export const X_SITE_ID = "BMAR"
export const SEARCH_PATH = "/api/avisos/searchV2"
export const DETAIL_PATH = "/api/candidates/fichaAvisoNormalizada"
export const SEARCH_URL = `${SITE}${SEARCH_PATH}`
export const DETAIL_URL = `${SITE}${DETAIL_PATH}`

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

interface RequestOpts {
  method?: "GET" | "POST"
  body?: unknown
}

/**
 * Fetch a JSON endpoint with exponential backoff + jitter on 429/5xx.
 * Returns `null` on a 404. Throws on other non-OK statuses or non-JSON bodies.
 */
export async function apiFetchJson(url: string, opts: RequestOpts = {}): Promise<unknown> {
  const maxRetries = 6
  let delay = 500
  const headers: Record<string, string> = {
    "User-Agent": UA,
    Accept: "application/json",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "x-site-id": X_SITE_ID,
  }
  if (opts.method === "POST") headers["Content-Type"] = "application/json"
  headers.Origin = SITE
  headers.Referer = `${SITE}/`

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
    })
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    const text = await response.text()
    try {
      return JSON.parse(text)
    } catch {
      throw new Error(`Expected JSON from ${url}, got non-JSON (${text.length} bytes)`)
    }
  }
  throw new Error("Request failed after max retries")
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
}

export interface JobDetail extends JobCard {
  description: string | null
  modality: string | null
  employmentType: string | null
  contractType: string | null
  seniority: string | null
  applyUrl: string | null
}

/**
 * Slugify the way Bumeran's SPA does (formatNameToStringId): lowercase, strip
 * accents and most punctuation, join words with hyphens. Used to reconstruct
 * a posting's canonical /empleos/ URL from a search hit.
 */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/\//g, " ")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[!#$%&'()*+,/:;=?@[\]]/g, "")
    .replace(/\s+/g, " ")
    .replace(/ /g, "-")
    .replace(/-+/g, "-")
    .replace(/-+$/g, "")
}

/** Build the posting URL from a search hit (mirrors makeFichaAvisoURL). */
export function makeAvisoUrl(id: string, title: string, company: string | null, confidential: boolean): string {
  const slug = slugify(title)
  const companySlug = confidential ? "" : company ? `-${slugify(company)}` : ""
  return `${SITE}/empleos/${slug}${companySlug}-${id}.html`
}

/**
 * Parse the searchV2 response into JobCards. Response shape:
 *   { number, size, total, content: [{ id, titulo, empresa, localizacion,
 *     fechaPublicacion, confidencial, modalidadTrabajo, ... }] }
 */
export function parseSearchResponse(json: unknown): { total: number; results: JobCard[] } {
  const root = (json ?? {}) as {
    total?: number
    content?: Array<Record<string, unknown>>
  }
  const total = typeof root.total === "number" ? root.total : 0
  const results: JobCard[] = []
  for (const j of root.content ?? []) {
    const id = j.id
    const title = j.titulo
    if (id === undefined || id === null || typeof title !== "string" || !title) continue
    const idStr = String(id)
    const confidential = j.confidencial === true
    const company = confidential ? null : typeof j.empresa === "string" && j.empresa ? j.empresa : null
    results.push({
      id: idStr,
      title,
      company,
      location: typeof j.localizacion === "string" && j.localizacion ? j.localizacion : null,
      date: typeof j.fechaPublicacion === "string" && j.fechaPublicacion ? j.fechaPublicacion : null,
      url: makeAvisoUrl(idStr, title, company, confidential),
    })
  }
  return { total, results }
}

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&nbsp;/g, " ")
}

function stripTagsKeepBreaks(html: string): string {
  const withBreaks = html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|ul|ol|h\d|section)>/gi, "\n")
  return decodeHtmlEntities(
    withBreaks.replace(/<[^>]+>/g, " ").replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n"),
  )
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

/**
 * Parse the fichaAvisoNormalizada detail response. Shape:
 *   { aviso: { id, titulo, empresa: { denominacion, confidencial },
 *     localizacion: { detalle }, fechaPublicacion, descripcion (HTML),
 *     modalidadTrabajo: { nombre }, tipoTrabajo: { nombre },
 *     tipoContratacion: { nombre }, nivelLaboral: { nombre }, seoFriendlyUrl } }
 */
export function parseDetailResponse(json: unknown, id: string): JobDetail {
  const root = (json ?? {}) as { aviso?: Record<string, unknown> }
  const a = root.aviso ?? {}

  const companyObj = (a.empresa ?? {}) as Record<string, unknown>
  const confidential = companyObj.confidencial === true
  const company = confidential ? null : typeof companyObj.denominacion === "string" && companyObj.denominacion ? companyObj.denominacion : null

  const locObj = (a.localizacion ?? {}) as Record<string, unknown>

  const rawDesc = typeof a.descripcion === "string" ? a.descripcion : ""
  const description = rawDesc ? stripTagsKeepBreaks(rawDesc) || null : null

  const seoUrl = typeof a.seoFriendlyUrl === "string" && a.seoFriendlyUrl ? a.seoFriendlyUrl : `/empleos/${id}.html`

  const name = (o: unknown): string | null => {
    const obj = o as Record<string, unknown> | undefined
    return obj && typeof obj.nombre === "string" && obj.nombre ? obj.nombre : null
  }

  return {
    id,
    title: typeof a.titulo === "string" && a.titulo ? a.titulo : "(untitled)",
    company,
    location: typeof locObj.detalle === "string" && locObj.detalle ? locObj.detalle : null,
    date: typeof a.fechaPublicacion === "string" && a.fechaPublicacion ? a.fechaPublicacion : null,
    url: `${SITE}${seoUrl}`,
    description,
    modality: name(a.modalidadTrabajo),
    employmentType: name(a.tipoTrabajo),
    contractType: name(a.tipoContratacion),
    seniority: name(a.nivelLaboral),
    applyUrl: `${SITE}${seoUrl}`,
  }
}

/**
 * Extract a job id from a raw id, a /empleos/...-<id>.html URL, or a bare id.
 * Bumeran/ZonaJobs posting URLs always end with "<id>.html", so prefer that
 * end-anchored form; fall back to a bare numeric id.
 */
export function normalizeId(input: string): string | null {
  const url = input.match(/(\d{6,})\.html(?:[\?#].*)?$/)
  if (url) return url[1]
  const bare = input.match(/^\d{6,}$/)
  if (bare) return input
  return null
}

/**
 * Map a --jobage (days) to the portal's posting-age filter value. Bumeran's
 * facets are fixed buckets ("Menor a 2 días", ..., "Menor a 1 semana", "Menor
 * a 1 mes"); we pick the smallest bucket that covers the requested days.
 */
const DATE_BUCKETS: Array<[number, string]> = [
  [2, "publicacion-menor-a-2-dias"],
  [3, "publicacion-menor-a-3-dias"],
  [4, "publicacion-menor-a-4-dias"],
  [5, "publicacion-menor-a-5-dias"],
  [6, "publicacion-menor-a-6-dias"],
  [7, "publicacion-menor-a-7-dias"],
  [15, "publicacion-menor-a-15-dias"],
  [Infinity, "publicacion-menor-a-1-mes"],
]

export function jobageFilter(days: number): string | null {
  if (!days || days <= 0 || days >= 9999) return null
  for (const [max, value] of DATE_BUCKETS) {
    if (days <= max) return value
  }
  return "publicacion-menor-a-1-mes"
}

// Argentine provinces -> search-filter semantic id, from the portal's own
// /api/provincias/1 response. Location filtering is province-level on this
// board; city-level detail needs a localidad id (not exposed here).
const PROVINCES: Array<[string, string]> = [
  ["buenos aires", "argentina|buenos-aires"],
  ["catamarca", "argentina|catamarca"],
  ["chaco", "argentina|chaco"],
  ["chubut", "argentina|chubut"],
  ["corrientes", "argentina|corrientes"],
  ["cordoba", "argentina|cordoba"],
  ["entre rios", "argentina|entre-rios"],
  ["formosa", "argentina|formosa"],
  ["jujuy", "argentina|jujuy"],
  ["la pampa", "argentina|la-pampa"],
  ["la rioja", "argentina|la-rioja"],
  ["mendoza", "argentina|mendoza"],
  ["misiones", "argentina|misiones"],
  ["neuquen", "argentina|neuquen"],
  ["rio negro", "argentina|rio-negro"],
  ["salta", "argentina|salta"],
  ["san juan", "argentina|san-juan"],
  ["san luis", "argentina|san-luis"],
  ["santa cruz", "argentina|santa-cruz"],
  ["santa fe", "argentina|santa-fe"],
  ["santiago del estero", "argentina|santiago-del-estero"],
  ["tierra del fuego", "argentina|tierra-del-fuego"],
  ["tucuman", "argentina|tucuman"],
]

// Common city / region aliases mapped to their province.
const CITY_ALIASES: Array<[string, string]> = [
  ["capital federal", "argentina|buenos-aires"],
  ["caba", "argentina|buenos-aires"],
  ["ciudad autonoma de buenos aires", "argentina|buenos-aires"],
  ["ciudad de buenos aires", "argentina|buenos-aires"],
  ["gran buenos aires", "argentina|buenos-aires"],
  ["gba", "argentina|buenos-aires"],
]

/**
 * Resolve a --location string to a provincia filter value. Accepts an explicit
 * semantic id ("argentina|buenos-aires"), a province name ("Buenos Aires",
 * "Córdoba"), or common aliases ("Capital Federal", "CABA"). Returns null when
 * the location can't be mapped — the caller skips the filter and warns.
 */
export function resolveLocation(location: string): string | null {
  const trimmed = location.trim()
  if (!trimmed) return null
  if (trimmed.includes("|")) return trimmed

  const norm = trimmed
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim()

  for (const [alias, value] of CITY_ALIASES) {
    if (norm === alias) return value
  }
  for (const [province, value] of PROVINCES) {
    if (norm === province) return value
  }
  return null
}
