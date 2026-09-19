# computrabajo-cli

CLI for searching job listings on **Computrabajo Argentina** (https://ar.computrabajo.com),
Argentina's largest general job board. Postings are in Spanish; the market is Argentina.

**Data source**: Computrabajo's public, server-rendered search and detail HTML pages.
**Authentication**: None required.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> **Personal use only.** This reads Computrabajo's public job pages. Computrabajo's
> robots.txt disallows a number of internal/filtered paths and automated bulk access may
> be against the portal's terms. Keep volume low, don't use it commercially or for bulk
> data collection, and run it on your own responsibility.

## Installation

```bash
cd .agents/skills/computrabajo-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings (`--query` required) |
| `detail` | Fetch full detail for a single job listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Developer roles (Argentine market, Spanish postings)
bun run src/cli.ts search -q "desarrollador" --format table

# Backend developer roles, last 7 days
bun run src/cli.ts search -q "desarrollador backend" --jobage 7 --limit 10 --format json

# Ruby on Rails roles
bun run src/cli.ts search -q "ruby on rails" --format table

# Second page of results
bun run src/cli.ts search -q "analista de datos" --page 2 --format table

# Full detail for one job (ID from search results)
bun run src/cli.ts detail 5C58C514E05320E961373E686DCF3405 --format plain
```

See `../SKILL.md` for the full flag reference and the personal-use note.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | **Required.** Keywords (title / skill / role). Include the city in the query to scope a location, e.g. `"desarrollador Buenos Aires"`. |
| `--jobage` | | Only postings published in the last N days. |
| `--page` | | 1-indexed page (20 results/page). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |
