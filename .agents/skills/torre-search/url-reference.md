# Torre API & URL Reference

This document records the endpoint contracts and schema definitions used by the `torre-search` CLI.

## Endpoints

### 1. Search Endpoint (Public REST API)
- **Method:** `POST`
- **URL:** `https://search.torre.co/opportunities/_search/?size={limit}&lang=en[&after={cursor}]`
- **Headers:**
  - `Content-Type: application/json`
  - `User-Agent: Mozilla/5.0 (compatible; torre-search-cli/1.0; +https://github.com/oscarbol09/ai-job-search)`
- **Body Schema:**
  ```json
  {
    "and": [
      { "similarto": { "items": [{ "refId": "Yd6mq4kw", "weight": 0 }] } },
      { "skill/role": { "text": "python", "experience": "potential-to-develop" } },
      { "status": { "code": "open" } },
      { "remote": { "term": true } },
      { "location": { "term": "Colombia" } }
    ]
  }
  ```
  `remote` and `location` clauses are optional.
- **Anchor requirement (observed 2026-10):** a query with no ranking anchor
  (`similarto` or `bestfor`) is rejected with `400 {"meta":{"message":"Invalid request"}}`,
  including the old `skill/role` + `status` body and even a bare `status` filter.
  `bestfor` needs a user (`ggId`/`username`) and personalises ranking, so the CLI
  uses `similarto` on a public posting with `weight: 0`. `skill/role`, `remote`
  and `location` still act as filters. A non-existent `refId` yields
  `500 {"meta":{"message":"Internal shard error"}}` (not retried; override the
  anchor with `TORRE_SEARCH_ANCHOR_ID`).
- **Pagination:** `offset` is ignored (always echoed back as `0`). The response
  carries `pagination.next` (opaque base64 cursor); pass it as `after=` for the
  next page. `pagination.next` is `null` on the last page.
- **Response:** `{ total, size, offset, aggregators, pagination: { previous, next }, results: [...] }`.
  Each result has `id`, `objective`, `organizations[].name`, `locations[]`,
  `remote`, `created`, `compensation.data`, `skills[].name`.

### 2. Detail Endpoint (Public REST API)
- **Method:** `GET`
- **URL:** `https://torre.co/api/suite/opportunities/{id}`
- **Headers:**
  - `Accept: application/json`
  - `User-Agent: Mozilla/5.0 (compatible; torre-search-cli/1.0; +https://github.com/oscarbol09/ai-job-search)`

## Canonical Post URLs
- Format: `https://torre.ai/post/{id}` or `https://torre.co/post/{id}`
