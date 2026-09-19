import { describe, expect, test } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

interface SearchResult {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  date: string | null;
  url: string;
  [k: string]: unknown;
}

interface SearchResponse {
  meta: { count: number; page: number };
  results: SearchResult[];
}

// Live smoke tests against Computrabajo Argentina's real pages. Keeps volume
// low — two requests: one search + one detail on the first hit. The test query
// is the fork's canonical Argentine market search.
describe("live search", () => {
  test('search -q "desarrollador" returns ≥1 real result', async () => {
    const result = await runCLI(["search", "-q", "desarrollador", "--limit", "5", "--format", "json"]);
    expect(result.exitCode).toBe(0);

    const body = parseJSON<SearchResponse>(result);
    expect(body.results.length).toBeGreaterThan(0);

    for (const r of body.results) {
      expect(r.id).toMatch(/^[0-9A-F]{32}$/);
      expect(r.title).toBeTruthy();
      expect(r.url).toMatch(/^https:\/\/ar\.computrabajo\.com\/ofertas-de-trabajo\//);
    }
  }, 60000);

  test("detail <id> returns a readable description for a search hit", async () => {
    const search = await runCLI(["search", "-q", "desarrollador", "--limit", "1", "--format", "json"]);
    const body = parseJSON<SearchResponse>(search);
    expect(body.results.length).toBeGreaterThan(0);
    const id = body.results[0].id;

    const result = await runCLI(["detail", id, "--format", "plain"]);
    expect(result.exitCode).toBe(0);
    expect(result.stdout.length).toBeGreaterThan(0);
    // Description must be readable text: no leftover HTML tags or entities.
    expect(result.stdout).not.toMatch(/<[a-z][^>]*>/i);
    expect(result.stdout).not.toMatch(/&[a-z]+;/i);
  }, 60000);
});
