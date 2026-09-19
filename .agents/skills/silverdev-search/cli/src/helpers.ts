// Data source: Silver.dev's public /jobs page and /jobs/<slug> detail pages.
// The board is a client-side SPA, but it embeds a full schema.org graph in
// <script type="application/ld+json"> on every page:
//   - /jobs            → an ItemList of 44 JobPosting objects (all fields, full
//                        descriptions), plus the HTML renders one <article>
//                        card per job whose href carries the slug.
//   - /jobs/<slug>     → a single JobPosting object with the full description.
// We therefore prefer JSON-LD over markup parsing: it is richer, already
// escaped/decoded, and far less fragile than the Tailwind class soup in the HTML.
// The only thing JSON-LD lacks is the per-listing slug, which we recover from
// the HTML cards (they render in the same order as the ItemList positions).

export const SEARCH_URL = "https://silver.dev/jobs"
export const DETAIL_URL = "https://silver.dev/jobs"
export const PAGE_SIZE = 20

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; silverdev-search-cli/1.0)"

/** Fetch HTML with exponential backoff on 429/5xx. Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
      },
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
    if (response.status === 404) return ""
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response.text()
  }
  throw new Error("Request failed after max retries")
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Public search-result shape (no heavy description field). */
export interface JobCard {
  id: string // slug, e.g. "agora-senior-full-stack-engineer"
  title: string
  company: string | null
  location: string | null // applicant country (e.g. "Argentina")
  date: string | null // YYYY-MM-DD
  epoch: number | null // ms since epoch, for --jobage filtering
  url: string
  salary: string | null // human label, e.g. "$150K–$200K"
  salaryMin: number | null
  salaryMax: number | null
  salaryCurrency: string | null
  employmentType: string | null
  industry: string | null
  occupationalCategory: string | null
  applyUrl: string | null // Ashby application link
}

/** Internal job used for query/age filtering (carries the description). */
export interface SilverJob extends JobCard {
  description: string | null
}

export interface JobDetail extends JobCard {
  description: string | null
}

// ---------------------------------------------------------------------------
// Low-level JSON / text helpers
// ---------------------------------------------------------------------------

interface JsonObj {
  [k: string]: unknown
}

function isObj(v: unknown): v is JsonObj {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

function str(v: unknown): string | null {
  return typeof v === "string" && v ? v : null
}

/** Decode the handful of HTML entities that appear in the markup. */
export function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, " ")
}

/** Trim and collapse internal whitespace of a title string. */
function cleanTitle(v: unknown): string {
  const s = str(v)
  return s ? s.replace(/ /g, " ").replace(/\s+/g, " ").trim() : ""
}

/** For matching: lowercase, trim, collapse whitespace. */
function normalize(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim()
}

/** Pull the company out of a "Company - Role" title. */
export function companyFromTitle(title: string): string | null {
  const sep = title.indexOf(" - ")
  return sep >= 0 ? title.slice(0, sep).trim() : null
}

/** Extract every <script type="application/ld+json"> block as parsed JSON. */
export function extractJsonLd(html: string): JsonObj[] {
  const blocks = [...html.matchAll(/<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)]
  const out: JsonObj[] = []
  for (const b of blocks) {
    try {
      const parsed = JSON.parse(b[1].trim())
      if (isObj(parsed)) out.push(parsed)
    } catch {
      // malformed block — skip; other blocks may still parse
    }
  }
  return out
}

// ---------------------------------------------------------------------------
// Field extraction from a JobPosting JSON-LD object
// ---------------------------------------------------------------------------

function postingFields(item: JsonObj): Partial<SilverJob> {
  const baseSalary = item.baseSalary
  const value = isObj(baseSalary) ? baseSalary.value : undefined
  const qv = isObj(value) ? value : undefined
  const min = qv && typeof qv.minValue === "number" ? qv.minValue : null
  const max = qv && typeof qv.maxValue === "number" ? qv.maxValue : null
  const currency = isObj(baseSalary) ? str(baseSalary.currency) : null

  const locReq = isObj(item.applicantLocationRequirements) ? item.applicantLocationRequirements : undefined
  const contact = isObj(item.applicationContact) ? item.applicationContact : undefined

  return {
    company: companyFromTitle(cleanTitle(item.title)),
    location: locReq ? str(locReq.name) : null,
    date: isoDate(item.datePosted),
    epoch: isoEpoch(item.datePosted),
    salary: salaryLabel(baseSalary),
    salaryMin: min,
    salaryMax: max,
    salaryCurrency: currency,
    employmentType: str(item.employmentType),
    industry: str(item.industry),
    occupationalCategory: str(item.occupationalCategory),
    applyUrl: contact ? str(contact.url) : null,
    description: typeof item.description === "string" ? item.description.replace(/ /g, " ").trim() || null : null,
  }
}

export function isoDate(datePosted: unknown): string | null {
  if (typeof datePosted !== "string") return null
  const m = datePosted.match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : null
}

export function isoEpoch(datePosted: unknown): number | null {
  if (typeof datePosted !== "string") return null
  const t = Date.parse(datePosted)
  return isNaN(t) ? null : t
}

