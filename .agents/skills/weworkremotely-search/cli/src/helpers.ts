// Data source: We Work Remotely's server-rendered Rails pages (global, English).
// - Search: GET /remote-jobs/search?term=<query> — returns every match on a single
//   page, grouped by category, as <li class=" new-listing-container "> cards.
//   The search endpoint is NOT paginated (a `page` param is ignored) and there is
//   no search RSS (`.rss` returns 406), so we parse the HTML.
// - Detail: GET /remote-jobs/<slug> — server-rendered listing with a sidebar
//   ("About the job") plus a (malformed) JSON-LD JobPosting block we enrich from.
// We parse both with regex; the markup is shallow and stable and the class anchors
// are versioned in url-reference.md.

export const SEARCH_URL = "https://weworkremotely.com/remote-jobs/search"
export const DETAIL_URL = "https://weworkremotely.com/remote-jobs"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 weworkremotely-search-cli/1.0"

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
  postedOn: string | null // relative, e.g. "4 days ago"
  applyBefore: string | null // deadline, e.g. "Sep 13th, 2026"
  employmentType: string | null
  category: string | null
  region: string | null
  skills: string | null
  salary: string | null
  applyUrl: string | null
  companyUrl: string | null
}

/**
 * Extract the inner HTML of a <div> identified by a CSS class name, correctly
 * handling nested <div> elements by tracking tag depth.
 */
export function extractDivContent(html: string, className: string): string | null {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const openRe = new RegExp(`<div[^>]*class="[^"]*${escaped}[^"]*"[^>]*>`, "i")
  const open = openRe.exec(html)
  if (!open) return null

  let i = open.index + open[0].length
  let depth = 1

  while (depth > 0 && i < html.length) {
    const nextOpen = html.indexOf("<div", i)
    const nextClose = html.indexOf("</div>", i)

    if (nextClose === -1) return null

    if (nextOpen !== -1 && nextOpen < nextClose) {
      depth++
      i = nextOpen + 4
    } else {
      depth--
      i = nextClose + 6
    }
  }

  return html.slice(open.index + open[0].length, i - 6)
}

/**
 * Convert a Unicode code point to a string. Uses `fromCodePoint` so
 * supplementary-plane code points (emoji) decode correctly; out-of-range values
 * are dropped instead of throwing.
 */
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
    .replace(/&nbsp;/g, " ")
    .replace(/&rsquo;/g, "’")
    .replace(/&lsquo;/g, "‘")
    .replace(/&ldquo;/g, "“")
    .replace(/&rdquo;/g, "”")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&hellip;/g, "…")
    .replace(/&middot;/g, "·")
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

function clean(html: string): string {
  return decodeHtmlEntities(stripTags(html))
}

/**
 * Convert We Work Remotely's relative date strings ("4d", "3w", "1mo", "today",
 * "yesterday", "4 hours ago") into an ISO yyyy-mm-dd date computed from today.
 * Returns the original string if it cannot be parsed.
 */
export function relativeDateToISO(text: string): string {
  const s = text.trim().toLowerCase()
  const today = new Date()
  let days = 0

  const m = s.match(/^(\d+)\s*d\b/)
  if (m) days = parseInt(m[1], 10)
  else if (s.match(/^(\d+)\s*w\b/)) days = parseInt(s.match(/^(\d+)\s*w\b/)![1], 10) * 7
  else if (s.match(/^(\d+)\s*mo\b/)) days = parseInt(s.match(/^(\d+)\s*mo\b/)![1], 10) * 30
  else if (s.match(/^(\d+)\s*y\b/)) days = parseInt(s.match(/^(\d+)\s*y\b/)![1], 10) * 365
  else if (s === "today") days = 0
  else if (s === "yesterday") days = 1
  else if (s.includes("hour")) days = 0
  else if (s.includes("minute") || s.includes("just now")) days = 0
  else if (s.match(/^(\d+)\s*days?\b/)) days = parseInt(s.match(/^(\d+)\s*days?\b/)![1], 10)
  else return text // unparseable — keep the raw string

  const d = new Date(today.getTime() - days * 86400000)
  return d.toISOString().slice(0, 10)
}

/**
 * Region chips on WWR listing cards (e.g. "Anywhere in the World",
 * "North America Only", "🇺🇸 United States of America") carry the work region for
 * a remote role. Job-type and salary chips ("Full-Time", "$130k+") do not. Detect
 * the region chip with a curated keyword list; fall back to the card's
 * company-headquarters line (which WWR mixes with the work location).
 */
const REGION_PAT =
  /anywhere in the world|north america|south america|central america|latin america|americas|europe|european|emea|asia|apac|oceania|australia|new zealand|middle east|africa|usa only|\bus only\b|\busa\b|united states|\bcanada\b|worldwide|\bglobal\b|^\s*remote\s*$/i

function detectLocation(categories: string[], headquarters: string | null): string | null {
  for (const chip of categories) {
    const t = chip.trim()
    if (REGION_PAT.test(t)) return t
  }
  return headquarters && headquarters.trim() ? headquarters.trim() : null
}

