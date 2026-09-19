// Data source: RemoteOK's public JSON API (https://remoteok.com/api). No
// authentication or API key required. The response is a JSON array whose first
// element is a metadata/legal object; every following element is a complete job
// object (the API already includes the full description), so both `search` and
// `detail` consume the same single fetch.
//
// Personal use only — RemoteOK's API terms require an attribution link-back to
// RemoteOK and mention traffic expectations; keep volume low and do not use it
// commercially or for bulk data collection. Run it on your own responsibility.

export const API_URL = "https://remoteok.com/api"

export const PAGE_SIZE = 50

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

// A browser-like User-Agent; the API has been observed to gate on it.
const UA = "Mozilla/5.0 (compatible; remoteok-search-cli/1.0)"

/** Fetch the RemoteOK API with exponential backoff on 429/5xx. Returns null on a 404. */
export async function jsonFetch(url: string): Promise<unknown> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "application/json,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(20000),
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
    return response.json()
  }
  throw new Error("Request failed after max retries")
}

export interface RemoteOkJob {
  id: string
  slug: string
  position: string
  company: string | null
  location: string | null
  date: string | null // ISO 8601, e.g. "2026-08-17T17:14:35+00:00"
  epoch: number | null
  tags: string[]
  description: string | null // HTML
  url: string
  applyUrl: string | null
  salaryMin: number | null
  salaryMax: number | null
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  salaryMin: number | null
  salaryMax: number | null
  tags: string[] | null
  applyUrl: string | null
}

export interface JobDetail extends JobCard {
  slug: string | null
  epoch: number | null
  description: string | null
}

/** Normalize a salary value: RemoteOK reports an unset salary as 0. */
function toNullableSalary(v: unknown): number | null {
  if (typeof v !== "number" || !isFinite(v) || v === 0) return null
  return v
}

/** Normalize the posting URL — the API emits "https://remoteOK.com/..." (mixed case). */
function normalizeUrl(raw: unknown, slug: string): string {
  const u = typeof raw === "string" ? raw : ""
  const lower = u.toLowerCase()
  if (lower.startsWith("https://remoteok.com/") || lower.startsWith("http://remoteok.com/")) {
    return lower
  }
  return `https://remoteok.com/remote-jobs/${slug}`
}

/** Clean a location string: RemoteOK often appends a trailing ", " or space. */
function cleanLocation(raw: unknown): string | null {
  if (typeof raw !== "string") return null
  const s = raw.trim().replace(/,+\s*$/, "").trim()
  return cleanText(s)
}

/** Non-empty string field, with HTML entities and mojibake repaired. */
function str(v: unknown): string | null {
  if (typeof v !== "string") return null
  const s = cleanText(v.trim())
  return s || null
}

/** Decode HTML entities, then repair RemoteOK's double-encoded UTF-8 mojibake. */
function cleanText(s: string): string {
  return fixMojibake(decodeHtmlEntities(s))
}

/**
 * Parse the API response array into job cards. The first element is a
 * metadata/legal object (no `id`) and is skipped; anything without an `id` is
 * skipped defensively so one malformed element cannot break the rest.
 */
export function parseJobs(payload: unknown): RemoteOkJob[] {
  if (!Array.isArray(payload)) return []
  const jobs: RemoteOkJob[] = []
  for (const raw of payload) {
    if (typeof raw !== "object" || raw === null) continue
    const rec = raw as Record<string, unknown>
    const id = str(rec["id"])
    const slug = str(rec["slug"])
    if (!id) continue // skips the leading metadata/legal object

    const title = str(rec["position"]) ?? "(untitled)"
    const company = str(rec["company"])
    const location = cleanLocation(rec["location"])
    const date = str(rec["date"])
    const epoch = typeof rec["epoch"] === "number" && isFinite(rec["epoch"]) ? rec["epoch"] : null
    const tags = Array.isArray(rec["tags"])
      ? rec["tags"].filter((t): t is string => typeof t === "string").map(cleanText)
      : []
    const description = str(rec["description"])
    const applyUrlRaw = str(rec["apply_url"])
    const applyUrl = applyUrlRaw ? applyUrlRaw.toLowerCase() : null

    jobs.push({
      id,
      slug: slug ?? id,
      position: title,
      company,
      location,
      date,
      epoch,
      tags,
      description,
      url: normalizeUrl(rec["url"], slug ?? id),
      applyUrl,
      salaryMin: toNullableSalary(rec["salary_min"]),
      salaryMax: toNullableSalary(rec["salary_max"]),
    })
  }
  return jobs
}

function toCard(j: RemoteOkJob): JobCard {
  return {
    id: j.id,
    title: j.position,
    company: j.company,
    location: j.location,
    date: j.date,
    url: j.url,
    salaryMin: j.salaryMin,
    salaryMax: j.salaryMax,
    tags: j.tags.length ? j.tags : null,
    applyUrl: j.applyUrl,
  }
}

/**
 * Convert a Unicode code point to a string, using `fromCodePoint` so
 * supplementary-plane code points (emoji) decode correctly.
 */
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

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/[ \t]+/g, " ").replace(/ ?\n ?/g, "\n")
}

