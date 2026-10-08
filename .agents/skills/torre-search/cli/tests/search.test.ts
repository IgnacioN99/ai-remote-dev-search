import { afterEach, beforeEach, describe, expect, test } from "bun:test"
import {
  buildSearchPayload,
  buildSearchUrl,
  describeSearchError,
  runSearch,
} from "../src/commands/search.js"
import { ApiError, DEFAULT_ANCHOR_ID, apiFetch, resolveAnchorId } from "../src/helpers.js"

// Network-free fixtures shaped like real search.torre.co responses (2026-10).
const PAGE_1 = {
  total: 3,
  size: 2,
  offset: 0,
  aggregators: {},
  pagination: { previous: null, next: "CURSOR_PAGE_2" },
  results: [
    {
      id: "aaaa1111",
      objective: "Full-Stack Python Developer",
      organizations: [{ name: "Example Co" }],
      locations: [],
      remote: true,
      created: "2026-10-06T14:56:19.000Z",
      compensation: { data: null, visible: false },
      skills: [{ name: "Python" }, { name: "Docker" }],
    },
    {
      id: "bbbb2222",
      objective: "Back-End Engineer (Python and SQL)",
      organizations: [{ name: "Jane Doe Labs" }],
      locations: ["Colombia"],
      remote: false,
      created: "2026-10-01T10:00:00.000Z",
      compensation: { data: { currency: "USD", minAmount: 3000, maxAmount: 5000, periodicity: "monthly" } },
      skills: [{ name: "SQL" }],
    },
  ],
}
const PAGE_2 = {
  total: 3,
  size: 2,
  offset: 0,
  aggregators: {},
  pagination: { previous: "CURSOR_PAGE_1", next: null },
  results: [
    {
      id: "cccc3333",
      objective: "Python Software Engineer",
      organizations: [],
      locations: [],
      remote: true,
      created: "2026-09-30T10:00:00.000Z",
      skills: [],
    },
  ],
}

type Call = { url: string; body: any }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

const realFetch = globalThis.fetch
const realStdout = process.stdout.write.bind(process.stdout)
const realStderr = process.stderr.write.bind(process.stderr)
let calls: Call[] = []
let stdout = ""
let stderr = ""

function mockFetch(handler: (url: string, body: any) => Response) {
  globalThis.fetch = (async (input: any, init?: any) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(init.body) : null
    calls.push({ url, body })
    return handler(url, body)
  }) as typeof fetch
}

beforeEach(() => {
  calls = []
  stdout = ""
  stderr = ""
  delete process.env.TORRE_SEARCH_ANCHOR_ID
  ;(process.stdout as any).write = (s: string) => {
    stdout += s
    return true
  }
  ;(process.stderr as any).write = (s: string) => {
    stderr += s
    return true
  }
})

afterEach(() => {
  globalThis.fetch = realFetch
  ;(process.stdout as any).write = realStdout
  ;(process.stderr as any).write = realStderr
  delete process.env.TORRE_SEARCH_ANCHOR_ID
})

describe("buildSearchPayload", () => {
  test("anchors on a similarto clause with weight 0 (Torre rejects unanchored queries)", () => {
    const payload = buildSearchPayload({ query: "python", page: 1, limit: 20, format: "json" })
    expect(payload.and).toBeArray()
    expect(payload.and.length).toBe(3)
    expect(payload.and[0].similarto.items).toEqual([{ refId: DEFAULT_ANCHOR_ID, weight: 0 }])
    expect(payload.and[1]["skill/role"].text).toBe("python")
    expect(payload.and[2].status.code).toBe("open")
  })

  test("uses an explicit anchor id", () => {
    const payload = buildSearchPayload({ query: "go", page: 1, limit: 5, format: "json" }, "Zz9Zz9Zz")
    expect(payload.and[0].similarto.items[0].refId).toBe("Zz9Zz9Zz")
  })

  test("adds location clause when specified", () => {
    const payload = buildSearchPayload({
      query: "react",
      location: "Colombia",
      page: 1,
      limit: 10,
      format: "table",
    })
    expect(payload.and.length).toBe(4)
    expect(payload.and[3].location.term).toBe("Colombia")
  })

  test("'remote' location becomes a server-side remote clause, not a location term", () => {
    const payload = buildSearchPayload({
      query: "node",
      location: "remote",
      remote: true,
      page: 1,
      limit: 10,
      format: "json",
    })
    expect(payload.and.length).toBe(4)
    expect(payload.and[3]).toEqual({ remote: { term: true } })
    expect(payload.and.some((c: any) => "location" in c)).toBe(false)
  })
})

