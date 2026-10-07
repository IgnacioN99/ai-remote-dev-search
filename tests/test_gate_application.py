"""Unit tests for tools/gate_application.py (deterministic pre-submit quality gate).

Written for `python3 -m unittest discover -s tests` (what CI runs) - stdlib only.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.candidate_profile import CandidateProfile  # noqa: E402
from tools.gate_application import evaluate_gate  # noqa: E402

MOCK_PROFILE = CandidateProfile(
    name="Alex Developer",
    location="Remote",
    phone="+1 555 123 4567",
    email="alex.developer@example.com",
    employers=["Tech Innovations Inc.", "CloudScale Solutions"],
    primary_skills=["Backend", "REST APIs", "SQL", "CI/CD"],
)

VALID_CV_TEXT = """
Alex Developer
Remote
MOBILE-ALT +1 555 123 4567 • Envelope alex.developer@example.com • LinkedIn • GitHub
Senior Software Engineer at Tech Innovations Inc. building backend services and APIs.
Formerly Software Engineer at CloudScale Solutions.
""" + "word " * 120

VALID_COVER_LETTER_TEXT = """
Dear Hiring Manager,
I am excited to apply for the Senior Software Engineer position.
With 4 years of experience delivering robust applications at Tech Innovations Inc. and CloudScale Solutions,
I specialize in API scalability, database optimization, and automated testing.
Sincerely,
Alex Developer
""" + "word " * 60


class GateApplicationTests(unittest.TestCase):
    def _make_app_dir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app_dir = Path(tmp.name) / "acme_backend-engineer"
        app_dir.mkdir()
        (app_dir / "job_posting.md").write_text("Acme Role", encoding="utf-8")
        return app_dir

    def _make_ats_named_app_dir(self) -> Path:
        app_dir = self._make_app_dir()
        (app_dir / "AlexDeveloper_CV.pdf").write_text("dummy", encoding="utf-8")
        (app_dir / "AlexDeveloper_CoverLetter.pdf").write_text("dummy", encoding="utf-8")
        return app_dir

    def test_missing_application_folder_fails(self):
        res = evaluate_gate("nonexistent_company_role", profile=MOCK_PROFILE)
        self.assertIs(res["passed"], False)
        self.assertTrue(any("not found" in err.lower() for err in res["errors"]))

    def test_ats_naming_violation_fails_when_only_internal_names_exist(self):
        app_dir = self._make_app_dir()
        (app_dir / "main_acme_backend-engineer.pdf").write_text("internal cv", encoding="utf-8")
        (app_dir / "cover_acme_backend-engineer.pdf").write_text("internal cl", encoding="utf-8")

        res = evaluate_gate(str(app_dir), profile=MOCK_PROFILE)
        self.assertIs(res["passed"], False)
        self.assertTrue(any("ATS Naming Violation" in err for err in res["errors"]))

    def test_compliant_application_passes(self):
        app_dir = self._make_ats_named_app_dir()

        with patch("tools.gate_application.extract_text_layer") as mock_extract:
            # Mock CV extraction: 2 pages, valid text
            # Mock Cover letter extraction: 1 page, valid text
            mock_extract.side_effect = [
                (VALID_CV_TEXT, 2, "mock_extractor"),
                (VALID_COVER_LETTER_TEXT, 1, "mock_extractor"),
            ]

            res = evaluate_gate(str(app_dir), profile=MOCK_PROFILE)
            self.assertIs(res["passed"], True)
            self.assertIs(res["needs_human_review"], False)
            self.assertEqual(len(res["errors"]), 0)

    def test_cv_page_count_violation_fails(self):
        app_dir = self._make_ats_named_app_dir()

        with patch("tools.gate_application.extract_text_layer") as mock_extract:
            # 3 pages for CV (violates exact 2 pages rule)
            mock_extract.side_effect = [
                (VALID_CV_TEXT, 3, "mock_extractor"),
                (VALID_COVER_LETTER_TEXT, 1, "mock_extractor"),
            ]

            res = evaluate_gate(str(app_dir), profile=MOCK_PROFILE)
            self.assertIs(res["passed"], False)
            self.assertTrue(any("Page Count Violation" in err for err in res["errors"]))

    def test_anti_hallucination_gate_detects_forbidden_claims(self):
        app_dir = self._make_ats_named_app_dir()

        # Injected hallucinated claim: "Ph.D. in Computer Science from Stanford"
        hallucinated_cv = VALID_CV_TEXT + "\nPh.D. in Computer Science from Stanford University\nCertified Kubernetes Administrator (CKA)"

        with patch("tools.gate_application.extract_text_layer") as mock_extract:
            mock_extract.side_effect = [
                (hallucinated_cv, 2, "mock_extractor"),
                (VALID_COVER_LETTER_TEXT, 1, "mock_extractor"),
            ]

            res = evaluate_gate(str(app_dir), profile=MOCK_PROFILE)
            self.assertIs(res["passed"], False)
            self.assertTrue(any("Anti-Hallucination Gate Failed" in err for err in res["errors"]))

    def test_detects_pending_human_review_marker(self):
        app_dir = self._make_ats_named_app_dir()
        (app_dir / "status.md").write_text("Screening Question 1: [?] Need user to specify US timezone overlap", encoding="utf-8")

        with patch("tools.gate_application.extract_text_layer") as mock_extract:
            mock_extract.side_effect = [
                (VALID_CV_TEXT, 2, "mock_extractor"),
                (VALID_COVER_LETTER_TEXT, 1, "mock_extractor"),
            ]

            res = evaluate_gate(str(app_dir), profile=MOCK_PROFILE)
            self.assertIs(res["passed"], True)
            self.assertIs(res["needs_human_review"], True)
            self.assertGreater(len(res["warnings"]), 0)


if __name__ == "__main__":
    unittest.main()