// RemoteOK descriptions are riddled with double-encoded UTF-8: the original
// UTF-8 bytes were read as Windows-1252 and then re-encoded to UTF-8. E.g. an
// em dash U+2014 (bytes E2 80 94) surfaces as the three characters â € " .
// Fix the observed sequences (three-byte E2/EF cases via a table, plus the
// generic two-byte Â/Ã cases) so descriptions read correctly.
const MOJIBAKE_PAIRS: Array<[string, string]> = [
  ["â", "–"], // en dash –
  ["â", "—"], // em dash —
  ["â", "‘"], // left single quote '
  ["â", "’"], // right single quote '
  ["â", "“"], // left double quote "
  ["â", "”"], // right double quote "
  ["â¢", "•"], // bullet •
  ["â¦", "…"], // ellipsis …
  ["âº", "›"], // single right-pointing angle quote ›
  ["â¯", " "], // narrow no-break space → space
  ["â", "→"], // rightwards arrow →
  ["â ", ""], // word joiner → drop
  ["â", "✓"], // check mark ✓
  ["â¨", "✨"], // sparkles ✨
  ["â¡", "⚡"], // high voltage ⚡
  ["ï·", "•"], // private-use bullet → •
]

/** Repair RemoteOK's double-encoded UTF-8 mojibake. */
export function fixMojibake(text: string): string {
  let out = text
  for (const [from, to] of MOJIBAKE_PAIRS) {
    out = out.split(from).join(to)
  }
  // Generic two-byte cases: "Â <byte>" → U+00<byte>, "Ã <byte>" → U+00C0+(byte-0x80).
  out = out.replace(/Â[-¿]/g, (m) => String.fromCodePoint(m.charCodeAt(1)))
  out = out.replace(/Ã[-¿]/g, (m) =>
    String.fromCodePoint(0xc0 + (m.charCodeAt(1) - 0x80)),
  )
  return out
}

/** Convert the HTML description to readable text with paragraph breaks preserved. */
export function htmlToText(html: string): string {
  const withBreaks = html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|ul|ol|h\d|tr)>/gi, "\n")
  return fixMojibake(decodeHtmlEntities(stripTags(withBreaks)))
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

// Common English stopwords, dropped from the query before matching so phrases
// like "ruby on rails" or "senior in Berlin" don't require the filler word to
// appear verbatim in every posting.
const STOPWORDS = new Set([
  "a", "an", "and", "any", "as", "at", "by", "for", "from", "in", "into",
  "is", "it", "of", "on", "or", "our", "the", "to", "with", "we", "you",
])

/** Non-stopword query tokens, lower-cased. */
export function queryTokens(query: string): string[] {
  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .filter((t) => !STOPWORDS.has(t))
}

/**
 * Relevance score for a job against a client-side query. The public API returns
 * the full listing with no query parameter, so we match each non-stopword token
 * wherever it appears and weight the strongest signals highest:
 * title (+3) > tags (+2) / company (+2) > location (+1) / description (+1).
 * Returns 0 for no match. A job matching in any field is a candidate; the
 * search command ranks candidates by score (description-only matches rank below
 * title/tag matches) so the closest postings surface first.
 */
export function scoreQuery(j: RemoteOkJob, query: string): number {
  const tokens = queryTokens(query)
  if (tokens.length === 0) return 1 // empty query matches everything
  const title = j.position.toLowerCase()
  const tags = j.tags.join(" ").toLowerCase()
  const company = (j.company || "").toLowerCase()
  const location = (j.location || "").toLowerCase()
  const desc = j.description ? htmlToText(j.description).toLowerCase() : ""
  let score = 0
  for (const t of tokens) {
    if (title.includes(t)) score += 3
    if (tags.includes(t)) score += 2
    if (company.includes(t)) score += 2
    if (location.includes(t)) score += 1
    if (desc.includes(t)) score += 1
  }
  return score
}

/** Whether a job matches a query at all (score > 0). */
export function matchesQuery(j: RemoteOkJob, query: string): boolean {
  return scoreQuery(j, query) > 0
}

/** Client-side recency filter: keep postings within `days` (null = all ages). */
export function withinDays(j: RemoteOkJob, days: number | null): boolean {
  if (days === null || days <= 0 || days >= 9999) return true
  if (j.epoch === null) return true // can't tell age; don't drop it
  const cutoff = Math.floor(Date.now() / 1000) - days * 86400
  return j.epoch >= cutoff
}

/** Split a full result set into the requested 1-indexed page (client-side). */
export function paginate(jobs: RemoteOkJob[], page: number): RemoteOkJob[] {
  const p = Math.max(1, page)
  const start = (p - 1) * PAGE_SIZE
  return jobs.slice(start, start + PAGE_SIZE)
}

/**
 * Locate a single job by id (numeric string), slug, or a full posting URL.
 * Used by the `detail` command.
 */
export function findJob(jobs: RemoteOkJob[], input: string): RemoteOkJob | null {
  // Strip any query string / fragment and trailing slashes so a posting URL
  // (possibly with ?utm=... tracking) still resolves.
  const clean = input.trim().split(/[?#]/, 1)[0].replace(/\/+$/, "")
  if (!clean) return null
  for (const j of jobs) {
    if (j.id === clean) return j
    if (j.slug === clean) return j
    if (j.url === clean) return j
    if (j.slug && clean.endsWith(`/${j.slug}`)) return j
  }
  return null
}

export function searchResults(jobs: RemoteOkJob[]): JobCard[] {
  return jobs.map(toCard)
}

export function detailResult(j: RemoteOkJob): JobDetail {
  return {
    ...toCard(j),
    slug: j.slug,
    epoch: j.epoch,
    description: j.description ? htmlToText(j.description) : null,
  }
}
