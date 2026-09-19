// Data source: Computrabajo Argentina public search/detail HTML pages
// (https://ar.computrabajo.com). Server-rendered HTML — no API key, no auth.
// We parse the shallow, stable markup with regex; a full DOM parser is
// unnecessary. One malformed card must not break the rest, so we split the
// results page into per-card chunks and parse each independently.

export const SITE = "https://ar.computrabajo.com"
export const SEARCH_PATH = "/trabajo-de-" // + slugified query
export const OFFER_PATH = "/ofertas-de-trabajo/" // + offer slug + "-" + id

// Computrabajo's detail URLs require the title slug (there is no ID-only
// route — bare-ID URLs 404). `search` therefore records every result's
// id -> url here so a later `detail <id>` can resolve the URL without
// re-searching. Best-effort; the file is gitignored.
const CACHE_FILE = new URL("../url-cache.json", import.meta.url)

export async function loadUrlCache(): Promise<Record<string, string>> {
  try {
    const f = Bun.file(CACHE_FILE.pathname)
    if (await f.exists()) {
      const text = await f.text()
      return text.trim() ? (JSON.parse(text) as Record<string, string>) : {}
    }
    return {}
  } catch {
    return {}
  }
}

export function saveUrlCache(cache: Record<string, string>): void {
  try {
    // Best-effort fire-and-forget — never fail a search because the cache
    // could not be written.
    Bun.write(CACHE_FILE.pathname, JSON.stringify(cache))
  } catch {
    // ignore
  }
}

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; computrabajo-search-cli/1.0)"

/** Fetch HTML with exponential backoff on 429/5xx. Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
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

/**
 * Slugify a free-text query into Computrabajo's URL path form.
 * Computrabajo lowercases, strips accents, and joins words with hyphens
 * (an accented slug like /trabajo-de-administraci%C3%B3n 301-redirects to
 * the accent-stripped /trabajo-de-administracion).
 */
export function slugify(query: string): string {
  return query
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // strip combining accents
    .replace(/[^a-z0-9]+/g, "-") // spaces/punctuation -> hyphen
    .replace(/^-+|-+$/g, "") // trim leading/trailing hyphens
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
  salary: string | null
  contractType: string | null
  schedule: string | null
  modality: string | null
  requirements: string | null
  keywords: string | null
  applyUrl: string | null
}

/**
 * Extract the inner HTML of a <div> whose opening tag matches `openRe`,
 * correctly handling nested <div> elements by tracking tag depth.
 */
export function extractDiv(html: string, openRe: RegExp): string | null {
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

/** Extract the inner HTML of a <div> identified by a CSS class name. */
export function extractDivContent(html: string, className: string): string | null {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  return extractDiv(html, new RegExp(`<div[^>]*class="[^"]*${escaped}[^"]*"[^>]*>`, "i"))
}

/** Convert a Unicode code point to a string (surrogate-safe, drops out-of-range). */
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
    // Numeric character references: decimal (&#233;) and hexadecimal (&#xE9;).
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&nbsp;/g, " ")
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

/** Strip tags but keep paragraph/line breaks: <br> and block closes become newlines. */
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

function clean(html: string): string {
  return decodeHtmlEntities(stripTags(html))
}

