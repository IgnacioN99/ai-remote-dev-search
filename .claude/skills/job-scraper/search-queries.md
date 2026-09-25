# Search Queries for Job Scraper

<!-- SETUP: Customized by running /setup based on your target role and technical skills -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. Active tech & remote CLIs include `linkedin-search`, `silverdev-search`, `getonbrd-search`, `remotive-search`, `remoteok-search`, `weworkremotely-search`, `freehire-search`, and `company-careers-search`.

### Key Company Slugs for `company-careers-search`:
- **Stripe** (`--company stripe`): Global financial infrastructure, world's leading Ruby shop (Sorbet, high-scale APIs).
- **Anthropic** (`--company anthropic`): AI safety & research lab (Claude, Claude Code).
- **OpenAI** (`--company openai`): Frontier models & infrastructure.
- **Perplexity** (`--company perplexity`): AI search, evaluation, and agent orchestration.
- **ARQ Finance** (`--company arq`): Cross-border fintech / digital banking (formerly DolarApp), payments & crypto rails on Ashby.
- **Despegar** (`--company despegar`): Top Argentine tech employer; SOFIA AI platform and Flights backend.
- **GitLab** (`--company gitlab`): 100% remote-global Ruby on Rails architecture.

The `site:` query templates in this file are the **WebSearch fallback** — for portals without a CLI, company career pages, or direct applications.

**Language scope:** queries are written in **English and Spanish** (the two working languages in CLAUDE.md). A posting requiring a language you have not declared as a job condition is excluded before scoring; a posting requiring a higher level than declared (e.g. "fluent English" vs declared B1) is flagged for your judgment, not excluded — see `04-job-evaluation.md`'s Language Gate.

## Search Sites

Primary (Argentina + remote-global tech job boards):
- **getonbrd.com** - Get on Board (premier LatAm tech & remote board; covered by `getonbrd-search` CLI)
- **silver.dev/jobs** - Silver.dev (curated LatAm -> US startups with USD salaries; covered by `silverdev-search` CLI)
- **linkedin.com/jobs** - LinkedIn job listings (remote + Argentina; covered by `linkedin-search` CLI)
- **ar.computrabajo.com** - Computrabajo Argentina (covered by `computrabajo-search` CLI)
- **bumeran.com.ar** - Bumeran Argentina (covered by `bumeran-search` CLI)
- **zonajobs.com.ar** - ZonaJobs Argentina (covered by `zonajobs-search` CLI)

Remote-global boards & Direct Portals:
- **remotive.com** - Remotive (global remote tech & direct clients; covered by `remotive-search` CLI)
- **remoteok.com** - Remote OK (global remote tech; covered by `remoteok-search` CLI)
- **weworkremotely.com** - We Work Remotely (global remote; covered by `weworkremotely-search` CLI)
- **nousresearch.com/careers** - Nous Research (open-source AI lab; direct email to recruiting@nousresearch.com)
- **lemoncash.teamtailor.com** - Lemon Cash (crypto/fintech)
- **cocos-capital.recruitee.com** - Cocos Capital (fintech brokerage)
- **careers-meli.mercadolibre.com** - Mercado Libre (corporate portal; flagged low priority due to guardias)
- **uala.com.ar** - Ualá (fintech portal; flagged caution due to layoffs)
- **revolut.com/careers** - Revolut (global fintech; remote RevFlex & LinkedIn)
- **uber.com/careers** - Uber (global tech platform; corporate careers & LinkedIn)

Secondary (company career pages via Google / direct ATS):
- Direct Google searches with `site:` filters for known target companies and specialized Rails consultancies

## Query Categories

Queries are grouped by priority. Each category is written in English and Spanish.

### Priority 1: Backend / Ruby on Rails (primary role)

These match the strongest, most desired career direction.

```
site:linkedin.com/jobs "Ruby on Rails" developer remote
site:getonbrd.com "Ruby on Rails" OR "ruby developer"
site:remoteok.com "Ruby on Rails" OR "backend developer"
site:weworkremotely.com ruby rails backend
site:ar.computrabajo.com "Ruby on Rails" desarrollador
site:linkedin.com/jobs "desarrollador backend" "Ruby on Rails" Argentina
site:bumeran.com.ar "backend" "Ruby on Rails"
site:zonajobs.com.ar "Ruby on Rails" OR "desarrollador backend"
```