describe("resolveAnchorId", () => {
  test("defaults when env var unset or blank", () => {
    expect(resolveAnchorId({})).toBe(DEFAULT_ANCHOR_ID)
    expect(resolveAnchorId({ TORRE_SEARCH_ANCHOR_ID: "  " })).toBe(DEFAULT_ANCHOR_ID)
  })

  test("accepts a bare id or a post URL", () => {
    expect(resolveAnchorId({ TORRE_SEARCH_ANCHOR_ID: "AbC123xy" })).toBe("AbC123xy")
    expect(resolveAnchorId({ TORRE_SEARCH_ANCHOR_ID: "https://torre.ai/post/AbC123xy" })).toBe("AbC123xy")
  })
})

describe("buildSearchUrl", () => {
  test("sends size and lang, no offset", () => {
    const url = new URL(buildSearchUrl(20))
    expect(url.searchParams.get("size")).toBe("20")
    expect(url.searchParams.get("lang")).toBe("en")
    expect(url.searchParams.has("offset")).toBe(false)
    expect(url.searchParams.has("after")).toBe(false)
  })

  test("passes the pagination cursor as `after`", () => {
    const url = new URL(buildSearchUrl(5, "abc=="))
    expect(url.searchParams.get("after")).toBe("abc==")
  })
})

describe("apiFetch errors", () => {
  test("surfaces Torre's meta.message on 400", async () => {
    mockFetch(() => jsonResponse(400, { meta: { message: "Invalid request" } }))
    const err = await apiFetch("https://example.invalid/x").catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(400)
    expect(err.apiMessage).toBe("Invalid request")
    expect(err.message).toContain("Invalid request")
    expect(calls.length).toBe(1)
  })

  test("does not retry a deterministic shard error", async () => {
    mockFetch(() => jsonResponse(500, { meta: { message: "Internal shard error" } }))
    const err = await apiFetch("https://example.invalid/x").catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(500)
    expect(calls.length).toBe(1)
  })

  test("retries other 5xx with backoff", async () => {
    let n = 0
    mockFetch(() => (++n < 3 ? jsonResponse(503, {}) : jsonResponse(200, { ok: true })))
    const res = await apiFetch<any>("https://example.invalid/x", {}, { baseDelayMs: 1 })
    expect(res.ok).toBe(true)
    expect(calls.length).toBe(3)
  })
})

describe("describeSearchError", () => {
  test("maps anchor failures to ANCHOR_UNAVAILABLE with the env var hint", () => {
    const r = describeSearchError(new ApiError(500, "Internal Server Error", "Internal shard error"), "dead0000")
    expect(r.code).toBe("ANCHOR_UNAVAILABLE")
    expect(r.error).toContain("TORRE_SEARCH_ANCHOR_ID")
    expect(r.error).toContain("dead0000")
  })

  test("maps a generic 400 to API_REJECTED with enabled:false guidance", () => {
    const r = describeSearchError(new ApiError(400, "Bad Request", "Invalid request"), "x")
    expect(r.code).toBe("API_REJECTED")
    expect(r.error).toContain("Invalid request")
    expect(r.error).toContain("enabled: false")
  })

  test("maps 401/403 to AUTH_REQUIRED", () => {
    expect(describeSearchError(new ApiError(401, "Unauthorized", null), "x").code).toBe("AUTH_REQUIRED")
    expect(describeSearchError(new ApiError(403, "Forbidden", null), "x").code).toBe("AUTH_REQUIRED")
  })

  test("falls back to FETCH_FAILED", () => {
    expect(describeSearchError(new Error("network down"), "x")).toEqual({
      error: "network down",
      code: "FETCH_FAILED",
    })
  })
})

