# Setup Guide

Step-by-step instructions for getting the AI Job Search framework running.

## 1. Prerequisites

### Claude Code

Install Claude Code (Anthropic's CLI for Claude):

```bash
npm install -g @anthropic-ai/claude-code
```

You'll need an Anthropic API key or a Claude Pro/Team subscription. See the [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) for details.

### Python

Python 3.10+ is required for the salary lookup tool. Check with:

```bash
python3 --version
```

On Windows, `py --version` is often the most reliable check. If your system exposes Python as `python` instead of `python3`, use `python` in the commands below.

### Bun (for job search tools)

The job portal CLIs (four Danish portals plus the country-agnostic `linkedin-search` and `freehire-search` tools) are written in TypeScript and run with Bun.

- macOS/Linux:

```bash
curl -fsSL https://bun.sh/install | bash
```

- Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://bun.sh/install.ps1 | iex"
```

If you prefer a package manager, `winget install Oven-sh.Bun` also works on Windows.

### LaTeX (for compiling CVs and cover letters)

Install a LaTeX distribution to compile the generated `.tex` files to PDF:

- **Windows:** [MiKTeX](https://miktex.org/download)
- **macOS:** [MacTeX](https://tug.org/mactex/)
- **Linux:** `sudo apt install texlive-full` or `sudo dnf install texlive-scheme-full`

The CV compiles with `lualatex` (pdflatex often fails on modern MiKTeX installs with `fontawesome5` font-expansion errors). The cover letter compiles with `xelatex` because `cover.cls` requires `fontspec` for its custom Lato/Raleway fonts.

#### Minimal TeX install: TinyTeX/BasicTeX

Full TeX distributions work out of the box, but minimal distributions need a few extra packages before the stock templates compile.

On macOS, a user-level TinyTeX install avoids a system-wide installer and does not require `sudo`:

```bash
curl -fsSL https://yihui.org/tinytex/install-bin-unix.sh -o /tmp/tinytex-install-bin-unix.sh
sh /tmp/tinytex-install-bin-unix.sh /tmp --no-path
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"
```

Then install the template dependencies:

```bash
tlmgr install \
  moderncv fontawesome5 fontawesome6 academicons import luatexbase pgf \
  titlesec textpos xltxtra xunicode cite realscripts needspace
```

For BasicTeX/MacTeX, make sure the TeX binary directory is on `PATH` first (for example via `/Library/TeX/texbin`), then run the same `tlmgr install ...` command.

Quick smoke tests after setup:

```bash
cd cv && lualatex -interaction=nonstopmode -halt-on-error main_example.tex && cd ..

SMOKE_DIR="$(mktemp -d /tmp/ai-job-cover-smoke.XXXXXX)"
cp -R cover_letters/cover.cls cover_letters/OpenFonts "$SMOKE_DIR/"
cat >"$SMOKE_DIR/cover_smoke.tex" <<'EOF'
\documentclass[]{cover}
\begin{document}
\namesection{Test}{Candidate}{test@example.com}
\companyname{Example Company}
\companyaddress{123 Hiring Street\\Example City}
\currentdate{\today}
\lettercontent{Dear Hiring Manager,}
\lettercontent{This smoke test verifies that xelatex can load cover.cls and the bundled fonts.}
\closing{Sincerely,}
\signature{Test Candidate}
\end{document}
EOF
(cd "$SMOKE_DIR" && xelatex -interaction=nonstopmode -halt-on-error cover_smoke.tex)
```

#### Windows: Basic MiKTeX

The full MiKTeX installer bundles every CTAN package and works out of the box, but the smaller [Basic MiKTeX](https://miktex.org/download) installer (`basic-miktex-*.exe`) only ships a minimal package set and needs a couple of one-time settings before the stock templates compile.

By default, MiKTeX installs missing packages on demand but pops up a GUI prompt for each one — which blocks non-interactive terminals (including Claude Code's Bash tool). Turn that into a silent auto-install instead:

```powershell
initexmf --admin --set-config-value=[MPM]AutoInstall=1
initexmf --set-config-value=[MPM]AutoInstall=1
```

(Run the first line from an elevated/Admin PowerShell if you installed MiKTeX for all users; the second line covers a per-user install. Only one will apply depending on how you installed it — running both is harmless.)

If you'd rather not rely on on-the-fly installs at all (for example, for a fully offline compile later), pre-install the same package set the macOS TinyTeX section above lists, using MiKTeX's package manager:

```powershell
mpm --admin --install=moderncv --install=fontawesome5 --install=fontawesome6 --install=academicons --install=import --install=luatexbase --install=pgf --install=titlesec --install=textpos --install=xltxtra --install=xunicode --install=cite --install=realscripts --install=needspace
```

Drop `--admin` if MiKTeX is installed for the current user only. If a package name doesn't resolve, `mpm --find=<name>` searches the repository for the correct name.

Quick smoke tests after setup (PowerShell):

```powershell
Set-Location cv; lualatex -interaction=nonstopmode -halt-on-error main_example.tex; Set-Location ..

$SmokeDir = New-Item -ItemType Directory -Path (Join-Path $env:TEMP "ai-job-cover-smoke-$(Get-Random)")
Copy-Item cover_letters\cover.cls, cover_letters\OpenFonts -Destination $SmokeDir -Recurse
@'
\documentclass[]{cover}
\begin{document}
\namesection{Test}{Candidate}{test@example.com}
\companyname{Example Company}
\companyaddress{123 Hiring Street\\Example City}
\currentdate{\today}
\lettercontent{Dear Hiring Manager,}
\lettercontent{This smoke test verifies that xelatex can load cover.cls and the bundled fonts.}
\closing{Sincerely,}
\signature{Test Candidate}
\end{document}
'@ | Set-Content (Join-Path $SmokeDir "cover_smoke.tex")
Push-Location $SmokeDir; xelatex -interaction=nonstopmode -halt-on-error cover_smoke.tex; Pop-Location
```

### Optional: ATS text extraction (pypdf, then pdftotext)

`/apply` runs an ATS parseability check on the compiled CV: it extracts the PDF's text layer and verifies contact details, reading order, and keyword coverage the way an applicant-tracking system sees them.

The default extractor is **pypdf** (BSD, `pip install pypdf`). Poppler `pdftotext` remains an optional fallback:

- **macOS:** `brew install poppler`
- **Debian/Ubuntu:** `sudo apt install poppler-utils`
- **Windows:** `choco install poppler`

If a command still uses `pdftotext -layout`, it must pass `-enc UTF-8` as well. If **neither** extractor is available, `/apply` skips the mechanical check with a warning and falls back to a visual keyword review — everything else works normally.

## 2. Fork and clone

```bash
gh repo fork MadsLorentzen/ai-job-search --clone
cd ai-job-search
gh repo set-default <your-github-username>/ai-job-search
```

Or manually: fork on GitHub, then clone your fork.

> **The `set-default` line is not optional.** `gh repo fork --clone` sets the
> **upstream** repo as gh's default repository ("The `upstream` remote will be set as
> the default remote repository" — `gh repo fork --help`), and gh uses the default for
> **creating issues and PRs**. Without it, any later `gh issue create` run from this
> clone — by you or by an agent you have asked to track your applications — silently
> files on the upstream **public** tracker, publishing whatever the issue contains
> under your GitHub identity, on a repo where you cannot delete it (#389).

> **Before you go further: forks are public.** GitHub cannot make a fork of a public
> repository private. `/setup` (section 6) keeps your personal data in gitignored
> `<file>.personal` copies (see "Where your data lives" below), so it never enters a commit -
> but never force-add one, and keep tailored CVs and the tracker out of a fork too. If you
> want a remote backup of your own setup, prefer a **private repository** with this repo as
> `upstream` (section 8, step 1). Everything else in this guide works identically either way.

## 3. Install job search CLI dependencies
Run these from the repository root.

- PowerShell:

```powershell
$tools = @("jobbank-search", "jobdanmark-search", "jobindex-search", "jobnet-search", "linkedin-search", "freehire-search")
foreach ($tool in $tools) {
  Push-Location ".agents/skills/$tool/cli"
  bun install
  Pop-Location
}
```

- Bash / zsh / Git Bash:
```bash
for tool in jobbank-search jobdanmark-search jobindex-search jobnet-search linkedin-search freehire-search; do
  (cd .agents/skills/$tool/cli && bun install)
done
```

For `linkedin-search` and `freehire-search` the install is optional: both have zero runtime dependencies and run with plain `bun`; `bun install` only pulls TypeScript dev types.

If you're outside Denmark, you can generate an equivalent search skill for your local job board with `/add-portal` — it scaffolds the same CLI structure for any public portal and test-runs a live query before registering. See the "Job search tools" section in the README.

## 4. Run the setup interview

Start Claude Code in the repository:

```bash
claude
```

Then run the onboarding:

```
/setup
```

Claude will offer three paths:

- **Path A (documents folder):** Add your CV, LinkedIn export, diplomas, references, or past applications under `documents/`. Claude reads and cross-references them before proposing profile updates. This is best when you have several source files.
- **Path B (single CV import):** Share one CV/resume by mentioning the file with `@` or pasting the text. Claude extracts it and asks follow-up questions for anything missing.
- **Path C (interview mode):** Answer structured interview questions section by section.

All three paths produce the same result: fully populated profile files.

### What gets populated

| File | Content |
|------|---------|
| `CLAUDE.md` | Your full candidate profile |
| `01-candidate-profile.md` | Structured education, experience, skills |
| `02-behavioral-profile.md` | Behavioral assessment |
| `04-job-evaluation.md` | Personalized skill match areas and career goals |
| `05-cv-templates.md` | Profile statement templates for your background |
| `07-interview-prep.md` | STAR examples from your experience |
| `cv/main_example.tex` | Your LaTeX CV with actual details |
| `search-queries.md` | Job search queries for `/scrape` |

### Where your data lives: the `.personal` overlay

The tracked profile/data files (`CLAUDE.md`, `01-*.md` ... `09-*.md` under `.claude/skills/job-application-assistant/`, `job-scraper/search-queries.md`, and the master CV `cv/main_example.tex`) stay placeholder **templates**. `/setup` writes your data to a gitignored copy beside each one, `<file>.personal` (for example `CLAUDE.md.personal`), and every command reads that copy instead of the template when it exists. `CLAUDE.md` imports `CLAUDE.md.personal` on load, so Claude Code sees your profile automatically. Because `*.personal` is gitignored, your profile never lands in a commit or a public fork. `/apply` reads the master CV through `python3 tools/personal_overlay.py resolve cv/main_example.tex` and copies it into each tailored `cv/main_<company>_<role>.tex`; the `.personal` file itself is never compiled.

- **Fresh clone, before `/setup`:** `CLAUDE.md.personal` does not exist yet, so the `@CLAUDE.md.personal` import in `CLAUDE.md` points at a missing file. Claude Code skips an import it cannot find (no error; at most a notice), and every command falls back to the placeholder template until `/setup` creates the copy. Run `/setup` first: until then fit evaluations and drafts have no real profile to work from.

- `python3 tools/personal_overlay.py status` lists which copy each file resolves to.
- A `.personal` file is a full copy, so later framework updates to its template (scoring rules, checklists) do not flow into it on their own. `status` (and `tools/doctor.py`) flags a copy whose template has a newer `framework_version`; merge the template change into your copy by hand.
- **Upgrading a checkout that was personalized in place** (before the overlay existed): after pulling, run `python3 tools/migrate_personal_overlay.py` (dry run), then `--apply`. It copies your personalized versions into `<file>.personal` (keeping their original `framework_version`, so `status` then tells you which templates gained rules you should merge in), never overwrites an existing `.personal` file (it writes `<file>.incoming.personal` for you to merge instead, with a count of the lines that are genuinely yours), and backs up existing copies to `documents/memory/backup-<timestamp>/`. Re-running `--apply` is safe: with nothing left to do it writes nothing. After merging an `.incoming.personal` file into your `.personal` copy (keeping only the lines you want), delete it: the next run reports that file `[resolved]` and never recreates it, and the merge is reopened only if the source content changes (state in the gitignored `.agents/state/personal_migration.json`). If you merged and deleted incoming files written by an earlier version of the script and they are still listed as `manual merge needed`, run `python3 tools/migrate_personal_overlay.py --resolved-all` once (or `--resolved <file>` for a single file). A copy created by an earlier version of the script carries the template's newer `framework_version` instead of its source version; if you are unsure it holds the current framework rules, compare it with the template and lower the stamp by hand so `status` flags it. If you edited `cv/main_example.tex` in place, it is copied to `cv/main_example.tex.personal`; then discard your edits to the tracked file.

### Re-running setup

You can update specific sections later:

```
/setup --section skills
/setup --section experience
/setup --section search
```

The `--section search` option is especially useful as your priorities evolve. It re-runs the search configuration interview and suggests role types you may not have considered based on your full profile.

## 5. Optional: Set up salary benchmarking

If you have salary data (from a union, salary survey, Glassdoor, or personal research):

1. **Option A:** Create `salary_data.json` manually in the repo root (see `tools/README_SALARY_TOOL.md` for the format)
2. **Option B:** Convert from Excel:
   ```bash
   pip install openpyxl
   python3 tools/convert_salary_excel.py path/to/salary-data.xlsx --source "My Salary Data 2025"
   ```

This creates `salary_data.json` which the `/apply` workflow uses for salary benchmarking. If you skip this step, salary lookup is simply omitted.

## 6. Test the workflow

Find a job posting you're interested in, then:

```
/apply https://jobindex.dk/job/1234567
```

Or paste the job description directly:

```
/apply [paste job posting text here]
```

Claude will:
1. Evaluate the fit against your profile
2. Ask if you want to proceed
3. Draft a tailored CV and cover letter
4. Have a reviewer agent critique the drafts
5. Revise and present the final output

## 7. Compile your documents

After `/apply` creates the LaTeX files:

```bash
# Bash / zsh / Git Bash
cd cv && lualatex main_<company>_<role>.tex && cd ..
cd cover_letters && xelatex cover_<company>_<role>.tex && cd ..
```

```powershell
# PowerShell
Set-Location cv; lualatex main_<company>_<role>.tex; Set-Location ..
Set-Location cover_letters; xelatex cover_<company>_<role>.tex; Set-Location ..
```

These commands apply to the stock templates (moderncv CV, `cover.cls` cover letter). If you'd rather use your own LaTeX template, run `/add-template` — it captures the template's compile engine, fonts, style rules, and page limit, test-compiles it, and wires it into `/apply`. See the "LaTeX templates" section in the README.

## 8. Pulling upstream updates into your fork

Upstream keeps improving the methodology files your fork has personalized, so plan for updates from day one:

**Prefer releases over raw `master`.** Tagged [releases](../../releases) are vetted checkpoints, each described in [CHANGELOG.md](CHANGELOG.md). Updating to a tag pulls a stable, documented state instead of whatever `master` happens to be mid-review. Fetch tags with `git fetch upstream --tags` and merge a release (for example `git merge v1.0.0`) when you want stability; pull `master` directly only when you specifically want the latest unreleased changes. The steps below apply either way - substitute the release tag for `upstream/master` where you see it.

1. **Keep your personalization out of commits.** `/setup` writes your profile to gitignored `<file>.personal` copies, so the tracked files stay templates and upstream updates merge without conflicts; `python3 tools/personal_overlay.py status` then flags any copy whose template gained framework rules. If you also commit anything of your own, remember that a GitHub **fork of this repo is public** - forks of public repositories cannot be made private - so anything you commit *and push to a fork* is visible to anyone. If you want your profile in a remote at all, don't push it to a fork: create a **private** repository, push there, and add this repo as the `upstream` remote (`git remote add upstream https://github.com/MadsLorentzen/ai-job-search.git`) to keep receiving updates. Committing locally without pushing is also fine. The genuinely sensitive files (tracker, salary data, `documents/`, application archives) are gitignored and never enter git either way. An uncommitted working tree is the most common reason `git pull` refuses to merge at all (`Your local changes ... would be overwritten`).
2. **Preview what changed before pulling:**
   ```bash
   git remote add upstream https://github.com/MadsLorentzen/ai-job-search.git   # first time only, if you cloned your own fork
   git fetch upstream    # or origin, if you cloned the template directly
   python3 tools/check_upstream_updates.py
   ```
   It compares the `framework_version` markers in your framework files against upstream and lists exactly which methodology files changed, with the diff command for each.

   Two tools answer two different questions, and it's worth running both:
   - **`check_upstream_updates.py`** — *which of my personalized files changed?* It reads the `framework_version` stamp on each methodology file, so it flags exactly the customized files a release touched.
   - **`upstream_triage.py`** — *which upstream commits deserve my attention?* It walks the commits you're behind and sorts them into "worth reviewing" vs "probably skip", dropping anything you've already cherry-picked (matched by `git patch-id`, so ported work falls off with no bookkeeping), commits that only touch files your fork removed, and SHAs you've listed in `.github/upstream-wontport.txt`. It's report-only — it prints ready-to-run `git cherry-pick` lines but never merges, pushes, or opens a PR, because on a fork "applies cleanly" isn't "correct".

     ```bash
     python3 tools/upstream_triage.py --remote upstream
     ```

     Forks also inherit a `.github/workflows/upstream-watch.yml` that runs this weekly and writes the result into a single rolling issue (it no-ops on the upstream template itself, and stays disabled on a fork until you enable Actions).
3. **Merge normally.** `git merge upstream/master` (or `git pull`) three-way-merges upstream's edits around your personalization; because methodology edits rarely touch the lines `/setup` filled in, most updates land cleanly. A conflict in a personalized file is a *feature*, not a failure — it means upstream changed methodology in a section you customized, and the version marker plus its changelog commit tell you why. Resolve by keeping your data and adopting the methodology change around it.

## 9. Optional: Using Google Antigravity

Claude Code reads `.claude/` directly. Google Antigravity does not: it only exposes as `/name` the skills in `.agents/skills/<name>/SKILL.md`, and it reads `AGENTS.md` plus `.agents/rules/*.md` as always-on rules. The repo ships both:

- `.agents/skills/<command>/SKILL.md` - a generated **full copy** of every `.claude/commands/*.md` command and of the `scrape`, `upskill` and `job-application-assistant` skills, with tool names translated (`WebFetch` -> `read_url_content`, `WebSearch` -> `search_web`, subagents -> `invoke_subagent` or inline).
- `AGENTS.md` - the command -> skill table and the rule "when the user types `/X`, load skill X and follow it step by step".
- `.agents/rules/core.md` - the non-negotiable rules (2-page CV, 1-page cover letter, no hallucination, ATS file naming).

**Keep the copies in sync.** `.claude/` is the source of truth. After editing anything under `.claude/commands/` or `.claude/skills/`, and after `/setup`, `/reset`, `/add-template` or `/add-portal` (those commands run it as their last step), run:

```bash
python3 tools/sync_agent_skills.py          # regenerate .agents/skills copies
python3 tools/sync_agent_skills.py --check  # exit 1 if anything drifted (CI runs this via tools/lint_skills.py)
```

Never edit the generated `SKILL.md` copies by hand - the next sync overwrites them. Profile and data files (`.claude/skills/job-application-assistant/01-*.md` ... `09-*.md`, `search-queries.md`) are not copied: the generated skills read and write them at their `.claude/` paths.

**Use Fast mode for skill runs.** In Antigravity, run `/apply`, `/rank`, `/scrape` and the other skills in **Fast** mode, or set **Artifact Review Mode** to *always proceed*. In Planning mode the agent tends to replace the skill with its own Implementation Plan, Task List and Walkthrough artifacts and pause for review, skipping or reordering the skill's steps; the skills already stop where your decision is needed (fit evaluation, before submission).

**WSL notes.** Antigravity's global configuration lives in `~/.gemini/config/` (inside the WSL home when the agent runs in WSL, not the Windows profile). Workspace MCP servers for Antigravity go in `.agents/mcp_config.json` (generated from `.mcp.json`; see the MCP section of the README). Open the repo from the WSL filesystem path so `python3`, `bun` and `lualatex` resolve to the Linux toolchain.

**Quick check.** Open the repo in Antigravity, type `/` and confirm `/apply`, `/rank`, `/setup`, `/scrape` appear in the slash menu; run `/rank` and confirm the agent says it is following `.agents/skills/rank/SKILL.md` rather than starting a generic flow.

## Troubleshooting

### "salary_data.json not found"
This is expected if you haven't set up salary benchmarking. The `/apply` workflow skips this step automatically.

### Job search CLI tools not working
Make sure Bun is installed and you ran `bun install` in each CLI directory. The tools require network access to fetch job listings.

### LaTeX compilation errors
- CV: uses `lualatex` (pdflatex often fails on modern MiKTeX with `fontawesome5` font-expansion errors; lualatex handles the same sources cleanly)
- Cover letter: uses `xelatex` (for custom fonts in `OpenFonts/fonts/`)
- Make sure your LaTeX distribution includes the `moderncv` package

### Fonts not found in cover letter
The cover letter template expects fonts in `cover_letters/OpenFonts/fonts/`. Make sure this directory exists and contains the Lato and Raleway font files.

### Stale `.claude/settings.local.json` from an older clone
Shared Claude Code permissions now live in `.claude/settings.json` (scoped to `bun run`, `python salary_lookup.py`, and `python3 salary_lookup.py`). Earlier versions of this repo committed a broader `.claude/settings.local.json` that pre-approved `Bash(curl:*)`, `Bash(python:*)` and `Bash(bun:*)`. If you cloned before that change, git leaves the old file behind in your working copy, and its permissions still apply on top of `settings.json`. Delete it (or trim it to your own personal overrides):

```bash
rm .claude/settings.local.json
```

## Issue reporting

During operator runs (`/scrape`, `/rank`, `/apply`, ...) the agent never patches the framework. When it hits a tool failure, a broken/degraded portal, doc drift or an improvement idea, it files a sanitized issue on **your fork** with `python3 tools/report_issue.py` (rules: `.agents/rules/issue-reporting.md`). The tool resolves the target from `origin` (override with `JOBSEARCH_ISSUES_REPO=owner/repo`), hard-refuses the upstream template, strips personal data, comments on a matching open issue instead of duplicating, and queues to `documents/memory/pending_issues.jsonl` (gitignored) when `gh` is offline (`--flush` replays). Your fork is public, so the sanitizer matters: still glance at what gets filed.

One-time setup (replace `<you>/<fork>`):

```bash
gh repo edit <you>/<fork> --enable-issues
gh repo set-default <you>/<fork>   # gh otherwise resolves to upstream
for l in agent-reported framework operator-mode portal-health; do gh label create "$l" -R <you>/<fork> --force; done
python3 tools/report_issue.py --kind bug --title "test" --body "x" --dry-run   # check the target
```

Claude Code is pre-approved via `.claude/settings.json`. In **Antigravity**, add the allow-list entry `command(python3 tools/report_issue.py)` in Settings (it can only be set in the UI); keep raw `gh issue` behind approval.

**`/apply` quality gate is enforced at stop time (both runtimes).** `/apply` marks its run with `python3 tools/apply_state.py start <company>_<role>` (gitignored `.agents/state/apply.json`) and clears it with `done` once the gate passes. While the marker exists and the run's CV or cover letter exists, the Stop hook `.claude/hooks/apply_gate_stop.py` (registered in `.claude/settings.json` and `.agents/hooks.json`) runs `python3 tools/gate_application.py <slug>` whenever the agent tries to end its turn; a failing gate (exit 1) sends the agent back with the violations (Claude Code: `decision: block`; Antigravity: `decision: continue`). Exit 0 allows the stop and clears the marker; exit 2 (pending human review) allows it so the agent can ask you. It blocks at most 3 times per run, does not block again in Claude Code once `stop_hook_active` is set after one of its own blocks, ignores markers older than 12 hours, never fires before this run has written documents (fit evaluation, declined postings, or a redraft still at its consent step - files older than the marker do not count), ignores stops from another project directory, another checkout (main checkout vs a linked worktree under `.claude/worktrees/`), or another session than the one that ran `start` (Claude Code: recorded from `CLAUDE_CODE_SESSION_ID`; otherwise claimed by the first stopping session whose transcript shows the `start` command), lets the gate ignore PDFs older than the marker (`gate_application.py --since`) so a redraft's previous exports never pass for this run's, and fails open with a stderr warning on internal errors. If you cancel a run, `/apply` clears the marker with `python3 tools/apply_state.py done <slug>`; `python3 tools/apply_state.py status` shows the current marker.
   - **Antigravity has no `stop_hook_active` flag**, so a run whose gate keeps failing can be sent back up to 3 times (the per-run cap) before the stop is allowed.
   - **Native Windows:** the hooks run `python3 ...`; make sure `python3` is on `PATH` (the python.org installer only adds `python` and `py`; enable the App Execution Alias or add a `python3` shim). Under WSL this already holds.

## Operator mode: keeping the framework read-only

Day-to-day commands (`/scrape`, `/rank`, `/apply`, `/interview`, `/outcome`, ...) run in **operator mode**: they must not change framework files in your main checkout. Problems they find are filed as issues on your fork (`tools/report_issue.py`), and fixes happen later in a linked git worktree. Three layers enforce this:

1. **Edit-time hook** (on by default): `.claude/hooks/guard_framework.py`, registered in `.claude/settings.json` for Claude Code and in `.agents/hooks.json` for Antigravity. It denies edits to tracked files (and new files under `tools/`, `.claude/`, `.agents/`, `tests/`, `.github/`, `.githooks/`, `templates/`) in the main checkout. Gitignored outputs and linked worktrees are never blocked. In every checkout it also denies writes inside a git directory (`.git/config`, `.git/hooks/*`) and to `.claude/settings.local.json` (your personal permissions; `.claude/settings.json` adds the deny rule `Edit(/.claude/settings.local.json)` too). Claude Code's own "Yes, and don't ask again" still saves rules there, because Claude Code writes that file itself rather than through the Edit tool; edit it yourself or use `/permissions`. The hook needs git 2.31 or later. With an older git, or when git fails, it prints a warning to stderr and allows the edit.
   - **Shell writes are not hooked.** The hook sees only the file-edit tools (Edit/Write/MultiEdit/NotebookEdit, and Antigravity's write/replace tools). A `python`, `sed` or `>` redirect run through the shell bypasses it. The drift check below is the backstop.
   - **Antigravity prompts.** For every write it does not deny, the Antigravity hook answers `"ask"` so that Antigravity's own review flow decides. Depending on your review policy, that can mean a prompt for each file write. If that gets annoying, pick **Always Allow** on the prompt (Antigravity caches that choice), or relax the file-edit review policy in Antigravity's agent settings. Denied framework writes stay denied either way.
2. **Drift check**: `python3 tools/check_framework_immutable.py [--report]`, run as the last step of `/scrape`, `/rank`, `/apply`, `/interview` and `/outcome`. It catches shell writes the hook cannot see. Gitignored files (your `<file>.personal` profile copies included) are never drift; editing a tracked profile template such as `CLAUDE.md` or `01-candidate-profile.md` is.
3. **Pre-commit hook** (opt-in, once per clone):

   ```bash
   git config core.hooksPath .githooks
   ```

   It rejects commits of framework files from the main checkout. Commit framework work from a worktree, or override deliberately (for example when merging reviewed branches into `master`) with `ALLOW_FRAMEWORK_COMMIT=1 git commit ...`. A clean `git merge upstream/master` (section 8) creates its merge commit without running pre-commit. A **conflicted** merge does not: after you resolve the conflicts, the concluding `git commit` runs the hook and is rejected, so finish it with `ALLOW_FRAMEWORK_COMMIT=1 git commit` (or `ALLOW_FRAMEWORK_COMMIT=1 git merge --continue`).

**Personalization** that commands write by design is listed in `tools/personalization_paths.json`. `/setup`, `/reset`, `/expand`, `/add-portal` and `/add-template` switch to config mode with `python3 tools/set_mode.py config` and back with `python3 tools/set_mode.py operator`; `python3 tools/set_mode.py show` prints the current mode. The mode lives in the gitignored `.agents/state/mode` and expires after 4 hours.

**Working on the framework**: in Claude Code, ask for the `framework-dev` agent with an issue number (it runs in its own worktree under `.claude/worktrees/`; `.worktreeinclude` is intentionally empty, so no personal files are copied in and the tests run without them), or start `claude -w issue-<n>`. In Antigravity: `git worktree add ../ai-job-search-issue-<n> -b fix/issue-<n>` and open that folder.

**Optional OS sandbox**: Claude Code's sandbox can additionally deny shell writes to framework paths, but on Linux/WSL it needs bubblewrap (`sudo apt install bubblewrap socat`). It is not enabled in the shipped settings.