### Priority 1.5: AI-Native & Modernized Rails (high leverage)

Roles seeking Rails engineers who leverage AI coding assistants (Claude Code, Cursor) or build LLM/AI integrations (pgvector, LangChain.rb, embeddings).

```
site:linkedin.com/jobs "Ruby on Rails" AND ("AI" OR "LLM" OR "Cursor" OR "Claude" OR "agents") remote
site:getonbrd.com "Ruby on Rails" ("inteligencia artificial" OR "AI" OR "LLM")
site:weworkremotely.com "rails" ("AI" OR "LLM" OR "vector")
site:remoteok.com "ruby" AI remote
```

### Priority 2: Full-stack (domain expertise)

These match full-stack web development.

```
site:linkedin.com/jobs "full stack developer" "Ruby on Rails" remote
site:remoteok.com "full stack" react rails
site:getonbrd.com "full stack" ruby
site:ar.computrabajo.com "desarrollador full stack" rails OR react
site:bumeran.com.ar "full stack" react
```

### Priority 3: React / TypeScript frontend (adjacent)

Adjacent roles the candidate can pivot into.

```
site:linkedin.com/jobs "react developer" typescript remote
site:getonbrd.com react typescript
site:ar.computrabajo.com "desarrollador react" OR "desarrollador frontend"
site:zonajobs.com.ar react typescript
```

### Priority 4: Broader technical

Wider net for general technical roles.

```
site:linkedin.com/jobs ruby developer remote Argentina
site:ar.computrabajo.com desarrollador ruby OR rails
site:getonbrd.com "software engineer" ruby OR rails
site:remoteok.com postgresql developer
```

### Priority 5: Target company career pages & FinTechs (WebSearch fallback)

Company career pages and portals **not** covered by the standard ATS backend of `company-careers-search`. These queries keep `/scrape` covering them via web search:

```
site:careers.google.com "software engineer" OR "backend engineer"
site:careers.microsoft.com "software engineer" OR "backend"
site:revolut.com/careers "software engineer" OR "backend" OR "site reliability"
site:uber.com/careers "software engineer" OR "backend"
site:nousresearch.com/careers OR "nous research" "engineer"
"Lemon Cash" OR "lemon.me" "trabaja" OR "careers" OR "backend"
"Cocos Capital" "empleos" OR "trabaja" OR "desarrollador"
site:careers-meli.mercadolibre.com "backend" OR "software engineer"
site:uala.com.ar "empleo" OR "trabaja" OR "software"
site:oportunidades.ypf.com tecnología OR datos OR sistemas OR software
"Tiendanube" OR "Nuvemshop" "Ruby on Rails" OR "backend developer"
"OmbuLabs" OR "FastRuby.io" "Ruby on Rails" OR "Rails upgrade"
"WyeWorks" "Ruby on Rails" developer OR engineer
"Apply Digital" "Ruby on Rails" developer
site:linkedin.com/jobs ("Brubank" OR "Naranja X") ("backend" OR "software") Argentina
site:linkedin.com/jobs ("Revolut" OR "Uber") ("software" OR "backend" OR "engineer") Argentina
```

## Location Filter

Remote is the default priority for distributed engineering roles. When evaluating results, verify location against candidate preferences:

- **Ideal:** Fully Remote Global / Worldwide, compatible with candidate timezones, or local hybrid roles within preferred commute range.
- **Acceptable:** Regional remote (e.g. Americas / EMEA / APAC depending on candidate profile) or on-site roles within commute area.
- **Borderline:** On-site roles requiring international relocation — only for verified high-impact opportunities with sponsorship.
- **Excluded:** Roles requiring mandatory physical presence outside candidate eligibility or country restrictions without visa/relocation support.

## Language Filter

Compare vacancy language requirements against the Languages table configured in `CLAUDE.md` / `01-candidate-profile.md`. Postings matching declared working proficiencies are prioritized.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
