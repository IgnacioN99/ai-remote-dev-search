# Contributing

Thanks for considering a contribution! This repo has a deliberate, narrow philosophy, and most declined PRs are well-executed work that simply didn't know about it. Read this first; it will save you effort and tell you where your work will land best.

## The one rule everything follows from

**This repo is a universal template.** People fork it and adapt it to their own market, language, and profile. Upstream stays market-agnostic, person-agnostic, and Claude Code-native. The corollary: a contribution is judged by fit to this rule first, execution quality second. Well-built but off-policy still gets declined (kindly, with reasons).

## What gets merged

- **Universal customization features**: anything that makes the fork-and-adapt path better for everyone. Precedent: `/add-template` ([#30]), `/add-portal` ([#37]).
- **Robustness and correctness fixes** with the failing case demonstrated. Precedent: NaN flag validation ([#35]), HTML entity decoding ([#55], [#56]), salary column detection ([#64]).
- **Docs that close real gaps**: platform-specific setup ([#41], [#60]), stale references ([#36], [#68]).
- **Infrastructure that reduces review burden** and is argued from evidence, not speculation. Precedent: CI ([#59]), which caught a latent bug while being built.

## What gets declined

- **Market- or country-specific skills and content.** One country's portal opens the door to every country's portal; there is no principled stopping point. Precedent: [#31] (India), [#39] (France, despite an honest and excellent PR), [#67] (China). The in-tree portal skills are either country-agnostic (`linkedin-search`) or the maintainer's own demonstration instance (the Danish portals).
- **Personal profile data.** The template ships placeholders; your populated profile lives in your fork. CI enforces this (`placeholder-integrity`). Precedent: [#17], [#72].
- **Alternative-harness ports and duplicate workflow sources.** The markdown specs ARE the implementation; a second copy (another agent CLI, an orchestration layer, a wrapper command) drifts from the first the moment either changes. Precedent: [#44], [#49], [#66].
- **Speculative infrastructure.** Complexity must be argued from a problem that exists, not one that might. Precedent: [#63].
- **Kitchen-sink PRs.** One concern per PR. Bundles get asked to split ([#73]) - and splits get reviewed fast ([#75], [#76] arrived within the hour and were handled same-day).

## The bar for new commands

The core lifecycle is **feature-complete**: `/setup` → `/scrape` → `/rank` → `/apply` → `/interview` → `/outcome` → calibration back into `/setup`, with `/expand`, `/upskill`, `/add-template`, `/add-portal`, and `/reset` around it. Every stage of a real job hunt has an owner.

A new command therefore faces a high bar. The test that admitted the existing ones: **does it operationalize something error-prone that already exists in the framework** (documented machinery nothing executes, data something writes but nothing reads)? "Useful" and "possible" are not sufficient; the strongest proposals connect two things that already exist without modifying either ([#43], [#54]).

## Claims get verified

Reviews here are empirical. Bug reports are reproduced on master before the fix is considered; "all tests green" is checked against whether the tests can distinguish master from the fix. PRs whose premise doesn't reproduce get declined even when the code is fine - it has happened ([#35]'s converter fix, [#52]'s first version). You can make this fast:

- State the failing case and how to reproduce it.
- **Reproduce on the real path, not a constructed input.** A test that fails on master and passes on the fix is necessary but not sufficient: the failing input has to be one the workflow actually produces, not one the test hand-builds. Show the failure through the path the code really runs - the documented CLI invocation, real portal output, an actual data file - not a synthetic value fed straight to the function. A fix whose only demonstration is an input the real code path never receives gets declined even though its test is green.
- Put CLI tests in `.agents/skills/<name>/cli/tests/` (bun test, network-free where possible); Python tool tests in `tests/`.
- Run what CI runs: `python3 tools/lint_skills.py`, `python3 tools/check_framework_version.py`, `python3 tools/security_guards.py`, `python3 -m unittest discover -s tests`, and in touched CLIs `bun run typecheck` + `bun test`.

**Credit norm:** a change that incorporates your actual code gets a `Co-authored-by` trailer; a change written independently from your observation or report gets a named mention in the commit message and PR. Both happen unprompted.

## Building for your own market? Do this instead

1. Fork the repo and run `/add-portal` with your local job board - it scaffolds a portal skill matching the shipped contract, and `/scrape` picks it up automatically.
2. Announce your fork in the pinned [Community forks & adaptations](https://github.com/MadsLorentzen/ai-job-search/discussions/78) discussion so others can find it.
3. Run the framework update checker (`python3 tools/check_upstream_updates.py`) in your fork to check if upstream has updated any framework files and compare them with your personalized variants.

Market-specific skills are genuinely valuable - they just live in forks, where their maintainers can test them and their users can find them.

One practical warning: when you open a PR from a fork, GitHub targets this upstream repo by default, not your own - three personalized-fork PRs landed here by accident in a single week ([#155], [#162], [#165]). Check the "base repository" dropdown before publishing.

## Porting to another AI runtime? Forks too

Claude Code is the reference runtime: it is what the maintainer runs daily and what every methodology change is verified on. A parallel command tree for another runtime (Codex, Antigravity, Gemini CLI, ...) would ship untested on every change - CI cannot run those harnesses - and each accepted runtime makes the next one harder to refuse. It is the same arithmetic that keeps market-specific portals in forks.

How this fork supports Google Antigravity without a hand-maintained parallel tree:

- **`.claude/` is the single source of truth.** Edit only `.claude/commands/*.md` and `.claude/skills/*/`.
- **`.agents/skills/<command>/SKILL.md` is generated** by `python3 tools/sync_agent_skills.py`: a full copy of each command and of the `scrape`/`upskill`/`job-application-assistant` skills, with Claude-only tool names translated. Never edit those copies; re-run the generator and commit its output in the same PR. `tools/lint_skills.py` (CI) runs `sync_agent_skills.py --check` and fails on drift.
- The portal search skills in `.agents/skills/*-search/` are hand-written in the portable Agent Skills format and are not touched by the generator (beyond a `.skillignore`).
- `AGENTS.md` (command -> skill routing table) and `.agents/rules/*.md` (always-on rules) are the Antigravity entry points; keep them terse - Antigravity gives all always-on rules a shared 20k-token budget.
- Framework instruction files carry `framework_version` markers, so a runtime fork can track methodology changes precisely (`python3 tools/check_upstream_updates.py`).

Announce your runtime fork in the pinned [Community forks & adaptations](https://github.com/MadsLorentzen/ai-job-search/discussions/78) discussion and it gets listed alongside the market adaptations. The proven shape is a thin pointer: reference the specs here instead of copying them, so upstream improvements reach your fork on rebase.

This is a decision, not a dogma: if cross-runtime standards mature to the point where these specs run unmodified elsewhere, or the community's center of gravity moves to runtime forks, the trade-off gets re-evaluated. Background: the architecture thread in [Community forks & adaptations](https://github.com/MadsLorentzen/ai-job-search/discussions/78).

## Practical notes

- **Personal data stays out of tracked files**: profile/data files (`CLAUDE.md`, `job-application-assistant/01-*.md` ... `09-*.md`, `job-scraper/search-queries.md`) ship as placeholder templates. Candidate data belongs in the gitignored `<file>.personal` overlay (`tools/personal_overlay.py`); a command spec that reads or writes one of these files must honor the overlay rule. Never commit a personalized version of a template.
- **Portal-skill contract**: `search`/`detail` commands, `--format json|table|plain`, stderr JSON errors with exit 1, backoff on 429/5xx, zero runtime dependencies by default. See `/add-portal`'s spec and `linkedin-search` as the reference implementation.
- **Personal-use boundaries**: portal skills that touch ToS-restricted sources carry a prominent personal-use-only warning, and CI deliberately makes no live portal requests. Don't "fix" that.
- **LaTeX changes**: both templates must compile (`lualatex` for the CV, `xelatex` for the cover letter) and hold their exact page counts. CI smoke-checks this.

## Writing command and skill specs

The specs in `.claude/commands/` and `.claude/skills/` are prompts that run on Claude Code and, through the generated `.agents/skills/` copies, on Antigravity/Gemini. Keep them portable and lean:

- **Frontmatter.** Every command starts with YAML frontmatter: a third-person `description` (what it does, "Use when ...", trigger phrases, "Also triggered by /name", under 1024 characters and not overlapping another command's), an `argument-hint`, and `disable-model-invocation: true` on commands with side effects the user should start explicitly (`/setup`, `/reset`, `/outcome`, `/gmail-sync`, `/notion-sync`, `/add-portal`, `/add-template`). `tools/sync_agent_skills.py` publishes that same description in the generated copy, so there is one source for it; `tools/lint_skills.py` fails a command whose frontmatter lacks one.
- **Steps.** Keep the existing `## Step N: <action>` headings (tests and cross-references such as "/outcome Step 1.4" pin them). Each step has one verifiable output. Where the flow needs the user, write an explicit `STOP — present X and wait for the user's reply` line and ask one question per turn. End long workflows with a final checklist that asks for the quoted output of every `tools/` command run.
- **Emphasis.** Reserve MUST/NEVER/ALWAYS/CRITICAL and bold "never" for real hard gates (fabrication, data loss, privacy, untrusted input, confirmation before destructive writes), each with a one-line reason. Write everything else as a plain affirmative instruction.
- **One canonical copy.** The compile/page/layout/ATS procedure lives in `/apply` Step 5 and the content verification checklist in `/apply` Step 6; `CLAUDE.md`, `05-cv-templates.md` and `06-cover-letter-templates.md` point there instead of repeating it. `CLAUDE.md` holds the profile and a short workflow pointer, not procedures, because it is loaded into every conversation.
- **Rationale goes here, not in the prompt.** Incident histories and design arguments cost context on every run; record them below and keep a one-line "why" in the spec.

## Design notes

Background for rules that the specs now state in one line.

- **`/apply` standing rule (write new facts back to the profile).** The Step 3 Factual Grounding Audit is deliberately strict: an ungrounded claim is removed, and it cannot tell a fabrication from a real fact the user stated out loud last week. That strictness is correct, and it is why confirmed facts have to reach the sources in the same turn they surface. `01-candidate-profile.md` is one of the audit's three sources, so a fact recorded there is grounded on the next run. A fact present in `01` but absent from `CLAUDE.md` and the master CV is an absence, not a contradiction, and does not trip the profile-consistency warning.
- **`/apply` Step 0 archives the posting and primes the brief up front.** `tools/gate_application.py` requires `job_posting.md` in the application folder, and `tools/prime_job.py` reads it to build `brief.md`; writing it in Step 6b alone left both without input. A run the user declines at Step 1 removes the folder again so `tools/check_consistency.py` does not report an orphan.
- **`/apply` Step 5 always runs.** LaTeX page-break decisions are unpredictable: sources that look fine commonly compile into orphaned `\cventry` titles, cover letters spilling to page 2, or bullet lists in the wrong font. Most corporate and bank sites also reject the default fetch user agent while serving a browser normally, which is why Step 0 escalates through `09-web-research.md` instead of drafting from a posting title.
- **`/scrape` routes picks to `/apply`.** The light assistant flow skipped the compile checks, the ATS export and the pre-submit gate; `/apply` owns all three.
- **gmail-sync.md intro:** the command's job is not "notice something in an inbox" but "propose a correct, sourced line for a permanent record, and write it only once the user says yes".
- **gmail-sync.md Step 7a (notes sanitising):** no writer emits a quoted tracker field and no reader unquotes one, so an unescaped comma splits the row identically for a naive split and for csv.DictReader; a line break ends the row and starts a second one. The double quote is stripped as cheap insurance for the day something does quote a field. The subject is a human-readable breadcrumb, not data anything reads back. This matters more than it looks: /gmail-sync is the only tracker writer that copies third-party text, and the only one that runs unattended, so nobody is watching the row it edits.
- **notion-sync.md Step 2 (deadline precedence):** both deadlines were read from the posting at different times; the safe-looking min() would substitute a date the user never applied against.
- **job-scraper/SKILL.md Step 4 (`source` field):** provenance keeps a ghost-job report diagnosable after the run's summary is gone: a stored entry whose URL later resolves to nothing (or to a different job) reads very differently depending on whether it came from live CLI output or from a search index that can be weeks stale - and a presented job with no entry at all points at fabrication, which Rule 1 forbids.
- **job-scraper/SKILL.md Step 4 (`posted_date` field):** Step 1b uses the CLI `date` to scope the run to 14 days and then dropped it, so nothing downstream could distinguish a posting published yesterday from one published two years ago (`first_seen` is when the scraper first saw it). Persisting it makes the window auditable and gives /rank a freshness signal. Incident: a freehire-search posting dated 2024-05-13 was scraped and ranked Strong Fit at position 1 of 133, its own scoring note observing the listing "may be long stale" with nothing able to act on it.
- **job-scraper/SKILL.md Step 4 (job_key helper):** the helper length-caps long titles and disambiguates the cap with a hash of the full slug, so a truncated title is stable across runs and two different long titles never collide.
- **job-scraper/SKILL.md Step 2.5 (mass posting):** the pattern alone proves nothing is wrong (companies legitimately hire the same role across several cities); it describes distribution, not legitimacy.
- **job-scraper/SKILL.md Step 2 (closed-at-source):** expired LinkedIn URLs redirect to similar live jobs, so a search hit can be a ghost; an absent seen_jobs entry looks identical to a job never seen, and the recorded `expired` status is what makes a later ghost report self-triaging.
- **setup.md Step 0 (origin preflight):** the check runs before anything is written because the Step 4 privacy note fires only once every file is already on disk, which is too late to inform the decision.
- **setup.md Design Principles:** three onboarding paths converge on the same skill files; Path A is read-before-write and idempotent (re-running as documents are added never duplicates or overwrites, conflicts are surfaced for explicit resolution) and labels inferred behavioral/style additions for critical review; Path C sections are a natural conversation, not a form, and optional sections can be skipped; answers are synthesized into structured formats so the user needs no markdown or LaTeX; `--section <name>` re-runs one section; Section 9 proactively suggests role types the user may not have considered; the run ends by suggesting /scrape and /apply with a test posting.
- **setup.md Final Step (sync):** the generated .agents/skills copies must be refreshed while the framework is still writable (config mode), and the CI drift check depends on it even for users who only run Claude Code.

Questions and proposals are welcome in [Discussions](https://github.com/MadsLorentzen/ai-job-search/discussions) - an Idea thread costs nothing and can save you building the wrong thing :-)

[#17]: https://github.com/MadsLorentzen/ai-job-search/issues/17
[#30]: https://github.com/MadsLorentzen/ai-job-search/issues/30
[#31]: https://github.com/MadsLorentzen/ai-job-search/issues/31
[#35]: https://github.com/MadsLorentzen/ai-job-search/issues/35
[#36]: https://github.com/MadsLorentzen/ai-job-search/issues/36
[#37]: https://github.com/MadsLorentzen/ai-job-search/issues/37
[#39]: https://github.com/MadsLorentzen/ai-job-search/issues/39
[#41]: https://github.com/MadsLorentzen/ai-job-search/issues/41
[#43]: https://github.com/MadsLorentzen/ai-job-search/issues/43
[#44]: https://github.com/MadsLorentzen/ai-job-search/issues/44
[#49]: https://github.com/MadsLorentzen/ai-job-search/issues/49
[#52]: https://github.com/MadsLorentzen/ai-job-search/issues/52
[#54]: https://github.com/MadsLorentzen/ai-job-search/issues/54
[#55]: https://github.com/MadsLorentzen/ai-job-search/issues/55
[#56]: https://github.com/MadsLorentzen/ai-job-search/issues/56
[#59]: https://github.com/MadsLorentzen/ai-job-search/issues/59
[#60]: https://github.com/MadsLorentzen/ai-job-search/issues/60
[#63]: https://github.com/MadsLorentzen/ai-job-search/issues/63
[#64]: https://github.com/MadsLorentzen/ai-job-search/issues/64
[#66]: https://github.com/MadsLorentzen/ai-job-search/issues/66
[#67]: https://github.com/MadsLorentzen/ai-job-search/issues/67
[#68]: https://github.com/MadsLorentzen/ai-job-search/issues/68
[#72]: https://github.com/MadsLorentzen/ai-job-search/issues/72
[#73]: https://github.com/MadsLorentzen/ai-job-search/issues/73
[#75]: https://github.com/MadsLorentzen/ai-job-search/issues/75
[#76]: https://github.com/MadsLorentzen/ai-job-search/issues/76
[#155]: https://github.com/MadsLorentzen/ai-job-search/pull/155
[#162]: https://github.com/MadsLorentzen/ai-job-search/pull/162
[#165]: https://github.com/MadsLorentzen/ai-job-search/pull/165
