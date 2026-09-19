---
name: remotive-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search remote developer jobs, tech
  roles, or engineering positions on Remotive (remotive.com) — a leading global
  remote-work job board with high transparency on USD compensation, timezone
  flexibility, and direct client / startup hiring. Invoke it for searching open
  positions, finding Ruby on Rails, backend, full-stack, or React roles globally
  or in Americas/Worldwide timezones, checking USD salary ranges, or looking up a
  specific Remotive posting. Trigger phrases: remotive, remotive jobs, remotive.com,
  trabajo remoto en remotive, remote software jobs, global remote developer, USD remote jobs.
context: fork
enabled: true
allowed-tools: Bash(bun run .agents/skills/remotive-search/cli/src/cli.ts *)
---

# Remotive Search Skill

Search live remote developer and engineering job listings from **Remotive** (https://remotive.com), one of the world's most trusted platforms for global remote tech careers. Postings are in English; roles span worldwide remote, Americas timezones (ideal for Argentina/LatAm), and Europe. Many listings publish transparent **USD salary ranges** directly.

Zero runtime dependencies — runs natively with `bun`.

## ⚠️ Personal use only

This consumes Remotive's official public API (`https://remotive.com/api/remote-jobs`). Keep **request volume low** and respectful.

## When to use this skill

- Search Remotive's software development openings by keyword or stack (Ruby, Rails, React, Backend, etc.)
- Filter by recency (`--jobage <days>`)
- Check USD salary ranges and candidate location requirements (e.g. `Worldwide`, `Americas, Europe`, `USA timezones`)
- Fetch full job descriptions, tech tags, and application instructions

## Commands

### Search job listings

```bash
bun run .agents/skills/remotive-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (e.g. `"ruby"`, `"rails"`, `"react"`, `"backend"`). Optional; omit to list latest software jobs.
- `--jobage <days>` — only listings published within the last N days.
- `--limit <n>` / `-n <n>` — max results to display (default: 20).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/remotive-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

Accepts:
- A numeric Remotive job ID: `2069746`
- A full Remotive job URL: `https://remotive.com/remote-jobs/software-development/tech-lead-full-stack-rails-engineer-2069746`

## Examples

```bash
# Search for Rails roles
bun run .agents/skills/remotive-search/cli/src/cli.ts search -q "rails" --format table

# Search backend roles from the last 14 days
bun run .agents/skills/remotive-search/cli/src/cli.ts search -q "backend" --jobage 14 --format table

# Get full job description and application details
bun run .agents/skills/remotive-search/cli/src/cli.ts detail 2069746 --format plain
```
