---
framework_version: 1.2.0
---

# Agent Guidelines: AI Job Search

Job-search workspace: portal scrapers, ranked shortlists, tailored LaTeX CVs and cover letters, interview prep. Claude Code is the reference runtime; this file and `.agents/` make the same workflows run in Google Antigravity, Codex and other Agent Skills runtimes.

## Hard rule: commands route to skills

When the user types `/X` (or asks for X's workflow in words), **load skill `X` from `.agents/skills/X/SKILL.md` and follow it step by step, in order.** Never use a built-in, guided or generic flow instead, never improvise steps, never skip the verification steps. Text typed after `/X` is the skill's `$ARGUMENTS`.

| Command | Skill file | Purpose |
|---|---|---|
| `/setup` | `.agents/skills/setup/SKILL.md` | Profile onboarding |
| `/scrape` | `.agents/skills/scrape/SKILL.md` | Find new jobs across all portal CLIs |
| `/rank` | `.agents/skills/rank/SKILL.md` | Score scraped jobs into a shortlist |
| `/apply` | `.agents/skills/apply/SKILL.md` | Evaluate fit, tailor CV + cover letter, gate, track |
| `/interview` | `.agents/skills/interview/SKILL.md` | Interview prep pack / mock interview |
| `/outcome` | `.agents/skills/outcome/SKILL.md` | Record application results, follow-ups |
| `/upskill` | `.agents/skills/upskill/SKILL.md` | Skill-gap analysis and learning plan |
| `/expand` | `.agents/skills/expand/SKILL.md` | Mine documents for extra competencies |
| `/gmail-sync` | `.agents/skills/gmail-sync/SKILL.md` | Sync application status from Gmail |
| `/notion-sync` | `.agents/skills/notion-sync/SKILL.md` | Push jobs/applications to Notion |
| `/html-report` | `.agents/skills/html-report/SKILL.md` | HTML tracker dashboard |
| `/add-portal` | `.agents/skills/add-portal/SKILL.md` | Scaffold a new portal search CLI |
| `/add-template` | `.agents/skills/add-template/SKILL.md` | Register a custom CV / cover letter template |
| `/reset` | `.agents/skills/reset/SKILL.md` | Reset profile data (destructive, confirm first) |
| (no slash) | `.agents/skills/job-application-assistant/SKILL.md` | Ad-hoc questions about a posting, CV, cover letter |

Portal skills (`.agents/skills/*-search/`) are tools for `/scrape`; use one directly only when the user names that portal.

**Antigravity: run skills in Fast mode** (or set Artifact Review Mode to *always proceed*). Planning mode turns a skill into an Implementation Plan / Task List / Walkthrough and waits for review, which replaces the skill's own steps; the skills already define their checkpoints.

## Tool translation (source specs are written for Claude Code)

| Spec says | Use |
|---|---|
| `WebFetch` | `read_url_content` (or a browser tool for JS-heavy pages) |
| `WebSearch` | `search_web` |
| Agent tool / subagent | `invoke_subagent` if available; otherwise do the work inline, sequentially |
| `AskUserQuestion` | Ask the user in chat and wait for the answer |
| Read / Write / Edit / Glob / Grep / Bash | Your file-view, file-edit, file-search and terminal tools |

## Sources of truth

- `.claude/commands/*.md` and `.claude/skills/*/SKILL.md` are the canonical specs. `.agents/skills/{apply,rank,setup,...}/SKILL.md` are **generated** copies: never edit them; edit the `.claude/` source and run `python3 tools/sync_agent_skills.py`.
- Candidate profile: `CLAUDE.md` plus `.claude/skills/job-application-assistant/01-*.md` ... `09-*.md`. Read and write profile/data files at those `.claude/` paths.

## Always-on rules

- [.agents/rules/core.md](.agents/rules/core.md) - non-negotiable output and honesty rules
- [.agents/rules/issue-reporting.md](.agents/rules/issue-reporting.md) - how to report framework problems
- [.agents/rules/operator-mode.md](.agents/rules/operator-mode.md) - never edit the framework while running workflows

## Verification toolchain

- `python3 tools/doctor.py` - toolchain and state-file health
- `python3 tools/check_consistency.py [--fix]` - tracker / seen jobs / archive drift
- `python3 tools/prime_job.py <slug|url>` - deterministic `brief.md` for a posting
- `python3 tools/gate_application.py <slug>` - pre-submit gate (ATS naming, CV=2 pages, CL=1 page, contacts, anti-hallucination). Exit 0 pass, 1 fail, 2 human review
- `python3 tools/remember.py "<insight>"` - append-only learnings ledger
