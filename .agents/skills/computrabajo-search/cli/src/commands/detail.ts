import { SITE, OFFER_PATH, htmlFetch, idFromUrl, loadUrlCache, parseJobDetail, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a bare job ID or a full Computrabajo offer URL. */
function normalizeId(input: string): string | null {
  const urlId = idFromUrl(input)
  if (urlId) return urlId
  const bare = input.match(/^[0-9A-Fa-f]{32}$/)
  if (bare) return input.toUpperCase()
  return null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`Could not parse a job ID from "${opts.id}" (expected a 32-char hex ID or an offer URL)`, "BAD_ID")
    return 1
  }
  try {
    // Computrabajo detail URLs require the title slug, which a bare ID alone
    // cannot reconstruct. Resolve via the cache written by `search`; fall back
    // to the (likely 404) slug-less URL so the error is accurate.
    const cache = await loadUrlCache()
    const url = cache[id] ?? `${SITE}${OFFER_PATH}oferta-de-trabajo-de-${id}`
    const html = await htmlFetch(url)
    if (!html) {
      writeError(
        "Job not found (or this ID has not been seen by `search` yet — pass the full offer URL from the search results)",
        "NOT_FOUND",
      )
      return 1
    }
    const job = parseJobDetail(html, id)

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}`,
        "",
        job.salary ? `Salary: ${job.salary}` : "",
        job.contractType ? `Contract: ${job.contractType}` : "",
        job.schedule ? `Schedule: ${job.schedule}` : "",
        job.modality ? `Modality: ${job.modality}` : "",
        "",
        job.description || "(no description)",
        "",
        job.requirements ? `Requirements:\n${job.requirements}` : "",
        job.keywords ? `Keywords: ${job.keywords}` : "",
        "",
        `URL: ${job.url}`,
        job.applyUrl ? `Apply: ${job.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}
