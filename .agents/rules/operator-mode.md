---
trigger: always_on
---

# Operator mode: the main checkout is read-only framework

When running job-search work (/scrape, /rank, /apply, /interview, /outcome, /gmail-sync, /notion-sync, /html-report, /upskill) you are an **operator**, not a framework developer.

- **Never edit framework files in the main checkout**: anything tracked by git, or new files under `tools/`, `.claude/`, `.agents/`, `tests/`, `.github/`, `.githooks/`, `templates/`, `AGENTS.md`, `CLAUDE.md`. This includes shell writes (`sed -i`, `>`, `cp`), not just edit tools. Gitignored outputs (tracker, archives, `job_scraper/`, `cv/main_<company>_*`) are fine.
- **Allowed personalization** is listed in `tools/personalization_paths.json`: `01-candidate-profile.md` and `07-interview-prep.md` always; a portal's `enabled:` line always; the rest only in config mode.
- **Config mode** belongs to /setup, /reset, /expand, /add-portal, /add-template only: they run `python3 tools/set_mode.py config` first and `python3 tools/set_mode.py operator` last. Never switch modes to get around a denial.
- **Found a bug or improvement?** Do not fix it. File it: `python3 tools/report_issue.py --kind <bug|improvement|portal-health|drift|doc> --title "..." --body "..." [--component X]` (paths and symptoms only, no personal data). Exit 0 = filed/queued, 2 = refused, 1 = error; if the tool is missing, tell the user. Then continue the task with a workaround.
- **A hook denial** ("Operator mode: ...") is final for this session: report the issue, don't retry another way.
- **Final step of /scrape, /rank, /apply**: `python3 tools/check_framework_immutable.py --report`. If it lists paths, tell the user; do not restore them yourself.

## Framework development happens in a worktree

Only when the user explicitly asks to work on an issue:

- Claude Code: use the `framework-dev` agent (runs with `isolation: worktree`) or `claude -w issue-<n>`.
- Antigravity: `git worktree add ../ai-job-search-issue-<n> -b fix/issue-<n>`, open that folder as the workspace, implement, run `python3 -m unittest discover -s tests`, commit there, and open a PR with `gh pr create -R <origin owner/repo>` (never upstream).