function fmtUsdK(n: number): string {
  return `$${Math.round(n / 1000)}K`
}

function money(n: number, currency: string | null): string {
  return currency === "USD" ? fmtUsdK(n) : `${currency ? currency + " " : "$"}${n.toLocaleString()}`
}

/** Format baseSalary as a short human label: "$150K–$200K", "$100K+", or null. */
export function salaryLabel(baseSalary: unknown): string | null {
  if (!isObj(baseSalary)) return null
  const currency = str(baseSalary.currency)
  const value = baseSalary.value
  const qv = isObj(value) ? value : undefined
  const min = qv && typeof qv.minValue === "number" ? qv.minValue : null
  const max = qv && typeof qv.maxValue === "number" ? qv.maxValue : null
  if (min !== null && max !== null) return `${money(min, currency)}–${money(max, currency)}`
  if (min !== null) return `${money(min, currency)}+`
  if (max !== null) return `up to ${money(max, currency)}`
  return null
}

// ---------------------------------------------------------------------------
// Page parsers
// ---------------------------------------------------------------------------

function slugFromUrl(url: string): string {
  return url.split("/").pop() || ""
}

/**
 * Parse the /jobs page. Uses the embedded ItemList JSON-LD as the source of
 * truth and recovers each slug from the HTML cards (same render order as the
 * ItemList positions). One malformed card or block never breaks the rest.
 */
export function parseSearchPage(html: string): SilverJob[] {
  const blocks = extractJsonLd(html)
  const list = blocks.find((b) => b["@type"] === "ItemList")
  if (!list || !Array.isArray(list.itemListElement)) return []

  // (slug, title) pairs from the HTML cards, in render order.
  const cards = [...html.matchAll(/<article><a href="\/jobs\/([^"]+)">[\s\S]*?<h2>([\s\S]*?)<\/h2>/gi)].map((m) => ({
    slug: m[1],
    title: cleanTitle(decodeHtmlEntities(m[2])),
  }))

  const jobs: SilverJob[] = []
  for (let i = 0; i < list.itemListElement.length; i++) {
    const entry = list.itemListElement[i]
    const item = isObj(entry) && isObj(entry.item) ? entry.item : undefined
    if (!item) continue
    const title = cleanTitle(item.title)
    if (!title) continue

    // Match by normalized title; fall back to same-position card.
    const norm = normalize(title)
    let card = cards.find((c) => normalize(c.title) === norm)
    if (!card && i < cards.length) card = cards[i]
    if (!card) continue
    const slug = card.slug || slugFromUrl(card.title)

    jobs.push({
      id: slug,
      title,
      ...postingFields(item),
      url: `${DETAIL_URL}/${slug}`,
    } as SilverJob)
  }
  return jobs
}

/** Parse a /jobs/<slug> detail page: a single JobPosting JSON-LD object. */
export function parseDetailPage(html: string, id: string): JobDetail | null {
  const blocks = extractJsonLd(html)
  const post = blocks.find((b) => b["@type"] === "JobPosting")
  if (!post) return null
  const title = cleanTitle(post.title) || "(untitled)"
  return {
    id,
    title,
    ...postingFields(post),
    url: `${DETAIL_URL}/${id}`,
  } as JobDetail
}

// ---------------------------------------------------------------------------
// Search-time filtering
// ---------------------------------------------------------------------------

/** Tokenize a query into lowercase words. */
function queryTokens(query: string): string[] {
  return query.toLowerCase().match(/[\w.#+]+(?:[\w.#+ -]*[\w.#+]+)?/g)?.map((t) => t.trim()) ?? []
}

/** Score a job against a query: title matches weigh most, then company/location. */
export function scoreQuery(job: SilverJob, query: string): number {
  const tokens = queryTokens(query)
  if (tokens.length === 0) return 1 // empty query matches everything
  const title = normalize(job.title)
  const company = normalize(job.company || "")
  const location = normalize(job.location || "")
  const category = normalize(job.occupationalCategory || "")
  const desc = normalize(job.description || "")
  let score = 0
  for (const t of tokens) {
    if (title.includes(t)) score += 3
    if (category.includes(t)) score += 2
    if (company.includes(t)) score += 2
    if (location.includes(t)) score += 1
    if (desc.includes(t)) score += 1
  }
  return score
}

export function matchesQuery(job: SilverJob, query: string): boolean {
  return scoreQuery(job, query) > 0
}

export function withinDays(job: SilverJob, days: number | null): boolean {
  if (days === null || days <= 0 || days >= 9999) return true
  if (job.epoch === null) return true // can't tell age; don't drop it
  const cutoff = Date.now() - days * 86400 * 1000
  return job.epoch >= cutoff
}

export function paginate(jobs: SilverJob[], page: number): SilverJob[] {
  const p = Math.max(1, page)
  const start = (p - 1) * PAGE_SIZE
  return jobs.slice(start, start + PAGE_SIZE)
}

/** Drop the heavy internal fields to produce the public search-result shape. */
export function searchResults(jobs: SilverJob[]): JobCard[] {
  return jobs.map(({ description: _d, ...card }) => card)
}
