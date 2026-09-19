# company-careers-cli

Search job listings on **company career pages** backed by Greenhouse, Lever, or Ashby.

One CLI covers any company on those ATS platforms — no per-company code. Pass the company
slug and the backend is auto-detected (or pinned with `--ats`).

## Install & typecheck

```bash
cd .agents/skills/company-careers-search/cli
bun install          # dev types only — zero runtime dependencies
bun run typecheck    # tsc --noEmit
```

## Usage

```bash
# search (JSON by default)
bun run src/cli.ts search -c anthropic -q "software engineer" --format table
bun run src/cli.ts search -c despegar -q "ruby" --limit 10

# detail (by URL or by id + company)
bun run src/cli.ts detail https://job-boards.greenhouse.io/anthropic/jobs/4461450008 --format plain
bun run src/cli.ts detail 4461450008 -c anthropic --format plain
```

## Tests

```bash
bun run test
```

Tests mock `fetch` — no network required, so they are CI-safe. (Live verification is a
manual step; see SKILL.md.)

## Backends

| Backend | List endpoint | Description in |
|---------|--------------|----------------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/<company>/jobs` | single-job `content` |
| Lever | `api.lever.co/v0/postings/<company>?mode=json` | list `descriptionPlain` |
| Ashby | `api.ashbyhq.com/posting-api/job-board/<company>` | list `descriptionHtml` |

See `../url-reference.md` for the exact field anchors to update if a portal changes its API.
