# RemoteOK URL Reference

Public, unauthenticated JSON API for RemoteOK (https://remoteok.com), the global
remote-work job board. Postings are in English; companies and postings are worldwide
(all remote). Global — no market-specific parameter; one endpoint serves everything.

> Personal use only — RemoteOK's API terms require an attribution link-back to
> RemoteOK ("so we get traffic back from your site"); keep volume low.

## Endpoint

```
GET https://remoteok.com/api
```

No required parameters. **No authentication and no API key.** A browser-like
User-Agent is expected (the CLI sends one).

### Parameters

| Param | Effect | Verified |
|-------|--------|----------|
| *(none)* | Returns the full listing (all active postings) as one JSON array | yes |
| `tags=<tag>` | Server-side filter to postings carrying that tag (e.g. `tags=ruby`) | yes |
| `q` / `query` | **Ignored** — no server-side keyword filter (verified: same full response) | yes |

There is **no** server-side pagination or date-window parameter. `--query`, `--jobage`,
and `--page` in the CLI therefore filter/slice the full listing client-side.

## Response shape

The response is a JSON **array**:

- Element `0` is a **metadata/legal object**:
  ```json
  { "last_updated": 1787068857,
    "legal": "API Terms of Service: Please link back ... mention Remote OK as a source ..." }
  ```
  It has no `id` — parsers must skip it.
- Elements `1..N` are individual job objects.

### Job object fields (verified live)

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (numeric) | Unique posting id — the CLI's `detail` key |
| `slug` | string | URL slug, ends in the id |
| `position` | string | Job title |
| `company` | string | Company name |
| `company_logo` | string | Logo URL (often empty) |
| `location` | string | e.g. `"Global"`, `"US only"`, or a city — often has trailing `", "` that the CLI trims |
| `date` | string | ISO 8601, e.g. `"2026-08-17T17:14:35+00:00"` |
| `epoch` | number | Unix timestamp (seconds) — used for `--jobage` |
| `tags` | string[] | Category tags (e.g. `"dev"`, `"engineer"`, `"customer support"`) |
| `description` | string | Full HTML description (already included — no separate detail fetch needed) |
| `url` | string | Posting URL — emitted as `https://remoteOK.com/...` (mixed-case domain), CLI normalizes to lowercase |
| `apply_url` | string | External apply link |
| `salary_min` | number | Lower bound — `0` when unset (CLI treats `0` as `null`) |
| `salary_max` | number | Upper bound — `0` when unset |
| `logo` | string | Company logo (often empty) |

### Per-result mapping in the CLI

| CLI field | API field | Notes |
|-----------|-----------|-------|
| `id` | `id` | |
| `title` | `position` | |
| `company` | `company` | `null` if empty |
| `location` | `location` | trailing `", "` trimmed; `null` if empty |
| `date` | `date` | ISO string kept as-is |
| `url` | `url` | normalized to `https://remoteok.com/...` |
| `salaryMin`/`salaryMax` | `salary_min`/`salary_max` | `0` → `null` |
| `tags` | `tags` | `null` if empty |
| `applyUrl` | `apply_url` | |

## Detail

`detail` re-fetches `GET https://remoteok.com/api` and selects the posting by
`id` (numeric string), `slug`, or full posting URL — the API already returns the
full `description` for every posting, so there is no separate detail endpoint.

## Notes

- The whole listing is one ~450KB JSON response; fetch it once per command.
- Respect rate limits — the CLI backs off on 429/5xx with exponential backoff.
- **Data quirk:** description/company text is shipped **double-encoded** — the
  original UTF-8 bytes were read as Windows-1252 then re-encoded to UTF-8, so e.g.
  an em dash `—` (U+2014) appears as the three characters `â` `€` `"`. The CLI
  repairs the common sequences (`fixMojibake` in `helpers.ts`).
- If RemoteOK changes the API, the parser anchors to check: the leading metadata
  element (no `id`), and the `position`/`company`/`location`/`description` fields.
