---
name: company-careers-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for job listings on a specific
  company's career page, look up openings at a named employer, or find a company's
  job board. Works for any company whose careers page runs on Greenhouse, Lever, or
  Ashby (Anthropic, Despegar, GitLab, Stripe, Datadog, Spotify, Notion, and hundreds
  more). Trigger phrases: company jobs, career page, jobs at <company>, openings at
  <company>, busco trabajo en <empresa>, vacantes en <empresa>, buscar empleo en una
  empresa.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/company-careers-search/cli/src/cli.ts *)
---

# Company Careers Search Skill

Search live job listings on **company career pages** backed by one of three common
ATS platforms: **Greenhouse**, **Lever**, and **Ashby**. No authentication, no API key,
and **zero runtime dependencies** — it runs with just `bun`. One skill covers any company
on those platforms; pass the company slug and the backend is auto-detected.

> Because Greenhouse/Lever/Ashby power the career pages of hundreds of tech companies,
> this single skill replaces a per-company portal. To add a company later you only need
> to know its ATS slug (e.g. `anthropic`, `despegar`, `gitlab`).

## When to use this skill

- Search openings at a specific company (title/keyword + location + recency)
- Look up a single posting's full description
- Feed `/scrape` for a set of target companies (it discovers this skill automatically)

## Commands

### Search job listings

```bash
bun run .agents/skills/company-careers-search/cli/src/cli.ts search --company <slug> [flags]
```

Key flags:
- `--company <slug>` / `-c <slug>` — **required.** The company's ATS slug (the part of the careers URL before `/jobs`), e.g. `anthropic`, `despegar`, `gitlab`, `stripe`, `datadog`, `spotify`, `notion`.
- `--ats <backend>` — pin the backend: `greenhouse` | `lever` | `ashby`. Default: auto-detect.
- `--query <text>` / `-q <text>` — keywords; matched against title, company, location, and description (case-insensitive). Comma-separate for OR: `"software engineer,backend engineer,developer"` matches any of the terms.
- `--location <text>` / `-l <text>` — filter by location substring, e.g. `remote`, `Buenos Aires`, `Argentina`.
- `--jobage <days>` — only jobs posted within N days. Omit for all.
- `--page <n>` — 1-indexed page (25 results/page by default).
- `--limit <n>` / `-n <n>` — results per page (client-side cap). Default 25.
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/company-careers-search/cli/src/cli.ts detail <id|url> [--company <slug>] [--format json|plain]
```

Pass either the raw id from `search` (with `--company`), or a full posting URL (the CLI
extracts company + id from it).

## Usage examples

```bash
# Backend roles at Anthropic
bun run .agents/skills/company-careers-search/cli/src/cli.ts search -c anthropic -q "software engineer" --format table

# Ruby/Rails roles at Despegar (Spanish postings)
bun run .agents/skills/company-careers-search/cli/src/cli.ts search -c despegar -q "ruby" --format table

# Remote backend roles at GitLab, posted in the last 30 days
bun run .agents/skills/company-careers-search/cli/src/cli.ts search -c gitlab -q "backend" -l remote --jobage 30

# Any opening at Stripe in a location
bun run .agents/skills/company-careers-search/cli/src/cli.ts search -c stripe -l "New York" --format table

# Full description of a single posting (by URL)
bun run .agents/skills/company-careers-search/cli/src/cli.ts detail https://job-boards.greenhouse.io/anthropic/jobs/4461450008 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- **Backends:** Greenhouse, Lever, Ashby. Auto-detection tries each and uses the first non-404 board. Pin with `--ats` to skip the probe.
- **Company slug** is the lowercase identifier in the careers URL (`boards.greenhouse.io/<slug>/jobs`, `jobs.lever.co/<slug>/`, `jobs.ashbyhq.com/<slug>/`). If auto-detect says unknown, check the slug or pin `--ats`.
- **`--query` matches title, company, location, and description** (Greenhouse fetches `?content=true`; Lever/Ashby include descriptions inline). So `ruby` finds roles that mention Ruby anywhere, not just in the title. Broad terms like `software engineer`, `backend`, or `developer` catch more than stack-specific ones, since most companies title roles "Software Engineer" without naming the language.
- **`--jobage`** compares the posting date (`first_published`/`createdAt`/`publishedAt`) against now; missing dates are kept.
- These are public ATS endpoints; the CLI retries 429/5xx with exponential backoff. **Keep volume low** (a handful of requests per run, no bulk crawling).
- Companies on other ATS platforms (Workday, SuccessFactors, or custom JS careers sites — e.g. Google, Microsoft, YPF) are **not** covered here; those fall back to WebSearch `site:` queries in the job-scraper.

## Known companies (verified slugs)

Each of these was verified to return jobs from its ATS board. Add a new one by passing
its slug to `--company`; if auto-detect can't find it, try `--ats`.

| Slug | Backend | Note |
|------|---------|------|
| anthropic | greenhouse | AI, Python/TS; US/UK |
| gitlab | greenhouse | Ruby on Rails; remote global |
| stripe | greenhouse | Ruby; US/remote |
| datadog | greenhouse | Go/Python; US/remote |
| block | greenhouse | Ruby (Square/Cash App); US |
| coinbase | greenhouse | Ruby; remote US/Canada |
| gusto | greenhouse | Ruby on Rails; US |
| airbnb | greenhouse | Ruby/Rails; US remote |
| instacart | greenhouse | Ruby/Rails; US/Canada remote |
| flexport | greenhouse | Ruby/Rails; US/global |
| twilio | greenhouse | Ruby; remote US/EU |
| chime | greenhouse | Ruby; US |
| dropbox | greenhouse | Ruby/Python; US |
| elastic | greenhouse | Ruby/Go; remote-first |
| remotecom | greenhouse | Remote.com (Elixir/Rails); remote-first |
| nubank | ashby | Kotlin/Clojure (+legacy Ruby); LatAm (BR/MX/CO) |
| notion | ashby | TypeScript/Node; US |
| zapier | ashby | Python/JS; remote |
| sentry | ashby | Python; remote |
| posthog | ashby | Python/TS; remote |
| deel | ashby | Rails/Node; remote — ⚠ empty (re-check) |
| loft | ashby | Rails/Node; Brazil/LatAm — ⚠ empty (re-check) |
| despegar | lever | Java/.NET/Node; LatAm |
| spotify | lever | Java/Python; EU/US |
| kavak | lever | backend/fullstack; LatAm (MX/AR) |

⚠ = board returns 0 jobs right now (may have migrated ATS or paused hiring). Kept here for a later re-check rather than dropped.

