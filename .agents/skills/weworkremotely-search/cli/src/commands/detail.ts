import { DETAIL_URL, htmlFetch, parseJobDetail, slugFromUrl, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a slug ("proxify-ab-x"), a full /remote-jobs/<slug> URL, or a bare path. */
function normalizeSlug(input: string): string | null {
  const slug = slugFromUrl(input)
  if (slug) return slug
  // Tolerate a trailing slash / query on an otherwise-valid slug path.
  const m = input.match(/([a-z0-9]+(?:-[a-z0-9]+)*)\/?$/)
  return m && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(m[1]) ? m[1] : null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const slug = normalizeSlug(opts.id)
  if (!slug) {
    writeError(
      `Could not parse a job slug from "${opts.id}" — expected a /remote-jobs/<slug> URL or a bare slug`,
      "BAD_ID",
    )
    return 1
  }
  try {
    const html = await htmlFetch(`${DETAIL_URL}/${slug}`)
    if (!html) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const job = parseJobDetail(html, slug)

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.region || job.location || "—"}`,
        "",
        job.date ? `Posted: ${job.date}` : "",
        job.postedOn ? `Posted on: ${job.postedOn}` : "",
        job.applyBefore ? `Apply before: ${job.applyBefore}` : "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.category ? `Category: ${job.category}` : "",
        job.region ? `Region: ${job.region}` : "",
        job.skills ? `Skills: ${job.skills}` : "",
        job.salary ? `Salary: ${job.salary}` : "",
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
