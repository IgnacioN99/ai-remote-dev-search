"""Unit tests for tools/prime_job.py (deterministic brief builder)."""

from pathlib import Path
import pytest
from tools.prime_job import (
    analyze_skill_match,
    build_deterministic_brief,
    resolve_vacancy,
    extract_tech_keywords,
)
from tools.remember import record_insight


def test_extract_tech_keywords():
    text = "We are looking for a Senior Ruby on Rails developer with PostgreSQL, Redis, and React experience. AWS a plus."
    techs = extract_tech_keywords(text)
    assert "ruby on rails" in techs
    assert "postgresql" in techs
    assert "redis" in techs
    assert "react" in techs
    assert "aws" in techs


def test_analyze_skill_match_classification():
    text = "Requirements: Ruby on Rails, RSpec, PostgreSQL, React, TypeScript, and Go or Rust experience."
    analysis = analyze_skill_match(text)

    # Core matches
    assert "ruby on rails" in analysis["direct_matches"]
    assert "rspec" in analysis["direct_matches"]
    assert "postgresql" in analysis["direct_matches"]

    # Secondary matches
    assert "react" in analysis["adjacent"]
    assert "typescript" in analysis["adjacent"]

    # Gaps
    assert "go" in analysis["gaps"]
    assert "rust" in analysis["gaps"]


def test_build_deterministic_brief_contains_candidate_facts(tmp_path: Path):
    mem_file = tmp_path / "insights.jsonl"
    slug = "acme_senior-backend-engineer"
    metadata = {
        "company": "Acme Corp",
        "title": "Senior Backend Engineer",
        "url": "https://acme.com/jobs/123",
        "location": "Remote",
        "salary": "USD $4,000/month",
    }
    posting_text = "Building Rails APIs with PostgreSQL and RSpec. Experience with Claude Code preferred."

    brief = build_deterministic_brief(slug, metadata, posting_text, memory_file=mem_file)

    # Check required sections
    assert "# Deterministic Application Brief: Acme Corp — Senior Backend Engineer" in brief
    assert "## 1. Vacancy Metadata" in brief
    assert "## 2. Hard Constraints & Deal-Breakers" in brief
    assert "## 3. Candidate Profile Facts" in brief
    assert "## 4. Skills Match & Gaps Matrix" in brief
    assert "## 5. Key Tailoring Angles" in brief
    assert "## 6. Relevant Memory & Insights" in brief

    # Check candidate verified profile facts
    assert "Ignacio Flores" in brief
    assert "Rootstrap" in brief
    assert "Snappler S.R.L." in brief
    assert "Min USD $3,500/month" in brief
    assert "Claude Code" in brief


def test_memory_insights_injected_into_brief(tmp_path: Path):
    mem_file = tmp_path / "insights.jsonl"
    record_insight(
        text="Acme Corp values deep RSpec mutation testing and query batching",
        tags=["rails", "rspec"],
        company="acme-corp",
        source="interview",
        memory_file=mem_file,
    )

    metadata = {
        "company": "Acme Corp",
        "title": "Senior Rails Dev",
        "url": "https://acme.com/jobs/123",
    }
    posting_text = "Looking for Senior Rails developer with RSpec"

    brief = build_deterministic_brief("acme-corp_senior-rails-dev", metadata, posting_text, memory_file=mem_file)

    assert "deep RSpec mutation testing" in brief
    assert "[ACME-CORP]" in brief
