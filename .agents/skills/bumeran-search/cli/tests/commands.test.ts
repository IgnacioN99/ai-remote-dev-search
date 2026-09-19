import { afterEach, describe, expect, test } from "bun:test";
import { runSearch } from "../src/commands/search";
import { runDetail } from "../src/commands/detail";
import type { JobCard } from "../src/helpers";

const originalFetch = globalThis.fetch;
const originalStdoutWrite = process.stdout.write;
const originalStderrWrite = process.stderr.write;

function captureStdout(): { get: () => string } {
  let buf = "";
  process.stdout.write = ((chunk: string | Uint8Array) => {
    buf += chunk.toString();
    return true;
  }) as typeof process.stdout.write;
  return { get: () => buf };
}

function captureStderr(): { get: () => string; restore: () => void } {
  let buf = "";
  process.stderr.write = ((chunk: string | Uint8Array) => {
    buf += chunk.toString();
    return true;
  }) as typeof process.stderr.write;
  return { get: () => buf, restore: () => (process.stderr.write = originalStderrWrite) };
}

interface CapturedRequest {
  url: string;
  method: string;
  body: unknown;
}

/** Stub fetch with a canned JSON response, capturing the request that was made. */
function mockFetch(status: number, body: unknown): { req: () => CapturedRequest } {
  let captured: CapturedRequest = { url: "", method: "", body: null };
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    captured = {
      url: typeof input === "string" ? input : input.toString(),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : null,
    };
    return new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return { req: () => captured };
}

function jobCard(overrides: Partial<JobCard> = {}): JobCard {
  return {
    id: "1118391216",
    title: "Desarrollador/a de Software Jr",
    company: "HIPODROMO PALERMO",
    location: "Capital Federal, Buenos Aires",
    date: "05-08-2026",
    url: "https://www.bumeran.com.ar/empleos/desarrollador-jr-hipodromo-palermo-1118391216.html",
    ...overrides,
  };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  process.stdout.write = originalStdoutWrite;
  process.stderr.write = originalStderrWrite;
});

const baseOpts = {
  jobage: 9999,
  page: 1,
  limit: undefined as number | undefined,
  format: "json" as const,
};

describe("runSearch (mocked fetch)", () => {
  test("emits the contract envelope with meta.count/page/total", async () => {
    mockFetch(200, {
      total: 95,
      number: 0,
      size: 1,
      content: [{ id: 1118391216, titulo: "Desarrollador", empresa: "Acme", localizacion: "CABA", fechaPublicacion: "05-08-2026", confidencial: false }],
    });
    const out = captureStdout();

    const code = await runSearch({ ...baseOpts, query: "desarrollador" });
    expect(code).toBe(0);

    const parsed = JSON.parse(out.get());
    expect(parsed.meta).toEqual({ count: 1, page: 1, total: 95 });
    expect(parsed.results).toHaveLength(1);
    expect(parsed.results[0].id).toBe("1118391216");
  });

  test("POSTs to /api/avisos/searchV2 with a query body and 1-indexed→0-indexed page", async () => {
    const mock = mockFetch(200, { total: 0, content: [] });
    captureStdout();

    await runSearch({ ...baseOpts, query: "desarrollador backend", page: 2 });

    const req = mock.req();
    expect(req.method).toBe("POST");
    expect(new URL(req.url).pathname).toBe("/api/avisos/searchV2");
    expect(new URL(req.url).searchParams.get("page")).toBe("1");
    expect(new URL(req.url).searchParams.get("pageSize")).toBe("20");
    const body = req.body as Record<string, unknown>;
    expect(body.query).toBe("desarrollador backend");
    expect(body.internacional).toBe(false);
    expect(body.filtros).toEqual([]);
  });

  test("maps --location to a provincia filter", async () => {
    const mock = mockFetch(200, { total: 0, content: [] });
    captureStdout();

    await runSearch({ ...baseOpts, query: "desarrollador", location: "Córdoba" });

    const body = mock.req().body as { filtros: Array<{ id: string; value: string }> };
    expect(body.filtros).toContainEqual({ id: "provincia", value: "argentina|cordoba" });
  });

  test("maps --jobage to the date bucket filter", async () => {
    const mock = mockFetch(200, { total: 0, content: [] });
    captureStdout();

    await runSearch({ ...baseOpts, query: "desarrollador", jobage: 7 });

    const body = mock.req().body as { filtros: Array<{ id: string; value: string }> };
    expect(body.filtros).toContainEqual({ id: "dias_fecha_publicacion", value: "publicacion-menor-a-7-dias" });
  });

  test("--limit sets pageSize and caps emitted results", async () => {
    const mock = mockFetch(200, {
      total: 5,
      content: [
        { id: 1, titulo: "A", empresa: "X", localizacion: "Y", fechaPublicacion: "01-01-2026", confidencial: false },
        { id: 2, titulo: "B", empresa: "X", localizacion: "Y", fechaPublicacion: "01-01-2026", confidencial: false },
        { id: 3, titulo: "C", empresa: "X", localizacion: "Y", fechaPublicacion: "01-01-2026", confidencial: false },
      ],
    });
    const out = captureStdout();

    await runSearch({ ...baseOpts, query: "dev", limit: 2 });

    expect(new URL(mock.req().url).searchParams.get("pageSize")).toBe("2");
    expect(JSON.parse(out.get()).results).toHaveLength(2);
  });

  test("a 404 from the search endpoint is an error, not an empty result set", async () => {
    mockFetch(404, { error: "not found" });
    const err = captureStderr();
    const out = captureStdout();

    const code = await runSearch({ ...baseOpts, query: "dev" });
    err.restore();

    expect(code).toBe(1);
    expect(out.get()).toBe("");
    expect(JSON.parse(err.get()).error).toMatch(/avisos\/searchV2|Request failed/);
  });

  test("network failure exits 1 with SEARCH_FAILED", async () => {
    globalThis.fetch = (async () => {
      throw new Error("ECONNREFUSED");
    }) as typeof fetch;
    const err = captureStderr();

    const code = await runSearch({ ...baseOpts, query: "dev" });
    err.restore();

    expect(code).toBe(1);
    expect(JSON.parse(err.get()).code).toBe("SEARCH_FAILED");
  });
});

