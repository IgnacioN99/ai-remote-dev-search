import { describe, test, expect } from "bun:test";
import {
  parseJobCards,
  parseJobDetail,
  extractDivContent,
  relativeDateToISO,
  jobageToSort,
  slugFromUrl,
} from "../src/helpers";

// A single WWR search-page card. Only the anchors parseJobCards reads matter:
// the container <li class=" new-listing-container ">, the /remote-jobs/<slug>
// link, the title span, the company-name <p>, the headquarters <p>, the date <p>,
// and the category chips.
function searchCard(opts: {
  slug: string;
  title: string;
  company?: string;
  hq?: string;
  date?: string;
  categories?: string[];
  ad?: boolean;
}): string {
  const href = opts.ad ? "/listing_ads/11/click?pk=xyz" : `/remote-jobs/${opts.slug}`;
  const cats = (opts.categories ?? [])
    .map((c) => `<p class="new-listing__categories__category"> ${c} </p>`)
    .join("");
  return `<li class=" new-listing-container ">
    <a class="listing-link--unlocked" href="${href}">
      <div class=" new-listing ">
        <div class="new-listing__header">
          <h3 class="new-listing__header__title"><span class="new-listing__header__title__text">${opts.title}</span></h3>
          <div class=" new-listing__header__icons "><p class="new-listing__header__icons__date"> ${opts.date ?? "4d"} </p></div>
        </div>
        <p class="new-listing__company-name"> ${opts.company ?? "Acme"} <img alt="" src="x.svg"/></p>
        <p class="new-listing__company-headquarters"> ${opts.hq ?? "Sweden"} <i class="fa-solid fa-location-dot"></i></p>
        <div class="new-listing__categories">${cats}</div>
      </div>
    </a>
  </li>`;
}

describe("parseJobCards", () => {
  test("extracts id/title/company/location/date/url from a real card", () => {
    const html = searchCard({
      slug: "proxify-ab-senior-ruby-on-rails-developer",
      title: "Senior Ruby on Rails Developer",
      company: "Proxify AB",
      hq: "Sweden",
      date: "4d",
      categories: ["Full-Time", "Anywhere in the World"],
    });
    const [card] = parseJobCards(html);
    expect(card).toBeDefined();
    expect(card.id).toBe("proxify-ab-senior-ruby-on-rails-developer");
    expect(card.title).toBe("Senior Ruby on Rails Developer");
    expect(card.company).toBe("Proxify AB");
    expect(card.location).toBe("Anywhere in the World"); // region chip wins over HQ
    expect(card.url).toBe(
      "https://weworkremotely.com/remote-jobs/proxify-ab-senior-ruby-on-rails-developer",
    );
  });

  test("falls back to company headquarters when no chip looks like a region", () => {
    const html = searchCard({
      slug: "dexcom-senior-software-design-assurance",
      title: "Senior Software Design Assurance",
      hq: "San Diego",
      categories: ["Full-Time"],
    });
    const [card] = parseJobCards(html);
    expect(card.location).toBe("San Diego");
  });

  test("uses a flag-prefixed country chip as the region", () => {
    const html = searchCard({
      slug: "samsara-staff-software-engineer",
      title: "Staff Software Engineer",
      hq: "Remote",
      categories: ["Featured", "Full-Time", "🇺🇸 United States of America"],
    });
    const [card] = parseJobCards(html);
    expect(card.location).toBe("🇺🇸 United States of America");
  });

  test("skips promoted ad cards that link to /listing_ads/", () => {
    const html =
      searchCard({
        slug: "proxify-ab-x",
        title: "Real Job",
        hq: "Sweden",
        categories: ["Anywhere in the World"],
      }) +
      searchCard({
        slug: "metana",
        title: "Promoted Job",
        hq: "Remote",
        categories: ["Full-Time"],
        ad: true,
      });
    const cards = parseJobCards(html);
    expect(cards).toHaveLength(1);
    expect(cards[0].title).toBe("Real Job");
  });

  test("dedupes cards that share the same slug", () => {
    const card = searchCard({
      slug: "dropbox-infrastructure-software-engineer",
      title: "Infrastructure Software Engineer",
      hq: "Remote - Canada",
      categories: ["Full-Time", "Anywhere in the World"],
    });
    expect(parseJobCards(card + card)).toHaveLength(1);
  });

  test("decodes HTML entities in title and company", () => {
    const html = searchCard({
      slug: "gorin-systems-software-ux-ui-design-lead",
      title: "Software UX/UI Design Lead &#8211; REMOTE",
      company: "Gorin Systems &amp; Co",
      hq: "Remote",
      categories: ["Remote"],
    });
    const [card] = parseJobCards(html);
    expect(card.title).toBe("Software UX/UI Design Lead – REMOTE");
    expect(card.company).toBe("Gorin Systems & Co");
  });
});

describe("relativeDateToISO", () => {
  test("converts day/week/month suffixes to an ISO date", () => {
    expect(relativeDateToISO("today")).toBe(new Date().toISOString().slice(0, 10));
    expect(relativeDateToISO("1d")).toBe(
      new Date(Date.now() - 86400000).toISOString().slice(0, 10),
    );
    expect(relativeDateToISO("3w")).toBe(
      new Date(Date.now() - 21 * 86400000).toISOString().slice(0, 10),
    );
    expect(relativeDateToISO("1mo")).toBe(
      new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10),
    );
    expect(relativeDateToISO("4 hours ago")).toBe(new Date().toISOString().slice(0, 10));
  });

  test("returns the raw string when unparseable", () => {
    expect(relativeDateToISO("sometime")).toBe("sometime");
  });
});

