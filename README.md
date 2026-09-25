# AI Remote Dev Search

*Autonomous Job Search, Tailored Applications & Invariant Quality Gates for Remote Software Developers Worldwide.*

[![Toolchain Diagnostic](https://img.shields.io/badge/Doctor-Passing-success)](tools/doctor.py)
[![Verification Gates](https://img.shields.io/badge/Quality_Gates-Enforced-blue)](tools/gate_application.py)
[![Integrated Portals](https://img.shields.io/badge/Scraper_Portals-19_Active-informational)](.agents/skills/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An agentic job application framework built for **remote software engineers, developers, and tech talent worldwide**. Fork it, define your single source of truth (SSOT) profile, and let AI evaluate openings, generate verified ATS-compliant CVs & cover letters, track applications, and maintain persistent cross-run memory.

> **Based on [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)**, upgraded with 19 international tech job boards, deterministic quality gates, state drift reconciliation, append-only memory ledgers, and technology-agnostic architecture.

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

Run them all concurrently with dynamic date windows:
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

## 🔒 Privacy & Data Hygiene

This framework is built with strict privacy guarantees:
* **`documents/memory/insights.jsonl`** is ignored by default.
* **`job_search_tracker.csv`** and **`seen_jobs.json`** are gitignored.
* **`documents/applications/**`** (briefs, notes, cover letters, tailored CVs) remain on your local drive.
* **`cv/*_CV*.*`** and **`cover_letters/*_CoverLetter*.*`** are never pushed upstream.

Fork freely without leaking your personal career history.

---

## 🤝 Contributing & Community

Pull requests for new job portal scrapers, improved ATS validation rules, and agent workflows are welcome!
Please review [`AGENTS.md`](AGENTS.md) for architectural guidelines and ensure `python tools/doctor.py` and unit tests pass before submitting.

```bash
uv run --with pytest pytest
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
