# Get on Board Jobs URL Reference

Get on Board (https://www.getonbrd.com) is Latin America's primary tech job board. Postings are in Spanish and English; roles are focused on software engineering, product, DevOps, data, design, and QA across LatAm (Argentina, Chile, Colombia, Mexico, Peru, Uruguay) and global remote.

> Personal use only — keep request volume low and respect endpoints.

## Endpoints

### 1. Search API (JSON)

```http
GET https://www.getonbrd.com/api/v0/search/jobs?query={query}&page={page}&per_page={per_page}
```

- Public endpoint without authentication required.
- Query parameters:
  - `query`: Free-text search string (e.g. `ruby`, `react`, `backend`).
  - `page`: 1-indexed page integer.
  - `per_page`: Number of results per page (up to 50).

Response structure:
```json
{
  "data": [
    {
      "id": "staff-backend-engineer-dugu-remote",
      "type": "job",
      "attributes": {
        "title": "Staff Back-end Engineer",
        "remote": true,
        "remote_modality": "full",
        "countries": ["South America"],
        "min_salary": 5500,
        "max_salary": 8000,
        "published_at": 1789103047,
        "company": {
          "data": { "id": 20469, "type": "company" }
        }
      },
      "links": {
        "public_url": "https://www.getonbrd.com/jobs/staff-backend-engineer-dugu-remote"
      }
    }
  ]
}
```

### 2. Category Programming Endpoint (JSON)

When no search query is specified, recent programming listings are fetched from:
```http
GET https://www.getonbrd.com/api/v0/categories/programming/jobs?page={page}&per_page={per_page}
```

### 3. Company Metadata (JSON)

To resolve company name from ID:
```http
GET https://www.getonbrd.com/api/v0/companies/{id}
```

### 4. Job Detail Page (HTML)

```http
GET https://www.getonbrd.com/jobs/{slug}
```
Redirects to `https://www.getonbrd.com/jobs/{category}/{slug}`.
Embeds schema.org microdata (`itemscope itemtype="http://schema.org/JobPosting"`) and formatted sections:
- `<span itemprop="title">`: Role title
- `<div itemprop="hiringOrganization">`: Company logo & name
- `<span itemprop="minValue">` / `<span itemprop="maxValue">`: Salary numbers
- `<span itemprop="currency">`: USD
- `<div id="job-body">`: Full description, responsibilities, requirements, and perks
- `<div class="gb-tags" itemprop="skills">`: Skill tags
