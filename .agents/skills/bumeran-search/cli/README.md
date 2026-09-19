# bumeran-cli

CLI for searching jobs on **Bumeran Argentina** (www.bumeran.com.ar), one of the
largest job boards in the country.

**Data source**: Bumeran's public web API (`/api/avisos/searchV2` and
`/api/candidates/fichaAvisoNormalizada/<id>`), the same endpoints the site's own
SPA uses. The HTML page is a client-rendered shell and carries no listings.
**Authentication**: None (the API needs an `x-site-id: BMAR` header — a public
site constant, not a credential).
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and
only pulls dev type defs.

> **Personal use only.** This reads Bumeran's public listings through their web
> API; keep volume low, don't use it commercially or for bulk data collection,
> and run it on your own responsibility.

## Installation

```bash
cd .agents/skills/bumeran-search/cli
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
# Backend developer roles across Argentina, last 7 days
bun run src/cli.ts search -q "desarrollador backend" --jobage 7 --format table

# Rails roles in Buenos Aires province (or CABA)
bun run src/cli.ts search -q "ruby on rails" -l "Buenos Aires" --format table
bun run src/cli.ts search -q "react" -l "Capital Federal" --limit 10 --format table

# Full detail for one job
bun run src/cli.ts detail 1118391216 --format plain
```

See `../SKILL.md` for the full flag reference and the personal-use note.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | **Required.** Keywords (title / skill / role). |
| `--location` | `-l` | Province or city (e.g. `"Buenos Aires"`, `"Córdoba"`, `"CABA"`) or a semantic id (`"argentina|buenos-aires"`). |
| `--jobage` | | Posted within N days. Buckets: 2, 3, 4, 5, 6, 7, 15, 31. |
| `--page` | | 1-indexed page. |
| `--limit` | `-n` | Results per page / cap on results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |
