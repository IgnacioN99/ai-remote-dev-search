---
name: getonbrd-search
version: 1.1.0
description: >-
  Searches and looks up tech job postings on Get on Board (getonbrd.com), a Latin
  American tech job board. Use ONLY when invoked from the /scrape workflow, or
  when the user explicitly names Get on Board / getonbrd. For a general job search
  ("find jobs", "search jobs") use the /scrape skill instead.
context: fork
enabled: true
allowed-tools: Bash(bun run .agents/skills/getonbrd-search/cli/src/cli.ts *)
---

# Get on Board Search Skill

Search live tech job listings from **Get on Board** (https://www.getonbrd.com), the premier job board for software engineering, tech, and digital talent in Latin America and remote worldwide. Postings are in Spanish and English; the market is Latin America (Argentina, Chile, Colombia, Mexico, Peru, Uruguay, etc.) and remote-global. Many listings publish transparent **USD salary ranges** and explicit remote modalities (100% remote worldwide, locally remote in LatAm, hybrid).

Runs with zero external dependencies via `bun`.

## ⚠️ Personal use only

This uses Get on Board's public REST endpoints (`/api/v0/search/jobs`) and public job detail pages. Keep **request volume low** and do not use it commercially or for bulk scraping.

## When to use this skill

- Search Get on Board's tech and programming openings by role, stack, or company
- Filter by remote work policy (`--remoteOnly`)
- Filter by recency (`--jobage <days>`)
- See USD salary ranges (e.g. `$5,500–$8,000 USD`) directly in results
- Fetch full job descriptions, must-have qualifications, nice-to-have skills, benefits, and apply links

## Commands

### Search job listings

```bash
bun run .agents/skills/getonbrd-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (e.g. `"ruby"`, `"react"`, `"full stack"`, `"backend"`). Optional; omit to list recent programming openings.
- `--jobage <days>` — only listings published within the last N days.
- `--remoteOnly` — only return remote positions.
- `--page <n>` — 1-indexed page number (default `1`).
- `--limit <n>` / `-n <n>` — max results to display (default `20`).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/getonbrd-search/cli/src/cli.ts detail <id|url|slug> [--format json|plain]
```

Accepts:
- A bare slug: `staff-backend-engineer-dugu-remote`
- A relative path: `/jobs/programming/staff-backend-engineer-dugu-remote`
- A full URL: `https://www.getonbrd.com/jobs/staff-backend-engineer-dugu-remote`

## Examples

```bash
# Search for Ruby jobs in table format
bun run .agents/skills/getonbrd-search/cli/src/cli.ts search -q "ruby" --format table

# Search remote backend roles from the last 14 days
bun run .agents/skills/getonbrd-search/cli/src/cli.ts search -q "backend" --remoteOnly --jobage 14 --limit 5 --format table

# Get full job details and requirements
bun run .agents/skills/getonbrd-search/cli/src/cli.ts detail staff-backend-engineer-dugu-remote --format plain
```
