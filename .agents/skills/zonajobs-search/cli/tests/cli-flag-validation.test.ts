import { describe, test, expect } from "bun:test";
import { runCLI } from "./helpers";

function parsedStderr(stderr: string): { error?: string; code?: string } {
  try {
    return JSON.parse(stderr);
  } catch {
    return {};
  }
}

describe("ZonaJobs CLI flag validation", () => {
  test("--jobage with a non-numeric value exits 1 with BAD_ARG", async () => {
    const result = await runCLI(["search", "-q", "dev", "--jobage", "foo"]);
    expect(result.exitCode).toBe(1);
    const err = parsedStderr(result.stderr);
    expect(err.code).toBe("BAD_ARG");
    expect(err.error).toMatch(/jobage/);
  });

  test("--jobage as a bare flag (no value) exits 1", async () => {
    const result = await runCLI(["search", "-q", "dev", "--jobage"]);
    expect(result.exitCode).toBe(1);
    expect(result.stderr).toBeTruthy();
  });

  test("--page with a non-numeric value exits 1 with BAD_ARG", async () => {
    const result = await runCLI(["search", "-q", "dev", "--page", "abc"]);
    expect(result.exitCode).toBe(1);
    const err = parsedStderr(result.stderr);
    expect(err.code).toBe("BAD_ARG");
    expect(err.error).toMatch(/page/);
  });

  test("--limit with a non-numeric value exits 1 with BAD_ARG", async () => {
    const result = await runCLI(["search", "-q", "dev", "--limit", "xyz"]);
    expect(result.exitCode).toBe(1);
    const err = parsedStderr(result.stderr);
    expect(err.code).toBe("BAD_ARG");
    expect(err.error).toMatch(/limit/);
  });

  test("unknown command exits 1 with BAD_CMD", async () => {
    const result = await runCLI(["frobnicate"]);
    expect(result.exitCode).toBe(1);
    const err = parsedStderr(result.stderr);
    expect(err.code).toBe("BAD_CMD");
  });
});
