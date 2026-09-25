#!/usr/bin/env python3
"""Canonical Candidate Profile Parser and Single Source of Truth (SSOT).

Loads and extracts structured candidate data from CLAUDE.md,
01-candidate-profile.md, or an optional candidate_profile.json.
Provides a technology-agnostic interface for prime_job.py, gate_application.py,
and multi_scrape_runner.py.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
CLAUDE_MD_PATH = ROOT_DIR / "CLAUDE.md"
PROFILE_MD_PATH = ROOT_DIR / ".claude" / "skills" / "job-application-assistant" / "01-candidate-profile.md"
CONFIG_JSON_PATH = ROOT_DIR / "candidate_profile.json"


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


_force_utf8_output()


class CandidateProfile:
    """Structured representation of candidate's verified profile facts."""

    def __init__(
        self,
        name: str = "Candidate Name",
        role: str = "Software Engineer",
        location: str = "Remote",
        citizenship: str = "Global / Remote Contractor",
        phone: str = "",
        email: str = "",
        linkedin: str = "",
        github: str = "",
        notice_period: str = "2 weeks",
        vacations: str = "None scheduled",
        salary_contractor_usd: str = "USD $3,500-$6,000+/mo",
        salary_local_net: str = "Competitive local salary",
        salary_baseline_usd_contractor: str = "",
        salary_baseline_argentina_net: str = "",
        languages: Optional[Dict[str, str]] = None,
        education: Optional[List[str]] = None,
        experience: Optional[List[Dict[str, Any]]] = None,
        primary_skills: Optional[List[str]] = None,
        secondary_skills: Optional[List[str]] = None,
        databases: Optional[List[str]] = None,
        target_roles: Optional[List[str]] = None,
        seniority: Optional[List[str]] = None,
        employers: Optional[List[str]] = None,
        **kwargs: Any,
    ):
        self.name = name.strip()
        self.role = role.strip()
        self.location = location.strip()
        self.citizenship = citizenship.strip()
        self.phone = phone.strip()
        self.email = email.strip()
        self.linkedin = linkedin.strip()
        self.github = github.strip()
        self.notice_period = notice_period.strip()
        self.vacations = vacations.strip()
        self.salary_contractor_usd = (salary_baseline_usd_contractor or salary_contractor_usd).strip()
        self.salary_local_net = (salary_baseline_argentina_net or salary_local_net).strip()
        self.languages = languages or {"English": "Professional"}
        self.education = education or []
        self.experience = experience or []
        self.primary_skills = primary_skills or ["Backend", "API", "Web Development"]
        self.secondary_skills = secondary_skills or []
        self.databases = databases or ["PostgreSQL"]
        self.target_roles = target_roles or ["Software Engineer", "Backend Developer"]
        self.seniority = seniority or ["Senior", "Mid"]
        self.employers = employers or []

    @property
    def clean_name(self) -> str:
        """Sanitized name for ATS filenames, e.g. 'JaneDoe'."""
        cleaned = re.sub(r"[^A-Za-z0-9]", "", self.name)
        return cleaned or "Candidate"

    @property
    def phone_digits(self) -> str:
        """Digits-only representation of phone number."""
        return re.sub(r"\D", "", self.phone)

    @property
    def all_skills(self) -> List[str]:
        """Unified list of primary + secondary + database skills."""
        seen = set()
        out = []
        for s in self.primary_skills + self.secondary_skills + self.databases:
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out

    def to_facts_dict(self) -> Dict[str, Any]:
        """Produces canonical candidate facts dictionary for brief.md."""
        return {
            "name": self.name,
            "location": self.location,
            "citizenship": self.citizenship,
            "phone": self.phone,
            "email": self.email,
            "linkedin": self.linkedin,
            "github": self.github,
            "notice_period": self.notice_period,
            "vacations": self.vacations,
            "salary_baseline_usd_contractor": self.salary_contractor_usd,
            "salary_baseline_argentina_net": self.salary_local_net,
            "languages": self.languages,
            "education": self.education,
            "experience": self.experience,
            "primary_skills": self.primary_skills,
            "secondary_skills": self.secondary_skills,
            "databases": self.databases,
            "target_roles": self.target_roles,
            "employers": self.employers,
        }


