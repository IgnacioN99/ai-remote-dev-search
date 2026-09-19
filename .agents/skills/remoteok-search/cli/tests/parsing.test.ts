import { describe, test, expect } from "bun:test";
import {
  parseJobs,
  matchesQuery,
  scoreQuery,
  queryTokens,
  withinDays,
  htmlToText,
  decodeHtmlEntities,
  fixMojibake,
  findJob,
} from "../src/helpers";

// RemoteOK's API returns a JSON array: element 0 is a metadata/legal object
// (no `id`), every following element is a full job object. Replicate that shape.
const META = { last_updated: 1787068857, legal: "API Terms of Service: ... link back ..." };

function job(id: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    slug: `remote-senior-ruby-engineer-${id}`,
    id,
    epoch: 1786986875,
    date: "2026-08-17T17:14:35+00:00",
    company: "Acme Corp",
    company_logo: "",
    position: "Senior Ruby Engineer",
    tags: ["ruby", "backend", "dev"],
    description: "<strong>About</strong><br>Build Ruby on Rails APIs.<br><p>Remote-first team.</p>",
    location: "Global, ",
    apply_url: "https://remoteok.com/apply",
    salary_min: 100000,
    salary_max: 140000,
    logo: "",
    url: "https://remoteOK.com/remote-jobs/remote-senior-ruby-engineer-123",
    ...overrides,
  };
}

const PAYLOAD = [META, job("123"), job("456", { position: "React Developer", tags: ["react", "frontend"] })];

describe("parseJobs", () => {
  test("skips the leading metadata object and maps each job", () => {
    const jobs = parseJobs(PAYLOAD);
    expect(jobs).toHaveLength(2);
    expect(jobs[0].id).toBe("123");
    expect(jobs[1].id).toBe("456");
  });

  test("normalizes the mixed-case remoteOK.com URL to lowercase", () => {
    const [j] = parseJobs(PAYLOAD);
    expect(j.url).toBe("https://remoteok.com/remote-jobs/remote-senior-ruby-engineer-123");
  });

  test("falls back to a constructed URL when the url field is empty", () => {
    const jobs = parseJobs([META, job("789", { url: "" })]);
    expect(jobs[0].url).toBe("https://remoteok.com/remote-jobs/remote-senior-ruby-engineer-789");
  });

  test("treats a 0 salary as null", () => {
    const jobs = parseJobs([META, job("111", { salary_min: 0, salary_max: 0 })]);
    expect(jobs[0].salaryMin).toBeNull();
    expect(jobs[0].salaryMax).toBeNull();
  });

  test("cleans trailing punctuation from the location", () => {
    const [j] = parseJobs(PAYLOAD);
    expect(j.location).toBe("Global");
  });

  test("returns empty array for a non-array payload", () => {
    expect(parseJobs({ not: "an array" })).toHaveLength(0);
    expect(parseJobs(null)).toHaveLength(0);
  });

  test("an element without an id is skipped defensively", () => {
    const jobs = parseJobs([META, { slug: "no-id-here", position: "Broken" }, job("999")]);
    expect(jobs).toHaveLength(1);
    expect(jobs[0].id).toBe("999");
  });
});

describe("queryTokens", () => {
  test("drops common stopwords so phrase queries match loosely", () => {
    expect(queryTokens("ruby on rails")).toEqual(["ruby", "rails"]);
    expect(queryTokens("senior in Berlin developer")).toEqual(["senior", "berlin", "developer"]);
  });

  test("lowercases and splits on whitespace", () => {
    expect(queryTokens("  React   Developer ")).toEqual(["react", "developer"]);
    expect(queryTokens("")).toEqual([]);
  });
});

describe("matchesQuery / scoreQuery", () => {
  test("matches a token anywhere in title/company/location/tags/description", () => {
    const [j] = parseJobs(PAYLOAD);
    expect(matchesQuery(j, "ruby on rails")).toBe(true); // rails appears in the description
    expect(matchesQuery(j, "senior ruby engineer")).toBe(true);
    expect(matchesQuery(j, "backend")).toBe(true); // tag match
    expect(matchesQuery(j, "acme")).toBe(true); // company match
    expect(matchesQuery(j, "unrelated tech")).toBe(false);
  });

  test("is case-insensitive", () => {
    const [j] = parseJobs(PAYLOAD);
    expect(matchesQuery(j, "RUBY ON RAILS")).toBe(true);
  });

  test("empty query matches everything", () => {
    const jobs = parseJobs(PAYLOAD);
    expect(matchesQuery(jobs[0], "")).toBe(true);
    expect(matchesQuery(jobs[0], "   ")).toBe(true);
  });

  test("title and tag hits score higher than a description-only hit", () => {
    const [j] = parseJobs(PAYLOAD);
    expect(scoreQuery(j, "senior")).toBe(3); // title word
    expect(scoreQuery(j, "backend")).toBe(2); // tag word
    expect(scoreQuery(j, "rails")).toBe(1); // description-only word
  });
});

describe("withinDays", () => {
  test("null/0/9999 days means no recency filtering", () => {
    const [j] = parseJobs(PAYLOAD);
    expect(withinDays(j, null)).toBe(true);
    expect(withinDays(j, 0)).toBe(true);
    expect(withinDays(j, 9999)).toBe(true);
  });

  test("keeps fresh postings and drops stale ones", () => {
    const now = Math.floor(Date.now() / 1000);
    const fresh = parseJobs([META, job("1", { epoch: now - 60 })])[0];
    const stale = parseJobs([META, job("2", { epoch: now - 86400 * 10 })])[0];
    expect(withinDays(fresh, 7)).toBe(true);
    expect(withinDays(stale, 7)).toBe(false);
  });
});

describe("htmlToText", () => {
  test("strips tags, decodes entities, and preserves paragraph breaks", () => {
    const text = htmlToText("<strong>About</strong><br>Build Ruby on Rails APIs.<br><p>Remote-first team.</p>");
    expect(text).toContain("Build Ruby on Rails APIs.");
    expect(text).toContain("Remote-first team.");
    expect(text).not.toContain("<strong>");
    expect(text).not.toContain("&amp;");
  });

  test("decodes entities", () => {
    expect(decodeHtmlEntities("AT&amp;T &amp; &#233; &#x1F600;")).toBe("AT&T & é 😀");
  });
});

describe("fixMojibake", () => {
  test("repairs double-encoded smart punctuation and dashes", () => {
    expect(fixMojibake("Lemon.io â the marketplace")).toBe("Lemon.io — the marketplace");
    expect(fixMojibake("Itâs a match")).toBe("It’s a match");
    expect(fixMojibake("CafÃ© Ã©")).toBe("Café é"); // CafÃ© → Café, Ã© → é
  });

  test("htmlToText applies the fix so detail output reads cleanly", () => {
    const text = htmlToText("<p>Remote â not a Ã©-role.</p>");
    expect(text).toContain("—");
    expect(text).toContain("é");
    expect(text).not.toContain("â");
  });
});

describe("findJob", () => {
  test("matches by numeric id, slug, or full URL", () => {
    const jobs = parseJobs(PAYLOAD);
    expect(findJob(jobs, "123")?.id).toBe("123");
    expect(findJob(jobs, "remote-senior-ruby-engineer-123")?.id).toBe("123");
    expect(findJob(jobs, "https://remoteok.com/remote-jobs/remote-senior-ruby-engineer-123")?.id).toBe("123");
    expect(findJob(jobs, "https://remoteok.com/remote-jobs/remote-senior-ruby-engineer-123?x=1")?.id).toBe("123");
    expect(findJob(jobs, "does-not-exist")).toBeNull();
  });
});
