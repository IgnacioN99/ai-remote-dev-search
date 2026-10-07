"""Unit tests for tools/candidate_profile.py.

Written for `python3 -m unittest discover -s tests` (what CI runs) - stdlib only.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.candidate_profile import (  # noqa: E402
    CandidateProfile,
    load_candidate_profile,
    parse_profile_from_markdown,
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


class CandidateProfileTests(unittest.TestCase):
    def test_candidate_profile_defaults(self):
        profile = CandidateProfile(name="Alex Smith")
        self.assertEqual(profile.name, "Alex Smith")
        self.assertEqual(profile.clean_name, "AlexSmith")
        self.assertIn("Backend", profile.primary_skills)

    def test_parse_profile_from_markdown(self):
        profile = parse_profile_from_markdown(SAMPLE_MARKDOWN_PROFILE)

        self.assertEqual(profile.name, "Jane Doe")
        self.assertEqual(profile.clean_name, "JaneDoe")
        self.assertEqual(profile.email, "jane.doe@example.com")
        self.assertIn("442079460991", profile.phone_digits)
        self.assertIn("Go", profile.primary_skills)
        self.assertIn("Kubernetes", profile.primary_skills)
        self.assertIn("Python", profile.secondary_skills)
        self.assertIn("ClickHouse", profile.databases)
        self.assertIn("FinTech Cloud", profile.employers)
        self.assertIn("DataPipe Systems", profile.employers)
        self.assertEqual(len(profile.experience), 2)

    def test_candidate_facts_dict(self):
        profile = parse_profile_from_markdown(SAMPLE_MARKDOWN_PROFILE)
        facts = profile.to_facts_dict()

        self.assertEqual(facts["name"], "Jane Doe")
        self.assertEqual(facts["email"], "jane.doe@example.com")
        self.assertIn("Go", facts["primary_skills"])
        self.assertIn("FinTech Cloud", facts["employers"])

    def test_load_candidate_profile_fallback(self):
        # Empty directory with no config or CLAUDE.md
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_candidate_profile(Path(tmp))
        self.assertNotEqual(profile.name, "")
        self.assertNotEqual(profile.clean_name, "")


if __name__ == "__main__":
    unittest.main()
