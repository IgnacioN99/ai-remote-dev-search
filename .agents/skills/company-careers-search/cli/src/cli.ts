#!/usr/bin/env bun
// Self-contained CLI for searching job listings on company career pages backed
// by Greenhouse, Lever, or Ashby. No authentication, no API key, and zero
// runtime dependencies — it runs anywhere `bun` is available.
//
// Personal use only — keep volume low; these are public ATS endpoints.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { c: "company", q: "query", l: "location", n: "limit" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
      const next = argv[i + 1]
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true
      } else {
        flags[key] = next
        i++
      }
    } else {
      ;(flags._ as string[]).push(a)
    }
  }
  return flags
}

const HELP = `company-careers-cli — search jobs on company career pages (Greenhouse / Lever / Ashby)

USAGE
  bun run src/cli.ts search --company <slug> [flags]
  bun run src/cli.ts detail <id|url> [--company <slug>] [--format json|plain]

SEARCH FLAGS
  --company, -c <slug>    Company ATS slug. REQUIRED. e.g. anthropic, despegar, gitlab,
                          stripe, datadog, spotify, notion.
  --ats <backend>         Pin the backend: greenhouse | lever | ashby. Default auto-detect.
  --query, -q <text>      Keywords; matches title, company, location, and description.
                          Comma-separate for OR: "software engineer,backend engineer,developer".
  --location, -l <text>   Filter by location substring (e.g. "remote", "Buenos Aires").
  --jobage <days>         Only jobs posted within N days. Default: all.
  --page <n>              1-indexed page. Default 1.
  --limit, -n <n>         Results per page (client-side cap). Default 25.
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -c anthropic -q "software engineer" --format table
  bun run src/cli.ts search -c despegar -q "ruby" --format table
  bun run src/cli.ts search -c gitlab -q "backend" -l remote --jobage 30
  bun run src/cli.ts detail https://job-boards.greenhouse.io/anthropic/jobs/4461450008 --format plain
  bun run src/cli.ts detail 4461450008 -c anthropic --format plain

Personal use only — uses public ATS endpoints; keep volume low.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  if (cmd === "search") {
    const company = typeof flags.company === "string" ? flags.company : undefined
    if (!company) {
      process.stderr.write(
        JSON.stringify({ error: 'the --company/-c flag is required (e.g. -c anthropic, -c despegar)', code: "NO_COMPANY" }) + "\n",
      )
      return 1
    }
    const fmt = (flags.format as string) || "json"

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n")
        return null
      }
      return val
    }

    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage)
      if (v === null) return 1
      flags.jobage = String(v)
    }
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page)
      if (v === null) return 1
      flags.page = String(v)
    }
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit)
      if (v === null) return 1
      flags.limit = String(v)
    }

    const opts: SearchOpts = {
      company,
      ats: typeof flags.ats === "string" ? flags.ats : "auto",
      query: typeof flags.query === "string" ? flags.query : undefined,
      location: typeof flags.location === "string" ? flags.location : undefined,
      jobage: flags.jobage ? parseInt(flags.jobage as string, 10) : 9999,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      limit: flags.limit ? Math.max(1, parseInt(flags.limit as string, 10)) : 25,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const target = (flags._ as string[])[1]
    if (!target) {
      process.stderr.write(JSON.stringify({ error: "detail requires an <id|url>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = {
      target,
      company: typeof flags.company === "string" ? flags.company : undefined,
      ats: typeof flags.ats === "string" ? flags.ats : "auto",
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main()
  .then((code) => {
    process.exitCode = code
  })
  .catch((e) => {
    process.stderr.write(
      JSON.stringify({ error: e instanceof Error ? e.message : String(e), code: "INTERNAL_ERROR" }) + "\n",
    )
    process.exitCode = 1
  })
