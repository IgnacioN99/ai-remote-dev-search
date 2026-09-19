# remoteok-cli

CLI for searching jobs on **RemoteOK** (https://remoteok.com), the global remote-work
job board — postings in English, worldwide + remote.

**Data source**: RemoteOK public JSON API (`GET https://remoteok.com/api`).
**Authentication**: None required, no API key.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> **Personal use only.** RemoteOK's API terms require an attribution link-back to
> RemoteOK ("mention Remote OK as a source, so we get traffic back from your
> site") and discourage bulk/commercial use. Keep volume low and run it on your
> own responsibility.

## Installation

```bash
cd .agents/skills/remoteok-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search the live RemoteOK listing (client-side keyword + recency filter) |
| `detail` | Fetch the full description for a single posting |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Ruby on Rails roles
bun run src/cli.ts search -q "ruby on rails" --limit 5 --format table

# Backend roles posted in the last week
bun run src/cli.ts search -q "backend developer" --jobage 7 --format table

# React roles
bun run src/cli.ts search -q "react developer" --format table

# Full detail for one posting
bun run src/cli.ts detail 1136926 --format plain
```

See `../SKILL.md` for the full flag reference and the Terms/attribution note.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keywords (title / skill / company / role). |
| `--jobage` | | Only postings from the last N days (client-side). |
| `--page` | | 1-indexed page (50 results/page, client-side). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

Note: RemoteOK has **no server-side search query or date window** — the API returns the
full listing in one response, so `--query` and `--jobage` filter that list client-side.
(It does support a server-side `?tags=` filter on the tag field, which this CLI does not
use since keyword search is broader.)
