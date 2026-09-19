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
   - The step-by-step instructions and triggers for tasks (setup, scrape, rank, apply, upskill, interview) are defined in the [.claude/](.claude/) directory (specifically under `.claude/skills/` and `.claude/commands/`).
   - Do not duplicate these rules or specifications. Treat `.claude/` files as the single source of truth.
3. **Portal Search Skills:**
   - Job-portal search CLIs live under [.agents/skills/](.agents/skills/) in the portable Agent Skills format (with a `SKILL.md` per portal). Codex and Antigravity discover these automatically; the `/scrape` workflow in [.claude/skills/job-scraper/](.claude/skills/job-scraper/) orchestrates them.
4. **Subagent Delegation & Context Isolation (Antigravity / AGY & Autonomous Agents):**
   - High-token, multi-step operations (such as multi-portal scraping across 15+ portals, web searches, company culture audits on r/devsarg / Blind / Glassdoor, and salary benchmarks) MUST be delegated to isolated subagents (using `invoke_subagent` with the `research` agent or custom subagents like `gemini-research-expert` defined in [.claude/agents/](.claude/agents/)).
   - The subagent executes the external commands, parses the voluminous search output in its own isolated context, and returns ONLY the synthesized findings and ranked results to the parent session.
   - This keeps the main session context clean, preventing token bloat so that candidate profile evaluation, CV tailoring, and direct user interaction retain full context window capacity.
