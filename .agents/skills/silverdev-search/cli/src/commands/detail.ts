import { DETAIL_URL, htmlFetch, parseDetailPage, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a bare slug, a relative /jobs/<slug>, or a full silver.dev URL. */
function normalizeId(input: string): string | null {
  const url = input.match(/silver\.dev\/jobs\/([\w-]+)/i)
  if (url) return url[1]
  const rel = input.match(/^\/jobs\/([\w-]+)$/)
  if (rel) return rel[1]
  const bare = input.match(/^[\w-]+$/)
  if (bare) return input
  return null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`Could not parse a job slug from "${opts.id}"`, "BAD_ID")
    return 1
  }
  try {
    const html = await htmlFetch(`${DETAIL_URL}/${id}`)
    if (!html) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const job = parseDetailPage(html, id)
    if (!job) {
      writeError("Detail page did not contain a job listing", "NOT_FOUND")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"} · ${job.date || "—"}${job.salary ? ` · ${job.salary}` : ""}`,
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.occupationalCategory ? `Category: ${job.occupationalCategory}` : "",
        "",
        job.description || "(no description)",
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
