---
name: torre-search
version: 1.1.0
description: >-
  Searches and looks up tech job postings on Torre (torre.ai), a Latin American
  talent platform. Use ONLY when invoked from the /scrape workflow, or when the
  user explicitly names Torre. For a general job search ("find jobs", "search
  jobs") use the /scrape skill instead.
context: fork
enabled: true
allowed-tools: Bash(bun run .agents/skills/torre-search/cli/src/cli.ts *)
---

# Torre Search Skill

Search live tech, software, data, product, and remote job listings from **Torre** (`torre.ai` / `torre.co`).
Powered by Torre's open public REST API — **zero scraping, zero authentication, no API key required**, and **zero runtime dependencies** (runs with pure TypeScript on `bun`).

> Colombian-founded tech and remote talent platform connecting professionals across Colombia,
> Latin America, and globally with top startups, scaleups, and tech enterprises.

## When to use this skill

- Search for software engineering, tech, data, AI, product, and remote roles
- Filter jobs in Colombia, specific LATAM countries, or global remote
- Filter by currency or salary ranges (USD, COP)
- Retrieve rich job details: required skills/strengths, compensation ranges, remote status, and direct apply links

## Commands

### 1. Search job listings

```bash
bun run .agents/skills/torre-search/cli/src/cli.ts search --query "<text>" [flags]
```

Flags:
- `--query, -q <text>`: Role keywords, skills, or job title (e.g. `"python"`, `"fullstack"`, `"react"`, `"data engineer"`). **Required**.
- `--location, -l <country>`: Country restriction (e.g. `"Colombia"`, `"remote"`).
- `--remote`: Filter only remote positions.
- `--page, -p <n>`: 1-indexed page number (default `1`). Torre pages by cursor, so page `n` costs `n` requests; prefer a larger `--limit` over deep paging.
- `--limit, -n <n>`: Cap results emitted (default `20`, max `50`).
- `--format <fmt>`: `json` (default) | `table` | `plain`.

JSON output `meta` carries `count`, `page`, `total` (matches on Torre) and `next` (opaque cursor, `null` on the last page).

#### Search anchor (`TORRE_SEARCH_ANCHOR_ID`)

Since late 2026 `search.torre.co` answers `400 Invalid request` to any opportunity query without a ranking anchor. The CLI anchors every search on an existing public posting through a `similarto` clause with weight `0`, so the anchor does not bias results. If that posting is ever removed, Torre returns `500 Internal shard error` and the CLI exits with code `ANCHOR_UNAVAILABLE`. Fix it by setting `TORRE_SEARCH_ANCHOR_ID` to the ID (or `https://torre.ai/post/<id>` URL) of any live posting.

#### When Torre breaks again

Errors are JSON on stderr with exit code 1. `API_REJECTED` (400) or `AUTH_REQUIRED` (401/403) means Torre changed its public API contract. Until the CLI is fixed, set `enabled: false` in this file's frontmatter so `/scrape` skips Torre instead of failing on it.

### 2. Fetch job detail

```bash
bun run .agents/skills/torre-search/cli/src/cli.ts detail <url-or-id> [--format json|plain]
```

Accepts either a Torre opportunity ID (e.g. `Yd6mq4kw`) or a full URL (`https://torre.ai/post/Yd6mq4kw` or `https://torre.co/post/Yd6mq4kw`).

## Output Schema (Normalized)

```json
{
  "id": "Yd6mq4kw",
  "title": "Fullstack - Python Engineer",
  "company": "Cognits an HTEC Company",
  "location": "Colombia, Guatemala (Remote)",
  "date": "2025-08-29",
  "salary": "USD 3,500 - 5,500 / month",
  "url": "https://torre.ai/post/Yd6mq4kw",
  "skills": ["Python", "JavaScript", "Docker", "Unit testing"]
}
```
