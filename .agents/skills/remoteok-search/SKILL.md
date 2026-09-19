---
name: remoteok-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for remote jobs or look up a
  specific job posting on RemoteOK, the global remote-work job board. Covers
  remote positions worldwide in English — software engineering, design,
  marketing, sales, ops, customer support, and other remote roles. Trigger
  phrases: remote jobs, remote work, remoteok, work remotely, "are there any
  remote X jobs", "find remote X roles", look up this RemoteOK posting, remote
  job search.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/remoteok-search/cli/src/cli.ts *)
---

# RemoteOK Search Skill

Search live job listings from **RemoteOK** (https://remoteok.com), the global
remote-tech job board — postings in English, from companies worldwide, all remote.
Uses RemoteOK's public JSON API: no authentication, no API key, and **zero runtime
dependencies** — it runs with just `bun`.

> RemoteOK is global (not market-specific), so this skill is a country-agnostic
> worked example of the repo's job-portal-skill pattern, like `linkedin-search`.

## ⚠️ Personal use only

RemoteOK's API terms require an attribution **link-back to RemoteOK** ("mention
Remote OK as a source, so we get traffic back from your site") and expect low,
non-bulk traffic. **Keep volume low, don't use it commercially or for bulk data
collection.** Run it on your own responsibility.

## When to use this skill

- Search for remote job openings worldwide (any role — the full RemoteOK listing)
- Filter by recency (`--jobage <days>`)
- Get the full description of a specific remote posting

Note: RemoteOK has **no server-side search query or date window** — the API returns
the full listing in one response, so `--query` and `--jobage` filter that list
client-side. The board does not have locations to search; each posting carries its
own `location` field (e.g. "Global", "US only", or a city).

## Commands

### Search job listings

```bash
bun run .agents/skills/remoteok-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (title, skill, company, or role). Matches
  across title, company, location, tags, and description.
- `--jobage <days>` — only postings from the last N days (client-side). Omit for all ages.
- `--page <n>` — page number (1-indexed, 50 results per page, client-side).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/remoteok-search/cli/src/cli.ts detail <id|slug|url> [--format json|plain]
```

`id` is the numeric job id from `search` results (e.g. `1136926`). You may also pass
the posting URL or its trailing slug. Returns the full description, salary range,
tags, and apply link.

## Usage examples

```bash
# Ruby on Rails roles
bun run .agents/skills/remoteok-search/cli/src/cli.ts search -q "ruby on rails" --limit 5 --format table

# Backend roles posted in the last week
bun run .agents/skills/remoteok-search/cli/src/cli.ts search -q "backend developer" --jobage 7 --format table

# React developer roles
bun run .agents/skills/remoteok-search/cli/src/cli.ts search -q "react developer" --format table

# Senior frontend roles, second page
bun run .agents/skills/remoteok-search/cli/src/cli.ts search -q "senior frontend" --page 2 --format table

# Full details for a specific posting
bun run .agents/skills/remoteok-search/cli/src/cli.ts detail 1136926 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning (includes a salary column) |
| `plain` | Reading a single job's full detail (`detail` command) |

JSON output shape: `{ "meta": { "count": ..., "page": ... }, "results": [...] }`
where each result has at least `id`, `title`, `company`, `location`, `date`, `url`
(missing values are `null`, never omitted), plus `salaryMin`/`salaryMax`, `tags`,
and `applyUrl`.

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the
process exits with code `1`.

## Notes

- Data is from RemoteOK's public JSON API (`GET https://remoteok.com/api`) — no
  credentials required.
- The API response is a JSON array whose **first element is a metadata/legal object**
  (no job id) — the CLI skips it.
- `--query` and `--jobage` filter the full listing client-side (the API has no
  server-side query or date-window params).
- RemoteOK may rate-limit; the CLI retries 429/5xx with exponential backoff. Keep
  volume low (see the attribution note above).
- Job ids are numeric strings (e.g. `1136926`) — pass them as-is to `detail`.
- Posting URLs are normalized to lowercase `https://remoteok.com/...` (the API
  emits the domain mixed-case as `remoteOK.com`).
- Descriptions (and some company names) contain **double-encoded UTF-8 mojibake**
  (e.g. an em dash surfaces as `â`), because RemoteOK stored the text with the
  original UTF-8 bytes mis-read as Windows-1252. The CLI repairs the common
  sequences (`fixMojibake` in `helpers.ts`).
