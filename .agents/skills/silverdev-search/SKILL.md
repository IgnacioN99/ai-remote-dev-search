---
name: silverdev-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search job openings on Silver.dev
  (silver.dev/jobs) — a curated job board for Latin American software engineers
  hired by US/global (often VC-backed / YC) startups, with USD salary
  transparency and remote-global / LatAm roles. Invoke it for searching open
  positions, finding full-stack / backend / frontend / data roles, checking USD
  salary ranges, or looking up a specific Silver.dev posting — whether or not
  the user names the site. Trigger phrases: silver.dev, silverdev, jobs at
  silver.dev, silver jobs, LatAm remote jobs, latin american remote software
  jobs, remote jobs Argentina, remote work for LatAm developers, jobs with USD
  salary, remote software engineer, full stack remote, backend remote, busqueda
  de trabajo remoto, empleos remotos, trabajo remoto en español, ofertas
  laborales remotas, salario en USD, empleos para desarrolladores de América
  Latina, trabajos remotos en Argentina, desarrollo remoto, buscar empleo
  remoto, vacantes remotas, empleo en inglés remoto.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/silverdev-search/cli/src/cli.ts *)
---

# Silver.dev Search Skill

Search live job listings from **Silver.dev** (https://silver.dev/jobs), a curated
job board where Latin American software engineers are hired by US/global (often
VC-backed / YC) startups. Postings are in English; the market is remote-global /
LatAm (Argentina, Mexico, Brazil, Spain), and most roles publish **USD salary
ranges**. No authentication, no API key, and **zero runtime dependencies** — it
runs with just `bun`.

The board is a client-side SPA, but it embeds a full schema.org JSON-LD graph on
every page. The CLI reads that JSON (not the markup) and applies the
role/tech/salary-style filters client-side, the same way `remoteok-search` does.

## ⚠️ Personal use only

This uses Silver.dev's public pages. Keep **request volume low** (a handful of
fetches, not a crawl) and don't use it commercially or for bulk data collection.
Run it on your own responsibility. robots.txt is permissive
(`User-agent: * / Allow: /`), but be respectful anyway.

## When to use this skill

- Search Silver.dev's open positions for a role, skill, or company
- Filter by recency (posted within N days)
- See USD salary ranges (e.g. `$120K–$180K`) without opening each posting
- Get the full description and Ashby apply link of a specific listing

## Commands

### Search job listings

```bash
bun run .agents/skills/silverdev-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (job title, skill, company, role). **Optional** — omit to list every open position.
- `--jobage <days>` — only listings posted within the last N days (client-side filter on the posting date). Omit for all.
- `--page <n>` — page number (1-indexed, 20 results per page).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/silverdev-search/cli/src/cli.ts detail <id|url|slug> [--format json|plain]
```

`id` is the listing's slug from `search` results (e.g. `agora-senior-full-stack-engineer`).
You may also pass a full URL (`https://silver.dev/jobs/<slug>`) or a relative
`/jobs/<slug>`. Returns the full description, salary, employment type, category,
and the Ashby apply link.

## Usage examples

```bash
# Backend roles (title/skill/description match)
bun run .agents/skills/silverdev-search/cli/src/cli.ts search -q "backend" --limit 5 --format table

# Ruby on Rails roles
bun run .agents/skills/silverdev-search/cli/src/cli.ts search -q "ruby on rails" --format table

# Full-stack roles posted in the last 30 days
bun run .agents/skills/silverdev-search/cli/src/cli.ts search -q "full stack" --jobage 30 --format json

# Every open position right now
bun run .agents/skills/silverdev-search/cli/src/cli.ts search --format table

# Full details for a specific job
bun run .agents/skills/silverdev-search/cli/src/cli.ts detail agora-senior-full-stack-engineer --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing slugs to `detail` |
| `table` | Quick human-readable scanning (ids are truncated to 30 chars) |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- **Data source:** Silver.dev's public `/jobs` page and `/jobs/<slug>` detail
  pages — the schema.org JSON-LD graph embedded in each. The per-listing slug
  comes from the HTML cards (same render order as the JSON-LD `ItemList`).
- **Salary:** stored as USD min/max integers; rendered in `K` notation
  (`$150K–$200K`). ~35 of the current 44 listings carry salary; missing values
  are `null`.
- **Location** is country-level (`Argentina` dominates — 40 of 44). Roles are
  remote (`TELECOMMUTE`) for most listings.
- **Company** is the title prefix before `" - "` (e.g. `Coperniq (YC W23)`).
- **`--jobage` and `--page` are client-side:** the portal exposes no server-side
  filter or pagination params, so the CLI fetches the full list once and filters
  locally. `--page` slices 20 results at a time over the filtered set.
- **Long slugs:** some ids exceed 40 chars — grab them from `--format json`/`plain`
  output, not the truncated table column, before passing them to `detail`.
- The CLI retries 429/5xx with exponential backoff. Keep volume low (see the
  personal-use note above).