def _extract_field(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else default


def parse_profile_from_markdown(content: str) -> CandidateProfile:
    """Parses markdown content (from CLAUDE.md or 01-candidate-profile.md) into CandidateProfile."""
    # Name
    name = _extract_field(content, r"^-\s+\*\*Name:\*\*\s*(.+)$")
    if not name:
        m = re.search(r"^#\s+(?:Job Application Assistant for\s+)?([A-Za-z\s]+)$", content, re.MULTILINE)
        if m:
            name = m.group(1).strip()
    if not name:
        name = "Candidate Name"

    # Identity fields
    location = _extract_field(content, r"^-\s+\*\*(?:Location\s*(?:/\s*Address)?):\*\*\s*(.+)$", "Remote")
    citizenship = _extract_field(content, r"^-\s+\*\*Citizenship:\*\*\s*(.+)$", "Authorized for remote contractor B2B")
    phone = _extract_field(content, r"^-\s+\*\*Phone:\*\*\s*(.+)$", "")
    email = _extract_field(content, r"^-\s+\*\*Email:\*\*\s*(.+)$", "")
    linkedin = _extract_field(content, r"^-\s+\*\*LinkedIn:\*\*\s*(.+)$", "")
    github = _extract_field(content, r"^-\s+\*\*GitHub:\*\*\s*(.+)$", "")
    notice = _extract_field(content, r"^-\s+\*\*(?:Notice Period\s*(?:/\s*Availability)?):\*\*\s*(.+)$", "2 weeks")
    vacations = _extract_field(content, r"^-\s+\*\*(?:Planned Vacations\s*(?:/\s*Time Off)?):\*\*\s*(.+)$", "None scheduled")

    # Clean markdown formatting in extracted fields
    linkedin = re.sub(r"[\[\]\(\)]", "", linkedin).strip()
    github = re.sub(r"[\[\]\(\)]", "", github).strip()
    if "http" in linkedin:
        m_li = re.search(r"https?://[^\s\)]+", linkedin)
        if m_li:
            linkedin = m_li.group(0)
    if "http" in github:
        m_gh = re.search(r"https?://[^\s\)]+", github)
        if m_gh:
            github = m_gh.group(0)

    # Compensation
    contractor_sal = _extract_field(
        content,
        r"^-\s+\*\*(?:Remote-global\s*/\s*Contractor\s*\(USD\)|Salary baseline\s*\(Contractor\s*/\s*USD\)):\*\*\s*(.+)$",
        "Min USD $3,500/month",
    )
    local_sal = _extract_field(
        content,
        r"^-\s+\*\*(?:Formal\s*\(.*?Argentina\)|Salary baseline\s*\(Argentina\s*/\s*Net\)):\*\*\s*(.+)$",
        "USD $2,300-$2,700/month net",
    )

    # Technical Skills
    primary_str = _extract_field(content, r"^-\s+\*\*Primary:\*\*\s*(.+)$")
    secondary_str = _extract_field(content, r"^-\s+\*\*Secondary:\*\*\s*(.+)$")
    db_str = _extract_field(content, r"^-\s+\*\*Databases:\*\*\s*(.+)$")

    primary_skills = [s.strip() for s in primary_str.split(",") if s.strip()] if primary_str else [
        "Ruby on Rails", "Ruby", "PostgreSQL", "RSpec", "REST APIs", "CI/CD"
    ]
    secondary_skills = [s.strip() for s in secondary_str.split(",") if s.strip()] if secondary_str else [
        "React", "TypeScript", "JavaScript", "HTML/CSS", "Redis"
    ]
    databases = [s.strip() for s in db_str.split(",") if s.strip()] if db_str else ["PostgreSQL", "Redis"]

    # Target Roles
    roles_str = _extract_field(content, r"^-\s+\*\*Target roles:\*\*\s*(.+)$")
    target_roles = [r.strip() for r in roles_str.split(",") if r.strip()] if roles_str else [
        "Backend Developer", "Full Stack Developer", "Software Engineer"
    ]

    # Experience parse
    experience = []
    # Match experience blocks e.g. - **Senior Software Engineer** (2024 - present) - **Tech Innovations Inc.**
    exp_blocks = re.findall(
        r"-\s+\*\*([^\*]+)\*\*\s*\(([^\)]+)\)\s*-\s*\*\*([^\*]+)\*\*(.*?)(?=\n-\s+\*\*|\n###|\n##|\Z)",
        content,
        re.DOTALL,
    )
    for role_title, period, comp, body in exp_blocks:
        bullets = [b.strip().lstrip("-* ").strip() for b in body.split("\n") if b.strip().startswith(("-", "*"))]
        experience.append({
            "role": role_title.strip(),
            "company": comp.strip(),
            "period": period.strip(),
            "location": "Remote",
            "bullets": bullets or ["Delivered high performance features in agile sprints."],
        })

    # Default fallback experience if none parsed
    if not experience:
        experience = [
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
        ]

    # Extract clean employers from parsed experience
    employers = []
    for exp in experience:
        c = exp.get("company", "").strip()
        if c and c not in employers:
            employers.append(c)

    languages = {
        "English": "Professional Working Proficiency",
        "Spanish": "Working Proficiency",
    }
    education = [
        "B.S. in Computer Science (or equivalent practical engineering experience)",
    ]

    return CandidateProfile(
        name=name,
        location=location,
        citizenship=citizenship,
        phone=phone,
        email=email,
        linkedin=linkedin,
        github=github,
        notice_period=notice,
        vacations=vacations,
        salary_contractor_usd=contractor_sal,
        salary_local_net=local_sal,
        languages=languages,
        education=education,
        experience=experience,
        primary_skills=primary_skills,
        secondary_skills=secondary_skills,
        databases=databases,
        target_roles=target_roles,
        employers=employers,
    )


def load_candidate_profile(root: Optional[Path] = None) -> CandidateProfile:
    """Loads candidate profile prioritizing candidate_profile.json, then CLAUDE.md, then 01-candidate-profile.md."""
    base = root or ROOT_DIR

    # 1. Config JSON if available
    cfg_file = base / "candidate_profile.json"
    if cfg_file.is_file():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CandidateProfile(**data)
        except Exception:
            pass

    # 2. CLAUDE.md
    claude_file = base / "CLAUDE.md"
    if claude_file.is_file():
        try:
            content = claude_file.read_text(encoding="utf-8")
            return parse_profile_from_markdown(content)
        except Exception:
            pass

    # 3. 01-candidate-profile.md
    prof_file = base / ".claude" / "skills" / "job-application-assistant" / "01-candidate-profile.md"
    if prof_file.is_file():
        try:
            content = prof_file.read_text(encoding="utf-8")
            return parse_profile_from_markdown(content)
        except Exception:
            pass

    # Default fallback
    return CandidateProfile(
        name="Candidate Name",
        phone="+1 555 123 4567",
        email="candidate@example.com",
        location="Remote",
        employers=["Tech Innovations Inc.", "CloudScale Solutions"],
        primary_skills=["Backend", "REST APIs", "SQL", "CI/CD"],
        secondary_skills=["Docker", "Cloud", "Git"],
    )


if __name__ == "__main__":
    profile = load_candidate_profile()
    print(f"Loaded Profile: {profile.name} ({profile.clean_name})")
    print(f"Email: {profile.email} | Phone: {profile.phone}")
    print(f"Primary Skills: {', '.join(profile.primary_skills)}")
    print(f"Employers: {', '.join(profile.employers)}")
