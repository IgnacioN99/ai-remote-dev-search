// Data source: company career pages backed by three common ATS platforms.
// Greenhouse, Lever, and Ashby each expose a public JSON job-board API with no
// authentication. The CLI auto-detects which backend a company uses, or the
// backend can be pinned with --ats.

export const BACKENDS = ["greenhouse", "lever", "ashby"] as const
export type Backend = (typeof BACKENDS)[number]

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; company-careers-search/1.0)"

// URL builders --------------------------------------------------------------

export function greenhouseJobsUrl(company: string): string {
  return `https://boards-api.greenhouse.io/v1/boards/${encodeURIComponent(company)}/jobs`
}
export function greenhouseJobUrl(company: string, id: string): string {
  return `https://boards-api.greenhouse.io/v1/boards/${encodeURIComponent(company)}/jobs/${encodeURIComponent(id)}`
}
export function greenhouseContentJobsUrl(company: string): string {
  return `https://boards-api.greenhouse.io/v1/boards/${encodeURIComponent(company)}/jobs?content=true`
}
export function leverJobsUrl(company: string): string {
  return `https://api.lever.co/v0/postings/${encodeURIComponent(company)}?mode=json`
}
export function ashbyJobsUrl(company: string): string {
  return `https://api.ashbyhq.com/posting-api/job-board/${encodeURIComponent(company)}`
}

// Fetching ------------------------------------------------------------------

/** Fetch a JSON endpoint with exponential backoff on 429/5xx. Returns null on 404. */
export async function fetchJson(url: string): Promise<unknown | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: { "User-Agent": UA, Accept: "application/json" },
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
    if (!response.ok) throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    return (await response.json()) as unknown
  }
  throw new Error("Request failed after max retries")
}

// Result shapes -------------------------------------------------------------

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  description: string | null
}

export interface JobDetail extends JobCard {
  description: string | null
  applyUrl: string | null
}

// HTML helpers --------------------------------------------------------------

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

export function decodeHtmlEntities(text: string): string {
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

/** Strip tags and decode entities, preserving paragraph/line breaks. */
export function htmlToText(html: string): string {
  // Decode entities FIRST: Greenhouse returns entity-encoded HTML (&lt;div&gt;),
  // and stripping tags before decoding would leave the encoded tags intact.
  return decodeHtmlEntities(html)
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|ul|ol|div|h\d|tr)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

/** Title-case a company slug for display: "despegar" -> "Despegar". */
export function prettyCompany(slug: string): string {
  return slug
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ")
}

// Parsers (one per backend) -------------------------------------------------

export function parseGreenhouse(json: unknown, company: string): JobCard[] {
  const jobs = (json as { jobs?: unknown[] })?.jobs ?? []
  const out: JobCard[] = []
  for (const raw of jobs as Record<string, unknown>[]) {
    if (!raw || typeof raw !== "object") continue
    const location = (raw.location as { name?: string } | null)?.name ?? null
    out.push({
      id: String(raw.id ?? ""),
      title: String(raw.title ?? ""),
      company: raw.company_name ? String(raw.company_name) : company,
      location,
      date: raw.first_published ? String(raw.first_published) : raw.updated_at ? String(raw.updated_at) : null,
      url: String(raw.absolute_url ?? ""),
      description: typeof raw.content === "string" ? htmlToText(raw.content) : null,
    })
  }
  return out
}

export function parseLever(json: unknown, company: string): JobCard[] {
  if (!Array.isArray(json)) return []
  const out: JobCard[] = []
  for (const raw of json as Record<string, unknown>[]) {
    const cats = (raw.categories ?? {}) as { location?: string; allLocations?: string[] }
    out.push({
      id: String(raw.id ?? ""),
      title: String(raw.text ?? ""),
      company: prettyCompany(company),
      location: cats.location ?? cats.allLocations?.[0] ?? null,
      date: typeof raw.createdAt === "number" ? new Date(raw.createdAt).toISOString() : null,
      url: String(raw.hostedUrl ?? ""),
      description:
        typeof raw.descriptionPlain === "string"
          ? raw.descriptionPlain
          : typeof raw.description === "string"
            ? htmlToText(raw.description)
            : null,
    })
  }
  return out
}

export function parseAshby(json: unknown, company: string): JobCard[] {
  const jobs = (json as { jobs?: unknown[] })?.jobs ?? []
  const out: JobCard[] = []
  for (const raw of jobs as Record<string, unknown>[]) {
    if (!raw || typeof raw !== "object") continue
    out.push({
      id: String(raw.id ?? ""),
      title: String(raw.title ?? ""),
      company: prettyCompany(company),
      location: raw.location ? String(raw.location) : null,
      date: raw.publishedAt ? String(raw.publishedAt) : null,
      url: String(raw.jobUrl ?? ""),
      description: typeof raw.descriptionHtml === "string" ? htmlToText(raw.descriptionHtml) : null,
    })
  }
  return out
}

export function parseCards(json: unknown, backend: Backend, company: string): JobCard[] {
  if (backend === "greenhouse") return parseGreenhouse(json, company)
  if (backend === "lever") return parseLever(json, company)
  return parseAshby(json, company)
}

export function jobsUrlFor(backend: Backend, company: string): string {
  if (backend === "greenhouse") return greenhouseJobsUrl(company)
  if (backend === "lever") return leverJobsUrl(company)
  return ashbyJobsUrl(company)
}

// Backend detection ---------------------------------------------------------

/** Return the first backend whose board returns a recognizable, non-404 payload. */
export async function detectBackend(company: string): Promise<Backend | null> {
  // A company can leave an empty board behind after migrating ATS (e.g. Nubank's
  // empty Greenhouse board vs its populated Ashby one). Probe all three and pick
  // the board with the most jobs rather than the first one that returns 200.
  let best: Backend | null = null
  let bestCount = -1
  for (const backend of BACKENDS) {
    const json = await fetchJson(jobsUrlFor(backend, company))
    if (json == null) continue
    const jobs = backend === "lever" ? json : (json as { jobs?: unknown }).jobs
    const count = Array.isArray(jobs) ? jobs.length : -1
    if (count >= 0 && count > bestCount) {
      bestCount = count
      best = backend
    }
  }
  return best
}

// URL parsing for detail ----------------------------------------------------

export interface ParsedUrl {
  backend: Backend
  company: string
  id: string
}

export function parseJobUrl(url: string): ParsedUrl | null {
  let m = url.match(/job-boards\.greenhouse\.io\/([^/]+)\/jobs\/([^/?#]+)/)
  if (m) return { backend: "greenhouse", company: decodeURIComponent(m[1]), id: m[2] }
  m = url.match(/jobs\.lever\.co\/([^/]+)\/([^/?#]+)/)
  if (m) return { backend: "lever", company: decodeURIComponent(m[1]), id: m[2] }
  m = url.match(/jobs\.ashbyhq\.com\/([^/]+)\/([^/?#]+)/)
  if (m) return { backend: "ashby", company: decodeURIComponent(m[1]), id: m[2] }
  return null
}

// Date filtering ------------------------------------------------------------

/** True when the date string is missing/unparseable or falls within the last N days. */
export function withinDays(dateStr: string | null, days: number): boolean {
  if (!dateStr) return true
  const t = Date.parse(dateStr)
  if (isNaN(t)) return true
  return t >= Date.now() - days * 86400_000
}
