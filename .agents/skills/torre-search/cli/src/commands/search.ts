import {
  SEARCH_API_URL,
  POST_BASE_URL,
  ANCHOR_ENV_VAR,
  ApiError,
  apiFetch,
  isShardError,
  resolveAnchorId,
  writeError,
  formatCompensation,
  formatLocation,
  formatIsoDate,
  type TorreJobCard,
} from "../helpers.js"

export interface SearchOpts {
  query: string
  location?: string
  remote?: boolean
  page: number
  limit: number
  format: "json" | "table" | "plain"
}

export function buildSearchPayload(opts: SearchOpts, anchorId: string = resolveAnchorId()): any {
  const andClauses: any[] = [
    {
      similarto: {
        items: [{ refId: anchorId, weight: 0 }],
      },
    },
    {
      "skill/role": {
        text: opts.query,
        experience: "potential-to-develop",
      },
    },
    {
      status: {
        code: "open",
      },
    },
  ]

  if (opts.remote) {
    andClauses.push({ remote: { term: true } })
  }

  if (opts.location && opts.location.toLowerCase() !== "remote") {
    andClauses.push({
      location: {
        term: opts.location,
      },
    })
  }

  return {
    and: andClauses,
  }
}

function renderTable(cards: TorreJobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 36).padEnd(36)
    const company = (c.company || "—").slice(0, 24).padEnd(24)
    const loc = (c.location || "—").slice(0, 22).padEnd(22)
    const sal = (c.salary || "—").slice(0, 22).padEnd(22)
    const date = c.date || "—"
    return `${c.id.padEnd(10)} ${title} ${company} ${loc} ${sal} ${date}`
  })
  const header =
    "ID".padEnd(10) +
    " " +
    "TITLE".padEnd(36) +
    " " +
    "COMPANY".padEnd(24) +
    " " +
    "LOCATION".padEnd(22) +
    " " +
    "SALARY".padEnd(22) +
    " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

/** Build the search URL. Torre ignores `offset`; paging uses the `after` cursor. */
export function buildSearchUrl(limit: number, after?: string | null): string {
  const params = new URLSearchParams({ size: String(limit), lang: "en" })
  if (after) params.set("after", after)
  return `${SEARCH_API_URL}/?${params.toString()}`
}

/** Map a failed search request to a clear, actionable CLI error. */
export function describeSearchError(err: unknown, anchorId: string): { error: string; code: string } {
  if (err instanceof ApiError) {
    const msg = err.apiMessage || ""
    if (isShardError(msg) || /similarto/i.test(msg)) {
      return {
        error:
          `Torre rejected the search anchor opportunity '${anchorId}' (${err.status}: ${msg || "no message"}). ` +
          `Set ${ANCHOR_ENV_VAR} to the ID of any live posting (e.g. from https://torre.ai/post/<id>) and retry.`,
        code: "ANCHOR_UNAVAILABLE",
      }
    }
    if (err.status === 400 || err.status === 401 || err.status === 403) {
      return {
        error:
          `Torre search API rejected the request (${err.status}: ${msg || "no message"}). ` +
          "The public API contract has likely changed again; see .agents/skills/torre-search/url-reference.md. " +
          "Until fixed, set `enabled: false` in .agents/skills/torre-search/SKILL.md so /scrape skips Torre.",
        code: err.status === 400 ? "API_REJECTED" : "AUTH_REQUIRED",
      }
    }
  }
  const e = err as any
  return { error: (e && e.message) || String(err), code: "FETCH_FAILED" }
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  const anchorId = resolveAnchorId()
  try {
    const limit = Math.max(1, Math.min(opts.limit, 50))
    const page = Math.max(1, opts.page)
    const payload = buildSearchPayload(opts, anchorId)

    let after: string | null = null
    let response: any = null
    for (let p = 1; p <= page; p++) {
      response = await apiFetch<any>(buildSearchUrl(limit, after), {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Content-Type": "application/json" },
      })
      if (!response || !Array.isArray(response.results)) {
        writeError("Invalid response from Torre search API", "INVALID_RESPONSE")
        return 1
      }
      if (p < page) {
        after = response.pagination?.next || null
        if (!after) {
          // Requested page lies past the last one.
          response = { ...response, results: [], pagination: { next: null } }
          break
        }
      }
    }

    const cards: TorreJobCard[] = response.results.map((r: any) => {
      const org = Array.isArray(r.organizations) && r.organizations[0] ? r.organizations[0] : null
      const isRemote = Boolean(r.remote)
      const skills = Array.isArray(r.skills) ? r.skills.map((s: any) => s.name).filter(Boolean) : []
      return {
        id: r.id,
        title: r.objective || "",
        company: org ? org.name : null,
        location: formatLocation(r.locations, isRemote),
        date: formatIsoDate(r.created),
        url: `${POST_BASE_URL}/${r.id}`,
        salary: formatCompensation(r.compensation),
        remote: isRemote,
        skills: skills.slice(0, 8),
      }
    })

    // Server-side `remote` clause already applied; keep a client-side guard.
    const filtered = opts.remote ? cards.filter((c) => c.remote) : cards

    if (opts.format === "json") {
      process.stdout.write(
        JSON.stringify(
          {
            meta: {
              count: filtered.length,
              page,
              total: typeof response.total === "number" ? response.total : null,
              next: response.pagination?.next || null,
            },
            results: filtered,
          },
          null,
          2
        ) + "\n"
      )
    } else if (opts.format === "table") {
      process.stdout.write(renderTable(filtered) + "\n")
    } else {
      for (const card of filtered) {
        process.stdout.write(`• ${card.title}\n`)
        process.stdout.write(`  Company:  ${card.company || "Unknown"}\n`)
        process.stdout.write(`  Location: ${card.location}\n`)
        if (card.salary) process.stdout.write(`  Salary:   ${card.salary}\n`)
        if (card.date) process.stdout.write(`  Date:     ${card.date}\n`)
        if (card.skills && card.skills.length > 0) {
          process.stdout.write(`  Skills:   ${card.skills.join(", ")}\n`)
        }
        process.stdout.write(`  URL:      ${card.url}\n\n`)
      }
    }
    return 0
  } catch (err: unknown) {
    const { error, code } = describeSearchError(err, anchorId)
    writeError(error, code)
    return 1
  }
}
