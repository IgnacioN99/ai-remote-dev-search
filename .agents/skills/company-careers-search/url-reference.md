# Company Careers URL Reference

Three public, unauthenticated ATS JSON APIs back this skill. Auto-detection probes them
in order (greenhouse → lever → ashby) and uses the first non-404 board.

## Greenhouse

```
# List (no descriptions)
GET https://boards-api.greenhouse.io/v1/boards/<company>/jobs

# List with descriptions (the CLI uses this for search so --query can match descriptions)
GET https://boards-api.greenhouse.io/v1/boards/<company>/jobs?content=true

# Single job (includes "content": "<html>")
GET https://boards-api.greenhouse.io/v1/boards/<company>/jobs/<id>
```

Response shape (list):

```json
{ "jobs": [ { "id": 4461450008, "title": "...", "company_name": "Anthropic",
  "location": { "name": "New York City, NY; ..." },
  "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/4461450008",
  "first_published": "2024-12-20T13:53:38-05:00", "updated_at": "...",
  "requisition_id": "...", "metadata": [...] } ], "meta": { "total": N } }
```

Mapped fields: `id`, `title`, `company_name`, `location.name`, `first_published` (fallback
`updated_at`), `absolute_url`. Description comes from the single-job `content` field.

## Lever

```
# List (includes full description + apply URL)
GET https://api.lever.co/v0/postings/<company>?mode=json
```

Response shape (list) — a top-level JSON array:

```json
[ { "id": "<uuid>", "text": "Job title", "hostedUrl": "https://jobs.lever.co/<company>/<id>",
  "applyUrl": "...", "categories": { "commitment": "Full Time", "location": "Buenos Aires",
  "team": "...", "allLocations": ["Buenos Aires"] },
  "createdAt": 1712320432451, "description": "<html>", "descriptionPlain": "text",
  "workplaceType": "remote" } ]
```

Mapped fields: `id`, `text` (title), `categories.location` (fallback `allLocations[0]`),
`createdAt` (epoch ms), `hostedUrl`. Description from `descriptionPlain` (fallback `description`).
No single-posting endpoint — `detail` re-fetches the list and looks up by id.

## Ashby

```
# List (already includes descriptionHtml)
GET https://api.ashbyhq.com/posting-api/job-board/<company>
```

Response shape (list):

```json
{ "jobs": [ { "id": "<uuid>", "title": "...", "department": "...", "team": "...",
  "employmentType": "FullTime", "location": "San Francisco, California",
  "secondaryLocations": [...], "publishedAt": "2026-08-24T14:44:49.699+00:00",
  "isRemote": true, "workplaceType": "Hybrid",
  "jobUrl": "https://jobs.ashbyhq.com/<company>/<id>",
  "applyUrl": ".../application", "descriptionHtml": "<h1>...</h1>" } ], "total": N }
```

Mapped fields: `id`, `title`, `location`, `publishedAt`, `jobUrl`. Description from
`descriptionHtml` (already present in the list, so `detail` also looks up by id in the list).

## Notes

- All three return 404 for an unknown/empty board slug; a 200 with an empty `jobs`/array is a valid (but empty) board.
- Auto-detect relies on the 404 signal and a recognizable shape (`jobs` array for greenhouse/ashby, top-level array for lever).
- Company slugs are lowercase identifiers from the careers URL; see SKILL.md for examples.
