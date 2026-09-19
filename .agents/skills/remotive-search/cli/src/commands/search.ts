import {
  API_BASE,
  PAGE_SIZE,
  jsonFetch,
  parseRemotiveJob,
  writeError,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  jobage?: number
  limit?: number
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const id = (c.id || "").slice(0, 10).padEnd(10)
    const title = (c.title || "").slice(0, 38).padEnd(38)
    const company = (c.company || "—").slice(0, 20).padEnd(20)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const salary = (c.salary || "—").slice(0, 18).padEnd(18)
    const date = c.date || "—"
    return `${id} ${title} ${company} ${loc} ${salary} ${date}`
  })
  const header =
    "ID".padEnd(10) +
    " " +
    "TITLE".padEnd(38) +
    " " +
    "COMPANY".padEnd(20) +
    " " +
    "LOCATION".padEnd(24) +
    " " +
    "SALARY".padEnd(18) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const url = opts.query
      ? `${API_BASE}?category=software-dev&search=${encodeURIComponent(opts.query)}`
      : `${API_BASE}?category=software-dev`

    const data = await jsonFetch(url)
    if (!data || !Array.isArray(data.jobs)) {
      if (opts.format === "json") {
        console.log(JSON.stringify({ meta: { count: 0 }, results: [] }))
      } else {
        console.log("No results.")
      }
      return 0
    }

    let items = data.jobs

    // Filter by jobage if specified
    if (opts.jobage !== undefined && opts.jobage > 0) {
      const cutoff = Date.now() - opts.jobage * 86400000
      items = items.filter((it: any) => {
        const pub = it.publication_date ? new Date(it.publication_date).getTime() : null
        return pub ? pub >= cutoff : true
      })
    }

    const cards: JobCard[] = items.map((it: any) => parseRemotiveJob(it))

    // Limit if specified
    const limit = opts.limit ?? PAGE_SIZE
    const sliced = cards.slice(0, limit)

    if (opts.format === "json") {
      console.log(
        JSON.stringify(
          {
            meta: {
              count: sliced.length,
              totalInFeed: cards.length,
            },
            results: sliced,
          },
          null,
          2
        )
      )
    } else if (opts.format === "table") {
      console.log(renderTable(sliced))
    } else {
      for (const c of sliced) {
        console.log([c.id, c.title, c.company, c.location, c.salary, c.date, c.url].join("\t"))
      }
    }

    return 0
  } catch (err: any) {
    writeError(err.message || String(err), "SEARCH_FAILED")
    return 1
  }
}
