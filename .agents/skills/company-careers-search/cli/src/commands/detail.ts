import {
  BACKENDS,
  ashbyJobsUrl,
  detectBackend,
  fetchJson,
  greenhouseJobUrl,
  htmlToText,
  leverJobsUrl,
  parseJobUrl,
  parseCards,
  writeError,
  type Backend,
  type JobDetail,
} from "../helpers.js"

export interface DetailOpts {
  target: string // a raw id or a full job URL
  company?: string
  ats: string // "auto" or a backend name
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  try {
    let backend: Backend
    let company: string
    let id: string

    const fromUrl = parseJobUrl(opts.target)
    if (fromUrl) {
      backend = fromUrl.backend
      company = fromUrl.company
      id = fromUrl.id
    } else {
      id = opts.target
      if (!opts.company) {
        writeError("detail requires --company when given a raw id (or pass the full job URL)", "NO_COMPANY")
        return 1
      }
      company = opts.company
      if ((BACKENDS as readonly string[]).includes(opts.ats)) {
        backend = opts.ats as Backend
      } else {
        const detected = await detectBackend(company)
        if (!detected) {
          writeError(`Could not detect a Greenhouse/Lever/Ashby board for "${company}".`, "UNKNOWN_COMPANY")
          return 1
        }
        backend = detected
      }
    }

    let detail: JobDetail

    if (backend === "greenhouse") {
      const json = await fetchJson(greenhouseJobUrl(company, id))
      if (json == null) {
        writeError("Job not found", "NOT_FOUND")
        return 1
      }
      const j = json as Record<string, unknown>
      const absoluteUrl = String(j.absolute_url ?? "")
      detail = {
        id,
        title: String(j.title ?? "(untitled)"),
        company: j.company_name ? String(j.company_name) : company,
        location: (j.location as { name?: string } | null)?.name ?? null,
        date: j.first_published ? String(j.first_published) : null,
        url: absoluteUrl,
        description: typeof j.content === "string" ? htmlToText(j.content) : null,
        applyUrl: absoluteUrl || null,
      }
    } else if (backend === "lever") {
      const json = await fetchJson(leverJobsUrl(company))
      const arr = Array.isArray(json) ? (json as Record<string, unknown>[]) : []
      const posting = arr.find((p) => String(p.id) === id)
      if (!posting) {
        writeError("Job not found", "NOT_FOUND")
        return 1
      }
      const card = parseCards(arr, "lever", company).find((c) => c.id === id)
      detail = {
        id,
        title: String(posting.text ?? card?.title ?? "(untitled)"),
        company: card?.company ?? company,
        location: card?.location ?? null,
        date: card?.date ?? null,
        url: String(posting.hostedUrl ?? card?.url ?? ""),
        description:
          typeof posting.descriptionPlain === "string"
            ? posting.descriptionPlain
            : typeof posting.description === "string"
              ? htmlToText(posting.description)
              : null,
        applyUrl: typeof posting.applyUrl === "string" ? posting.applyUrl : null,
      }
    } else {
      // ashby — the board list already carries descriptionHtml, so look up the id there.
      const json = await fetchJson(ashbyJobsUrl(company))
      const jobs = (json as { jobs?: Record<string, unknown>[] } | null)?.jobs ?? []
      const posting = jobs.find((p) => String(p.id) === id)
      if (!posting) {
        writeError("Job not found", "NOT_FOUND")
        return 1
      }
      const card = parseCards({ jobs }, "ashby", company).find((c) => c.id === id)
      detail = {
        id,
        title: String(posting.title ?? card?.title ?? "(untitled)"),
        company: card?.company ?? company,
        location: card?.location ?? null,
        date: card?.date ?? null,
        url: String(posting.jobUrl ?? card?.url ?? ""),
        description: typeof posting.descriptionHtml === "string" ? htmlToText(posting.descriptionHtml) : null,
        applyUrl: typeof posting.applyUrl === "string" ? posting.applyUrl : null,
      }
    }

    if (opts.format === "plain") {
      const lines = [
        detail.title,
        `${detail.company || "—"} · ${detail.location || "—"}`,
        detail.date ? `Posted: ${detail.date}` : "",
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
