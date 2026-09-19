import { describe, expect, test } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

// Live smoke test against the real portal. The test query is "ruby on rails";
// if WWR ever returns zero results for it, fall back to "backend" (see SKILL.md).
const TEST_QUERY = "ruby on rails";

describe("weworkremotely live smoke test", () => {
  test("search returns >= 1 real result with id/title/url", async () => {
    const result = await runCLI(["search", "-q", TEST_QUERY, "--limit", "5"]);
    expect(result.exitCode).toBe(0);

    const data = parseJSON<{
      meta: { count: number };
      results: Array<{
        id: string;
        title: string;
        company: string | null;
        location: string | null;
        date: string | null;
        url: string;
      }>;
    }>(result);

    expect(data.results.length).toBeGreaterThan(0);
    const r = data.results[0];
    expect(r.id).toBeTruthy();
    expect(r.title).toBeTruthy();
    expect(r.url).toContain("weworkremotely.com/remote-jobs/");
  });

  test("detail on a search result returns a readable description", async () => {
    const search = await runCLI(["search", "-q", TEST_QUERY, "--limit", "1", "--format", "json"]);
    expect(search.exitCode).toBe(0);

    const data = JSON.parse(search.stdout);
    const id: string | undefined = data.results?.[0]?.id;
    if (!id) return; // nothing to exercise if the portal returned no results

    const detail = await runCLI(["detail", id, "--format", "plain"]);
    expect(detail.exitCode).toBe(0);
    expect(detail.stdout.length).toBeGreaterThan(0);
    expect(detail.stdout).not.toContain("(no description)");
  });
});
