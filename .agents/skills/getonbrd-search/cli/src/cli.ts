#!/usr/bin/env bun
// Self-contained CLI for searching job listings on Get on Board (getonbrd.com).
// No external CLI framework, runs anywhere `bun` is available with zero external dependencies.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

const ALIAS: Record<string, string> = { q: "query", n: "limit", h: "help" }
const KNOWN = new Set(["query", "jobage", "remoteOnly", "page", "limit", "format", "help"])

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = ALIAS[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
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

const HELP = `getonbrd-cli — search tech jobs on Get on Board (Latin America & remote)

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <id|url|slug> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>   Keywords (e.g. "ruby", "react", "backend", "lead"). Optional;
                       omit to list latest programming positions.
  --jobage <days>      Filter listings published within the last N days.
  --remoteOnly         Only return remote jobs.
  --page <n>           Page number (default: 1).
  --limit, -n <n>      Max results to display (default: 20).
  --format <fmt>       json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "ruby" --format table
  bun run src/cli.ts search -q "full stack" --remoteOnly --limit 5 --format table
  bun run src/cli.ts search -q "rails" --jobage 30 --format json
  bun run src/cli.ts detail staff-backend-engineer-dugu-remote --format plain
  bun run src/cli.ts detail https://www.getonbrd.com/jobs/staff-backend-engineer-dugu-remote --format json

Personal use only — uses Get on Board public endpoints; keep request volume low.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (flags.help || flags.h) {
    process.stdout.write(HELP)
    return 0
  }
  if (!cmd) {
    process.stdout.write(HELP)
    return 1
  }

  if (cmd === "search") {
    const unknown = Object.keys(flags).filter((k) => k !== "_" && !KNOWN.has(k))
    if (unknown.length > 0) {
      process.stderr.write(
        JSON.stringify({ error: `Unknown flag "--${unknown[0]}"`, code: "BAD_FLAG" }) + "\n"
      )
      return 1
    }

    const fmt = (flags.format as string) || "json"
    if (fmt !== "json" && fmt !== "table" && fmt !== "plain") {
      process.stderr.write(
        JSON.stringify({
          error: `Invalid --format "${fmt}". Must be json, table, or plain.`,
          code: "BAD_FORMAT",
        }) + "\n"
      )
      return 1
    }

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(
          JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n"
        )
        return null
      }
      return val
    }

    let jobage: number | undefined
    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage)
      if (v === null) return 1
      jobage = v
    }

    let page = 1
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page)
      if (v === null) return 1
      page = v
    }

    let limit: number | undefined
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit)
      if (v === null) return 1
      limit = v
    }

    const opts: SearchOpts = {
      query: (flags.query as string) || undefined,
      jobage,
      remoteOnly: Boolean(flags.remoteOnly),
      page,
      limit,
      format: fmt,
    }

    return await runSearch(opts)
  }

  if (cmd === "detail") {
    const target = (flags._ as string[])[1]
    if (!target) {
      process.stderr.write(
        JSON.stringify({ error: "Missing job slug or URL for detail command", code: "MISSING_ARG" }) + "\n"
      )
      return 1
    }

    const fmt = (flags.format as string) || "plain"
    if (fmt !== "json" && fmt !== "plain") {
      process.stderr.write(
        JSON.stringify({
          error: `Invalid --format "${fmt}". Detail supports json or plain.`,
          code: "BAD_FORMAT",
        }) + "\n"
      )
      return 1
    }

    const opts: DetailOpts = {
      id: target,
      format: fmt,
    }

    return await runDetail(opts)
  }

  process.stderr.write(
    JSON.stringify({ error: `Unknown command "${cmd}"`, code: "UNKNOWN_COMMAND" }) + "\n"
  )
  return 1
}

main().then((code) => {
  if (code !== 0) process.exit(code)
})
