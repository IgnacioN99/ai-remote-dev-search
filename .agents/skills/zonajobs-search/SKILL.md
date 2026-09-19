---
name: zonajobs-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Argentina on
  ZonaJobs (www.zonajobs.com.ar), one of the country's largest job boards
  (owned by the same group as Bumeran). Invoke for open positions, vacancies,
  and hiring across any sector or role (software, data, design, marketing,
  finance, operations, etc.). Trigger phrases: buscar trabajo, búsqueda de
  empleo, ofertas de empleo, vacantes, empleos en <ciudad/provincia>, trabajos
  de <rol> en Argentina, empleo en zonajobs, job search, job openings,
  vacancies, hiring, jobs in Argentina.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/zonajobs-search/cli/src/cli.ts *)
---

# ZonaJobs Argentina Search Skill

Search live job listings from **ZonaJobs Argentina** (www.zonajobs.com.ar), one
of the largest job boards in the country, via its public web API. No
authentication, no API key, and **zero runtime dependencies** — it runs with
just `bun`.

> ZonaJobs and Bumeran Argentina share the same backend (both are Navent
> brands); this skill targets the ZonaJobs portal and its postings.

## ⚠️ Personal use only

This uses ZonaJobs' public job listings through its web API; automated access is
against the spirit of the site's terms, so **keep volume low and don't use it
commercially or for bulk data collection.** Run it on your own responsibility.

## When to use this skill

- Search for job openings in Argentina by keyword (role, skill, seniority)
- Filter by location (province / city) and recency (posted within N days)
- Get the full description of a specific job listing

## Commands

### Search job listings

```bash
bun run .agents/skills/zonajobs-search/cli/src/cli.ts search --query "<keywords>" [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — **required.** Keyword search (title, skill, role).
- `--location <text>` / `-l <text>` — province or city, e.g. `"Buenos Aires"`,
  `"Córdoba"`, `"Santa Fe"`, `"Capital Federal"`, `"CABA"`. Matched against a
  province map; an explicit semantic id like `"argentina|buenos-aires"` also works.
  Location filtering is **province-level** on this board — if a city name isn't
  recognized you get a stderr warning and the filter is skipped.
- `--jobage <days>` — posted within N days. The portal has fixed buckets
  (2, 3, 4, 5, 6, 7, 15, 31); the smallest bucket covering N is used.
- `--page <n>` — page number (1-indexed). Default 1.
- `--limit <n>` / `-n <n>` — results per page / cap on results emitted.
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/zonajobs-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the numeric job ID from `search` results (e.g. `2188012`). You may also
pass the full `/empleos/...-<id>.html` URL. Returns the full description with
paragraph breaks preserved, plus modality, employment type, and seniority.

## Usage examples

```bash
# Desarrollador roles across Argentina
bun run .agents/skills/zonajobs-search/cli/src/cli.ts search -q "desarrollador" --format table

# Backend developer roles, Buenos Aires province, last 7 days
bun run .agents/skills/zonajobs-search/cli/src/cli.ts search -q "desarrollador backend" -l "Buenos Aires" --jobage 7 --format table

# Ruby on Rails roles in Capital Federal
bun run .agents/skills/zonajobs-search/cli/src/cli.ts search -q "ruby on rails" -l "Capital Federal" --format json

# React roles in Córdoba, first 10
bun run .agents/skills/zonajobs-search/cli/src/cli.ts search -q "react" -l "Córdoba" --limit 10 --format table

# Full details for a specific job
bun run .agents/skills/zonajobs-search/cli/src/cli.ts detail 2188012 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Data is from ZonaJobs' public web API (`POST /api/avisos/searchV2`,
  `GET /api/candidates/fichaAvisoNormalizada/<id>`); the page HTML is a
  client-rendered shell with no listings.
- The API requires an `x-site-id` header; ZonaJobs Argentina uses `ZJAR`
  (Bumeran uses `BMAR` against the same backend). This is a public site
  constant, not a credential.
- Pagination is 0-indexed in the API; the CLI exposes it as 1-indexed.
- Posting-age filtering maps to the portal's fixed date buckets
  (2, 3, 4, 5, 6, 7, 15, 31 days).
- Location filtering is province-level; unknown city names warn and skip.
- ZonaJobs may rate-limit; the CLI retries 429/5xx with exponential backoff.
  Keep volume low (see personal-use note above).
- Job IDs are numeric (e.g. `2188012`) — pass them as-is to `detail`.
