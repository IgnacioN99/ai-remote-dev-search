export const API_BASE = "https://www.getonbrd.com/api/v0"
export const SEARCH_URL = `${API_BASE}/search/jobs`
export const CATEGORY_URL = `${API_BASE}/categories/programming/jobs`
export const DETAIL_BASE_URL = "https://www.getonbrd.com/jobs"
export const PAGE_SIZE = 20

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; getonbrd-search-cli/1.0)"

/** Fetch JSON with exponential backoff on 429/5xx. */
export async function jsonFetch(url: string): Promise<any> {
  const maxRetries = 4
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, {
        headers: {
          "User-Agent": UA,
          Accept: "application/json",
        },
        redirect: "follow",
        signal: AbortSignal.timeout(15000),
      })
      if (response.status === 429 || response.status >= 500) {
        if (attempt === maxRetries) {
          throw new Error(`Request failed: ${response.status} ${response.statusText}`)
        }
        const jitter = Math.floor(Math.random() * 300)
        await new Promise((r) => setTimeout(r, delay + jitter))
        delay = Math.min(delay * 2, 4000)
        continue
      }
      if (response.status === 404) return null
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      return await response.json()
    } catch (err: any) {
      if (attempt === maxRetries) throw err
      await new Promise((r) => setTimeout(r, delay))
      delay = Math.min(delay * 2, 4000)
    }
  }
  throw new Error("Request failed after max retries")
}

