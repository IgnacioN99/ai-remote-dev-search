import { describe, expect, test } from "bun:test";
import {
  parseSearchPage,
  parseDetailPage,
  scoreQuery,
  withinDays,
  paginate,
  companyFromTitle,
  salaryLabel,
  type SilverJob,
} from "../src/helpers";

/** A JSON-LD JobPosting object (subset of Silver.dev's schema.org graph). */
function posting(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: "Acme - Senior Backend Engineer",
    description: "Build APIs.\n\nRuby on Rails and PostgreSQL.",
    datePosted: "2026-08-04T13:49:06.952+00:00",
    validThrough: "2026-11-16T18:15:03.598Z",
    employmentType: "FULLTIME",
    hiringOrganization: { "@type": "Organization", name: "Engineering" },
    applicantLocationRequirements: { "@type": "Country", name: "Argentina" },
    jobLocationType: "TELECOMMUTE",
    baseSalary: {
      "@type": "MonetaryAmount",
      currency: "USD",
      value: { "@type": "QuantitativeValue", minValue: 120000, maxValue: 180000, unitText: "YEAR" },
    },
    applicationContact: { "@type": "ContactPoint", url: "https://jobs.ashbyhq.com/Silver/abc/application" },
    industry: "Technology",
    occupationalCategory: "Software Engineering",
    ...overrides,
  };
}

function listPage(items: unknown[]): string {
  return `<html><head>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"ItemList","name":"Open Positions at Silver.dev","numberOfItems":${items.length},"itemListElement":${JSON.stringify(
    items.map((item, i) => ({ "@type": "ListItem", position: i + 1, item })),
  )}}</script>
  </head><body>${card(items, 0, "acme-senior-backend-engineer", "Acme - Senior Backend Engineer")}${card(
    items,
    1,
    "acme-frontend-engineer",
    "Acme - Frontend Engineer &amp; Web",
  )}</body></html>`;
}

function card(items: unknown[], i: number, slug: string, title: string): string {
  return i < items.length
    ? `<article><a href="/jobs/${slug}"><div data-slot="card" class="c"><div class="w-full"><div class="t"><h2>${title}</h2></div></div></div></a></article>`
    : "";
}

describe("parseSearchPage", () => {
  test("extracts id/slug, title, company, location, salary, date, url", () => {
    const html = listPage([posting(), posting({ title: "Acme - Frontend Engineer & Web", baseSalary: null })]);
    const jobs = parseSearchPage(html);

    expect(jobs).toHaveLength(2);

    const first = jobs[0];
    expect(first.id).toBe("acme-senior-backend-engineer");
    expect(first.title).toBe("Acme - Senior Backend Engineer");
    expect(first.company).toBe("Acme");
    expect(first.location).toBe("Argentina");
    expect(first.date).toBe("2026-08-04");
    expect(first.epoch).not.toBeNull();
    expect(first.salary).toBe("$120K–$180K");
    expect(first.salaryMin).toBe(120000);
    expect(first.salaryMax).toBe(180000);
    expect(first.salaryCurrency).toBe("USD");
    expect(first.employmentType).toBe("FULLTIME");
    expect(first.occupationalCategory).toBe("Software Engineering");
    expect(first.applyUrl).toBe("https://jobs.ashbyhq.com/Silver/abc/application");
    expect(first.url).toBe("https://silver.dev/jobs/acme-senior-backend-engineer");

    const second = jobs[1];
    // HTML entity in the card title is decoded for the slug fallback; the
    // JSON-LD title is authoritative.
    expect(second.id).toBe("acme-frontend-engineer");
    expect(second.title).toBe("Acme - Frontend Engineer & Web");
    expect(second.salary).toBeNull();
  });

  test("trims trailing whitespace from titles", () => {
    const html = listPage([posting({ title: "Acme - Senior Backend Engineer " })]);
    expect(parseSearchPage(html)[0].title).toBe("Acme - Senior Backend Engineer");
  });

  test("a missing JSON-LD ItemList yields no jobs instead of crashing", () => {
    expect(parseSearchPage("<html><body>nothing here</body></html>")).toEqual([]);
  });

  test("company extraction: no ' - ' separator leaves company null", () => {
    const jobs = parseSearchPage(listPage([posting({ title: "Fullstack Engineers who want to move to SF" })]));
    expect(jobs[0].company).toBeNull();
    expect(jobs[0].title).toBe("Fullstack Engineers who want to move to SF");
  });
});

