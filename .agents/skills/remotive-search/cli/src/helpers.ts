export const API_BASE = "https://remotive.com/api/remote-jobs"
export const PAGE_SIZE = 20

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; remotive-search-cli/1.0)"

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

/** Fetch HTML with exponential backoff on 429/5xx. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 4
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, {
        headers: {
          "User-Agent": UA,
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
  salary: string | null
  url: string
  category: string | null
  tags: string[]
}

export interface JobDetail extends JobCard {
  description: string | null
  applyUrl: string | null
  jobType: string | null
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
    .replace(/&#x2f;/gi, "/")
    .replace(/&nbsp;/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

export function parseRemotiveJob(item: any): JobDetail {
  const epoch = item.publication_date ? new Date(item.publication_date).getTime() : null
  const date = epoch ? new Date(epoch).toISOString().slice(0, 10) : null
  const loc = item.candidate_required_location || "Worldwide"

  let title = item.title || ""
  title = title.replace(/^\[Hiring\]\s*/i, "")
  if (item.company_name && title.includes(`@${item.company_name}`)) {
    title = title.replace(new RegExp(`\\s*@${item.company_name}.*$`, "i"), "").trim()
  }

  return {
    id: String(item.id),
    title,
    company: item.company_name || null,
    location: loc.toLowerCase().includes("remote") ? loc : `Remote (${loc})`,
    date,
    epoch,
    remote: true,
    salary: item.salary && item.salary.trim() !== "" ? item.salary.trim() : null,
    url: item.url,
    category: item.category || null,
    tags: Array.isArray(item.tags) ? item.tags : [],
    description: stripHtml(item.description),
    applyUrl: item.url,
    jobType: item.job_type || null,
  }
}

export function parseDetailPage(html: string, url: string, fallbackId: string): JobDetail | null {
  if (!html) return null

  // Check JSON-LD
  const lds = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/gi)]
  for (const ld of lds) {
    try {
      const obj = JSON.parse(ld[1])
      if (obj["@type"] === "JobPosting") {
        let title = obj.title || fallbackId
        title = title.replace(/^\[Hiring\]\s*/i, "")
        const company = obj.hiringOrganization?.name || null
        if (company && title.includes(`@${company}`)) {
          title = title.replace(new RegExp(`\\s*@${company}.*$`, "i"), "").trim()
        }

        const dateStr = obj.datePosted || null
        const epoch = dateStr ? new Date(dateStr).getTime() : null
        const date = epoch ? new Date(epoch).toISOString().slice(0, 10) : null

        return {
          id: fallbackId,
          title,
          company,
          location: "Remote (Global)",
          date,
          epoch,
          remote: true,
          salary: null,
          url,
          category: "Software Development",
          tags: [],
          description: stripHtml(obj.description),
          applyUrl: url,
          jobType: obj.employmentType || null,
        }
      }
    } catch {
      // Continue searching
    }
  }

  return null
}
