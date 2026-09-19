import {
  API_URL,
  jsonFetch,
  parseJobs,
  findJob,
  detailResult,
  writeError,
} from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  try {
    const payload = await jsonFetch(API_URL)
    const jobs = parseJobs(payload)
    const job = findJob(jobs, opts.id)
    if (!job) {
      writeError(`No job matched id/slug/url "${opts.id}"`, "NOT_FOUND")
      return 1
    }
    const detail = detailResult(job)

    if (opts.format === "plain") {
      const salary = [job.salaryMin, job.salaryMax].every((s) => s !== null)
        ? `$${job.salaryMin!.toLocaleString()}–$${job.salaryMax!.toLocaleString()}`
        : job.salaryMin !== null
          ? `$${job.salaryMin.toLocaleString()}+`
          : job.salaryMax !== null
            ? `up to $${job.salaryMax.toLocaleString()}`
            : ""
      const lines = [
        detail.title,
        `${detail.company || "—"} · ${detail.location || "Remote"} · ${(detail.date || "").slice(0, 10)}${salary ? ` · ${salary}` : ""}`,
        detail.tags && detail.tags.length ? `Tags: ${detail.tags.join(", ")}` : "",
        "",
        detail.description || "(no description)",
        "",
        `URL: ${detail.url}`,
        detail.applyUrl ? `Apply: ${detail.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(detail, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}
