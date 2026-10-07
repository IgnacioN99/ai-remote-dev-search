---
name: job-application-assistant
description: >-
  Answers ad-hoc questions about the candidate's profile, CV and cover-letter craft: a quick fit
  read on a posting, rewording a CV bullet or letter paragraph, application-form answers,
  positioning and career strategy. Use when the user asks such a question without a slash
  command (keywords: CV, resume, cover letter, job fit, profile, career). Writing a CV or cover
  letter for a posting goes to /apply, interview preparation to /interview, application news
  (rejection, offer, invite) to /outcome, and finding jobs to /scrape.
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Bash, Edit, Write, AskUserQuestion
framework_version: 1.3.8
---

# Job Application Assistant

**Personal overlay:** every profile/data file this spec names (`CLAUDE.md`, the job-application-assistant `01-*.md` ... `09-*.md` files, `job-scraper/search-queries.md`, the master CV `cv/main_example.tex`) may have a gitignored `<file>.personal` beside it. When it exists, read it **instead of** the tracked file - it is the candidate's full copy, and the tracked file is a placeholder template. Write candidate data only to `<file>.personal`; when it is missing, create it first with `python3 tools/personal_overlay.py ensure <file>` (copies the template) and edit the copy. Never write candidate data into the tracked file.

---

## Routing - check this first

This skill handles ad-hoc questions. Hand the larger flows to their commands, which carry the compile checks, the quality gate and the tracker writes:

- The user wants a **CV or cover letter for a posting** (apply, tailor, write, draft - one document or both, URL or pasted text): run `/apply <url-or-text>`. `/apply` is the only path that drafts these documents; this skill never drafts one from scratch.
- The user has an **interview** on a tracked application: run `/interview <company>`.
- The user reports **news on an application** ("I got rejected", "they made an offer", "I got an interview invite", "I submitted it"): tell them to run `/outcome <company>` to record it; for scheduling or preparing the interview itself, `/interview <company>`.
- The user wants **new jobs** found: run `/scrape`; to triage what it found, `/rank`.

Use the steps below only for a single piece the user asks for explicitly (an evaluation alone, an edit to an existing document, one answer). **Any change to an existing CV or cover letter** - even one bullet - is followed by `/apply` Steps 5a-5d and 5f-5g and the Step 6 checklist (`.claude/commands/apply.md`) before the result is presented.

## Workflow

### Step 1: Research & Evaluate Fit
- Fetch the job posting content (use WebFetch for URLs). **A 403 is not a dead end** - follow the escalation order in `09-web-research.md` before concluding a page is unavailable, and prefer the employer's own careers posting over an aggregator listing
- Keep the **full posting text verbatim** for Step 3b to archive - never a summary
- Analyze the posting for required competencies, keywords, and priorities
- Research the company (website, LinkedIn, mission, recent news), per `09-web-research.md`
- Score the posting against the candidate's profile using the framework in `04-job-evaluation.md`
- Present the evaluation table and verdict
- Suggest whether the candidate should call the employer before applying (see `04-job-evaluation.md` for guidance)
- Ask the user if they want to proceed with an application; on yes, run `/apply` on the posting (it re-runs the evaluation with its own anchoring brief)

### Step 2: Edit an Existing CV
- A new CV for a posting is drafted by `/apply`, not here. This step edits a `cv/main_<company>_<role>.*` that already exists (a reworded bullet, a fact the user corrected).
- Before editing either document, derive `<company>_<role>` once by the **Subfolder naming** rule in `documents/README.md`; reuse that exact value for the CV, cover letter, and Step 3b archive path. If the rule says to stop because the derived name is empty, stop before creating any file.
- Follow the guidelines in `05-cv-templates.md`; keep every claim grounded in the profile
- After the edit, run `/apply` Steps 5a-5d (compile, layout, iterate, ATS check), 5f-5g (re-export, blocking gate) and the Step 6 checklist, and report their output before presenting the CV

### Step 3: Edit an Existing Cover Letter
- A new cover letter for a posting is drafted by `/apply`, not here. This step edits a `cover_letters/cover_<company>_<role>.*` that already exists.
- Follow the writing style rules in `03-writing-style.md` (critical: no em-dashes, no cliches) and the template structure in `06-cover-letter-templates.md`
- After the edit, run the same `/apply` Steps 5a-5d, 5f-5g and Step 6 checklist as in Step 2 before presenting the letter

### Step 3b: Record the Application
- Run this after an edit in Step 2 or 3, once both documents exist. A CV or cover letter alone is not yet an application.
- Follow **`/apply` Step 6b** (`.claude/commands/apply.md`) exactly: same header, same match-then-update rule, same `drafted` row, same posting archive, same prohibition on touching `job_scraper/seen_jobs.json`. It is stated there once so the two paths cannot drift. Four of its values are named in `/apply`'s own terms: `cv_file`/`cover_letter_file` are the paths written in Steps 2 and 3 here, `source` is the posting URL from Step 1, `deadline` is the application deadline from the posting text Step 1 keeps verbatim (empty when the posting states none - never guess one), and the posting text item 7 archives is the one Step 1 read.
- This step covers the ad-hoc edit path, which runs outside `/apply`. Without it, an edit to documents that were never recorded (or whose row is still open) leaves the tracker stale.

### Step 4: Interview Preparation (quick questions only)
- For a scheduled interview on a tracked application, run `/interview <company>` instead
- Follow the framework in `07-interview-prep.md`
- Prepare STAR-format answers for likely questions
- Identify role-specific talking points
- Draft questions the candidate should ask the interviewer

---

## Reference Files

| File | Purpose |
|------|---------|
| `01-candidate-profile.md` | Education, experience, skills, publications, awards |
| `02-behavioral-profile.md` | Behavioral assessment, strengths, ideal environments |
| `03-writing-style.md` | Tone, structure, do's and don'ts |
| `04-job-evaluation.md` | Scoring framework for job fit |
| `05-cv-templates.md` | LaTeX CV structure and tailoring rules |
| `06-cover-letter-templates.md` | LaTeX cover letter structure and tailoring rules |
| `07-interview-prep.md` | STAR examples, tough questions, roleplay guidelines |
| `08-application-forms.md` | Portal free-text fields: self-introduction, project entries, character-limited pitches |
| `09-web-research.md` | Fetching postings and company pages: trust boundary, the WebFetch 403 fallback, escalation order, claim verification |

---

## Quick Commands

The user may also ask for individual steps without the full workflow:
- "Evaluate this job posting" - Step 1 only
- "Write a CV for [company]" / "Write a cover letter for [role] at [company]" - run `/apply <posting>` (it owns all drafting, verification and the gate)
- "Change [bullet/paragraph] in my CV/cover letter for [company]" - Step 2 or 3, then the `/apply` Step 5a-5d, 5f-5g and Step 6 checks
- "I got rejected / an offer / an interview invite from [company]" - `/outcome <company>` (`/interview <company>` to prepare)
- "How would I answer [question]?" - Step 4 only (a scheduled interview goes to `/interview`)
- "What jobs should I look for?" - Career strategy discussion using profile + evaluation framework
