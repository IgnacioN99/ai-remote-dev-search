import {
  BACKENDS,
  detectBackend,
  fetchJson,
  greenhouseContentJobsUrl,
  jobsUrlFor,
  parseCards,
  withinDays,
  writeError,
  type Backend,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  company: string
  ats: string // "auto" or a backend name
  query?: string
  location?: string
  jobage: number // days; a large sentinel means "all"
  page: number
  limit: number
  format: "json" | "table" | "plain"
}

function resolveBackend(ats: string): Backend | "auto" {
  return (BACKENDS as readonly string[]).includes(ats) ? (ats as Backend) : "auto"
}

function matches(card: JobCard, query?: string, location?: string): boolean {
  if (query) {
    // Comma-separated terms are OR'd: "software engineer,backend engineer,developer"
    // matches a role whose title/company/location/description contains ANY term.
    const terms = query
      .toLowerCase()
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
    if (terms.length > 0) {
      const hay = `${card.title} ${card.company ?? ""} ${card.location ?? ""} ${card.description ?? ""}`.toLowerCase()
      if (!terms.some((t) => hay.includes(t))) return false
    }
  }
  if (location) {
    const l = location.toLowerCase()
    if (!(card.location ?? "").toLowerCase().includes(l)) return false
  }
  return true
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 40).padEnd(40)
    const company = (c.company || "—").slice(0, 20).padEnd(20)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const date = (c.date || "—").slice(0, 10)
    return `${c.id.slice(0, 12).padEnd(12)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(12) +
    " " +
    "TITLE".padEnd(40) +
    " " +
    "COMPANY".padEnd(20) +
    " " +
    "LOCATION".padEnd(24) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const resolved = resolveBackend(opts.ats)
    const backend: Backend | null = resolved === "auto" ? await detectBackend(opts.company) : resolved
    if (!backend) {
      writeError(
        `Could not detect a Greenhouse/Lever/Ashby board for "${opts.company}". Pass --ats to pin one, or check the company slug.`,
        "UNKNOWN_COMPANY",
      )
      return 1
    }

    const fetchUrl =
      backend === "greenhouse" ? greenhouseContentJobsUrl(opts.company) : jobsUrlFor(backend, opts.company)
    const json = await fetchJson(fetchUrl)
    if (json == null) {
      writeError(`No job board found for "${opts.company}" on ${backend}.`, "NOT_FOUND")
      return 1
    }

    let cards = parseCards(json, backend, opts.company).filter((c) => c.id && c.title)
    cards = cards.filter((c) => matches(c, opts.query, opts.location))
    if (opts.jobage < 9999) {
      cards = cards.filter((c) => withinDays(c.date, opts.jobage))
    }

    const pageSize = Math.max(1, opts.limit)
    const start = (Math.max(1, opts.page) - 1) * pageSize
    const pageCards = cards.slice(start, start + pageSize)

    if (opts.format === "table") {
      process.stdout.write(renderTable(pageCards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        pageCards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify({ meta: { count: cards.length, page: opts.page }, results: pageCards }, null, 2) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}
