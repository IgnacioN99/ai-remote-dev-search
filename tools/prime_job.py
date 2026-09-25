#!/usr/bin/env python3
"""Deterministic Application Brief Builder.

Deterministic context packaging and invariant-driven brief builder.
Takes a job vacancy (by application slug, URL, or company/role identifier),
extracts and cleans the job posting, crosses requirements against the
canonical candidate profile (CLAUDE.md / 01-candidate-profile.md),
retrieves relevant memory & insights from tools/remember.py, and outputs
a frozen, deterministic, token-budgeted brief.md.

Avoids token bloat (30k+ tokens across subagents) and prevents hallucinations
by establishing an immutable verified profile anchor for CV tailoring and cover letters.

Usage:
  python3 tools/prime_job.py codepath_staff-software-engineer
  python3 tools/prime_job.py documents/applications/bridgenext_senior-full-stack-engineer-rails-react-claude-code
  python3 tools/prime_job.py https://talent.fullstack.com/jobs/03113619-94e5-4f20-bb8f-73059cb3c49b/apply
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
SEEN_JOBS_FILE = ROOT_DIR / "job_scraper" / "seen_jobs.json"
APPLICATIONS_DIR = ROOT_DIR / "documents" / "applications"
TRACKER_CSV = ROOT_DIR / "job_search_tracker.csv"
MEMORY_FILE = ROOT_DIR / "documents" / "memory" / "insights.jsonl"

# Import memory and profile tools
sys.path.insert(0, str(ROOT_DIR / "tools"))
try:
    from remember import get_active_insights
except ImportError:
    get_active_insights = lambda **kwargs: []

try:
    from candidate_profile import load_candidate_profile
    _PROFILE = load_candidate_profile(ROOT_DIR)
    CANDIDATE_FACTS = _PROFILE.to_facts_dict()
    CANDIDATE_FACTS["skills_primary"] = _PROFILE.primary_skills
    CANDIDATE_FACTS["skills_secondary"] = _PROFILE.secondary_skills
    CANDIDATE_FACTS["ai_policy"] = "Explicitly reference Claude Code when discussing agentic engineering or AI-assisted development."
except Exception:
    # Canonical fallback if profile tool is unavailable
    CANDIDATE_FACTS = {
        "name": "Candidate Name",
        "location": "Remote",
        "citizenship": "Authorized for remote contractor B2B engagements",
        "phone": "+1 555 123 4567",
        "email": "candidate@example.com",
        "linkedin": "https://www.linkedin.com/in/candidate",
        "github": "https://github.com/candidate",
        "notice_period": "2 weeks",
        "vacations": "None scheduled",
        "salary_baseline_usd_contractor": "USD $3,500-$6,000+/month",
        "salary_baseline_argentina_net": "Competitive local salary",
        "languages": {
            "English": "Professional Working Proficiency",
            "Spanish": "Working Proficiency",
        },
        "education": [
            "B.S. in Computer Science (or equivalent practical engineering experience)",
        ],
        "experience": [
            {
                "role": "Senior Software Engineer",
                "company": "Tech Innovations Inc.",
                "period": "2024 - present",
                "location": "Remote",
                "bullets": [
                    "Architected and deployed high-throughput backend services and REST/gRPC APIs.",
                    "Optimized database queries, indexes, and caching strategies, reducing endpoint latency.",
                    "Expanded automated test suites in CI/CD pipelines, increasing coverage and deployment confidence.",
                ],
            },
            {
                "role": "Software Engineer",
                "company": "CloudScale Solutions",
                "period": "2021 - 2024",
                "location": "Remote",
                "bullets": [
                    "Developed backend business logic and integrated frontend applications.",
                    "Collaborated cross-functionally with product and design teams in agile sprints.",
                    "Maintained automated test coverage and documentation across services.",
                ],
            },
        ],
        "skills_primary": [
            "Backend", "REST APIs", "SQL", "CI/CD"
        ],
        "skills_secondary": [
            "Docker", "Cloud", "Git", "AI Tooling"
        ],
        "ai_policy": "Explicitly reference AI-assisted engineering tools when discussing agentic engineering.",
    }

KNOWN_TECH_STACKS = [
    "ruby", "rails", "ruby on rails", "python", "django", "fastapi", "react", "typescript",
    "javascript", "node", "nodejs", "express", "nestjs", "vue", "angular", "elixir", "phoenix",
    "go", "golang", "java", "spring", "c++", "c#", ".net", "rust", "php", "laravel",
    "postgresql", "postgres", "mysql", "redis", "mongodb", "elasticsearch", "clickhouse",
    "docker", "kubernetes", "aws", "gcp", "azure", "graphql", "rest", "ci/cd", "rspec",
    "jest", "tailwind", "stimulus", "turbo", "sidekiq", "claude code", "llm", "ai"
]


def slugify(text: str) -> str:
    if not text:
        return ""
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")


def extract_tech_keywords(text: str) -> List[str]:
    """Finds known technology keywords present in the text."""
    lower = text.lower()
    found = []
    for tech in KNOWN_TECH_STACKS:
        # Match word boundaries
        pattern = r"\b" + re.escape(tech) + r"\b"
        if re.search(pattern, lower):
            found.append(tech)
    return sorted(list(set(found)))


def resolve_vacancy(target: str) -> Tuple[str, Dict[str, Any], str]:
    """Resolves vacancy metadata and posting body from target.
    
    Target can be:
    - Path to application folder
    - Folder slug (e.g. 'codepath_staff-software-engineer')
    - Vacancy URL
    - Company name
    
    Returns (slug, metadata_dict, posting_text).
    """
    target = target.strip()

    # 1. Target is a local directory or relative path
    candidate_path = Path(target)
    if candidate_path.is_dir():
        slug = candidate_path.name
        return _load_from_app_folder(candidate_path, slug)

    if (APPLICATIONS_DIR / target).is_dir():
        slug = target
        return _load_from_app_folder(APPLICATIONS_DIR / target, slug)

    # 2. Target is in seen_jobs.json by key or URL
    if SEEN_JOBS_FILE.exists():
        try:
            with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
                seen = json.load(f).get("seen", {})
                # Direct key match
                if target in seen:
                    item = seen[target]
                    slug = target if not target.startswith("http") else slugify(f"{item.get('company')}_{item.get('title')}")
                    return _load_from_seen_item(slug, item)

                # Direct URL match
                for k, item in seen.items():
                    if item.get("url") == target or k == target:
                        slug = slugify(f"{item.get('company')}_{item.get('title')}")
                        return _load_from_seen_item(slug, item)

                # Substring search in seen jobs
                for k, item in seen.items():
                    c_title = f"{item.get('company')} {item.get('title')}".lower()
                    if target.lower() in k.lower() or target.lower() in c_title:
                        slug = slugify(f"{item.get('company')}_{item.get('title')}")
                        return _load_from_seen_item(slug, item)
        except Exception as e:
            print(f"Warning: could not search seen_jobs: {e}", file=sys.stderr)

    # 3. Fallback: treat as company/title query
    slug = slugify(target)
    metadata = {
        "company": target.replace("_", " ").title(),
        "title": "Software Engineer",
        "url": "",
        "source": "manual",
    }
    return slug, metadata, ""


def _load_from_app_folder(folder: Path, slug: str) -> Tuple[str, Dict[str, Any], str]:
    posting_file = folder / "job_posting.md"
    if not posting_file.exists():
        posting_file = folder / "job_description.md"

    posting_text = posting_file.read_text(encoding="utf-8") if posting_file.exists() else ""

    status_file = folder / "status.md"
    meta_url = ""
    meta_company = slug.split("_")[0].replace("-", " ").title()
    meta_title = " ".join(slug.split("_")[1:]).replace("-", " ").title() if "_" in slug else ""

    if status_file.exists():
        st = status_file.read_text(encoding="utf-8")
        m_url = re.search(r"Posting URL:\s*(\S+)", st)
        if m_url:
            meta_url = m_url.group(1)
        m_role = re.search(r"Role:\s*(.*)", st)
        if m_role:
            meta_title = m_role.group(1).strip()

    metadata = {
        "company": meta_company,
        "title": meta_title,
        "url": meta_url,
        "folder": str(folder),
        "source": "application_folder",
    }
    return slug, metadata, posting_text


def _load_from_seen_item(slug: str, item: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    # Check if application folder exists for posting text
    app_folder = APPLICATIONS_DIR / slug
    posting_text = ""
    if app_folder.is_dir():
        for pf in [app_folder / "job_posting.md", app_folder / "job_description.md"]:
            if pf.exists():
                posting_text = pf.read_text(encoding="utf-8")
                break

    if not posting_text:
        # Use description from seen_jobs if present
        posting_text = item.get("description") or item.get("snippet") or f"{item.get('title')} at {item.get('company')}"

    metadata = {
        "company": item.get("company", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "location": item.get("location", ""),
        "portal": item.get("portal", ""),
        "salary": item.get("salary", ""),
        "rank_score": item.get("rank_score", ""),
        "source": "seen_jobs",
    }
    return slug, metadata, posting_text


def analyze_skill_match(posting_text: str) -> Dict[str, List[str]]:
    techs = extract_tech_keywords(posting_text)
    primary = {s.lower() for s in CANDIDATE_FACTS["skills_primary"]}
    secondary = {s.lower() for s in CANDIDATE_FACTS["skills_secondary"]}
    all_candidate = primary | secondary | {"solid", "mvc", "api", "query optimization", "tdd"}

    direct_matches = []
    adjacent = []
    gaps = []

    for t in techs:
        t_low = t.lower()
        if any(t_low == c or t_low in c or c in t_low for c in primary):
            direct_matches.append(t)
        elif any(t_low == c or t_low in c or c in t_low for c in secondary):
            adjacent.append(t)
        else:
            gaps.append(t)

    return {
        "direct_matches": direct_matches,
        "adjacent": adjacent,
        "gaps": gaps,
        "all_detected": techs,
    }


def build_deterministic_brief(
    slug: str,
    metadata: Dict[str, Any],
    posting_text: str,
    memory_file: Path = MEMORY_FILE,
) -> str:
    """Builds a frozen, deterministic application brief markdown document."""
    company = metadata.get("company") or "Target Company"
    title = metadata.get("title") or "Target Role"
    url = metadata.get("url") or "N/A"
    portal = metadata.get("portal") or "Direct"
    loc = metadata.get("location") or "Remote"
    salary = metadata.get("salary") or "Unspecified in posting"

    analysis = analyze_skill_match(posting_text)

    # Query relevant memory insights
    company_slug = slugify(company)
    tech_tags = analysis["all_detected"]
    insights = []
    try:
        active = get_active_insights(memory_file=memory_file)
        for ins in active:
            ins_comp = ins.get("company") or ""
            ins_tags = ins.get("tags") or []
            if company_slug and company_slug in ins_comp:
                insights.append(ins)
            elif any(t in ins_tags for t in tech_tags):
                insights.append(ins)
    except Exception:
        insights = []

    doc: List[str] = []
    doc.append(f"# Deterministic Application Brief: {company} — {title}")
    doc.append("> Frozen context package for agentic tailoring. Token-budgeted & SSOT anchored.")
    doc.append("")

    # Section 1: Vacancy Metadata
    doc.append("## 1. Vacancy Metadata")
    doc.append(f"- **Company:** {company}")
    doc.append(f"- **Role / Title:** {title}")
    doc.append(f"- **Posting URL:** {url}")
    doc.append(f"- **Location / Arrangement:** {loc}")
    doc.append(f"- **Posting Salary:** {salary}")
    doc.append(f"- **Tracking Slug:** `{slug}`")
    doc.append("")

    # Section 2: Hard Constraints & Candidate Rules
    doc.append("## 2. Hard Constraints & Deal-Breakers (Candidate Rules)")
    doc.append(f"- **Candidate:** {CANDIDATE_FACTS['name']} ({CANDIDATE_FACTS['location']})")
    doc.append(f"- **Contact:** {CANDIDATE_FACTS.get('email', '')} | {CANDIDATE_FACTS.get('phone', '')}")
    doc.append(f"- **Authorization:** {CANDIDATE_FACTS['citizenship']}")
    doc.append(f"- **Availability / Notice Period:** {CANDIDATE_FACTS['notice_period']}")
    doc.append(f"- **Contractor Baseline (USD):** {CANDIDATE_FACTS['salary_baseline_usd_contractor']}")
    doc.append(f"- **Local Baseline (Net):** {CANDIDATE_FACTS.get('salary_baseline_argentina_net', '')}")
    lang_str = ", ".join(f"{k} ({v})" for k, v in CANDIDATE_FACTS.get("languages", {}).items())
    doc.append(f"- **Languages:** {lang_str}")
    doc.append(f"- **AI Reference Policy:** {CANDIDATE_FACTS['ai_policy']}")
    doc.append("")

    # Section 3: Candidate Profile Facts (Immutable Verifiable Facts)
    doc.append("## 3. Candidate Profile Facts (Immutable SSOT Evidence)")
    for exp in CANDIDATE_FACTS["experience"]:
        doc.append(f"### {exp['role']} — {exp['company']} ({exp['period']})")
        for b in exp["bullets"]:
            doc.append(f"- {b}")
    doc.append("")
    doc.append("### Education & Verified Studies")
    for edu in CANDIDATE_FACTS["education"]:
        doc.append(f"- {edu}")
    doc.append("")

    # Section 4: Skills Matrix & Gap Analysis
    doc.append("## 4. Skills Match & Gaps Matrix")
    direct_str = ", ".join(analysis["direct_matches"]) if analysis["direct_matches"] else "None explicitly detected"
    adj_str = ", ".join(analysis["adjacent"]) if analysis["adjacent"] else "None explicitly detected"
    gap_str = ", ".join(analysis["gaps"]) if analysis["gaps"] else "No obvious skill gaps detected"
    doc.append(f"- **Direct Core Matches:** {direct_str}")
    doc.append(f"- **Secondary / Adjacent Skills:** {adj_str}")
    doc.append(f"- **Potential Gaps / Out-of-Scope Technologies:** {gap_str}")
    doc.append("")

    # Section 5: Key Tailoring Angles
    doc.append("## 5. Key Tailoring Angles (STAR Evidence Points)")
    doc.append("1. **Backend Scalability & Performance:** Highlight database query optimization (indexing, query planning, connection pooling) and low-latency API architecture.")
    doc.append("2. **Engineering Rigor & Quality:** Emphasize test-driven automation in CI/CD pipelines, high coverage, and preventing regressions in production.")
    doc.append("3. **Full-stack & API Integration:** Feature decoupled backend service contracts integrated with modern web frontend clients.")
    doc.append("4. **AI-Native Engineering:** Position use of modern agentic coding tools for accelerated feature delivery, refactoring, and deterministic verification.")
    doc.append("")

    # Section 6: Relevant Memory & Insights
    doc.append("## 6. Relevant Memory & Insights (Learnings from Past Runs)")
    if insights:
        for ins in insights:
            tags_disp = ", ".join(ins.get("tags") or [])
            comp_disp = ins.get("company") or "general"
            doc.append(f"- **[{comp_disp.upper()}] (Tags: {tags_disp}):** {ins.get('text')}")
    else:
        doc.append("- No specific historical insights recorded for this company or stack yet. (Use `python3 tools/remember.py` to record new learnings).")
    doc.append("")

    return "\n".join(doc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic Application Brief Builder (token-budgeted context package)."
    )
    parser.add_argument(
        "target",
        help="Application folder, slug (e.g. codepath_staff-software-engineer), or vacancy URL",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path where brief.md should be written (defaults to documents/applications/<slug>/brief.md)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print generated brief to stdout instead of writing to disk",
    )
    parser.add_argument(
        "--memory-file",
        type=Path,
        default=MEMORY_FILE,
        help=f"Path to insights JSONL ledger (default: {MEMORY_FILE})",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        slug, metadata, posting_text = resolve_vacancy(args.target)
        brief_content = build_deterministic_brief(
            slug=slug,
            metadata=metadata,
            posting_text=posting_text,
            memory_file=args.memory_file,
        )

        if args.stdout:
            print(brief_content)
            return 0

        # Determine output path
        out_path = args.output
        if not out_path:
            target_dir = APPLICATIONS_DIR / slug
            target_dir.mkdir(parents=True, exist_ok=True)
            out_path = target_dir / "brief.md"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(brief_content, encoding="utf-8")
        print(f"[OK] Deterministic brief generated: {out_path}")
        return 0

    except Exception as e:
        print(f"Error building brief: {e}", file=sys.stderr)
        return 1


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
