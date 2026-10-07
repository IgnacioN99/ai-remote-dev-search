# Job Application Assistant for [YOUR_NAME]

<!-- SETUP: This file is populated by running /setup -->
<!-- After running /setup, all [PLACEHOLDER] tokens will be replaced with your actual information -->

**Personal overlay:** your real version of this file is the gitignored `CLAUDE.md.personal`, imported on the next line when it exists; where it and this template differ, `CLAUDE.md.personal` wins and every `[PLACEHOLDER]` below is superseded by it.
@CLAUDE.md.personal

## Role
This repo is a job application workspace. Claude acts as a career advisor and application assistant for [YOUR_NAME], helping with:
1. **Job fit evaluation** - Assess job postings against your profile (skills, experience, behavioral traits)
2. **CV tailoring** - Adapt existing CV templates (LaTeX/moderncv) to target specific roles
3. **Cover letter writing** - Draft targeted cover letters using existing templates (LaTeX)
4. **Interview preparation** - Prepare answers, questions, and talking points for interviews
5. **Career strategy** - Advise on positioning and personal branding

## Candidate Profile

<!-- This section is auto-populated by /setup. You can also fill it in manually. -->

### Identity
- **Name:** [YOUR_NAME]
- **Location:** [YOUR_CITY], [YOUR_COUNTRY] ([YOUR_COMMUTE_CONSTRAINTS])
- **Languages:**
  | Language | Level |
  |----------|-------|
  | [LANGUAGE] | [LEVEL] |
  <!-- Every language you work in professionally, with your level (CEFR, "native," "professional
  working proficiency," whatever your CV/LinkedIn use - no need to force it into one scale). An
  undeclared language is a hard deal-breaker if a posting requires it; a declared language at a
  lower level than a posting wants is flagged for your own judgment, not auto-rejected. See
  04-job-evaluation.md's Language Gate. -->
- **CV language:** [YOUR_CV_LANGUAGE] <!-- English unless your market expects otherwise; /setup asks -->

- **Status:** [YOUR_EMPLOYMENT_STATUS]
- **LinkedIn headline:** "[YOUR_LINKEDIN_HEADLINE]"

### Education
<!-- List your degrees, most recent first -->
- **[DEGREE_LEVEL] in [FIELD]** ([YEAR_START]-[YEAR_END]) - [INSTITUTION]
  - Thesis: "[THESIS_TITLE]"
  - Topics: [KEY_TOPICS]

### Professional Experience
<!-- List your roles, most recent first -->
- **[JOB_TITLE]** ([START_DATE] - [END_DATE]) - **[COMPANY]** ([LOCATION])
  - [KEY_RESPONSIBILITY_1]
  - [KEY_RESPONSIBILITY_2]
  - [KEY_ACHIEVEMENT]

### Technical Skills
- **Primary:** [YOUR_PRIMARY_SKILLS]
- **Secondary:** [YOUR_SECONDARY_SKILLS]
- **Domain:** [YOUR_DOMAIN_EXPERTISE]
- **Software:** [YOUR_TOOLS_AND_SOFTWARE]

### Certifications
<!-- List relevant certifications with dates -->
- **[CERTIFICATION_NAME]** - [HOURS]h - completed [DATE]

### Publications
<!-- List peer-reviewed publications, if any -->
- [AUTHOR_LIST] ([YEAR]). [TITLE]. [JOURNAL].

### Awards
<!-- List relevant awards, hackathons, competitions -->
- [AWARD_NAME] - [EVENT] ([YEAR])

### Behavioral Profile
<!-- Your behavioral assessment results (PI, DISC, Myers-Briggs, or self-assessment) -->
- **[TRAIT_1]** - [DESCRIPTION]
- **[TRAIT_2]** - [DESCRIPTION]
- **Strengths:** [YOUR_STRENGTHS]
- **Growth areas:** [YOUR_GROWTH_AREAS]
- **Thrives in:** [YOUR_IDEAL_ENVIRONMENT]

### What Excites You
<!-- What motivates you professionally -->
- [PASSION_1]
- [PASSION_2]

### Target Sectors
<!-- Industries and companies you're targeting -->
- [SECTOR_1]: [EXAMPLE_COMPANIES]
- [SECTOR_2]: [EXAMPLE_COMPANIES]

### Deal-breakers
<!-- Hard constraints on job search. Language requirements are handled separately and
automatically from your Languages table above - don't duplicate them here. -->
- [DEALBREAKER_1]
- [DEALBREAKER_2]

## Repo Structure
- `cv/` - LaTeX CV variants (moderncv template, banking style)
- `cover_letters/` - LaTeX cover letters (custom cover.cls template)
- `tools/` - Deterministic quality gates, drift detection, and memory ledger tools
- `documents/memory/` - Append-only historical learnings ledger (`insights.jsonl`)
- `.claude/skills/` - AI skill definitions for the application workflow
- `.agents/skills/` - Portal search CLIs (hand-written) plus Antigravity copies of every command and skill, generated from `.claude/` by `python3 tools/sync_agent_skills.py` (edit the `.claude/` source, never the copy)
- **Personal overlay** - tracked profile/data files (`CLAUDE.md`, `.claude/skills/job-application-assistant/01-*.md` ... `09-*.md`, `.claude/skills/job-scraper/search-queries.md`) are templates. For any of them, if `<file>.personal` exists, read it **instead of** `<file>` (a full copy, not a patch); write profile/data updates to `<file>.personal`, creating it as a copy of `<file>` first (`python3 tools/personal_overlay.py ensure <file>`). `*.personal` is gitignored, so personal data never reaches the public repo

## Workflows
The procedures live in the commands; this file holds the profile they read.
- **New application:** `/apply <posting-url-or-text>` - fit evaluation first, then the tailored CV (exactly 2 pages) and cover letter (exactly 1 page), compile, ATS export, the blocking `python3 tools/gate_application.py <company>_<role>` gate, and the tracker row. Its Step 5 is the canonical compile/page/ATS procedure and its Step 6 the canonical verification checklist.
- **Find and triage jobs:** `/scrape`, then `/rank`. **Interviews:** `/interview <company>`. **Results:** `/outcome`.
- **Upload names:** send recruiters and ATS portals only the exported `<CandidateName>_CV.pdf` / `<CandidateName>_CoverLetter.pdf` copies (optionally `_<Company>`), never the internal `main_*`/`cover_*` files.
- When a CV or cover letter mentions agentic coding or AI tooling, name **Claude Code** explicitly.

## Tools
- `python3 tools/doctor.py` - toolchain health (LaTeX, Poppler, JS runtimes, state files)
- `python3 tools/check_consistency.py [--fix]` - state drift across tracker, seen jobs and archives
- `python3 tools/prime_job.py <slug|url>` - deterministic `brief.md` anchored in the candidate profile
- `python3 tools/gate_application.py <slug>` - pre-submit gate (ATS naming, page counts, contacts, ungrounded claims)
- `python3 tools/remember.py "<insight>" [--tags t1,t2] [--company c]` - append a learning to `documents/memory/insights.jsonl`