/** Fetch HTML with exponential backoff on 429/5xx. Returns "" on 404. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 4
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, {
        headers: {
          "User-Agent": UA,
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        },
        redirect: "follow",
        signal: AbortSignal.timeout(15000),
      })
      if (response.status === 429 || response.status >= 500) {
        if (attempt === maxRetries) {
          throw new Error(`Request failed: ${response.status} ${response.statusText}`)
        }
        const jitter = Math.floor(Math.random() * 300)
        await new Promise((r) => setTimeout(r, delay + jitter))
        delay = Math.min(delay * 2, 4000)
        continue
      }
      if (response.status === 404) return ""
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      return await response.text()
    } catch (err: any) {
      if (attempt === maxRetries) throw err
      await new Promise((r) => setTimeout(r, delay))
      delay = Math.min(delay * 2, 4000)
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
  epoch: number | null
  remote: boolean
  remoteModality: string | null
  salary: string | null
  salaryMin: number | null
  salaryMax: number | null
  salaryCurrency: string | null
  url: string
  category: string | null
}

export interface JobDetail extends JobCard {
  description: string | null
  functions: string | null
  benefits: string | null
  desirable: string | null
  employmentType: string | null
  skills: string[]
  applyUrl: string | null
}

export function stripHtml(html: string | null | undefined): string {
  if (!html) return ""
  return html
    .replace(/<br\s*[\/]?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<\/li>/gi, "\n")
    .replace(/<li>/gi, "• ")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

const companyCache = new Map<number, string>()

export async function resolveCompanyName(companyId: number | null, fallbackSlug: string): Promise<string> {
  if (!companyId) {
    const parts = fallbackSlug.split("-")
    if (parts.length > 2) return parts[parts.length - 2]
    return "Unknown"
  }
  if (companyCache.has(companyId)) {
    return companyCache.get(companyId)!
  }
  try {
    const res = await jsonFetch(`${API_BASE}/companies/${companyId}`)
    const name = res?.data?.attributes?.name || fallbackSlug
    companyCache.set(companyId, name)
    return name
  } catch {
    return fallbackSlug
  }
}

export function formatSalary(min: number | null, max: number | null): string | null {
  if (!min && !max) return null
  if (min && max) {
    if (min === max) return `$${min} USD`
    return `$${min}–$${max} USD`
  }
  if (min) return `From $${min} USD`
  if (max) return `Up to $${max} USD`
  return null
}

export function parseGetonbrdCard(item: any, companyName: string): JobCard {
  const attr = item.attributes || {}
  const epoch = attr.published_at ? attr.published_at * 1000 : null
  const date = epoch ? new Date(epoch).toISOString().slice(0, 10) : null
  const countries = Array.isArray(attr.countries) ? attr.countries.join(", ") : null
  const location = attr.remote ? `Remote (${countries || "Global"})` : (countries || "On-site")

  return {
    id: item.id,
    title: attr.title || "",
    company: companyName,
    location,
    date,
    epoch,
    remote: Boolean(attr.remote),
    remoteModality: attr.remote_modality || null,
    salary: formatSalary(attr.min_salary, attr.max_salary),
    salaryMin: attr.min_salary || null,
    salaryMax: attr.max_salary || null,
    salaryCurrency: "USD",
    url: item.links?.public_url || `https://www.getonbrd.com/jobs/${item.id}`,
    category: attr.category_name || null,
  }
}

export function parseDetailPage(html: string, fallbackId: string, pageUrl: string): JobDetail | null {
  if (!html || (!html.includes("itemtype=\"http://schema.org/JobPosting\"") && !html.includes("job-body"))) {
    return null
  }

  // Title
  let title = ""
  const titleSpan = html.match(/<span[^>]*itemprop="title"[^>]*>([\s\S]*?)<\/span>/i)
  if (titleSpan) {
    title = titleSpan[1].replace(/<[^>]+>/g, "").trim()
  } else {
    const ogTitle = html.match(/<meta[^>]*property="og:title"[^>]*content="([^"]+)"/i)?.[1]
      || html.match(/<meta[^>]*content="([^"]+)"[^>]*property="og:title"/i)?.[1]
    if (ogTitle) {
      title = ogTitle.split(" at ")[0].trim()
    }
  }

  // Company
  let company: string | null = null
  const orgMatch = html.match(/itemprop="hiringOrganization"[\s\S]*?<img[^>]+>/i)
  if (orgMatch) {
    company = orgMatch[0].match(/alt="([^"]+)"/i)?.[1]?.trim() || null
  }
  if (!company) {
    const ogTitle = html.match(/<meta[^>]*property="og:title"[^>]*content="([^"]+)"/i)?.[1]
      || html.match(/<meta[^>]*content="([^"]+)"[^>]*property="og:title"/i)?.[1]
      || ""
    const m = ogTitle.match(/ at ([^-|]+?)(?:\s*-\s*|\s*\|)/i)
    if (m) company = m[1].trim()
  }

  // Salary
  const minM = html.match(/(?:itemprop="minValue"[^>]*content="(\d+)"|content="(\d+)"[^>]*itemprop="minValue")/i)
  const maxM = html.match(/(?:itemprop="maxValue"[^>]*content="(\d+)"|content="(\d+)"[^>]*itemprop="maxValue")/i)
  const salaryMin = minM ? parseInt(minM[1] || minM[2], 10) : null
  const salaryMax = maxM ? parseInt(maxM[1] || maxM[2], 10) : null
  const salary = formatSalary(salaryMin, salaryMax)

  // Date
  const dateM = html.match(/<time[^>]*datetime="([^"]+)"[^>]*itemprop="datePosted"/i)
  const dateStr = dateM ? dateM[1] : null
  const date = dateStr ? dateStr.slice(0, 10) : null
  const epoch = dateStr ? new Date(dateStr).getTime() : null

  // Remote & Location
  const isRemote = html.includes("Remote (work from home)") || html.includes("remoto") || html.includes("itemprop=\"jobLocation\"")
  let remoteModality: string | null = null
  if (html.includes("Full remote") || html.includes("100% remoto")) remoteModality = "full"
  else if (html.includes("Hybrid") || html.includes("Híbrido")) remoteModality = "hybrid"
  else if (isRemote) remoteModality = "remote"

  const locMatch = html.match(/<span[^>]*itemprop="addressLocality"[^>]*>([\s\S]*?)<\/span>/i)
  const location = isRemote ? `Remote (${locMatch ? locMatch[1].trim() : "Global"})` : (locMatch ? locMatch[1].trim() : "On-site")

  // Employment Type
  const empTypeM = html.match(/itemprop="employmentType"[^>]*content="([^"]+)"/i)
    || html.match(/<span[^>]*itemprop="employmentType"[^>]*>([\s\S]*?)<\/span>/i)
  const employmentType = empTypeM ? empTypeM[1].trim() : null

  // Skills / Tags
  const tagBlock = html.match(/<div class="gb-tags"[^>]*itemprop="skills"[\s\S]*?<\/div>/i)
  const skills = tagBlock
    ? [...tagBlock[0].matchAll(/<a[^>]*class="gb-tags__item"[^>]*>([\s\S]*?)<\/a>/gi)].map((m) => m[1].replace(/<[^>]+>/g, "").trim())
    : []

  // Job body
  const bodyIdx = html.indexOf('id="job-body"')
  let bodyHtml = ""
  if (bodyIdx !== -1) {
    const afterOpening = html.indexOf(">", bodyIdx)
    const start = afterOpening !== -1 ? afterOpening + 1 : bodyIdx
    const endIdx = html.indexOf('class="js-hide-fixed-actions"', start)
    const fallbackEnd = html.indexOf('id="js-apply-section"', start)
    const applyIdx = endIdx !== -1 ? endIdx : fallbackEnd
    bodyHtml = applyIdx !== -1 ? html.slice(start, applyIdx) : html.slice(start, start + 15000)
  }

  // Section extraction
  const funcMatch = bodyHtml.match(/<h3[^>]*>(?:Responsabilidades|What you['’]ll do|Funciones|Actividades)[\s\S]*?<\/h3>\s*<div class="gb-rich-txt[^"]*">([\s\S]*?)<\/div>/i)
  const desMatch = bodyHtml.match(/<h3[^>]*>(?:Deseables|Nice to have|Opcionales)[\s\S]*?<\/h3>\s*<div class="gb-rich-txt[^"]*">([\s\S]*?)<\/div>/i)
  const benMatch = bodyHtml.match(/<h3[^>]*>(?:Beneficios|Conditions|Perks|Beneficios y Cultura)[\s\S]*?<\/h3>\s*<div class="gb-rich-txt[^"]*">([\s\S]*?)<\/div>/i)

  return {
    id: fallbackId,
    title: title || fallbackId,
    company,
    location,
    date,
    epoch,
    remote: isRemote,
    remoteModality,
    salary,
    salaryMin,
    salaryMax,
    salaryCurrency: "USD",
    url: pageUrl,
    category: null,
    description: stripHtml(bodyHtml),
    functions: stripHtml(funcMatch?.[1]),
    desirable: stripHtml(desMatch?.[1]),
    benefits: stripHtml(benMatch?.[1]),
    employmentType,
    skills,
    applyUrl: pageUrl,
  }
}