describe("runSearch (mocked fetch)", () => {
  test("page 1 returns normalized cards and the next cursor", async () => {
    mockFetch(() => jsonResponse(200, PAGE_1))
    const code = await runSearch({ query: "python", page: 1, limit: 2, format: "json" })
    expect(code).toBe(0)
    expect(calls.length).toBe(1)
    expect(calls[0].body.and[0].similarto.items[0].weight).toBe(0)
    const out = JSON.parse(stdout)
    expect(out.meta).toEqual({ count: 2, page: 1, total: 3, next: "CURSOR_PAGE_2" })
    expect(out.results[0]).toMatchObject({
      id: "aaaa1111",
      title: "Full-Stack Python Developer",
      company: "Example Co",
      location: "Remote",
      url: "https://torre.ai/post/aaaa1111",
      skills: ["Python", "Docker"],
    })
    expect(out.results[1].salary).toBe("USD 3,000 - 5,000 / monthly")
  })

  test("page 2 walks the `after` cursor", async () => {
    mockFetch((url) =>
      new URL(url).searchParams.get("after") === "CURSOR_PAGE_2"
        ? jsonResponse(200, PAGE_2)
        : jsonResponse(200, PAGE_1)
    )
    const code = await runSearch({ query: "python", page: 2, limit: 2, format: "json" })
    expect(code).toBe(0)
    expect(calls.length).toBe(2)
    expect(new URL(calls[0].url).searchParams.has("after")).toBe(false)
    expect(new URL(calls[1].url).searchParams.get("after")).toBe("CURSOR_PAGE_2")
    const out = JSON.parse(stdout)
    expect(out.results.map((r: any) => r.id)).toEqual(["cccc3333"])
    expect(out.meta.next).toBeNull()
  })

  test("page past the end returns no results without extra requests", async () => {
    mockFetch(() => jsonResponse(200, PAGE_2))
    const code = await runSearch({ query: "python", page: 5, limit: 2, format: "json" })
    expect(code).toBe(0)
    expect(calls.length).toBe(1)
    expect(JSON.parse(stdout).results).toEqual([])
  })

  test("env override changes the anchor sent to Torre", async () => {
    process.env.TORRE_SEARCH_ANCHOR_ID = "https://torre.ai/post/Ov3rr1de"
    mockFetch(() => jsonResponse(200, PAGE_2))
    await runSearch({ query: "python", page: 1, limit: 2, format: "json" })
    expect(calls[0].body.and[0].similarto.items[0].refId).toBe("Ov3rr1de")
  })

  test("400 from Torre exits 1 with a JSON error on stderr", async () => {
    mockFetch(() => jsonResponse(400, { meta: { message: "Invalid request" } }))
    const code = await runSearch({ query: "python", page: 1, limit: 2, format: "json" })
    expect(code).toBe(1)
    expect(stdout).toBe("")
    const err = JSON.parse(stderr.trim())
    expect(err.code).toBe("API_REJECTED")
  })

  test("dead anchor exits 1 with ANCHOR_UNAVAILABLE", async () => {
    mockFetch(() => jsonResponse(500, { meta: { message: "Internal shard error" } }))
    const code = await runSearch({ query: "python", page: 1, limit: 2, format: "json" })
    expect(code).toBe(1)
    expect(JSON.parse(stderr.trim()).code).toBe("ANCHOR_UNAVAILABLE")
  })
})