describe("runDetail (mocked fetch)", () => {
  test("GETs fichaAvisoNormalizada and prints the reshaped detail", async () => {
    const mock = mockFetch(200, {
      aviso: {
        id: 1118391216,
        titulo: "Desarrollador/a de Software Jr",
        empresa: { denominacion: "HIPODROMO PALERMO", confidencial: false },
        localizacion: { detalle: "Capital Federal, Buenos Aires, Argentina" },
        fechaPublicacion: "05-08-2026",
        modalidadTrabajo: { nombre: "Híbrido" },
        tipoTrabajo: { nombre: "Full-time" },
        descripcion: "<p>En <strong>Hipódromo</strong> buscamos...</p>",
        seoFriendlyUrl: "/empleos/desarrollador-jr-hipodromo-palermo-1118391216.html",
      },
    });
    const out = captureStdout();

    const code = await runDetail({ id: "1118391216", format: "json" });
    expect(code).toBe(0);

    const req = mock.req();
    expect(req.method).toBe("GET");
    expect(req.url).toContain("/api/candidates/fichaAvisoNormalizada/1118391216");

    const parsed = JSON.parse(out.get());
    expect(parsed.id).toBe("1118391216");
    expect(parsed.company).toBe("HIPODROMO PALERMO");
    expect(parsed.description).toBe("En Hipódromo buscamos...");
    expect(parsed.description).not.toMatch(/<[a-z][^>]*>/i);
  });

  test("accepts a full URL as the id", async () => {
    const mock = mockFetch(200, { aviso: { id: 1118391216, titulo: "X", descripcion: "" } });
    captureStdout();

    const code = await runDetail(
      { id: "https://www.bumeran.com.ar/empleos/x-1118391216.html", format: "json" },
    );
    expect(code).toBe(0);
    expect(mock.req().url).toContain("/fichaAvisoNormalizada/1118391216");
  });

  test("404 exits 1 with NOT_FOUND", async () => {
    mockFetch(404, { error: "not found" });
    const err = captureStderr();

    const code = await runDetail({ id: "1118391216", format: "json" });
    err.restore();

    expect(code).toBe(1);
    expect(JSON.parse(err.get()).code).toBe("NOT_FOUND");
  });

  test("an unparseable id exits 1 with BAD_ID before any request", async () => {
    const err = captureStderr();
    const code = await runDetail({ id: "not-an-id", format: "json" });
    err.restore();
    expect(code).toBe(1);
    expect(JSON.parse(err.get()).code).toBe("BAD_ID");
  });
});
