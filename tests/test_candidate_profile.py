"""Unit tests for tools/candidate_profile.py."""

from pathlib import Path
import pytest
from tools.candidate_profile import (
    CandidateProfile,
    parse_profile_from_markdown,
    load_candidate_profile,
)

SAMPLE_MARKDOWN_PROFILE = """
# Job Application Assistant for Jane Doe

## Candidate Profile

### Identity
- **Name:** Jane Doe
- **Location:** London, UK (UTC+0)
- **Citizenship:** British Citizen
- **Phone:** +44 20 7946 0991
- **Email:** jane.doe@example.com
- **LinkedIn:** https://www.linkedin.com/in/janedoe
- **GitHub:** https://github.com/janedoe
- **Notice Period / Availability:** 1 month
- **Planned Vacations / Time Off:** 2026-12-20 to 2027-01-05

### Compensation Baseline
- **Remote-global / Contractor (USD):** USD $5,000–$8,000/month
- **Formal (UK / Net):** GBP 4,000/month net

### Technical Skills
- **Primary:** Go, Golang, Kubernetes, Docker, Microservices, gRPC
- **Secondary:** Python, TypeScript, React, Kafka, Redis
- **Databases:** PostgreSQL, ClickHouse, Redis

### Target Roles & Preferences
- **Target roles:** Senior Go Engineer, Principal Backend Architect

### Professional Experience
- **Senior Go Engineer** (2023 - present) - **FinTech Cloud**
  - Architected high-throughput microservices in Go.
  - Implemented event streaming using Kafka and ClickHouse.
- **Backend Developer** (2020 - 2023) - **DataPipe Systems**
  - Built scalable REST and gRPC services in Go and PostgreSQL.
"""


def test_candidate_profile_defaults():
    profile = CandidateProfile(name="Alex Smith")
    assert profile.name == "Alex Smith"
    assert profile.clean_name == "AlexSmith"
    assert "Backend" in profile.primary_skills


def test_parse_profile_from_markdown():
    profile = parse_profile_from_markdown(SAMPLE_MARKDOWN_PROFILE)

    assert profile.name == "Jane Doe"
    assert profile.clean_name == "JaneDoe"
    assert profile.email == "jane.doe@example.com"
    assert "442079460991" in profile.phone_digits
    assert "Go" in profile.primary_skills
    assert "Kubernetes" in profile.primary_skills
    assert "Python" in profile.secondary_skills
    assert "ClickHouse" in profile.databases
    assert "FinTech Cloud" in profile.employers
    assert "DataPipe Systems" in profile.employers
    assert len(profile.experience) == 2


def test_candidate_facts_dict():
    profile = parse_profile_from_markdown(SAMPLE_MARKDOWN_PROFILE)
    facts = profile.to_facts_dict()

    assert facts["name"] == "Jane Doe"
    assert facts["email"] == "jane.doe@example.com"
    assert "Go" in facts["primary_skills"]
    assert "FinTech Cloud" in facts["employers"]


def test_load_candidate_profile_fallback(tmp_path: Path):
    # Empty directory with no config or CLAUDE.md
    profile = load_candidate_profile(tmp_path)
    assert profile.name != ""
    assert profile.clean_name != ""
