import { describe, expect, test } from "bun:test";
import { runCLI } from "./helpers";

describe("RemoteOK CLI error contract", () => {
  test("detail without an ID fails before making a request", async () => {
    const result = await runCLI(["detail"]);

    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr)).toEqual({
      error: "detail requires an <id|slug|url>",
      code: "NO_ID",
    });
  });

  test("an unknown command fails with JSON on stderr", async () => {
    const result = await runCLI(["frobnicate"]);

    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr).code).toBe("BAD_CMD");
  });

  test("a non-numeric --jobage fails with JSON on stderr before any request", async () => {
    const result = await runCLI(["search", "--jobage", "not-a-number"]);

    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    const err = JSON.parse(result.stderr);
    expect(err.code).toBe("BAD_ARG");
    expect(err.error).toContain("jobage");
  });

  test("a non-numeric --page fails with JSON on stderr before any request", async () => {
    const result = await runCLI(["search", "--page", "abc"]);

    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr).code).toBe("BAD_ARG");
  });

  test("a non-positive --jobage fails with JSON on stderr before any request", async () => {
    const result = await runCLI(["search", "--jobage", "0"]);

    expect(result.exitCode).toBe(1);
    expect(result.stdout).toBe("");
    expect(JSON.parse(result.stderr).code).toBe("BAD_ARG");
  });
});
