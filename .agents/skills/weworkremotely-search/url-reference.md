# We Work Remotely URL Reference

Public, unauthenticated pages served by We Work Remotely (Rails). Global, English,
remote-only. No login required for any of these pages.

> Personal use only — this reads WWR's public pages; keep volume low. `robots.txt`
> allows `/remote-jobs/...` and `/categories/...` (only `/admin/`, `/account/`,
> `/manage-company/` and token URLs are disallowed).

## Search

```
GET https://weworkremotely.com/remote-jobs/search?term=<query>
```

Query params:

| Param | Meaning | Example |
|-------|---------|---------|
| `term` | Free-text keyword search (title / skill / role). Matches tokens. | `ruby on rails`, `backend`, `react` |
| `sort` | Recency dropdown value. | `Past 24 Hours` · `Past Week` · `Past 2 Weeks` · `Any Time` |
| `job_filter` | Promotion filter. | `all` (empty) · `hot` · `boosted` |

**Quirks:**
- **Unpaginated.** The endpoint returns *every* match on one page, grouped into
  category sections (`<section class="jobs" id="category-N">`). A `page` param is
  silently ignored. There is no search RSS (`/remote-jobs/search.rss` → 406).
- Keyword matching is token-based and can be selective: `ruby on rails` → 1 result,
  `react` → 3, `backend` → 9, `software` → 58 (checked 2026-08-18).
- Results are anchored at `<li class=" new-listing-container ">`. Promoted/ad
  placements link to `/listing_ads/<n>/click?...` and must be skipped — real jobs
  link to `/remote-jobs/<slug>`.
- The "All jobs" count badge is the first
  `data-job-filter-count>N` on a `data-job-filter-option="all"` button.

### Per-listing field anchors (search page)

| Field | Anchor |
|-------|--------|
| id / url | `href="/remote-jobs/<slug>"` (on `a.listing-link--unlocked`) |
| title | `<span class="new-listing__header__title__text">…</span>` |
| company | `<p class="new-listing__company-name"> Text <img/></p>` (text before the icon `<img>`) |
| location | Region detected from `new-listing__categories__category` chips (e.g. "Anywhere in the World", "North America Only", flag-prefixed countries); falls back to `new-listing__company-headquarters` |
| date | `<p class="new-listing__header__icons__date"> 4d </p>` (relative — converted to ISO) |

## Detail

```
GET https://weworkremotely.com/remote-jobs/<slug>
```

Single listing page (e.g. `/remote-jobs/proxify-ab-senior-ruby-on-rails-developer-ai-augmented-engineering`).

### Rendered HTML anchors

| Field | Anchor |
|-------|--------|
| title | `<h1 class="lis-container__header__hero__company-info__title">…</h1>` |
| company | `lis-container__job__sidebar__companyDetails__info__title` → `<h3> Name <img/></h3>` |
| company URL | `lis-container__job__sidebar__companyDetails__info__link` href |
| posted on | "Posted on `<span>4 days ago</span>`" (in the "About the job" `<ul>`) |
| apply before | "Apply before `<span>Sep 13th, 2026</span>`" |
| job type | `<span class="box box--jobType">…</span>` |
| category | `<span class="box box--blue">…</span>` (first occurrence) |
| region | `<span class="box box--multi box--region">…</span>` |
| skills | the `<li>` beginning "Skills" → its `<span class="box …">` chips |
| description | `<div class="lis-container__job__content__description">…</div>` (depth-tracked div extraction; tags stripped, paragraphs preserved) |
| apply link | `<a id="job-cta-alt" href="https://external.apply…">` |

### JSON-LD

Each detail page embeds one `<script type="application/ld+json">` with `@type: JobPosting`.
It carries `datePosted` (`2026-08-14 10:13:03 UTC`), `validThrough`, `employmentType`,
`occupationalCategory`, `jobLocationType`, `baseSalary` (currency + min/max; WWR emits
`0`/`0` when unspecified), and `hiringOrganization`. Its `url` field is the **apply**
URL, not the listing URL.

**Quirk:** the JSON-LD is *not* strict JSON — HTML-escaped string values
(`&lt;div&gt;`) and literal newlines inside the `description` string make
`JSON.parse` fail. The CLI reads individual top-level string fields with tolerant
regex and treats the rendered HTML as the source of truth, using JSON-LD only to
enrich `date`, `applyBefore`, `employmentType`, and `salary`.

## Also available

- Category/listing pages: `https://weworkremotely.com/categories/remote-<vertical>-jobs`
  (e.g. `remote-back-end-programming-jobs`, `remote-full-stack-programming-jobs`).
  These are paginated server-rendered listings.
- RSS feeds: `https://weworkremotely.com/remote-job-rss-feed` and per-category
  `<category>.rss`. Each `<item>` has `<title>` ("Company: Job Title"), `<region>`,
  `<category>`, a full HTML `<description>`, `<pubDate>` (RFC 2822), and
  `<guid>`/`<link>` (the detail URL). Search has no RSS. These are a convenient
  documented alternative for category browsing, but the CLI uses the search HTML.

## Notes

- No authentication required.
- Respect rate limits — the CLI backs off on 429/5xx.
- Global + English: suitable for remote-global roles; not Argentina-specific.
