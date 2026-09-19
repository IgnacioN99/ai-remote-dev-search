import { DETAIL_URL, apiFetchJson, parseDetailResponse, normalizeId, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`Could not parse a job ID from "${opts.id}"`, "BAD_ID")
    return 1
  }
  try {
    const json = await apiFetchJson(`${DETAIL_URL}/${id}`)
    if (json === null) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const job = parseDetailResponse(json, id)

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"} · ${job.date || ""}`.trim(),
        "",
        job.modality ? `Modality: ${job.modality}` : "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.contractType ? `Contract: ${job.contractType}` : "",
        job.seniority ? `Seniority: ${job.seniority}` : "",
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`,
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
