import {
  SEARCH_URL,
  htmlFetch,
  parseSearchPage,
  matchesQuery,
  scoreQuery,
  withinDays,
  paginate,
  searchResults,
  writeError,
  type JobCard,
  type SilverJob,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  jobage?: number // in days; omitted/undefined = all postings
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const id = (c.id || "").slice(0, 30).padEnd(30)
    const title = (c.title || "").slice(0, 36).padEnd(36)
    const company = (c.company || "—").slice(0, 22).padEnd(22)
    const loc = (c.location || "—").slice(0, 12).padEnd(12)
    const salary = (c.salary || "—").slice(0, 16).padEnd(16)
    const date = c.date || "—"
    return `${id} ${title} ${company} ${loc} ${salary} ${date}`
  })
  const header =
    "ID".padEnd(30) +
    " " +
    "TITLE".padEnd(36) +
    " " +
    "COMPANY".padEnd(22) +
    " " +
    "LOCATION".padEnd(12) +
    " " +
    "SALARY".padEnd(16) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

/** Rank matches by relevance (title/category first), then newest first. */
function rankByRelevance(jobs: SilverJob[], query: string): SilverJob[] {
  return [...jobs].sort((a, b) => {
    const diff = scoreQuery(b, query) - scoreQuery(a, query)
    if (diff !== 0) return diff
    return (b.epoch ?? 0) - (a.epoch ?? 0)
  })
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const html = await htmlFetch(SEARCH_URL)
    let jobs = parseSearchPage(html)

    if (opts.query) {
      const query = opts.query
      jobs = jobs.filter((j) => matchesQuery(j, query))
      jobs = rankByRelevance(jobs, query)
    }
    jobs = jobs.filter((j) => withinDays(j, opts.jobage ?? null))
    jobs = paginate(jobs, opts.page)

    let cards = searchResults(jobs)
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}${c.salary ? ` · ${c.salary}` : ""}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify({ meta: { count: cards.length, page: opts.page }, results: cards }, null, 2) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}
