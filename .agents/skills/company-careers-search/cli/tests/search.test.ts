import { afterEach, describe, expect, test } from "bun:test";
import { runSearch } from "../src/commands/search";
import { detectBackend } from "../src/helpers";

const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function captureStdout(): { stdout: string; restore: () => void } {
  let stdout = "";
  const orig = process.stdout.write;
  process.stdout.write = ((chunk: string | Uint8Array) => {
    stdout += chunk.toString();
    return true;
  }) as typeof process.stdout.write;
  return { get stdout() { return stdout; }, restore: () => { process.stdout.write = orig; } };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("runSearch", () => {
  test("greenhouse backend emits json with count and results", async () => {
    globalThis.fetch = (async () =>
      jsonResponse({
        jobs: [
          { id: 1, title: "Backend Engineer", company_name: "Anthropic", location: { name: "Remote" }, absolute_url: "u", first_published: "2024-01-01T00:00:00Z" },
        ],
      })) as typeof fetch;

    const cap = captureStdout();
    const code = await runSearch({ company: "anthropic", ats: "greenhouse", jobage: 9999, page: 1, limit: 25, format: "json" });
    cap.restore();

    expect(code).toBe(0);
    const parsed = JSON.parse(cap.stdout);
    expect(parsed.meta.count).toBe(1);
    expect(parsed.results[0].title).toBe("Backend Engineer");
    expect(parsed.results[0].company).toBe("Anthropic");
  });

  test("--query filters by title substring", async () => {
    globalThis.fetch = (async () =>
      jsonResponse({
        jobs: [
          { id: 1, title: "Ruby Engineer", company_name: "GitLab", location: { name: "Remote" }, absolute_url: "u", first_published: "2024-01-01" },
          { id: 2, title: "Data Scientist", company_name: "GitLab", location: { name: "Remote" }, absolute_url: "u2", first_published: "2024-01-01" },
        ],
      })) as typeof fetch;

    const cap = captureStdout();
    const code = await runSearch({ company: "gitlab", ats: "greenhouse", query: "ruby", jobage: 9999, page: 1, limit: 25, format: "json" });
    cap.restore();

    expect(code).toBe(0);
    const parsed = JSON.parse(cap.stdout);
    expect(parsed.meta.count).toBe(1);
    expect(parsed.results[0].title).toBe("Ruby Engineer");
  });

  test("--query matches the description, not just the title", async () => {
    globalThis.fetch = (async () =>
      jsonResponse({
        jobs: [
          { id: 1, title: "Software Engineer", company_name: "Acme", location: { name: "Remote" }, absolute_url: "u", first_published: "2024-01-01", content: "<p>We use Ruby on Rails heavily.</p>" },
        ],
      })) as typeof fetch;

    const cap = captureStdout();
    const code = await runSearch({ company: "acme", ats: "greenhouse", query: "ruby", jobage: 9999, page: 1, limit: 25, format: "json" });
    cap.restore();

    expect(code).toBe(0);
    const parsed = JSON.parse(cap.stdout);
    expect(parsed.meta.count).toBe(1);
    expect(parsed.results[0].title).toBe("Software Engineer");
  });

  test("comma-separated --query ORs the terms", async () => {
    globalThis.fetch = (async () =>
      jsonResponse({
        jobs: [
          { id: 1, title: "Backend Engineer", company_name: "Acme", location: { name: "Remote" }, absolute_url: "u", first_published: "2024-01-01" },
          { id: 2, title: "Frontend Engineer", company_name: "Acme", location: { name: "Remote" }, absolute_url: "u2", first_published: "2024-01-01" },
          { id: 3, title: "Full Stack Developer", company_name: "Acme", location: { name: "Remote" }, absolute_url: "u3", first_published: "2024-01-01" },
        ],
      })) as typeof fetch;

    const cap = captureStdout();
    const code = await runSearch({ company: "acme", ats: "greenhouse", query: "backend engineer,developer", jobage: 9999, page: 1, limit: 25, format: "json" });
    cap.restore();

    expect(code).toBe(0);
    const parsed = JSON.parse(cap.stdout);
    expect(parsed.meta.count).toBe(2); // Backend Engineer + Full Stack Developer, not Frontend
    expect(parsed.results.map((r) => r.title).sort()).toEqual(["Backend Engineer", "Full Stack Developer"]);
  });

  test("pagination slices results with --page and --limit", async () => {
    const jobs = [1, 2, 3].map((i) => ({ id: i, title: `Job ${i}`, company_name: "Acme", location: { name: "X" }, absolute_url: `u${i}` }));
    globalThis.fetch = (async () => jsonResponse({ jobs })) as typeof fetch;

    const cap = captureStdout();
    const code = await runSearch({ company: "acme", ats: "greenhouse", jobage: 9999, page: 2, limit: 2, format: "json" });
    cap.restore();

    expect(code).toBe(0);
    const parsed = JSON.parse(cap.stdout);
    expect(parsed.meta.count).toBe(3); // total filtered
    expect(parsed.results).toHaveLength(1); // page 2 of size 2 -> one item
    expect(parsed.results[0].id).toBe("3");
  });
});

describe("detectBackend", () => {
  test("picks the backend with the most jobs (empty greenhouse vs populated ashby)", async () => {
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("greenhouse")) return jsonResponse({ jobs: [] });
      if (url.includes("ashbyhq")) return jsonResponse({ jobs: [{ id: "1" }, { id: "2" }, { id: "3" }] });
      return new Response("not found", { status: 404 });
    }) as typeof fetch;

    expect(await detectBackend("nubank")).toBe("ashby");
  });

  test("returns null when no backend responds", async () => {
    globalThis.fetch = (async () => new Response("not found", { status: 404 })) as typeof fetch;
    expect(await detectBackend("nonexistent-company")).toBeNull();
  });
});
