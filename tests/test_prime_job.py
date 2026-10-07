"""Unit tests for tools/prime_job.py (deterministic brief builder).

Written for `python3 -m unittest discover -s tests` (what CI runs) - stdlib only.

The skill-match classification test pins its own fixture skill lists instead of
relying on whatever profile the module loaded at import time: `prime_job` reads
the gitignored `candidate_profile.json` when present (a real candidate's stack)
and falls back to CLAUDE.md placeholders otherwise (CI), so asserting against the
loaded profile is non-deterministic and candidate-specific.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import prime_job  # noqa: E402
from tools.prime_job import (  # noqa: E402
    analyze_skill_match,
    build_deterministic_brief,
    extract_tech_keywords,
)
from tools.remember import record_insight  # noqa: E402

# Fixture skills for a synthetic Rails-centric candidate (not any real person).
FIXTURE_SKILLS = {
    "skills_primary": ["Ruby on Rails", "Ruby", "PostgreSQL", "RSpec", "REST APIs"],
    "skills_secondary": ["React", "TypeScript", "JavaScript", "Redis", "Docker"],
}


class ExtractTechKeywordsTests(unittest.TestCase):
    def test_extract_tech_keywords(self):
        text = "We are looking for a Senior Ruby on Rails developer with PostgreSQL, Redis, and React experience. AWS a plus."
        techs = extract_tech_keywords(text)
        for kw in ("ruby on rails", "postgresql", "redis", "react", "aws"):
            with self.subTest(keyword=kw):
                self.assertIn(kw, techs)


class AnalyzeSkillMatchTests(unittest.TestCase):
    def test_analyze_skill_match_classification(self):
        text = "Requirements: Ruby on Rails, RSpec, PostgreSQL, React, TypeScript, and Go or Rust experience."
        with patch.dict(prime_job.CANDIDATE_FACTS, FIXTURE_SKILLS):
            analysis = analyze_skill_match(text)

        expected = {
            # Core matches
            "direct_matches": ("ruby on rails", "rspec", "postgresql"),
            # Secondary matches
            "adjacent": ("react", "typescript"),
            # Gaps
            "gaps": ("go", "rust"),
        }
        for bucket, keywords in expected.items():
            for kw in keywords:
                with self.subTest(bucket=bucket, keyword=kw):
                    self.assertIn(kw, analysis[bucket])


class BuildBriefTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mem_file = Path(self._tmp.name) / "insights.jsonl"

    def test_build_deterministic_brief_contains_candidate_facts(self):
        slug = "acme_senior-backend-engineer"
        metadata = {
            "company": "Acme Corp",
            "title": "Senior Backend Engineer",
            "url": "https://acme.com/jobs/123",
            "location": "Remote",
            "salary": "USD $4,000/month",
        }
        posting_text = "Building Rails APIs with PostgreSQL and RSpec. Experience with Claude Code preferred."

        brief = build_deterministic_brief(slug, metadata, posting_text, memory_file=self.mem_file)

        # Check required sections
        for section in (
            "# Deterministic Application Brief: Acme Corp — Senior Backend Engineer",
            "## 1. Vacancy Metadata",
            "## 2. Hard Constraints & Deal-Breakers",
            "## 3. Candidate Profile Facts",
            "## 4. Skills Match & Gaps Matrix",
            "## 5. Key Tailoring Angles",
            "## 6. Relevant Memory & Insights",
        ):
            with self.subTest(section=section):
                self.assertIn(section, brief)

        # Check candidate profile facts present in brief
        self.assertIn(prime_job.CANDIDATE_FACTS["name"], brief)
        self.assertIn(prime_job.CANDIDATE_FACTS["email"], brief)
        self.assertIn("Skills Match & Gaps Matrix", brief)

    def test_memory_insights_injected_into_brief(self):
        record_insight(
            text="Acme Corp values deep RSpec mutation testing and query batching",
            tags=["rails", "rspec"],
            company="acme-corp",
            source="interview",
            memory_file=self.mem_file,
        )

        metadata = {
            "company": "Acme Corp",
            "title": "Senior Rails Dev",
            "url": "https://acme.com/jobs/123",
        }
        posting_text = "Looking for Senior Rails developer with RSpec"

        brief = build_deterministic_brief("acme-corp_senior-rails-dev", metadata, posting_text, memory_file=self.mem_file)

        self.assertIn("deep RSpec mutation testing", brief)
        self.assertIn("[ACME-CORP]", brief)


if __name__ == "__main__":
    unittest.main()
