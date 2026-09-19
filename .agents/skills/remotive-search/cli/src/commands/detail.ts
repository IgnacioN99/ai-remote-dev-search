import {
  API_BASE,
  htmlFetch,
  jsonFetch,
  parseDetailPage,
  parseRemotiveJob,
  writeError,
  type JobDetail,
} from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const input = opts.id.trim()
  try {
    let job: JobDetail | null = null

    // Case 1: Full URL
    if (input.startsWith("http://") || input.startsWith("https://")) {
      const html = await htmlFetch(input)
      if (html) {
        const slug = input.split("/").filter(Boolean).pop() || "unknown"
        job = parseDetailPage(html, input, slug)
      }
    }

    // Case 2: Numeric ID or check via API
    if (!job) {
      const idMatch = input.match(/\d+$/)
      const targetId = idMatch ? idMatch[0] : input

      const data = await jsonFetch(API_BASE)
      if (data && Array.isArray(data.jobs)) {
        const found = data.jobs.find((j: any) => String(j.id) === targetId || j.url.includes(input))
        if (found) {
          job = parseRemotiveJob(found)
        }
      }
    }

    if (!job) {
      writeError(`Job not found for "${opts.id}"`, "NOT_FOUND")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"} · ${job.date || "—"}${job.salary ? ` · ${job.salary}` : ""}`,
        job.jobType ? `Employment: ${job.jobType}` : "",
        job.tags && job.tags.length > 0 ? `Tags: ${job.tags.join(", ")}` : "",
        "",
        job.description ? `DESCRIPTION:\n${job.description}\n` : "",
        `URL: ${job.url}`,
        job.applyUrl ? `Apply: ${job.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }

    return 0
  } catch (err: any) {
    writeError(err.message || String(err), "DETAIL_FAILED")
    return 1
  }
}
