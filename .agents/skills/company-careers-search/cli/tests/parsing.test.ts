import { describe, test, expect } from "bun:test";
import { parseGreenhouse, parseLever, parseAshby, parseJobUrl, htmlToText, prettyCompany } from "../src/helpers";

describe("parseGreenhouse", () => {
  test("maps fields and prefers company_name", () => {
    const json = {
      jobs: [
        {
          id: 4461450008,
          title: "Backend Engineer",
          company_name: "Anthropic",
          location: { name: "San Francisco, CA" },
          absolute_url: "https://job-boards.greenhouse.io/anthropic/jobs/4461450008",
          first_published: "2024-12-20T13:53:38-05:00",
        },
      ],
    };
    const [c] = parseGreenhouse(json, "anthropic");
    expect(c.id).toBe("4461450008");
    expect(c.title).toBe("Backend Engineer");
    expect(c.company).toBe("Anthropic");
    expect(c.location).toBe("San Francisco, CA");
    expect(c.date).toBe("2024-12-20T13:53:38-05:00");
    expect(c.url).toContain("/jobs/4461450008");
  });

  test("falls back to updated_at when first_published is absent", () => {
    const json = { jobs: [{ id: 1, title: "T", updated_at: "2025-01-01T00:00:00Z", absolute_url: "u" }] };
    const [c] = parseGreenhouse(json, "acme");
    expect(c.date).toBe("2025-01-01T00:00:00Z");
  });

  test("missing jobs key yields empty list", () => {
    expect(parseGreenhouse({}, "acme")).toEqual([]);
  });
});

describe("parseLever", () => {
  test("maps fields and title-cases the slug company", () => {
    const json = [
      {
        id: "abc-123",
        text: "Desarrollador Ruby on Rails",
        categories: { location: "Buenos Aires" },
        createdAt: 1712320432451,
        hostedUrl: "https://jobs.lever.co/despegar/abc-123",
      },
    ];
    const [c] = parseLever(json, "despegar");
    expect(c.id).toBe("abc-123");
    expect(c.title).toBe("Desarrollador Ruby on Rails");
    expect(c.company).toBe("Despegar");
    expect(c.location).toBe("Buenos Aires");
    expect(c.url).toBe("https://jobs.lever.co/despegar/abc-123");
    expect(c.date).toMatch(/^2024-/); // epoch ms -> ISO
  });

  test("non-array returns empty list", () => {
    expect(parseLever({ foo: 1 }, "acme")).toEqual([]);
  });
});

describe("parseAshby", () => {
  test("maps fields", () => {
    const json = {
      jobs: [
        {
          id: "uuid-1",
          title: "Software Engineer, Developer Platform",
          location: "San Francisco, California",
          publishedAt: "2026-08-24T14:44:49.699+00:00",
          jobUrl: "https://jobs.ashbyhq.com/notion/uuid-1",
        },
      ],
    };
    const [c] = parseAshby(json, "notion");
    expect(c.id).toBe("uuid-1");
    expect(c.title).toBe("Software Engineer, Developer Platform");
    expect(c.company).toBe("Notion");
    expect(c.location).toBe("San Francisco, California");
    expect(c.date).toBe("2026-08-24T14:44:49.699+00:00");
  });
});

describe("description extraction", () => {
  test("greenhouse content", () => {
    const [c] = parseGreenhouse(
      { jobs: [{ id: 1, title: "T", absolute_url: "u", content: "<p>Ruby on Rails</p>" }] },
      "acme",
    );
    expect(c.description).toBe("Ruby on Rails");
  });
  test("lever descriptionPlain", () => {
    const [c] = parseLever([{ id: "1", text: "T", hostedUrl: "u", descriptionPlain: "Rails role" }], "acme");
    expect(c.description).toBe("Rails role");
  });
  test("ashby descriptionHtml", () => {
    const [c] = parseAshby(
      { jobs: [{ id: "1", title: "T", jobUrl: "u", descriptionHtml: "<p>Ruby</p>" }] },
      "acme",
    );
    expect(c.description).toBe("Ruby");
  });
});

describe("parseJobUrl", () => {
  test("greenhouse", () => {
    expect(parseJobUrl("https://job-boards.greenhouse.io/anthropic/jobs/4461450008")).toEqual({
      backend: "greenhouse",
      company: "anthropic",
      id: "4461450008",
    });
  });
  test("lever", () => {
    expect(parseJobUrl("https://jobs.lever.co/despegar/abc-123")).toEqual({
      backend: "lever",
      company: "despegar",
      id: "abc-123",
    });
  });
  test("ashby", () => {
    expect(parseJobUrl("https://jobs.ashbyhq.com/notion/uuid-1")).toEqual({
      backend: "ashby",
      company: "notion",
      id: "uuid-1",
    });
  });
  test("unknown URL returns null", () => {
    expect(parseJobUrl("https://example.com/jobs/1")).toBeNull();
  });
});

describe("htmlToText", () => {
  test("strips tags, keeps paragraph breaks, decodes entities", () => {
    expect(htmlToText("<h1>Who</h1><p>Hello <strong>world</strong> &amp; co</p>")).toBe(
      "Who\nHello world & co",
    );
  });

  test("decodes entity-encoded tags (Greenhouse content) before stripping", () => {
    const out = htmlToText(
      '&lt;div class=&quot;content-intro&quot;&gt;&lt;h2&gt;About&lt;/h2&gt;&lt;p&gt;Mission &amp; goals&lt;/p&gt;&lt;/div&gt;',
    );
    expect(out).toBe("About\nMission & goals");
  });
});

describe("prettyCompany", () => {
  test("title-cases a slug", () => {
    expect(prettyCompany("despegar")).toBe("Despegar");
    expect(prettyCompany("my-company")).toBe("My Company");
  });
});
