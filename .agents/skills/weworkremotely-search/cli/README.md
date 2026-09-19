# weworkremotely-cli

CLI for searching remote job listings on **We Work Remotely** — a global,
English-language, remote-only job board with strong software development coverage.

**Data source**: WWR public pages — `/remote-jobs/search` (search) and
`/remote-jobs/<slug>` (detail). No authentication.
**Dependencies**: None (plain `bun` + `fetch` + regex). `bun install` is optional
and only pulls dev type defs. A parsing library is unnecessary — the markup is
shallow and the class anchors are stable (see `../url-reference.md`).

> **Personal use only.** This reads WWR's public pages; robots.txt permits the
> search/detail paths, but keep volume low and don't use it commercially or for
> bulk data collection. Run it on your own responsibility.

## Installation

```bash
cd .agents/skills/weworkremotely-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for remote job listings (`--query` required) |
| `detail` | Fetch full detail for a single listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Ruby on Rails remote roles
bun run src/cli.ts search -q "ruby on rails" --format table

# Backend developer roles posted in the last week
bun run src/cli.ts search -q "backend developer" --jobage 7 --format table

# React roles, first 5
bun run src/cli.ts search -q "react" --limit 5 --format table

# Full detail for one job
bun run src/cli.ts detail proxify-ab-senior-ruby-on-rails-developer-ai-augmented-engineering --format plain
```

See `../SKILL.md` for the full flag reference and the Terms-of-Service note.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | **Required.** Keywords (title / skill / role). |
| `--jobage` | | Posted within N days → WWR sort: `1` = Past 24 Hours, `2–7` = Past Week, `8–14` = Past 2 Weeks. |
| `--page` | | Accepted but has no effect — WWR search is unpaginated (all matches on one page). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |
