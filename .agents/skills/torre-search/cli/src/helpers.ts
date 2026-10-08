// Data source: Torre open public REST APIs (search.torre.co & torre.co/api/suite).
// Zero runtime dependencies, runs with native fetch and Bun.

export const SEARCH_API_URL = "https://search.torre.co/opportunities/_search"
export const DETAIL_API_URL = "https://torre.co/api/suite/opportunities"
export const POST_BASE_URL = "https://torre.ai/post"

// search.torre.co rejects (400 "Invalid request") any opportunity query that has
// no ranking anchor (`similarto` / `bestfor`). Anonymous callers can only anchor on
// an existing opportunity via `similarto`; weight 0 keeps it from biasing results.
// Override with TORRE_SEARCH_ANCHOR_ID=<any live torre.ai/post/<id>> if this one
// is ever deleted (Torre then answers 500 "Internal shard error").
export const DEFAULT_ANCHOR_ID = "Yd6mq4kw"
export const ANCHOR_ENV_VAR = "TORRE_SEARCH_ANCHOR_ID"

export function resolveAnchorId(env: Record<string, string | undefined> = process.env): string {
  const raw = (env[ANCHOR_ENV_VAR] || "").trim()
  return raw ? extractTorreId(raw) : DEFAULT_ANCHOR_ID
}

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; torre-search-cli/1.0; +https://github.com/oscarbol09/ai-job-search)"

export interface TorreJobCard {
  id: string
  title: string
  company: string | null
  companyUrl?: string | null
  location: string | null
  date: string | null
  url: string
  salary?: string | null
  remote?: boolean
  skills?: string[]
}

export interface TorreJobDetail extends TorreJobCard {
  description: string | null
  requirements?: string | null
  responsibilities?: string | null
  deadline?: string | null
  employmentType?: string | null
  applyUrl?: string | null
}

/** HTTP error carrying the status and Torre's `meta.message` (when present). */
export class ApiError extends Error {
  status: number
  apiMessage: string | null
  constructor(status: number, statusText: string, apiMessage: string | null) {
    super(
      `Request failed: ${status} ${statusText}` + (apiMessage ? ` (${apiMessage})` : "")
    )
    this.name = "ApiError"
    this.status = status
    this.apiMessage = apiMessage
  }
}

/** Torre answers a missing/deleted `similarto` anchor with this deterministic 500. */
export function isShardError(message: string | null | undefined): boolean {
  return /shard error/i.test(message || "")
}

async function readApiMessage(response: Response): Promise<string | null> {
  try {
    const text = await response.text()
    if (!text) return null
    try {
      const body = JSON.parse(text)
      const msg = body?.meta?.message ?? body?.message ?? body?.error
      if (typeof msg === "string" && msg) return msg.slice(0, 300)
    } catch {
      // not JSON
    }
    return text.slice(0, 300)
  } catch {
    return null
  }
}

/** Fetch JSON with exponential backoff on 429/5xx. Returns null on 404. */
export async function apiFetch<T>(
  url: string,
  options: RequestInit = {},
  retry: { maxRetries?: number; baseDelayMs?: number } = {}
): Promise<T | null> {
  const maxRetries = retry.maxRetries ?? 5
  let delay = retry.baseDelayMs ?? 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      ...options,
      headers: {
        "User-Agent": UA,
        Accept: "application/json",
        ...(options.headers || {}),
      },
      signal: AbortSignal.timeout(15000),
    })

    if (response.status === 429 || response.status >= 500) {
      const apiMessage = await readApiMessage(response)
      // A shard error is deterministic (bad anchor), so retrying only wastes time.
      if (attempt === maxRetries || isShardError(apiMessage)) {
        throw new ApiError(response.status, response.statusText, apiMessage)
      }
      const jitter = Math.floor(Math.random() * Math.min(500, delay))
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }

    if (response.status === 404) return null
    if (!response.ok) {
      throw new ApiError(response.status, response.statusText, await readApiMessage(response))
    }

    return (await response.json()) as T
  }
  throw new Error("Request failed after max retries")
}

/** Extract Torre opportunity ID from URL or bare ID string */
export function extractTorreId(input: string): string {
  const trimmed = input.trim()
  const match = trimmed.match(/(?:opportunities|post)\/([a-zA-Z0-9_-]+)/)
  if (match) return match[1]
  // If it's already an ID (alphanumeric string without slashes)
  if (/^[a-zA-Z0-9_-]+$/.test(trimmed)) {
    return trimmed
  }
  return trimmed
}

/** Format Torre compensation object into clean human-readable string */
export function formatCompensation(comp: any): string | null {
  if (!comp) return null
  const data = comp.data || comp
  const currency = data.currency || "USD"
  const periodicity = data.periodicity ? ` / ${data.periodicity}` : ""

  const min = data.minAmount !== undefined && data.minAmount !== null ? Number(data.minAmount) : null
  const max = data.maxAmount !== undefined && data.maxAmount !== null ? Number(data.maxAmount) : null

  if (min !== null && max !== null) {
    if (min === 0 && max === 0) return null
    const minStr = min.toLocaleString("en-US")
    const maxStr = max.toLocaleString("en-US")
    return `${currency} ${minStr} - ${maxStr}${periodicity}`
  }
  if (min !== null && min > 0) {
    return `${currency} ${min.toLocaleString("en-US")}+${periodicity}`
  }
  if (max !== null && max > 0) {
    return `Up to ${currency} ${max.toLocaleString("en-US")}${periodicity}`
  }
  return null
}

/** Format location and remote status */
export function formatLocation(locations: string[] | undefined, isRemote?: boolean): string {
  const locList = (locations || []).filter(Boolean)
  const locStr = locList.length > 0 ? locList.join(", ") : "Anywhere"
  if (isRemote) {
    return locList.length > 0 ? `${locStr} (Remote)` : "Remote"
  }
  return locStr
}

/** Format ISO date string into YYYY-MM-DD */
export function formatIsoDate(dateStr: string | undefined | null): string | null {
  if (!dateStr) return null
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return null
    return d.toISOString().split("T")[0]
  } catch {
    return null
  }
}
