# Remotive URL Reference

Remotive (https://remotive.com) is a remote-work job board and community focused on tech, software development, design, and marketing.

## Endpoints

### 1. Public API Endpoint

```http
GET https://remotive.com/api/remote-jobs?category=software-dev&search={query}
```

- Public API requiring no API keys.
- Query parameters:
  - `category`: `software-dev` (default for engineering roles).
  - `search`: Free text search keywords.
  - `limit`: Integer cap on returned items.

Response JSON format:
```json
{
  "00-warning": "...",
  "job-count": 15,
  "jobs": [
    {
      "id": 2069746,
      "url": "https://remotive.com/remote-jobs/software-development/tech-lead-full-stack-rails-engineer-2069746",
      "title": "Tech Lead Full-Stack Rails Engineer",
      "company_name": "Mitre Media",
      "category": "Software Development",
      "tags": ["api", "docker", "postgresql", "react", "ror", "ruby/rails"],
      "job_type": "full_time",
      "publication_date": "2026-09-14T20:33:27",
      "candidate_required_location": "USA, Canada, USA timezones",
      "salary": "$170k - $200k",
      "description": "<p>Full job HTML...</p>"
    }
  ]
}
```

### 2. Job Detail Page (HTML)

```http
GET https://remotive.com/remote-jobs/software-development/{slug}
```
Embeds `<script type="application/ld+json">` with schema.org `JobPosting` containing full metadata and structured description.
