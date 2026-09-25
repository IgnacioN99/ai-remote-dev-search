---
framework_version: 1.0.0
---

# Agent Guidelines: AI Job Search

This workspace is structured to manage job search activities, scraper tools, CVs, cover letters, and interview preparation.

## Thin-Pointer Design (Single Source of Truth)

To prevent duplication and configuration drift across different AI agent frameworks (Claude Code, Google Antigravity, Codex, Cursor, Gemini CLI, etc.), this workspace uses a unified thin-pointer design. All agent runtimes should load the canonical specifications and candidate profiles from the files and directories below:

1. **Personal Candidate Profile:**
   - The candidate profile, contact details, education, and target preferences are defined in [CLAUDE.md](CLAUDE.md) and the individual profile methodology files under [.claude/skills/job-application-assistant/](.claude/skills/job-application-assistant/) (specifically `01-*.md` etc.).
2. **Canonical Workflow Specifications:**
   - The step-by-step instructions and triggers for tasks (setup, scrape, rank, apply, upskill, interview) are defined in the [.claude/](.claude/) directory (specifically under [.claude/skills/](.claude/skills/) and [.claude/commands/](.claude/commands/)).
   - Do not duplicate these rules or specifications. Treat `.claude/` files as the single source of truth.
3. **Portal Search Skills:**
   - Job-portal search CLIs live under [.agents/skills/](.agents/skills/) in the portable Agent Skills format (with a `SKILL.md` per portal). Codex and Antigravity discover these automatically; the `/scrape` workflow in [.claude/skills/job-scraper/](.claude/skills/job-scraper/) orchestrates them.
4. **Subagent Delegation & Context Isolation (Antigravity / AGY & Autonomous Agents):**
   - High-token, multi-step operations (such as multi-portal scraping across 15+ portals, web searches, company culture audits on r/devsarg / Blind / Glassdoor, and salary benchmarks) MUST be delegated to isolated subagents (using `invoke_subagent` with the `research` agent or custom subagents like `gemini-research-expert` defined in [.claude/agents/](.claude/agents/)).
   - The subagent executes the external commands, parses the voluminous search output in its own isolated context, and returns ONLY the synthesized findings and ranked results to the parent session.
   - This keeps the main session context clean, preventing token bloat so that candidate profile evaluation, CV tailoring, and direct user interaction retain full context window capacity.
5. **PDF Naming for Applications & ATS Uploads:**
   - Before uploading or emailing PDFs to any recruiter, employer, or ATS platform (Greenhouse, Lever, Zoho Recruit, Ashby, Workday, etc.), always export/name the files using the candidate format:
     `IgnacioFlores_CV.pdf` (or `IgnacioFlores_CV_<Company>.pdf`)
     `IgnacioFlores_CoverLetter.pdf` (or `IgnacioFlores_CoverLetter_<Company>.pdf`)
   - Never upload files named with internal repo conventions (e.g. `main_<company>_<role>.pdf` or `cover_<company>_<role>.pdf`).
6. **Autonomous Job Application Subagent (`job-application-agent`):**
   - Defined under [.claude/agents/job-application-agent.md](.claude/agents/job-application-agent.md).
   - Can be invoked directly via `invoke_subagent` (`TypeName: "job-application-agent"`).
   - Orchestrates the end-to-end application pipeline: fit evaluation, tailored CV/Cover letter creation and layout verification, browser automation via Playwright/Stagehand MCP, pre-screening assessment formulation with human review gate, and tracker synchronization.
   - **Notion Sync:** Automatically syncs new applications and status transitions to the **[Job Search Tracker](https://app.notion.com/p/a3336e871ae6498d99e405f766f33fd1)** database in Notion (data source: `307df559-778a-4b97-b15e-d6d04e63cb1a`).
7. **Deterministic Verification & Invariant Integrity Toolchain:**
   - **Environment Health:** `python tools/doctor.py` — audits local tools (Python >= 3.10, uv, LuaLaTeX, XeLaTeX, Poppler, Bun/Node, Playwright) and state file integrity.
   - **State Drift Detection & Auto-Reconciliation:** `python tools/check_consistency.py` (with optional `--fix` / `--reconcile`) — audits sync between `job_search_tracker.csv`, `seen_jobs.json`, and `documents/applications/`.
   - **Deterministic Brief Builder:** `python tools/prime_job.py <slug|url>` — extracts vacancy requirements, crosses with candidate profile (SSOT), and queries memory insights to emit a token-budgeted `brief.md` anchor.
   - **Pre-Submit Quality Gate:** `python tools/gate_application.py <slug>` — mechanical gate enforcing ATS naming (`<CandidateName>_CV*.pdf`), exact page counts (CV=2, CL=1), text layer extraction, contact verification, and anti-hallucination checks. Exit 0 = pass, 1 = fail, 2 = human review needed.
   - **Append-Only Memory Ledger:** `python tools/remember.py` — records learnings from interviews, rejections, and ATS quirks in `documents/memory/insights.jsonl` with tombstone support.
