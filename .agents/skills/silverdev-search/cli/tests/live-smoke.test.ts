import { describe, expect, test } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

interface SearchResult {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  date: string | null;
  url: string;
}

/**
 * Live smoke test against Silver.dev's public /jobs page. Keep request volume
 * low — this file performs a single search and a single detail fetch.
 */
describe("live search", () => {
  test('search -q "backend" returns ≥1 real result with id/title/url', async () => {
    const result = await runCLI(["search", "-q", "backend", "--limit", "5", "--format", "json"]);
    expect(result.exitCode).toBe(0);

    const payload = parseJSON<{ meta: { count: number }; results: SearchResult[] }>(result);
    expect(payload.meta.count).toBeGreaterThanOrEqual(1);
    for (const job of payload.results) {
      expect(job.id).toBeTruthy();
      expect(job.title).toBeTruthy();
      expect(job.url).toMatch(/^https:\/\/silver\.dev\/jobs\/[\w-]+$/);
    }
  });

  test("detail on a live slug returns a readable description", async () => {
    const result = await runCLI(["search", "-q", "backend", "--limit", "1", "--format", "json"]);
    expect(result.exitCode).toBe(0);
    const first = parseJSON<{ results: SearchResult[] }>(result).results[0];

    const detail = await runCLI(["detail", first.id, "--format", "json"]);
    expect(detail.exitCode).toBe(0);
    const job = parseJSON<{ id: string; description: string | null }>(detail);
    expect(job.id).toBe(first.id);
    expect(job.description).toBeTruthy();
  });
});