/** Parse the 32-char hex job ID out of an offer URL (e.g. ...-5C58C514E05320E961373E686DCF3405). */
export function idFromUrl(url: string): string | null {
  const m = url.match(/-([0-9A-Fa-f]{32})(?:#|\?|$)/)
  return m ? m[1].toUpperCase() : null
}

/**
 * Parse the search-results page: a list of <article class="box_offer"> cards.
 * We split on the article marker and parse each chunk independently.
 */
export function parseJobCards(html: string): JobCard[] {
  const results: JobCard[] = []
  const chunks = html.split(/<article class="box_offer/).slice(1)

  for (const chunk of chunks) {
    // Job ID: clean data-id attribute (fallback: hex suffix of the offer URL).
    let idMatch = chunk.match(/data-id=['"]([0-9A-Fa-f]{32})['"]/i)
    if (!idMatch) {
      const u = chunk.match(/href="([^"]*ofertas-de-trabajo\/[^"]*)"/i)
      if (u) idMatch = [u[1], idFromUrl(u[1]) ?? ""]
    }
    if (!idMatch || !idMatch[1]) continue
    const id = idMatch[1].toUpperCase()

    // Title + link (the js-o-link anchor holds both).
    const link = chunk.match(/<a[^>]*class="js-o-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i)
    if (!link) continue
    const href = decodeHtmlEntities(link[1]).split("#")[0]
    const title = clean(link[2])
    if (!title) continue

    // Company: either a t_ellipsis anchor or plain text in the first dFlex <p>.
    // (The dFlex <p> class token varies — vm_fx / vm_fs — so anchor on the
    // company anchor first, then fall back to the paragraph text.)
    let company: string | null = null
    const compAnchor = chunk.match(/<a[^>]*class="fc_base t_ellipsis"[^>]*>([\s\S]*?)<\/a>/i)
    if (compAnchor) {
      company = clean(compAnchor[1]) || null
    } else {
      const compP = chunk.match(/<p class="dFlex [^"]*">([\s\S]*?)<\/p>/i)
      if (compP) company = clean(compP[1]) || null
    }

    // Location.
    const loc = chunk.match(/<p class="fs16 fc_base mt5">\s*<span class="mr10">([\s\S]*?)<\/span>/i)
    const location = loc ? clean(loc[1]) || null : null

    // Date (relative Spanish text, e.g. "Hace 2 horas", "Hace 3 días").
    const dt = chunk.match(/<p class="fs13 fc_aux mt15">([\s\S]*?)<\/p>/i)
    const date = dt ? clean(dt[1]) || null : null

    results.push({
      id,
      title,
      company,
      location,
      date,
      url: href.startsWith("http") ? href : `${SITE}${href}`,
    })
  }

  return results
}

/**
 * Parse the single-job detail page.
 * The whole offer (tags, description, requirements, keywords, date, apply
 * button) lives inside the <div div-link="oferta"> block.
 */
export function parseJobDetail(html: string, id: string): JobDetail {
  const titleMatch = html.match(/<h1[^>]*class="fwB fs24 mb5 box_detail w100_m"[^>]*>([\s\S]*?)<\/h1>/i)
  const title = titleMatch ? clean(titleMatch[1]) || "(untitled)" : "(untitled)"

  // Company - location line under the title.
  let company: string | null = null
  let location: string | null = null
  const cl = html.match(/<p class="fs16">([\s\S]*?)<\/p>/i)
  if (cl) {
    const text = clean(cl[1])
    const sep = text.lastIndexOf(" - ")
    if (sep !== -1) {
      company = text.slice(0, sep).trim() || null
      location = text.slice(sep + 3).trim() || null
    } else {
      company = text || null
    }
  }

  let description: string | null = null
  let salary: string | null = null
  let contractType: string | null = null
  let schedule: string | null = null
  let modality: string | null = null
  let requirements: string | null = null
  let keywords: string | null = null
  let applyUrl: string | null = null

  // The whole offer (tags, description, requirements, keywords, date, apply
  // button) lives inside the <div div-link="oferta"> block.
  const offerBlock = extractDiv(html, /<div[^>]*div-link="oferta"[^>]*>/i)
  const descScope = offerBlock ?? html

  // Salary / contract / schedule / modality tags.
  const tags = [...descScope.matchAll(/<span class="tag base mb10">([\s\S]*?)<\/span>/gi)].map((m) =>
    clean(m[1]),
  )
  if (tags.length) salary = tags[0]
  if (tags.length > 1) contractType = tags[1]
  if (tags.length > 2) schedule = tags[2]
  if (tags.length > 3) modality = tags[3]

  // Full description paragraph (br-separated lines -> newlines, kept readable).
  const descP = descScope.match(/<p class="mbB">([\s\S]*?)<\/p>/i)
  if (descP) description = stripTagsKeepBreaks(descP[1]) || null

  // Requirements list.
  const req = descScope.match(/<p class="fwB fs18 mtB mb10">[^<]*<\/p>\s*<ul class="disc mbB">([\s\S]*?)<\/ul>/i)
  if (req) {
    const items = [...req[1].matchAll(/<li[^>]*>([\s\S]*?)<\/li>/gi)].map((m) => clean(m[1]))
    requirements = items.filter((s) => s).join("\n") || null
  }

  // Keywords line.
  const kw = descScope.match(/Palabras clave:\s*([\s\S]*?)<\//i)
  if (kw) keywords = clean(kw[1]) || null

  // Date line ("Hace X (actualizada)").
  let date: string | null = null
  const dt = descScope.match(/<p class="fc_aux fs13">([\s\S]*?)<\/p>/i)
  if (dt) date = clean(dt[1]) || null

  // Apply URL.
  const ap = html.match(/data-href-offer-apply="([^"]+)"/i) || html.match(/data-href-access="([^"]+)"/i)
  if (ap) applyUrl = decodeHtmlEntities(ap[1])

  // Canonical URL for the posting.
  let url = `${SITE}${OFFER_PATH}oferta-de-trabajo-de-${id}`
  const canon = html.match(/<link rel="canonical"[^>]*href="([^"]+)"/i)
  if (canon) url = decodeHtmlEntities(canon[1])

  return {
    id,
    title,
    company,
    location,
    date,
    url,
    description,
    salary,
    contractType,
    schedule,
    modality,
    requirements,
    keywords,
    applyUrl,
  }
}
