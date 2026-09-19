import { describe, test, expect } from "bun:test";
import {
  parseSearchResponse,
  parseDetailResponse,
  slugify,
  makeAvisoUrl,
  jobageFilter,
  resolveLocation,
  normalizeId,
} from "../src/helpers";

function searchHit(overrides: Record<string, unknown> = {}) {
  return {
    id: 1118391216,
    titulo: "Desarrollador/a de Software Jr",
    empresa: "HIPODROMO PALERMO",
    localizacion: "Capital Federal, Buenos Aires",
    fechaPublicacion: "05-08-2026",
    confidencial: false,
    modalidadTrabajo: "Híbrido",
    ...overrides,
  };
}

describe("parseSearchResponse", () => {
  test("maps content to the contract envelope with id/title/company/location/date/url", () => {
    const { total, results } = parseSearchResponse({
      number: 0,
      size: 1,
      total: 95,
      content: [searchHit()],
    });
    expect(total).toBe(95);
    expect(results).toHaveLength(1);
    const r = results[0];
    expect(r.id).toBe("1118391216");
    expect(r.title).toBe("Desarrollador/a de Software Jr");
    expect(r.company).toBe("HIPODROMO PALERMO");
    expect(r.location).toBe("Capital Federal, Buenos Aires");
    expect(r.date).toBe("05-08-2026");
    expect(r.url).toBe(
      "https://www.bumeran.com.ar/empleos/desarrollador-a-de-software-jr-hipodromo-palermo-1118391216.html",
    );
  });

  test("confidential postings carry a null company", () => {
    const { results } = parseSearchResponse({
      total: 1,
      content: [searchHit({ confidencial: true, empresa: "Confidencial" })],
    });
    expect(results[0].company).toBeNull();
    expect(results[0].url).toBe(
      "https://www.bumeran.com.ar/empleos/desarrollador-a-de-software-jr-1118391216.html",
    );
  });

  test("missing company and location map to null", () => {
    const { results } = parseSearchResponse({
      total: 1,
      content: [searchHit({ empresa: null, localizacion: null })],
    });
    expect(results[0].company).toBeNull();
    expect(results[0].location).toBeNull();
  });

  test("skips hits without a title", () => {
    const { results } = parseSearchResponse({
      total: 2,
      content: [searchHit(), { id: 2, titulo: "" }],
    });
    expect(results).toHaveLength(1);
  });

  test("empty content yields an empty results array", () => {
    const { total, results } = parseSearchResponse({ total: 0, content: [] });
    expect(total).toBe(0);
    expect(results).toHaveLength(0);
  });
});

describe("parseDetailResponse", () => {
  const detailJson = {
    aviso: {
      id: 1118391216,
      titulo: "Desarrollador/a de Software Jr",
      empresa: { denominacion: "HIPODROMO PALERMO", confidencial: false },
      localizacion: { detalle: "Capital Federal, Buenos Aires, Argentina" },
      fechaPublicacion: "05-08-2026",
      modalidadTrabajo: { nombre: "Híbrido" },
      tipoTrabajo: { nombre: "Full-time" },
      tipoContratacion: { nombre: "Indeterminado" },
      nivelLaboral: { nombre: "Junior" },
      descripcion: "<p>En <strong>Hipódromo</strong> buscamos...</p><ul><li>Requisito 1</li></ul>",
      seoFriendlyUrl: "/empleos/desarrollador-a-de-software-jr-hipodromo-palermo-1118391216.html",
    },
  };

  test("extracts fields and converts HTML description to plain text", () => {
    const job = parseDetailResponse(detailJson, "1118391216");
    expect(job.title).toBe("Desarrollador/a de Software Jr");
    expect(job.company).toBe("HIPODROMO PALERMO");
    expect(job.location).toBe("Capital Federal, Buenos Aires, Argentina");
    expect(job.date).toBe("05-08-2026");
    expect(job.modality).toBe("Híbrido");
    expect(job.employmentType).toBe("Full-time");
    expect(job.contractType).toBe("Indeterminado");
    expect(job.seniority).toBe("Junior");
    expect(job.description).toContain("Hipódromo");
    expect(job.description).toContain("Requisito 1");
    expect(job.description).not.toMatch(/<[a-z][^>]*>/i);
    expect(job.url).toBe(
      "https://www.bumeran.com.ar/empleos/desarrollador-a-de-software-jr-hipodromo-palermo-1118391216.html",
    );
  });

  test("confidential detail carries a null company", () => {
    const job = parseDetailResponse(
      {
        aviso: { ...detailJson.aviso, empresa: { denominacion: "Confidencial", confidencial: true } },
      },
      "1118391216",
    );
    expect(job.company).toBeNull();
  });

  test("missing description maps to null", () => {
    const job = parseDetailResponse(
      { aviso: { ...detailJson.aviso, descripcion: "" } },
      "1118391216",
    );
    expect(job.description).toBeNull();
  });

  test("decodes numeric HTML entities in the description", () => {
    const job = parseDetailResponse(
      { aviso: { ...detailJson.aviso, descripcion: "<p>Caf&#233; &#x1f3af;</p>" } },
      "1",
    );
    expect(job.description).toContain("Café 🎯");
  });
});

describe("slugify", () => {
  test("lowercases, strips accents and punctuation, joins with hyphens", () => {
    expect(slugify("Desarrollador/a de Software Jr")).toBe("desarrollador-a-de-software-jr");
    expect(slugify("Administración & Finanzas (Córdoba)")).toBe("administracion-finanzas-cordoba");
  });
});

describe("makeAvisoUrl", () => {
  test("includes company slug when not confidential", () => {
    expect(makeAvisoUrl("1118391216", "Desarrollador Jr", "Hipódromo Palermo", false)).toBe(
      "https://www.bumeran.com.ar/empleos/desarrollador-jr-hipodromo-palermo-1118391216.html",
    );
  });

  test("omits company slug when confidential", () => {
    expect(makeAvisoUrl("1118391216", "Desarrollador Jr", null, true)).toBe(
      "https://www.bumeran.com.ar/empleos/desarrollador-jr-1118391216.html",
    );
  });
});

describe("jobageFilter", () => {
  test("maps days to the smallest covering bucket", () => {
    expect(jobageFilter(1)).toBe("publicacion-menor-a-2-dias");
    expect(jobageFilter(2)).toBe("publicacion-menor-a-2-dias");
    expect(jobageFilter(7)).toBe("publicacion-menor-a-7-dias");
    expect(jobageFilter(15)).toBe("publicacion-menor-a-15-dias");
    expect(jobageFilter(30)).toBe("publicacion-menor-a-1-mes");
    expect(jobageFilter(90)).toBe("publicacion-menor-a-1-mes");
  });

  test("returns null for 0 (no filter) and negatives", () => {
    expect(jobageFilter(0)).toBeNull();
    expect(jobageFilter(-5)).toBeNull();
    expect(jobageFilter(9999)).toBeNull();
  });
});

describe("resolveLocation", () => {
  test("accepts an explicit semantic id", () => {
    expect(resolveLocation("argentina|buenos-aires")).toBe("argentina|buenos-aires");
  });

  test("maps province names (accents-insensitive)", () => {
    expect(resolveLocation("Buenos Aires")).toBe("argentina|buenos-aires");
    expect(resolveLocation("Córdoba")).toBe("argentina|cordoba");
    expect(resolveLocation("cordoba")).toBe("argentina|cordoba");
    expect(resolveLocation("Entre Ríos")).toBe("argentina|entre-rios");
    expect(resolveLocation("Tierra del Fuego")).toBe("argentina|tierra-del-fuego");
  });

  test("maps common city aliases", () => {
    expect(resolveLocation("Capital Federal")).toBe("argentina|buenos-aires");
    expect(resolveLocation("CABA")).toBe("argentina|buenos-aires");
    expect(resolveLocation("GBA")).toBe("argentina|buenos-aires");
  });

  test("returns null for an unknown location", () => {
    expect(resolveLocation("La Plata")).toBeNull();
    expect(resolveLocation("Atlántida")).toBeNull();
    expect(resolveLocation("")).toBeNull();
  });
});

describe("normalizeId", () => {
  test("extracts id from a /empleos/ URL", () => {
    expect(
      normalizeId("https://www.bumeran.com.ar/empleos/desarrollador-jr-hipodromo-palermo-1118391216.html"),
    ).toBe("1118391216");
  });

  test("accepts a bare id", () => {
    expect(normalizeId("1118391216")).toBe("1118391216");
    expect(normalizeId("2188012")).toBe("2188012");
  });

  test("rejects short or non-numeric ids", () => {
    expect(normalizeId("abc")).toBeNull();
    expect(normalizeId("123")).toBeNull();
  });
});
