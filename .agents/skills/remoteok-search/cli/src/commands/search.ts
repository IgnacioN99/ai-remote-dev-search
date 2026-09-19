import {
  API_URL,
  jsonFetch,
  parseJobs,
  matchesQuery,
  scoreQuery,
  withinDays,
  paginate,
  searchResults,
  writeError,
  type JobCard,
  type RemoteOkJob,
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
    const title = (c.title || "").slice(0, 38).padEnd(38)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "Remote").slice(0, 20).padEnd(20)
    const salary = salaryLabel(c.salaryMin, c.salaryMax).slice(0, 20).padEnd(20)
    const date = (c.date || "").slice(0, 10)
    return `${c.id.padEnd(8)} ${title} ${company} ${loc} ${salary} ${date}`
  })
  const header =
    "ID".padEnd(8) +
    " " +
    "TITLE".padEnd(38) +
    " " +
    "COMPANY".padEnd(26) +
    " " +
    "LOCATION".padEnd(20) +
    " " +
    "SALARY".padEnd(20) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

/** Sort a matched set by descending relevance score, then newest first. */
function rankByRelevance(jobs: RemoteOkJob[], query: string): RemoteOkJob[] {
  return [...jobs].sort((a, b) => {
    const scoreDiff = scoreQuery(b, query) - scoreQuery(a, query)
    if (scoreDiff !== 0) return scoreDiff
    return (b.epoch ?? 0) - (a.epoch ?? 0)
  })
}

function salaryLabel(min: number | null, max: number | null): string {
  if (min === null && max === null) return ""
  if (min !== null && max !== null) return `$${min.toLocaleString()}–$${max.toLocaleString()}`
  return min !== null ? `$${min.toLocaleString()}+` : `up to $${max!.toLocaleString()}`
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const payload = await jsonFetch(API_URL)
    let jobs = parseJobs(payload)

    if (opts.query) {
      const query = opts.query
      jobs = jobs.filter((j) => matchesQuery(j, query))
      // Rank matches by relevance (title/tag matches first), then newest first.
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
          .map((c) => {
            const salary = salaryLabel(c.salaryMin, c.salaryMax)
            return [
              c.title,
              `  ${c.company || "—"} · ${c.location || "Remote"} · ${(c.date || "").slice(0, 10)}${salary ? ` · ${salary}` : ""}`,
              `  id: ${c.id}`,
              `  ${c.url}`,
            ].join("\n")
          })
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
