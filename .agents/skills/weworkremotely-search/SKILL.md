---
name: weworkremotely-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for remote jobs on We Work
  Remotely — a global, English-language remote-only job board with strong software
  development coverage (Rails, Python, React, DevOps, design, product, marketing,
  customer support, and more). All listings are remote. Invoke for fully remote
  openings, remote-first roles, or a specific remote role/skill, e.g. "ruby on
  rails", "backend developer", "react", "remote DevOps", "remote design job".
  Trigger phrases: remote jobs, work remotely, fully remote, remote role, remote
  software jobs, remote ruby on rails, remote developer jobs, "find me a remote
  <role> job".
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/weworkremotely-search/cli/src/cli.ts *)
---

# We Work Remotely Search Skill

Search live job listings from **We Work Remotely** (https://weworkremotely.com) —
a global, English-language, **remote-only** job board. Every posting is remote, so
this skill is a great fit for fully-remote roles across software development
(programming, DevOps, design, product, marketing, customer support, management).
No authentication, no API key, and **zero runtime dependencies** — it runs with
just `bun`.

## ⚠️ Personal use only

We Work Remotely's `robots.txt` permits the search and listing paths used here
(`/remote-jobs/...`), but this reads their public pages, so **keep volume low** and
don't use it commercially or for bulk data collection. Run it on your own
responsibility.

## When to use this skill

- Search for fully remote job openings by keyword (title, skill, or role)
- Filter by recency (last 24 hours / past week / past 2 weeks)
- Get the full description and metadata of a specific remote listing
- Browse a realistic remote-market snapshot: this is a global board in English,
  so it suits "remote-global" roles rather than Argentina-local listings (pair it
  with a local-market skill such as `jobbank-search` for Argentine postings)

## Commands

### Search job listings

```bash
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search --query "<keywords>" [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — **required.** Keyword search (title, skill, role), e.g. `"ruby on rails"`, `"backend developer"`, `"react"`.
- `--jobage <days>` — posted within N days. Mapped to WWR's sort dropdown: `1` = Past 24 Hours, `2`–`7` = Past Week, `8`–`14` = Past 2 Weeks. Omit for all postings.
- `--page <n>` — accepted for contract compatibility, but **WWR search is unpaginated**: the endpoint returns every match on a single page and ignores a `page` param, so pages beyond 1 return the same results.
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts detail <id|url|slug> [--format json|plain]
```

`id` is the slug from `search` results (e.g. `proxify-ab-senior-ruby-on-rails-developer-ai-augmented-engineering`). You may also pass a full `https://weworkremotely.com/remote-jobs/<slug>` URL or a bare slug. Returns the description, posted date, apply deadline, employment type, category, region, skills, salary (when published), and apply link.

## Usage examples

```bash
# Ruby on Rails remote roles
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q "ruby on rails" --format table

# Backend developer roles posted in the last week
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q "backend developer" --jobage 7 --format table

# React roles, newest first, first 5
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q "react" --limit 5 --format table

# Full details for a specific remote listing
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts detail proxify-ab-senior-ruby-on-rails-developer-ai-augmented-engineering --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

JSON output shape: `{ "meta": { "count": ..., "page": ..., "total": ... }, "results": [...] }` where each result has `id` (the `/remote-jobs/<slug>` slug), `title`, `company`, `location`, `date`, `url`. Missing values are `null`. `meta.total` is the number of matches WWR reports for the query (before `--limit`); `meta.count` is the number of results emitted.

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Data is from We Work Remotely's public server-rendered pages — no credentials required. The search page groups matches by category and, unusually, returns **all matches on one page** (no pagination, no search RSS).
- `location` is the work region shown on the card (e.g. `Anywhere in the World`, `North America Only`, `🇺🇸 United States of America`), detected from the listing's category chips; when no chip looks like a region, it falls back to the company-headquarters line.
- `date` is an ISO `yyyy-mm-dd` computed from WWR's relative date strings (`4d`, `3w`, `1mo`, …).
- `--jobage` maps to WWR's `sort` dropdown (`Past 24 Hours` / `Past Week` / `Past 2 Weeks`); values above 14 days disable the filter.
- WWR may rate-limit; the CLI retries 429/5xx with exponential backoff. Keep volume low (see the personal-use note above).
- If the "ruby on rails" test query ever returns zero matches, fall back to `"backend"` in the smoke test — see `cli/tests/smoke.test.ts`.
