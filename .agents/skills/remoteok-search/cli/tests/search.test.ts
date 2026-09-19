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

// Live smoke test against the real RemoteOK API. Keeps volume low — a single
// request. The test query is the fork's canonical global-remote role search.
describe("live search", () => {
  test('search -q "ruby on rails" returns ≥1 real result', async () => {
    const result = await runCLI(["search", "-q", "ruby on rails", "--limit", "5", "--format", "json"]);
    expect(result.exitCode).toBe(0);

    const body = parseJSON<SearchResponse>(result);
    expect(body.results.length).toBeGreaterThan(0);

    for (const r of body.results) {
      expect(r.id).toBeTruthy();
      expect(r.title).toBeTruthy();
      expect(r.url).toMatch(/^https:\/\/remoteok\.com\//);
    }
  }, 60000);
});
