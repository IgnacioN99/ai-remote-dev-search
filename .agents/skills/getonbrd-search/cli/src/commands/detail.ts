import { DETAIL_BASE_URL, htmlFetch, parseDetailPage, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a bare slug, a relative /jobs/<slug>, or a full getonbrd URL. */
function resolveJobUrl(input: string): { url: string; slug: string } {
  const trimmed = input.trim()
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    const slug = trimmed.split("/").filter(Boolean).pop() || trimmed
    return { url: trimmed, slug }
  }
  if (trimmed.startsWith("/")) {
    const slug = trimmed.split("/").filter(Boolean).pop() || trimmed
    return { url: `https://www.getonbrd.com${trimmed}`, slug }
  }
  return {
    url: `${DETAIL_BASE_URL}/${trimmed}`,
    slug: trimmed,
  }
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const { url, slug } = resolveJobUrl(opts.id)
  try {
    const html = await htmlFetch(url)
    if (!html) {
      writeError(`Job not found: ${opts.id}`, "NOT_FOUND")
      return 1
    }

    const job = parseDetailPage(html, slug, url)
    if (!job) {
      writeError("Detail page did not contain a valid job listing", "NOT_FOUND")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"} · ${job.date || "—"}${job.salary ? ` · ${job.salary}` : ""}`,
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.skills && job.skills.length > 0 ? `Skills: ${job.skills.join(", ")}` : "",
        "",
        job.functions ? `RESPONSIBILITIES:\n${job.functions}\n` : "",
        job.description ? `DESCRIPTION:\n${job.description}\n` : "",
        job.benefits ? `BENEFITS:\n${job.benefits}\n` : "",
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
