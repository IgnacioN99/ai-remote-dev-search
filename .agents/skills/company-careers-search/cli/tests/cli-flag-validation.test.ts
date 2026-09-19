import { describe, test, expect } from "bun:test";
import { runCLI } from "./helpers";

function parsedStderr(stderr: string): { error?: string; code?: string } {
  try {
    return JSON.parse(stderr);
  } catch {
    return {};
  }
}

describe("company-careers CLI flag validation (no network)", () => {
  test("search missing --company exits 1 with NO_COMPANY", async () => {
    const r = await runCLI(["search"]);
    expect(r.exitCode).not.toBe(0);
    expect(parsedStderr(r.stderr).code).toBe("NO_COMPANY");
  });

  test("search --limit NaN exits 1 with BAD_ARG before any request", async () => {
    const r = await runCLI(["search", "-c", "anthropic", "--limit", "xyz"]);
    expect(r.exitCode).not.toBe(0);
    expect(parsedStderr(r.stderr).code).toBe("BAD_ARG");
  });

  test("detail missing id exits 1 with NO_ID", async () => {
    const r = await runCLI(["detail"]);
    expect(r.exitCode).not.toBe(0);
    expect(parsedStderr(r.stderr).code).toBe("NO_ID");
  });

  test("detail with raw id but no --company exits 1 with NO_COMPANY", async () => {
    const r = await runCLI(["detail", "12345"]);
    expect(r.exitCode).not.toBe(0);
    expect(parsedStderr(r.stderr).code).toBe("NO_COMPANY");
  });

  test("unknown command exits 1 with BAD_CMD", async () => {
    const r = await runCLI(["frobnicate"]);
    expect(r.exitCode).not.toBe(0);
    expect(parsedStderr(r.stderr).code).toBe("BAD_CMD");
  });
});
