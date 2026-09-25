# AI Remote Dev Search

*Autonomous Job Search, Tailored Applications & Invariant Quality Gates for Remote Software Developers Worldwide.*

[![Toolchain Diagnostic](https://img.shields.io/badge/Doctor-Passing-success)](tools/doctor.py)
[![Verification Gates](https://img.shields.io/badge/Quality_Gates-Enforced-blue)](tools/gate_application.py)
[![Integrated Portals](https://img.shields.io/badge/Scraper_Portals-19_Active-informational)](.agents/skills/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An agentic job application framework built for **remote software engineers, developers, and tech talent worldwide**. Fork it, define your single source of truth (SSOT) profile, and let AI evaluate openings, generate verified ATS-compliant CVs & cover letters, track applications, and maintain persistent cross-run memory.

> **Based on [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)**, upgraded with 19 international tech job boards, deterministic quality gates, state drift reconciliation, append-only memory ledgers, recommended MCP servers, and technology-agnostic architecture.

```
/setup          /scrape              /rank                 /apply <url>
  |                |                    |                       |
  v                v                    v                       v
Profile        Search 19            Batch score          Drafter-Reviewer
Onboarding     Job Portals          5 dimensions         Pipeline (LaTeX)
  |                |                    |                       |
  v                v                    v                       v
Verified       Structured           Prioritized          Mechanical ATS Gate
SSOT Ready     Matches              Shortlist            (Exact 2p CV, 1p CL)
```

---

## 🎯 Why This Fork?

Traditional job search scripts suffer from three critical flaws:
1. **Context Window Bloat & Hallucination:** Agents reading 30k+ tokens hallucinate skills and experience you don't possess, leading to instant disqualification in technical interviews.
2. **Brittle ATS & Visual Formatting:** TeX compilers unpredictably spill content onto a 3rd page or break ATS text layers, making resumes unparseable by Greenhouse, Lever, Workday, or Ashby.
3. **Regional & Stack Rigidity:** Most tools are tied to a single country's job boards or hardcoded to specific tech stacks.

**AI Remote Dev Search solves this through formal engineering principles:**

* **Single Source of Truth (SSOT):** Fully technology-agnostic. Whether you write Go, Rust, Python, TypeScript, React, Java, Ruby on Rails, or Elixir, define your stack once in [`CLAUDE.md`](CLAUDE.md) or `candidate_profile.json`.
* **Deterministic Pre-Submit Quality Gate:** Automated mechanical barrier (`python tools/gate_application.py`) enforcing ATS naming (`<CandidateName>_CV.pdf`), exact page counts (CV=2, CL=1), extractable text layers, contact verification, and zero hallucinated claims.
* **Frozen Context Brief Packaging:** Compresses verbose job postings into a token-budgeted `<2.5k` token `brief.md` (`python tools/prime_job.py`), anchoring tailoring to verifiable facts.
* **State Drift & Reconciliation Engine:** Audits and self-heals state discrepancies between tracker CSVs, scraper archives, and application directories (`python tools/check_consistency.py --fix`).
* **Append-Only Memory Ledger:** Records learnings from recruiter preferences, ATS quirks, and interview feedback with tombstone support (`python tools/remember.py`).
* **Applicant Privacy by Default:** All personal memories (`insights.jsonl`), tailored CVs/cover letters, tracker rows, and personal documents are strictly ignored in `.gitignore`.

---

## 👤 Candidate Onboarding: How Your Profile is Read (`/setup`)

Output quality is directly bound to input fidelity. The framework establishes a **Single Source of Truth (SSOT)** representing your verified identity, capabilities, and constraints.

### The Three Onboarding Paths

When you run `/setup` inside your agent (Claude Code, Google Antigravity, Gemini CLI, Cursor, Cline), the assistant auto-detects what materials you provide:

1. **Path A — Career Documents Folder (Recommended):**
   Drop your existing career files into the `documents/` directory:
   * `documents/cv/`: Master CV (PDF or `.tex`).
   * `documents/linkedin/`: Exported LinkedIn profile PDF.
   * `documents/diplomas/`: University degrees, certifications, official transcripts.
   * `documents/references/`: Recommendation letters, performance reviews.
   * `documents/applications/`: Past cover letters and portfolio write-ups.
   
   The assistant scans all documents in parallel, parses dates, extracted achievements, and concrete metrics, and compiles your canonical profile without manual entry.

2. **Path B — Direct CV Import:**
   If you have a single existing resume, paste the text directly into the chat. The assistant parses your career chronology, education, and technical competencies into structured markdown sections.

3. **Path C — Guided Interview:**
   If starting from scratch, the assistant conducts an interactive diagnostic interview covering:
   * Core technical stack, secondary tools, databases, and infrastructure familiarity.
   * Target role titles, preferred team seniority, and engineering culture.
   * Location constraints, timezone availability, and remote contractor vs. local formal employment preferences.
   * Hard compensation baselines (Contractor USD / Local net).

### Profile Depth Matters

A thin profile produces generic applications; a detailed profile enables razor-sharp tailoring:
* **Contextual Achievements:** Avoid passive duty lists ("Responsible for APIs"). Document what you built, the scale, and the outcome ("Architected high-throughput REST API in Go with PostgreSQL, reducing p99 latency from 450ms to 85ms").
* **Transferable Skills & Learning Culture:** Document technologies you pick up quickly. The evaluation rubric distinguishes between core daily tools and rapidly learnable adjacent stacks.
* **Explicit Targeting vs. Latent Discovery:** Beyond explicit roles you already know, the framework analyzes your full trajectory to surface adjacent high-fit roles and emerging niches you might not have considered.

---

## ⚡ How `/apply` Works (Drafter-Reviewer Pipeline)

The `/apply` command runs a multi-agent **drafter-reviewer workflow** with mandatory compilation and visual inspection:

```
[Job Posting] ──► 1. Parse & Ingest Vacancy
                       │
                       ▼
                  2. Evaluate Fit (5 Scoring Dimensions + Language Gate)
                       │
                       ▼
                  3. Draft Tailored CV & Cover Letter (LaTeX)
                       │
                       ▼
                  4. Reviewer Agent (Company Research & Deep Critique)
                       │
                       ▼
                  5. Revise Drafts from Reviewer Feedback
                       │
                       ▼
                  6. Compile PDFs (lualatex for CV, xelatex for Cover Letter)
                       │
                       ▼
                  7. ATS Text Layer Verification (pdftotext extraction)
                       │
                       ▼
                  8. Pre-Submit Mechanical Gate (tools/gate_application.py)
```

### What Makes This Workflow Different

* **Deterministic PDF Verification Loop:** Most LaTeX templates produce output that looks fine in `.tex` but breaks in PDF (section titles orphaned on page 2, cover letters spilling onto a second page). `/apply` compiles and inspects page counts mechanically: CVs must be **exactly 2 pages**, and Cover Letters must be **exactly 1 page**.
* **ATS Text Layer Verification:** Applicant Tracking Systems (Greenhouse, Lever, Workday, Ashby) parse the raw text stream inside the PDF, not the rendered graphic. The gate runs `pdftotext` to ensure emails, phone numbers, and technical keywords extract cleanly without scrambled glyphs or ligatures.
* **Relevance-Weighted CV Pruning:** When tailoring causes a CV to exceed 2 pages, the workflow does not blindly delete the oldest job. It scores each bullet point by target keyword relevance, uniqueness, and cover letter alignment, preserving high-impact historical bullets that match the target role over less relevant recent bullets.
* **Context Isolation via Drafter-Reviewer Separation:** The drafter agent writes the application. A secondary reviewer agent with clean context independently audits the company, checks against recruiter red flags, and critiques the draft before submission.

---

## 💻 Available Slash Commands Reference

Once your profile is set up, these commands drive your day-to-day workflow:

| Command | Purpose | Description |
|---|---|---|
| `/setup` | Candidate Onboarding | Builds your SSOT profile via documents folder, pasted CV, or interview. |
| `/scrape` | Multi-Portal Discovery | Concurrently queries job boards, filters by recency (last 14 days), and runs language gates. |
| `/rank` | Batch Fit Triage | Batch-scores scraped jobs across the 5 evaluation dimensions, producing a prioritized shortlist. |
| `/apply <url\|text>` | Autonomous Application | Executes the full drafter-reviewer pipeline, compiles PDFs, and runs ATS quality gates. |
| `/interview <company_role>`| Interview Preparation | Generates stage-specific prep packs, company culture audits, STAR narratives, and mock questions. |
| `/outcome` | Status & State Updates | Records application results (`applied`, `interview`, `offer`, `rejected`), updates tracker, and archives materials. |
| `/gmail-sync` | Automated Inbox Sync | Connects via Gmail to detect interview invitations, assessments, and rejections automatically. |
| `/notion-sync` | Kanban Pipeline Sync | Synchronizes application records and pipeline stages to a Notion database board. |
| `/expand` | Profile Enrichment | Scans public links (GitHub, portfolio, Kaggle) and course syllabi to surface implicit skills. |
| `/upskill` | Market Gap Heatmap | Analyzes skill gaps across target vacancies and generates a focused learning plan with resources. |
| `/html-report` | Analytics Dashboard | Generates a zero-dependency offline HTML dashboard visualizing your application funnel and metrics. |
| `/add-portal` | Portal Skill Generator | Generates and scaffolds a new job portal search CLI skill under `.agents/skills/`. |
| `/add-template` | Template Registration | Registers custom CV or cover letter templates (LaTeX, Typst, Markdown). |
| `/reset` | Safe Workspace Wipe | Selectively resets profile data (`/reset profile`), document archives (`/reset documents`), or everything (`/reset all`). |

---

## 🌐 19 Integrated Job Portals

This workspace features 19 active scraper skills across international remote tech boards, startup networks, and regional platforms:

| Portal | Scope & Focus | Compensation & Tech |
|---|---|---|
| **Y Combinator (WAAS)** | YC-backed startups globally | Seed to Series C, Equity & USD salaries |
| **ENTRA Careers** | Direct Fastify ATS API across 36 countries | Greenhouse, Lever, Ashby live sync |
| **Himalayas** | Global remote software engineering | USD salary transparency & timezone filters |
| **Torre.ai** | LatAm & global remote tech | Transparent USD/COP ranges, verified skills |
| **Silver.dev** | LatAm developers hired by US startups | Curated remote roles, transparent USD pay |
| **Get on Board** | Leading Latin American tech platform | High-density remote & USD contractor roles |
| **Remotive** | Curated remote developer roles | Global remote, backend, fullstack, devops |
| **Freehire** | Aggregator spanning ~50 ATS platforms | Direct company career apply links |
| **We Work Remotely** | Longstanding remote-first tech board | Global remote engineering vacancies |
| **RemoteOK** | Worldwide tech, software, DevOps | Full remote positions |
| **LinkedIn** | Global queries with location filtering | Worldwide remote & local postings |
| **Company Careers** | Direct Greenhouse / Lever / Ashby lookup | Openings at Anthropic, Stripe, Despegar, etc. |
| **Regional Boards** | Computrabajo, Bumeran, ZonaJobs | Argentina & Spanish-speaking LatAm market |
| **European Boards** | Jobindex, Jobnet, Jobdanmark, Jobbank | Danish & Scandinavian tech ecosystem |

Run all scrapers concurrently with automated retry backoff:
```bash
python3 tools/multi_scrape_runner.py
```

---

## 🛠️ The Deterministic Toolchain

```
                     ┌───────────────────────┐
                     │ Candidate Profile     │
                     │ (CLAUDE.md / SSOT)    │
                     └──────────┬────────────┘
                                │
   /scrape ──────────► [prime_job.py] ────────► brief.md (< 2.5k tokens)
   (19 portals)                 │                     │
                                ▼                     ▼
                       [remember.py]           Draft CV (2p) & CL (1p)
                       (Memory Ledger)                │
                                                      ▼
                       [gate_application.py] ◄── Compile LaTeX
                       (Mechanical Gate)
                                │
                       ┌────────┴────────┐
                 PASS (Exit 0)      REVIEW (Exit 2)
                       │                 │
                       ▼                 ▼
                 Submit to ATS     Human Review Gate
```

### 1. Toolchain Diagnostic (`tools/doctor.py`)
Verifies your complete environment before running any operations:
```bash
python3 tools/doctor.py
```
Checks Python (>=3.10), uv, LuaLaTeX, XeLaTeX, Poppler (`pdftotext`, `pdfinfo`), JavaScript runtimes (Bun/Node), and workspace state integrity.

### 2. State Consistency & Auto-Reconciler (`tools/check_consistency.py`)
Detects orphan application folders, status discrepancies, or broken links:
```bash
# Check status
python3 tools/check_consistency.py

# Auto-reconcile state drift
python3 tools/check_consistency.py --fix
```

### 3. Context Brief Builder (`tools/prime_job.py`)
Builds a deterministic, frozen brief crossing job requirements with your verified candidate facts and historical memory insights:
```bash
python3 tools/prime_job.py <url-or-slug>
```

### 4. Mechanical Pre-Submit Quality Gate (`tools/gate_application.py`)
Blocks submission if invariants are violated:
```bash
python3 tools/gate_application.py <company_role>
```
* **Exit 0 (PASS):** ATS filename (`<CandidateName>_CV.pdf`), exact 2 pages CV, 1 page CL, extractable text layer, valid contacts, zero ungrounded claims.
* **Exit 1 (FAIL):** Layout overflow, missing files, or unverified technical claims.
* **Exit 2 (REVIEW):** Triggers The Hole Rule — subjective screening questions require human approval before submission.

### 5. Append-Only Memory Ledger (`tools/remember.py`)
Maintains an immutable ledger of learnings across application cycles:
```bash
# Record learning
python3 tools/remember.py "Company requires explicit mention of gRPC streaming" --company stripe --tags grpc,backend

# List active learnings
python3 tools/remember.py --list
```

---

## 📁 Repository Directory Structure

```
ai-remote-dev-search/
├── CLAUDE.md                          # Canonical candidate profile + system instructions
├── candidate_profile.json             # Optional local JSON profile (gitignored)
├── AGENTS.md                          # Thin-pointer guidelines for agent frameworks
├── .claude/
│   ├── commands/                      # Slash command specifications
│   │   ├── setup.md                   # /setup onboarding workflow
│   │   ├── scrape.md                  # /scrape discovery orchestration
│   │   ├── rank.md                    # /rank batch triage
│   │   ├── apply.md                   # /apply drafter-reviewer pipeline
│   │   ├── interview.md               # /interview prep pack generation
│   │   ├── outcome.md                 # /outcome result tracking
│   │   ├── gmail-sync.md              # /gmail-sync inbox tracking
│   │   ├── notion-sync.md             # /notion-sync database sync
│   │   ├── expand.md                  # /expand profile enrichment
│   │   ├── upskill.md                 # /upskill gap analysis & heatmap
│   │   ├── html-report.md             # /html-report dashboard builder
│   │   ├── add-portal.md              # /add-portal scraper generator
│   │   ├── add-template.md            # /add-template custom templates
│   │   └── reset.md                   # /reset workspace clean
│   └── skills/
│       ├── job-application-assistant/ # Core evaluation, CV & interview guidelines
│       ├── job-scraper/               # Search orchestration & queries
│       └── upskill/                   # Heatmap generation and curricula
├── .agents/skills/                    # 19 Job portal CLI search skills (portable format)
├── cv/
│   └── main_example.tex               # Moderncv master reference template (LaTeX)
├── cover_letters/
│   ├── cover.cls                      # Custom cover letter LaTeX document class
│   └── cover_example.tex              # Master cover letter reference template
├── documents/                         # Career source files (gitignored)
│   ├── cv/                            # Master CV source
│   ├── linkedin/                      # Profile export PDF
│   ├── diplomas/                      # Degrees & certifications
│   ├── references/                    # Recommendation letters
│   ├── memory/                        # insights.jsonl append-only ledger
│   └── applications/                  # Archived applications (<company>_<role>/)
├── job_scraper/                       # Scraper state cache (seen_jobs.json)
├── tools/                             # Deterministic verification toolchain
│   ├── doctor.py                      # Toolchain diagnostic
│   ├── check_consistency.py           # State drift reconciler
│   ├── prime_job.py                   # Frozen brief builder
│   ├── gate_application.py            # Pre-submit mechanical quality gate
│   ├── remember.py                    # Append-only memory ledger
│   └── multi_scrape_runner.py         # Multi-portal parallel runner
└── job_search_tracker.csv             # Central application tracking spreadsheet (gitignored)
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
* **Python 3.10+** and [uv](https://docs.astral.sh/uv/)
* **[Bun](https://bun.sh)** (or Node.js)
* **LaTeX Distribution**: TeX Live / MacTeX / MikTeX (`lualatex` for moderncv, `xelatex` for cover.cls)
* **Poppler utilities**: `pdftotext`, `pdfinfo`
  * Ubuntu/Debian: `sudo apt install poppler-utils`
  * macOS: `brew install poppler`
  * Windows: `choco install poppler`

Verify your setup in 5 seconds:
```bash
python3 tools/doctor.py
```

### 2. Clone and Setup
```bash
git clone https://github.com/IgnacioN99/ai-remote-dev-search.git
cd ai-remote-dev-search
```

Install CLI search dependencies:
```bash
for tool in himalayas-search torre-search waas-search entra-search remotive-search silverdev-search getonbrd-search freehire-search linkedin-search company-careers-search; do
  (cd .agents/skills/$tool/cli && bun install)
done
```

### 3. Configure Your Candidate Profile
Edit [`CLAUDE.md`](CLAUDE.md) or run `/setup` inside Claude Code / Antigravity / Gemini CLI:
* **Name & Contact Information**
* **Primary & Secondary Tech Stack** (Go, Rust, Python, Node, React, Java, Rails, etc.)
* **Verified Experience & Bullets**
* **Target Compensation & Notice Period**

### 4. Search & Apply
```bash
# Scrape across 19 portals concurrently
python3 tools/multi_scrape_runner.py

# Or use interactive slash commands inside your AI coding agent:
/scrape
/apply <job-url>
```

---

## 🔌 Recommended MCP Servers & Integrations

To unlock the full autonomous power of `ai-remote-dev-search` with AI agent runtimes (Claude Code, Google Antigravity, Cursor, Cline, Codex), connect these Model Context Protocol (MCP) servers:

### 1. Browser Automation (Playwright MCP)
* **Purpose:** Enables autonomous parsing of JavaScript-heavy job boards (Lever, Greenhouse, Workday, Ashby), extracting screening questions, and executing form submissions.
* **Configuration:**
  ```json
  {
    "mcpServers": {
      "playwright": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-playwright"]
      }
    }
  }
  ```

### 2. Google Workspace & Gmail MCP
* **Purpose:** Automates status updates directly from your inbox. Detects recruiter messages, interview invitations, and rejection notices to sync the tracking state automatically.
* **Configuration:**
  ```json
  {
    "mcpServers": {
      "google-workspace": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-google-workspace"]
      }
    }
  }
  ```

### 3. Notion Tracker MCP
* **Purpose:** Provides a visual Kanban board and relational database sync of all active applications, response times, and interview stages.
* **Usage:** Built-in workflow via `/notion-sync` or dedicated Notion database integrations.

### 4. Fetch & Web Research MCP
* **Purpose:** Token-efficient extraction of company culture, recent news, and salary benchmarks from tech forums and community boards without bloating your active context window.
* **Configuration:**
  ```json
  {
    "mcpServers": {
      "fetch": {
        "command": "uvx",
        "args": ["mcp-server-fetch"]
      }
    }
  }
  ```

### 5. Essential Local CLI Utilities
* **[uv](https://docs.astral.sh/uv/):** Blazing-fast Python package and project runner (`uv run --with pytest pytest`).
* **[Bun](https://bun.sh):** High-speed JavaScript/TypeScript runtime used by all 19 portal search CLIs under `.agents/skills/`.
* **[Poppler Utilities](https://poppler.freedesktop.org/):** Provides `pdftotext` and `pdfinfo` for mechanical ATS text layer validation and page count enforcement (`tools/gate_application.py`).
* **LaTeX Distribution:** `lualatex` (moderncv banking style) and `xelatex` (cover.cls) for ATS-compliant, deterministic PDF compilation.

---

## 🔒 Privacy & Data Hygiene

This framework is built with strict privacy guarantees:
* **`documents/memory/insights.jsonl`** is ignored by default.
* **`job_search_tracker.csv`** and **`seen_jobs.json`** are gitignored.
* **`documents/applications/**`** (briefs, notes, cover letters, tailored CVs) remain on your local drive.
* **`cv/*_CV*.*`** and **`cover_letters/*_CoverLetter*.*`** are never pushed upstream.
* **`candidate_profile.json`** and **`*.personal`** hold private candidate records safely.

Fork freely without leaking your personal career history.

---

## 🤝 Contributing & Community

Pull requests for new job portal scrapers, improved ATS validation rules, and agent workflows are welcome!
Please review [`AGENTS.md`](AGENTS.md) for architectural guidelines and ensure `python tools/doctor.py` and unit tests pass before submitting:

```bash
uv run --with pytest pytest
```

---

## 📄 License & Acknowledgements

- Based on [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search).
- [Mikkel Krogholm](https://github.com/mikkelkrogsholm) for original Danish CLI search skills.
- Licensed under the [MIT License](LICENSE).
