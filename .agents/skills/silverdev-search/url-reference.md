# Silver.dev Jobs URL Reference

Silver.dev (https://silver.dev/jobs) is a curated job board for Latin American
software engineers hired by US/global (often VC-backed / YC) startups, with USD
salary transparency. Postings are in English; the market is remote-global /
LatAm (mostly Argentina, plus Mexico, Brazil, and Spain).

> Personal use only — keep request volume low (a handful of fetches, not a crawl).

## Access

- `robots.txt` (`https://silver.dev/robots.txt`) is fully permissive:
  `User-agent: * / Allow: /`. A sitemap is published at `/sitemap.xml`.
- No authentication or API key is required to browse listings or detail pages.

## Rendering model

The board is a **client-side SPA** — the `/jobs` page renders all positions from
a full list fetched in the initial HTML, and the role/technology/salary/ordering
filters are applied in the browser (there is **no server-side filter endpoint**).
The CLI therefore fetches the full list once and filters client-side, the same
way `remoteok-search` does.

Crucially, every page embeds a **schema.org JSON-LD graph** in a
`<script type="application/ld+json">` block. That is the preferred data source
(richer and far more stable than the Tailwind markup):

| Page | JSON-LD block |
|------|---------------|
| `GET /jobs` | `{"@type":"ItemList", "numberOfItems":44, "itemListElement":[ {position, item: JobPosting} ... ]}` |
| `GET /jobs/<slug>` | a single `{"@type":"JobPosting", ...}` object |

## Search

```
GET https://silver.dev/jobs
```

One `ItemList` block holds every open position (44 as of the initial recon). Each
`JobPosting` item has these fields (all are used by the CLI):

| JSON-LD path | Meaning | Example |
|--------------|---------|---------|
| `title` | `"Company - Role"`, may carry trailing whitespace | `"Agora - Senior Full Stack Engineer "` |
| `description` | Full plain-text posting (embedded newlines, already decoded) | |
| `datePosted` | ISO-8601 timestamp with offset | `2026-08-04T13:49:06.952+00:00` |
| `validThrough` | Application window end (all share the same current-cycle value) | |
| `employmentType` | Always `FULLTIME` | |
| `hiringOrganization` | `Organization.name` — generic (`"Engineering"`), **not** the employer; use the title prefix for the company | |
| `applicantLocationRequirements` | `Country.name` — the target country | `"Argentina"`, `"Mexico"`, `"Brazil"`, `"Spain"` |
| `jobLocationType` | `TELECOMMUTE` for remote roles (absent on some) | |
| `baseSalary` | `MonetaryAmount{ currency, value: QuantitativeValue{ minValue, maxValue, unitText:"YEAR" } }`, or `null` | `USD 150000–200000` |
| `industry` | e.g. `Technology` | |
| `occupationalCategory` | e.g. `Software Engineering` | |
| `applicationContact` | `ContactPoint.url` — Ashby application link | |

The **per-listing slug is not in the JSON-LD**. It lives only in the rendered
HTML, one `<article>` card per job, in the **same order** as the `itemListElement`
positions:

```html
<article><a href="/jobs/agora-senior-full-stack-engineer">
  <h2>Agora - Senior Full Stack Engineer </h2>
  <p>$150K – $200K • Offers Equity • Offers Bonus</p>  <!-- display-only salary line -->
```

The CLI parses the slug + `<h2>` title from each card and merges them with the
JSON-LD items by normalized title (falling back to same-position matching).

## Detail

```
GET https://silver.dev/jobs/<slug>
```

Returns the same `JobPosting` JSON-LD object as the list page (full description
included — verified identical to the list-page description for the same job). The
`applicationContact.url` is the Ashby apply link.

## Filters (board UI, not server params)

The board exposes client-side filters: role (`Backend`, `Data`, `Founding`,
`Frontend`, `Fullstack`, `Mobile`, `Product`, `QA`), technology (`Ruby on Rails`,
`Python`, `TypeScript`, `Golang`, `React.js`, `Kubernetes`, …), salary floor
(`$50K+`, `$75K+`, `$100K+`), sort (`Date`/`Salary`/`Title`), and `silver` /
`livecoding` / `remote` checkboxes. None map to a server parameter; the CLI's
`--query` (keyword match over title/company/location/category/description) and
`--jobage` (posting-date filter) reproduce the useful ones client-side.

## Quirks

- **Slugs** are `kebab-case`, derived from `"Company - Role"` (`agora-senior-full-stack-engineer`),
  with a random-looking suffix appended on collision (`cognition-deployed-engineer-brmxar`).
  Some exceed 40 chars — grab the id from `--format json|plain` output, not the
  truncated table column.
- **Salary** is stored as USD min/max integers; the board renders them in `K`
  notation (`$150K – $200K`). The CLI emits the same `K`-style label plus the raw
  `salaryMin`/`salaryMax`/`salaryCurrency`. About 35 of 44 listings carry salary.
- **Date** is ISO-8601 with a UTC offset; the CLI normalizes it to `YYYY-MM-DD`.
- **Company** is the title prefix before the first `" - "`. A few odd titles
  (e.g. `Fullstack Engineers who want to move to SF`) have no separator — their
  `company` is `null`.
- All 44 listings are `FULLTIME`; ~31 are `TELECOMMUTE`. Locations are country-level
  (`Argentina` dominates — 40 of 44).