describe("parseDetailPage", () => {
  test("returns a full job with description", () => {
    const html = `<html><head><script type="application/ld+json">${JSON.stringify(
      posting(),
    )}</script></head><body></body></html>`;
    const job = parseDetailPage(html, "acme-senior-backend-engineer");
    expect(job).not.toBeNull();
    expect(job!.title).toBe("Acme - Senior Backend Engineer");
    expect(job!.description).toContain("Ruby on Rails and PostgreSQL");
    expect(job!.url).toBe("https://silver.dev/jobs/acme-senior-backend-engineer");
  });

  test("returns null when the page has no JobPosting JSON-LD", () => {
    expect(parseDetailPage("<html><body>gone</body></html>", "x")).toBeNull();
  });
});

describe("salaryLabel", () => {
  test("full range formats as $150K–$200K", () => {
    expect(
      salaryLabel({
        "@type": "MonetaryAmount",
        currency: "USD",
        value: { "@type": "QuantitativeValue", minValue: 150000, maxValue: 200000 },
      }),
    ).toBe("$150K–$200K");
  });
  test("min only formats as $100K+", () => {
    expect(
      salaryLabel({ "@type": "MonetaryAmount", currency: "USD", value: { minValue: 100000 } }),
    ).toBe("$100K+");
  });
  test("null baseSalary returns null", () => {
    expect(salaryLabel(null)).toBeNull();
  });
});

describe("companyFromTitle", () => {
  test("splits on first ' - '", () => {
    expect(companyFromTitle("Coperniq (YC W23) - Full Stack Engineer (Node/React)")).toBe(
      "Coperniq (YC W23)",
    );
  });
  test("null when no separator", () => {
    expect(companyFromTitle("Fullstack Engineers")).toBeNull();
  });
});

describe("search-time helpers", () => {
  function job(overrides: Partial<SilverJob> = {}): SilverJob {
    return {
      id: "x",
      title: "Acme - Senior Backend Engineer",
      company: "Acme",
      location: "Argentina",
      date: "2026-08-04",
      epoch: Date.parse("2026-08-04T13:49:06.952Z"),
      url: "https://silver.dev/jobs/x",
      salary: "$120K–$180K",
      salaryMin: 120000,
      salaryMax: 180000,
      salaryCurrency: "USD",
      employmentType: "FULLTIME",
      industry: "Technology",
      occupationalCategory: "Software Engineering",
      applyUrl: null,
      description: "Build APIs with Ruby on Rails and PostgreSQL.",
      ...overrides,
    };
  }

  test("scoreQuery ranks a title match above a description-only match", () => {
    const titleMatch = job({ title: "Acme - Senior Backend Engineer" });
    const descOnly = job({ title: "Acme - Platform Engineer", description: "We use backend Go services." });
    expect(scoreQuery(titleMatch, "backend")).toBeGreaterThan(scoreQuery(descOnly, "backend"));
  });

  test("withinDays keeps recent jobs and drops old ones", () => {
    const now = Date.now();
    const recent = job({ epoch: now - 5 * 86400 * 1000 });
    const old = job({ epoch: now - 60 * 86400 * 1000 });
    expect(withinDays(recent, 7)).toBe(true);
    expect(withinDays(old, 7)).toBe(false);
    expect(withinDays(old, null)).toBe(true); // no age filter
    expect(withinDays(job({ epoch: null }), 7)).toBe(true); // unknown age kept
  });

  test("paginate slices by PAGE_SIZE", () => {
    const jobs = Array.from({ length: 25 }, (_, i) => job({ id: String(i) }));
    expect(paginate(jobs, 1)).toHaveLength(20);
    expect(paginate(jobs, 2)).toHaveLength(5);
    expect(paginate(jobs, 0)).toHaveLength(20); // coerced to page 1
  });
});
