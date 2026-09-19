import { describe, expect, test } from "bun:test";
import { runCLI } from "./helpers";

describe("Bumeran CLI error contract", () => {
  test("search without a query fails with JSON on stderr and empty stdout", async () => {
    const result = await runCLI(["search"]);
    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr)).toEqual({
      error: "--query is required",
      code: "MISSING_REQUIRED",
    });
  });

  test("detail without an ID fails before making a request", async () => {
    const result = await runCLI(["detail"]);
    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr)).toEqual({
      error: "Job ID or URL is required",
      code: "MISSING_REQUIRED",
    });
  });

  test("an unknown command fails with BAD_CMD", async () => {
    const result = await runCLI(["searchz"]);
    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr).code).toBe("BAD_CMD");
  });
});
