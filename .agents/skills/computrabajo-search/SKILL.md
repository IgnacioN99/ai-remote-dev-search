---
name: computrabajo-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs on Computrabajo
  Argentina (https://ar.computrabajo.com), Argentina's largest general job board.
  Postings are in Spanish and the market is Argentina (Buenos Aires, CABA, Córdoba,
  Rosario, Mendoza, remote). Use it to find job listings, search for openings, or
  look up a specific posting on this board. Trigger phrases: "buscar trabajo",
  "ofertas laborales", "empleos", "bolsa de trabajo", "computrabajo", as well as
  English equivalents like find a job, job search, search for jobs, job openings,
  vacancies, hiring, look up this job posting (on Computrabajo Argentina).
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/computrabajo-search/cli/src/cli.ts *)
---

# Computrabajo Argentina Search Skill

Search live job listings from **Computrabajo Argentina** (https://ar.computrabajo.com),
Argentina's largest general job board. Postings are in **Spanish**; the market is
**Argentina**. No authentication, no API key, and **zero runtime dependencies** — it
runs with just `bun`.

## ⚠️ Personal use only

This uses Computrabajo's public job pages. The portal's `robots.txt` disallows several
internal/filtered paths (e.g. `/Ajax/*`, `/_services/*`, CV-hosted pages) and automated
access may be against its terms of use, so **keep volume low and don't use it
commercially or for bulk data collection.** Run it on your own responsibility.

## When to use this skill

- Search for job openings on Computrabajo Argentina by role or skill
- Filter by how recently a posting was published
- Get the full description, requirements, and apply link for a specific posting

## Commands

### Search job listings

```bash
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search --query "<role>" [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — **required.** A role, skill, or free-text query in
  Spanish, e.g. `"desarrollador"`, `"desarrollador backend"`, `"ruby on rails"`.
  There is **no separate location filter** — include the city in the query to scope a
  location (e.g. `-q "desarrollador Buenos Aires"`).
- `--jobage <days>` — only postings published in the last N days (maps to the portal's
  `pubdate` parameter). Omit for all postings.
- `--page <n>` — page number (1-indexed, 20 results per page).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/computrabajo-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the 32-character hex job ID from `search` results (e.g.
`5C58C514E05320E961373E686DCF3405`). You may also pass a full Computrabajo offer URL
(e.g. `https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-5C58C514E05320E961373E686DCF3405`).
Returns the full description, salary/contract/schedule/modality tags, requirements,
keywords, and the apply link.

## Usage examples

```bash
# Developer roles (the canonical Argentine market search)
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "desarrollador" --format table

# Backend developer roles, last 7 days
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "desarrollador backend" --jobage 7 --limit 10 --format json

# Ruby on Rails roles
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "ruby on rails" --format table

# Second page of results
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "analista de datos" --page 2 --format table

# Full details for a specific posting
bun run .agents/skills/computrabajo-search/cli/src/cli.ts detail 5C58C514E05320E961373E686DCF3405 --format plain

# Pass a full offer URL instead of the bare ID
bun run .agents/skills/computrabajo-search/cli/src/cli.ts detail "https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-senior-nosql-mongodb-backend-c-en-villa-crespo-5C58C514E05320E961373E686DCF3405" --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- **Data source**: Computrabajo's public, server-rendered HTML — no credentials required.
- **Query slugs**: the query is lowercased, accents are stripped, and spaces/punctuation
  become hyphens (`ruby on rails` → `trabajo-de-ruby-on-rails`; `administración` →
  `trabajo-de-administracion`). An accented slug 301-redirects to the stripped form,
  which `fetch` follows automatically.
- **Phrase matching**: multi-word queries are tokenized; a narrow phrase such as
  `ruby on rails` can return an empty page even though `ruby` alone has postings. If a
  phrase returns 0 results, try dropping a word.
- **Page size**: fixed at 20 results per page (`?p=<n>`, 1-indexed).
- **Posting age**: `--jobage <days>` maps to the portal's `pubdate=<days>` filter.
- **Dates**: shown as relative Spanish text on both search and detail pages
  (e.g. `Hace 2 horas`, `Hace 3 días`).
- Computrabajo may rate-limit; the CLI retries 429/5xx with exponential backoff. Keep
  volume low (see the personal-use note above).
