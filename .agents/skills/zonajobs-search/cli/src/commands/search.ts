import {
  SEARCH_URL,
  apiFetchJson,
  parseSearchResponse,
  jobageFilter,
  resolveLocation,
  writeError,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  location?: string
  jobage: number
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

interface SearchBody {
  filtros: Array<{ id: string; value: string }>
  query: string
  internacional: boolean
}

/** Build the POST body, resolving --location and --jobage into filters. */
export function buildSearchBody(opts: SearchOpts): { body: SearchBody; locationWarnings: string[] } {
  const filtros: SearchBody["filtros"] = []
  const locationWarnings: string[] = []

  if (opts.location) {
    const value = resolveLocation(opts.location)
    if (value) {
      filtros.push({ id: "provincia", value })
    } else {
      locationWarnings.push(`unrecognized location "${opts.location}" — location is province-level on this board; try a province name ("Buenos Aires", "Córdoba") or a semantic id ("argentina|buenos-aires")`)
    }
  }
  const age = jobageFilter(opts.jobage)
  if (age) filtros.push({ id: "dias_fecha_publicacion", value: age })

  return {
    body: { filtros, query: opts.query ?? "", internacional: false },
    locationWarnings,
  }
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const date = c.date || "—"
    return `${c.id.padEnd(12)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(12) +
    " " +
    "TITLE".padEnd(42) +
    " " +
    "COMPANY".padEnd(26) +
    " " +
    "LOCATION".padEnd(24) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const { body, locationWarnings } = buildSearchBody(opts)

    // The API's page is 0-indexed; the CLI contract is 1-indexed.
    const pageSize = opts.limit !== undefined ? Math.max(1, opts.limit) : 20
    const params = new URLSearchParams({
      pageSize: String(pageSize),
      page: String(Math.max(0, opts.page - 1)),
    })
    const url = `${SEARCH_URL}?${params.toString()}`
    const json = await apiFetchJson(url, { method: "POST", body })
    if (json === null) {
      // A 404 on the search endpoint means it has moved or is blocked — that
      // is not an empty result set, so surface it as an error.
      throw new Error(`Search endpoint returned 404: ${SEARCH_URL}`)
    }

    const { total, results } = parseSearchResponse(json)
    let cards = results
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    for (const w of locationWarnings) writeError(w, "LOCATION_UNRESOLVED")

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
          { meta: { count: cards.length, page: opts.page, total }, results: cards },
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