describe("jobageToSort", () => {
  test("maps day windows to WWR sort values", () => {
    expect(jobageToSort(1)).toBe("Past 24 Hours");
    expect(jobageToSort(7)).toBe("Past Week");
    expect(jobageToSort(14)).toBe("Past 2 Weeks");
    expect(jobageToSort(30)).toBeNull();
    expect(jobageToSort(0)).toBeNull();
  });
});

describe("slugFromUrl", () => {
  test("extracts a slug from a full detail URL, a bare path, or a bare slug", () => {
    expect(slugFromUrl("https://weworkremotely.com/remote-jobs/proxify-ab-x")).toBe(
      "proxify-ab-x",
    );
    expect(slugFromUrl("/remote-jobs/proxify-ab-x")).toBe("proxify-ab-x");
    expect(slugFromUrl("proxify-ab-x")).toBe("proxify-ab-x");
    expect(slugFromUrl("https://weworkremotely.com/remote-jobs/stripe-head-of-x?q=1")).toBe(
      "stripe-head-of-x",
    );
    expect(slugFromUrl("!!!not a slug!!!")).toBeNull();
  });
});

describe("parseJobDetail", () => {
  test("extracts fields from a detail page", () => {
    const html = `<html><head><script type="application/ld+json">{
      "@type": "JobPosting",
      "title": "X",
      "datePosted": "2026-08-14 10:13:03 UTC",
      "validThrough": "2026-09-13 10:13:03 UTC",
      "employmentType": "Full-Time",
      "baseSalary": { "@type": "MonetaryAmount", "currency": "USD", "value": { "minValue": "0", "maxValue": "0", "unitText": "YEAR" } }
    }</script></head><body>
      <section class="lis-container__header__hero">
        <h1 class="lis-container__header__hero__company-info__title"> Senior Ruby on Rails Developer </h1>
      </section>
      <section class="lis-container__job__sidebar">
        <div class="lis-container__job__sidebar__companyDetails__info__title"><h3> Proxify AB <img src="x.svg"/></h3></div>
        <a class="lis-container__job__sidebar__companyDetails__info__link" href="/company/proxify-ab"><span>View company</span></a>
        <ul class="lis-container__job__sidebar__job-about__list">
          <li> Posted on <span>4 days ago</span></li>
          <li> Apply before <span>Sep 13th, 2026</span></li>
          <li> Job type <a><span class="box box--jobType"><i class="fa-regular fa-clock"></i> Full-Time </span></a></li>
          <li> Category <a><span class="box box--blue"> Back-End Programming </span></a></li>
          <li> Region <div class="boxes"><span class="box box--multi box--region"> Anywhere in the World </span></div></li>
          <li> Skills <div><span class="box box--multi box--blue"> Ruby </span><span class="box box--multi box--blue"> Ruby on Rails </span></div></li>
        </ul>
        <a target="_blank" id="job-cta-alt" href="https://career.proxify.io/apply?utm_source=wwr"> Apply now </a>
      </section>
      <section class="lis-container__job">
        <div class="lis-container__job__content">
          <div class="lis-container__job__content__description">
            <div><h3>The Role:</h3><p>Build things with Ruby.</p></div>
            <div><p>Work from anywhere.</p></div>
          </div>
        </div>
      </section>
    </body></html>`;

    const job = parseJobDetail(html, "proxify-ab-senior-ruby-on-rails-developer");
    expect(job.id).toBe("proxify-ab-senior-ruby-on-rails-developer");
    expect(job.title).toBe("Senior Ruby on Rails Developer");
    expect(job.company).toBe("Proxify AB");
    expect(job.date).toBe("2026-08-14"); // from JSON-LD datePosted
    expect(job.postedOn).toBe("4 days ago");
    expect(job.applyBefore).toBe("Sep 13th, 2026");
    expect(job.employmentType).toBe("Full-Time");
    expect(job.category).toBe("Back-End Programming");
    expect(job.region).toBe("Anywhere in the World");
    expect(job.skills).toBe("Ruby, Ruby on Rails");
    expect(job.applyUrl).toBe("https://career.proxify.io/apply");
    expect(job.companyUrl).toBe("/company/proxify-ab");
    expect(job.description).toContain("Build things with Ruby.");
    expect(job.description).toContain("Work from anywhere.");
  });

  test("returns an empty description when the block is absent", () => {
    const job = parseJobDetail("<html><body>no description here</body></html>", "some-slug");
    expect(job.description).toBeNull();
    expect(job.title).toBe("(untitled)");
  });
});

describe("extractDivContent", () => {
  test("handles nested divs inside the description block", () => {
    const html = `<section class="lis-container__job">
      <div class="lis-container__job__content__description">
        <div>Requirements:</div>
        <ul><li>Ruby</li></ul>
        <div>About:</div>
      </div>
    </section>`;
    expect(extractDivContent(html, "lis-container__job__content__description")).toContain(
      "Requirements:",
    );
    expect(extractDivContent(html, "lis-container__job__content__description")).toContain(
      "About:",
    );
  });

  test("returns null when the class is not found", () => {
    expect(extractDivContent("<div>no class</div>", "nope")).toBeNull();
  });
});
