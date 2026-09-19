import {
  SEARCH_URL,
  CATEGORY_URL,
  PAGE_SIZE,
  jsonFetch,
  parseGetonbrdCard,
  resolveCompanyName,
  writeError,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  jobage?: number
  remoteOnly?: boolean
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const id = (c.id || "").slice(0, 32).padEnd(32)
    const title = (c.title || "").slice(0, 36).padEnd(36)
    const company = (c.company || "—").slice(0, 22).padEnd(22)
    const loc = (c.location || "—").slice(0, 20).padEnd(20)
    const salary = (c.salary || "—").slice(0, 18).padEnd(18)
    const date = c.date || "—"
    return `${id} ${title} ${company} ${loc} ${salary} ${date}`
  })
  const header =
    "ID".padEnd(32) +
    " " +
    "TITLE".padEnd(36) +
    " " +
    "COMPANY".padEnd(22) +
    " " +
    "LOCATION".padEnd(20) +
    " " +
    "SALARY".padEnd(18) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const url = opts.query
      ? `${SEARCH_URL}?query=${encodeURIComponent(opts.query)}&page=${opts.page}&per_page=50`
      : `${CATEGORY_URL}?page=${opts.page}&per_page=50`

    const data = await jsonFetch(url)
    if (!data || !Array.isArray(data.data)) {
      if (opts.format === "json") {
        console.log(JSON.stringify({ meta: { count: 0, page: opts.page }, results: [] }))
      } else {
        console.log("No results.")
      }
      return 0
    }

    let items = data.data

    // Filter by jobage if specified
    if (opts.jobage !== undefined && opts.jobage > 0) {
      const cutoff = Date.now() - opts.jobage * 86400000
      items = items.filter((it: any) => {
        const pub = it.attributes?.published_at
        return pub ? pub * 1000 >= cutoff : true
      })
    }

    // Filter by remote if specified
    if (opts.remoteOnly) {
      items = items.filter((it: any) => it.attributes?.remote === true)
    }

    // Limit if specified
    const limit = opts.limit ?? PAGE_SIZE
    items = items.slice(0, limit)

    // Resolve company names in parallel
    const cards: JobCard[] = await Promise.all(
      items.map(async (item: any) => {
        const companyId = item.attributes?.company?.data?.id ?? null
        const compName = await resolveCompanyName(companyId, item.id)
        return parseGetonbrdCard(item, compName)
      })
    )

    if (opts.format === "json") {
      console.log(
        JSON.stringify(
          {
            meta: {
              count: cards.length,
              page: opts.page,
            },
            results: cards,
          },
          null,
          2
        )
      )
    } else if (opts.format === "table") {
      console.log(renderTable(cards))
    } else {
      for (const c of cards) {
        console.log([c.id, c.title, c.company, c.location, c.salary, c.date, c.url].join("\t"))
      }
    }

    return 0
  } catch (err: any) {
    writeError(err.message || String(err), "SEARCH_FAILED")
    return 1
  }
}