function listCategories(cardHtml: string): string[] {
  return Array.from(
    cardHtml.matchAll(/new-listing__categories__category[^>]*>\s*(?:<i[^>]*><\/i>\s*)?([^<]+?)\s*</gi),
    (m) => m[1].trim(),
  ).filter(Boolean)
}

/** Extract the slug from a /remote-jobs/<slug> URL/path, or accept a bare slug. */
export function slugFromUrl(input: string): string | null {
  // Prefer the segment after /remote-jobs/ when present (drop query/fragment).
  const m = input.match(/\/remote-jobs\/([a-z0-9]+(?:-[a-z0-9]+)*)/i)
  if (m) return m[1].toLowerCase()
  // Otherwise treat the trimmed string as a bare kebab-case slug.
  const bare = input.trim().replace(/\/+$/, "")
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/i.test(bare) ? bare.toLowerCase() : null
}

/**
 * Parse the search response: <li class=" new-listing-container "> cards. We split
 * on the container class and parse each chunk independently so one malformed card
 * cannot break the rest. Cards whose link points at /listing_ads/... (promoted
 * placements) are skipped — only real /remote-jobs/<slug> listings are kept.
 */
export function parseJobCards(html: string): JobCard[] {
  const results: JobCard[] = []
  const chunks = html.split(/<li class="\s*new-listing-container/).slice(1)
  const seen = new Set<string>()

  for (const chunk of chunks) {
    const link = chunk.match(/href="(\/remote-jobs\/[^"?]+)"/i)
    if (!link) continue
    const path = link[1]
    const slug = slugFromUrl(path)
    if (!slug || seen.has(slug)) continue
    seen.add(slug)

    const titleMatch = chunk.match(/new-listing__header__title__text">([\s\S]*?)<\/span>/i)
    if (!titleMatch) continue
    const title = clean(titleMatch[1])
    if (!title) continue

    // Company name: text of the company-name <p>, before any icon <img>.
    const companyMatch = chunk.match(/class="new-listing__company-name">\s*([^<]*?)\s*</i)
    const company = companyMatch ? decodeHtmlEntities(companyMatch[1]).trim() || null : null

    const hqMatch = chunk.match(/class="new-listing__company-headquarters[^"]*">\s*([^<]*?)\s*</i)
    const headquarters = hqMatch ? decodeHtmlEntities(hqMatch[1]).trim() || null : null

    const dateMatch = chunk.match(/new-listing__header__icons__date">\s*([^<]+?)\s*</i)
    const rawDate = dateMatch ? dateMatch[1].trim() : null

    const location = detectLocation(listCategories(chunk), headquarters)

    results.push({
      id: slug,
      title,
      company,
      location,
      date: rawDate ? relativeDateToISO(rawDate) : null,
      url: `https://weworkremotely.com/remote-jobs/${slug}`,
    })
  }

  return results
}

/** Read the "All jobs" result-count badge from the search page (may be absent). */
export function parseTotalCount(html: string): number | null {
  const m = html.match(/data-job-filter-option="all"[^>]*>[\s\S]*?data-job-filter-count>(\d+)</i)
  return m ? parseInt(m[1], 10) : null
}

/** Read the top-level string fields out of the (malformed) JSON-LD JobPosting block. */
function jsonldField(script: string, key: string): string | null {
  const m = script.match(new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"`))
  if (!m) return null
  return decodeHtmlEntities(m[1].replace(/\\"/g, '"').replace(/\\\\/g, "\\"))
}

/** Read the JSON-LD JobPosting script block (present on detail pages). */
function jsonldScript(html: string): string | null {
  const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/i)
  return m ? m[1] : null
}

/** Normalize WWR's "2026-08-14 10:13:03 UTC" datePosted into yyyy-mm-dd. */
function normalizeWwrDate(value: string | null): string | null {
  if (!value) return null
  const m = value.match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : value
}

/**
 * Parse the single-job detail page. The rendered HTML is the source of truth for
 * human-readable fields; the JSON-LD JobPosting block enriches posted/validThrough
 * and salary (its string values are HTML-escaped and may contain raw newlines, so
 * strict JSON.parse would fail — we read individual fields with regex instead).
 */
export function parseJobDetail(html: string, slug: string): JobDetail {
  const script = jsonldScript(html)

  const titleMatch = html.match(/class="lis-container__header__hero__company-info__title"[^>]*>([\s\S]*?)<\/h1>/i)
  const title = titleMatch ? clean(titleMatch[1]) : "(untitled)"

  // Company: sidebar company-details <h3> (may contain an <img> icon after the text).
  const companyMatch = html.match(
    /lis-container__job__sidebar__companyDetails__info__title"[^>]*>\s*<h3>\s*([^<]*?)\s*</i,
  )
  const company = companyMatch ? decodeHtmlEntities(companyMatch[1]).trim() || null : null

  // "About the job" sidebar items: Posted on / Apply before / Job type / Category / Region / Skills.
  const postedMatch = html.match(/Posted on\s*<span[^>]*>\s*([^<]+?)\s*<\/span>/i)
  const postedOn = postedMatch ? postedMatch[1].trim() : null
  const applyBeforeMatch = html.match(/Apply before\s*<span[^>]*>\s*([^<]+?)\s*<\/span>/i)
  const applyBefore = applyBeforeMatch ? applyBeforeMatch[1].trim() : null

  const jobTypeMatch = html.match(/class="box box--jobType"[^>]*>\s*(?:<i[^>]*><\/i>\s*)?([^<]+?)\s*<\/span>/i)
  const employmentType = jobTypeMatch ? jobTypeMatch[1].trim() || null : null

  const categoryMatch = html.match(/class="box box--blue"[^>]*>\s*([^<]+?)\s*<\/span>/i)
  const category = categoryMatch ? categoryMatch[1].trim() || null : null

  const regionMatch = html.match(/class="box[^"]*box--region[^"]*"[^>]*>\s*([^<]+?)\s*<\/span>/i)
  const region = regionMatch ? regionMatch[1].trim() || null : null

  const skillsMatch = html.match(/<li[^>]*>\s*Skills\s*<([\s\S]*?)<\/li>/i)
  const skills = skillsMatch
    ? Array.from(
        skillsMatch[1].matchAll(/class="box[^"]*"[^>]*>\s*([^<]+?)\s*<\/span>/gi),
        (m) => m[1].trim(),
      ).join(", ") || null
    : null

  const applyMatch = html.match(/<a[^>]+id="job-cta-alt"[^>]*href="([^"]+)"/i)
  const applyUrl = applyMatch ? decodeHtmlEntities(applyMatch[1]).split("?")[0] : null

  const companyUrlMatch = html.match(/lis-container__job__sidebar__companyDetails__info__link"[^>]*href="([^"]+)"/i)
  const companyUrl = companyUrlMatch ? decodeHtmlEntities(companyUrlMatch[1]).split("?")[0] : null

  // Description block: strip tags while preserving paragraph/line breaks.
  let description: string | null = null
  const descHtml = extractDivContent(html, "lis-container__job__content__description")
  if (descHtml !== null && descHtml !== "") {
    const withBreaks = descHtml
      .replace(/<\s*br\s*\/?>/gi, "\n")
      .replace(/<\/(p|li|ul|ol|div|h[1-6])>/gi, "\n")
    description = decodeHtmlEntities(stripTags(withBreaks)).replace(/\n{3,}/g, "\n\n").trim() || null
  }

  // Enrichment from the JSON-LD block.
  const jsonDate = normalizeWwrDate(jsonldField(script ?? "", "datePosted"))
  const jsonValid = normalizeWwrDate(jsonldField(script ?? "", "validThrough"))
  const jsonJobType = jsonldField(script ?? "", "employmentType")
  const jsonSalary = (() => {
    if (!script) return null
    const bs = script.match(/"baseSalary"\s*:\s*\{([\s\S]*?)\}\s*,/)
    if (!bs) return null
    const currency = script.match(/"currency"\s*:\s*"([^"]+)"/)
    const minV = script.match(/"minValue"\s*:\s*"(\d+[^"]*)"/)
    const maxV = script.match(/"maxValue"\s*:\s*"(\d+[^"]*)"/)
    const unit = script.match(/"unitText"\s*:\s*"([^"]+)"/)
    const cur = currency ? currency[1] : null
    const mn = minV ? minV[1] : null
    const mx = maxV ? maxV[1] : null
    const un = unit ? unit[1] : null
    if (cur === null && mn === null && mx === null) return null
    const both = mn !== null && mx !== null
    const zero = (mn === "0" && mx === "0") || (mn === null && mx === null)
    if (both && zero) return null // WWR emits 0/0 for unspecified salary
    const range = mn && mx ? `${mn}–${mx}` : mn ?? mx
    return [cur, range, un && un !== "YEAR" ? un : null].filter(Boolean).join(" ") || null
  })()

  const date = jsonDate ?? (postedOn ? relativeDateToISO(postedOn) : null)
  const applyBeforeFinal = applyBefore ?? jsonValid

  return {
    id: slug,
    title,
    company,
    location: region,
    date,
    url: `https://weworkremotely.com/remote-jobs/${slug}`,
    description,
    postedOn,
    applyBefore: applyBeforeFinal,
    employmentType: employmentType ?? jsonJobType,
    category,
    region,
    skills,
    salary: jsonSalary,
    applyUrl,
    companyUrl,
  }
}

/**
 * Map a job-age in days to WWR's search `sort` dropdown values. WWR only offers
 * "Past 24 Hours", "Past Week", and "Past 2 Weeks"; returns null for anything older.
 */
export function jobageToSort(days: number): string | null {
  if (days <= 0) return null
  if (days <= 1) return "Past 24 Hours"
  if (days <= 7) return "Past Week"
  if (days <= 14) return "Past 2 Weeks"
  return null
}
