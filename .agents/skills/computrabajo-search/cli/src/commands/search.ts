import {
  SITE,
  SEARCH_PATH,
  htmlFetch,
  parseJobCards,
  saveUrlCache,
  loadUrlCache,
  slugify,
  writeError,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  jobage: number // 0 = no filter
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

export function buildSearchUrl(opts: SearchOpts): string {
  const query = (opts.query || "").trim()
  const slug = slugify(query) || "empleo"
  const params = new URLSearchParams()
  if (opts.jobage && opts.jobage > 0) params.set("pubdate", String(opts.jobage))
  if (opts.page > 1) params.set("p", String(opts.page))
  const qs = params.toString()
  return `${SITE}${SEARCH_PATH}${slug}${qs ? `?${qs}` : ""}`
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 40).padEnd(40)
    const company = (c.company || "—").slice(0, 24).padEnd(24)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const date = c.date || "—"
    return `${c.id.padEnd(33)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(33) +
    " " +
    "TITLE".padEnd(40) +
    " " +
    "COMPANY".padEnd(24) +
    " " +
    "LOCATION".padEnd(24) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const html = await htmlFetch(buildSearchUrl(opts))
    let cards = parseJobCards(html)
    // Record id -> url so a later `detail <id>` can resolve the URL
    // (Computrabajo detail URLs require the title slug).
    if (cards.length) {
      const cache = await loadUrlCache()
      for (const c of cards) cache[c.id] = c.url
      saveUrlCache(cache)
    }
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          { meta: { count: cards.length, page: opts.page }, results: cards },
          null,
          2,
        ) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}
