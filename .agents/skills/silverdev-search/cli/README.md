# silverdev-cli

CLI for searching job listings on **Silver.dev**'s curated job board for Latin
American software engineers hired by US/global (often VC-backed / YC) startups —
remote-global / LatAm roles with USD salary transparency.

**Data source**: Silver.dev's public `/jobs` page (schema.org JSON-LD graph) and
`/jobs/<slug>` detail pages.
**Authentication**: None required.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only
pulls dev type defs.

> **Personal use only.** This reads Silver.dev's public pages. Keep request volume
> low, don't use it commercially or for bulk data collection, and run it on your
> own responsibility.

## Installation

```bash
cd .agents/skills/silverdev-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings (`--query` optional — omitting it lists every open position) |
| `detail` | Fetch full detail for a single job listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts
`--format json|plain`. All errors are written to **stderr** as
`{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Backend roles
bun run src/cli.ts search -q "backend" --limit 5 --format table

# Ruby on Rails roles
bun run src/cli.ts search -q "ruby on rails" --format table

# Full-stack roles posted in the last 30 days
bun run src/cli.ts search -q "full stack" --jobage 30 --format json

# Everything currently open
bun run src/cli.ts search --format table

# Full detail for one job (id = slug from the json/plain output)
bun run src/cli.ts detail agora-senior-full-stack-engineer --format plain
```

See `../SKILL.md` for the full flag reference and the personal-use note.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keywords (title / skill / company / role). Optional. |
| `--jobage` | | Only listings posted within N days (client-side date filter). |
| `--page` | | 1-indexed page of results (20 per page). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |
