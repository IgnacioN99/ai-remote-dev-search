import { describe, test, expect } from "bun:test";
import { parseJobCards, parseJobDetail, slugify, idFromUrl } from "../src/helpers";

// Fixture mirroring the real /trabajo-de-<query> card markup.
function card(opts: {
  id: string;
  title: string;
  slug: string;
  company?: string;
  companyHref?: boolean;
  location?: string;
  date?: string;
}): string {
  const companyHref = opts.companyHref ?? true;
  return `<article class="box_offer  " data-id='${opts.id}' data-blind="false" id="${opts.id}" data-lc="ListOffers-Score4-1" data-offers-grid-offer-item-container>
    <h2 class="fs18 fwB prB">
        <a class="js-o-link fc_base" href="/ofertas-de-trabajo/oferta-de-trabajo-de-${opts.slug}-${opts.id}#lc=ListOffers-Score4-1">
            ${opts.title}
        </a>
        <div class="tags">
            <span class="tag postulated hide" applied-offer-tag>
                <span class="icon i_check_circle_full mr5"></span>
                Postulado
            </span>
        </div>
    </h2>
    <p class="dFlex vm_fx fs16 fc_base mt5">
        ${
          companyHref
            ? `<a class="fc_base t_ellipsis" href="https://ar.computrabajo.com/empresas/ofertas-de-trabajo-de-acme-12345" target='_blank' offer-grid-article-company-url>
                ${opts.company ?? "Acme"}
            </a>`
            : `${opts.company ?? "Importante empresa del sector"}`
        }
    </p>
    <p class="fs16 fc_base mt5">
        <span class="mr10">
            ${opts.location ?? "Buenos Aires"}
        </span>
    </p>
    <p class="fs13 fc_aux mt15">
        ${opts.date ?? "Hace  2  horas"}
    </p>
    <div class="opt_dots" shortcut-show>
        <div class="opt_bubble" shortcut-child>
    </div>
</article>`;
}

describe("parseJobCards", () => {
  test("parses title, company, location, date and URL", () => {
    const html = card({
      id: "5C58C514E05320E961373E686DCF3405",
      title: "Desarrollador Senior NoSQL",
      slug: "desarrollador-senior-nosql-mongodb-backend-c-en-villa-crespo",
      company: "Cognit Labs",
      location: "Villa Crespo, Capital Federal",
      date: "Hace 2 horas",
    });
    const cards = parseJobCards(html);
    expect(cards).toHaveLength(1);
    const c = cards[0];
    expect(c.id).toBe("5C58C514E05320E961373E686DCF3405");
    expect(c.title).toBe("Desarrollador Senior NoSQL");
    expect(c.company).toBe("Cognit Labs");
    expect(c.location).toBe("Villa Crespo, Capital Federal");
    expect(c.date).toBe("Hace 2 horas");
    expect(c.url).toBe(
      "https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-senior-nosql-mongodb-backend-c-en-villa-crespo-5C58C514E05320E961373E686DCF3405",
    );
  });

  test("handles cards without a company anchor (anonymous employer)", () => {
    const html = card({
      id: "234D0B4A468DAE2161373E686DCF3405",
      title: "Programador CNC",
      slug: "programador-cnc-turnos-rotativos-en-rosario",
      companyHref: false,
      location: "Rosario, Santa Fe",
    });
    const cards = parseJobCards(html);
    expect(cards).toHaveLength(1);
    expect(cards[0].company).toBe("Importante empresa del sector");
  });

  test("decodes numeric entities in date (días)", () => {
    const html = card({
      id: "AAA",
      title: "X",
      slug: "x",
      date: "Hace  2  d&#xED;as",
    }).replace("data-id='AAA'", "data-id='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'").replace("/x-AAA#", "/x-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA#");
    const cards = parseJobCards(html);
    expect(cards[0].date).toBe("Hace 2 días");
  });

  test("skips a malformed card without breaking the rest", () => {
    const good = card({
      id: "5C58C514E05320E961373E686DCF3405",
      title: "Desarrollador Senior NoSQL",
      slug: "desarrollador",
    });
    // First card is genuinely broken: a data-id but no js-o-link title anchor.
    const broken = `<article class="box_offer  " data-id='00000000000000000000000000000000'>
      <h2 class="fs18 fwB prB"><span>no link here</span></h2>
      <p class="fs16 fc_base mt5"><span class="mr10">Rosario, Santa Fe</span></p>
    </article>`;
    const cards = parseJobCards(broken + good);
    expect(cards).toHaveLength(1);
    expect(cards[0].id).toBe("5C58C514E05320E961373E686DCF3405");
  });

  test("returns empty array for an empty results page", () => {
    expect(parseJobCards("<html><body><p>No hay ofertas</p></body></html>")).toHaveLength(0);
  });
});

describe("parseJobDetail", () => {
  test("extracts title, company, location, description, requirements and apply URL", () => {
    const html = `<html><head><link rel="canonical" href="https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-5C58C514E05320E961373E686DCF3405" /></head><body>
      <h1 class="fwB fs24 mb5 box_detail w100_m">Desarrollador Senior NoSQL</h1>
      <p class="fs16">Cognit Labs - Villa Crespo, Capital Federal</p>
      <div class="box_border menu_top dFlex" offer-box-container>
        <div class="container">
          <div class="box_detail fl w100_m">
            <div class="mb40 pb40 bb1" div-link="oferta">
              <h3 class="fwB fs18 mb20">Descripción de la oferta</h3>
              <div class="mbB">
                  <span class="tag base mb10">A convenir</span>
                  <span class="tag base mb10">contrato a plazo fijo</span>
                  <span class="tag base mb10">Jornada completa</span>
                  <span class="tag base mb10">Presencial y remoto</span>
              </div>
              <p class="mbB"> Buscamos un desarrollador.<br />Requisitos<br />Python avanzado.<br />MongoDB. </p>
              <p class="fwB fs18 mtB mb10">Requerimientos</p>
              <ul class="disc mbB">
                  <li class='mb10'>Educación mínima: Secundaria</li><li class='mb10'>4 años de experiencia</li>
              </ul>
              <p class="fc_aux fs13 mbB mtB">Palabras clave: python, mongodb</p>
              <p class="fc_aux fs13">Hace  2  horas (actualizada)</p>
              <a data-href-access="https://candidato.ar.computrabajo.com/match/?oi=5C58C514E05320E961373E686DCF3405&amp;p=57" data-href-offer-apply="https://candidato.ar.computrabajo.com/match/?oi=5C58C514E05320E961373E686DCF3405&amp;p=57" class="b_primary big w100 t_no_wrap">
                  Postularme
              </a>
            </div>
          </div>
        </div>
      </div>
    </body></html>`;
    const job = parseJobDetail(html, "5C58C514E05320E961373E686DCF3405");
    expect(job.id).toBe("5C58C514E05320E961373E686DCF3405");
    expect(job.title).toBe("Desarrollador Senior NoSQL");
    expect(job.company).toBe("Cognit Labs");
    expect(job.location).toBe("Villa Crespo, Capital Federal");
    expect(job.salary).toBe("A convenir");
    expect(job.contractType).toBe("contrato a plazo fijo");
    expect(job.schedule).toBe("Jornada completa");
    expect(job.modality).toBe("Presencial y remoto");
    expect(job.description).toContain("Buscamos un desarrollador.");
    expect(job.description).toContain("\nRequisitos\n");
    expect(job.description).toContain("\nPython avanzado.");
    expect(job.requirements).toContain("Educación mínima: Secundaria");
    expect(job.requirements).toContain("4 años de experiencia");
    expect(job.keywords).toBe("python, mongodb");
    expect(job.date).toBe("Hace 2 horas (actualizada)");
    expect(job.applyUrl).toBe("https://candidato.ar.computrabajo.com/match/?oi=5C58C514E05320E961373E686DCF3405&p=57");
    expect(job.url).toBe("https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-5C58C514E05320E961373E686DCF3405");
  });
});

describe("slugify", () => {
  test("multi-word query becomes hyphenated path", () => {
    expect(slugify("ruby on rails")).toBe("ruby-on-rails");
    expect(slugify("desarrollador backend")).toBe("desarrollador-backend");
  });

  test("strips accents and lowercases", () => {
    expect(slugify("Administración")).toBe("administracion");
    expect(slugify("análisis de datos")).toBe("analisis-de-datos");
  });

  test("collapses punctuation", () => {
    expect(slugify("node.js developer")).toBe("node-js-developer");
    expect(slugify("c++")).toBe("c");
  });
});

describe("idFromUrl", () => {
  test("extracts 32-char hex id from an offer URL", () => {
    expect(
      idFromUrl("https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-5C58C514E05320E961373E686DCF3405"),
    ).toBe("5C58C514E05320E961373E686DCF3405");
    expect(idFromUrl("https://ar.computrabajo.com/ofertas-de-trabajo/x-5C58C514E05320E961373E686DCF3405#lc=1")).toBe(
      "5C58C514E05320E961373E686DCF3405",
    );
  });

  test("returns null when no hex id present", () => {
    expect(idFromUrl("https://example.com/foo")).toBeNull();
  });
});
