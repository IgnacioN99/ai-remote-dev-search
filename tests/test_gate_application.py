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


    def _run_with_cv_text(self, app_dir: Path, cv_text: str):
        with patch("tools.gate_application.extract_text_layer") as mock_extract:
            mock_extract.side_effect = [
                (cv_text, 2, "mock_extractor"),
                (VALID_COVER_LETTER_TEXT, 1, "mock_extractor"),
            ]
            return evaluate_gate(str(app_dir), profile=MOCK_PROFILE)

    def test_lowercase_mit_in_danish_or_german_text_is_not_a_claim(self):
        app_dir = self._make_ats_named_app_dir()
        cv = VALID_CV_TEXT + "\nMit arbejde handler om data. Ich arbeite mit Python und mit Teams."
        res = self._run_with_cv_text(app_dir, cv)
        self.assertIs(res["passed"], True, res["errors"])

    def test_mit_acronym_and_full_name_still_flagged(self):
        for claim in ("M.Sc. Computer Science, MIT", "Massachusetts Institute of Technology"):
            app_dir = self._make_ats_named_app_dir()
            res = self._run_with_cv_text(app_dir, VALID_CV_TEXT + "\n" + claim)
            self.assertIs(res["passed"], False, claim)
            self.assertTrue(any("Anti-Hallucination" in e for e in res["errors"]), claim)

    def test_mit_license_is_not_a_claim(self):
        app_dir = self._make_ats_named_app_dir()
        res = self._run_with_cv_text(app_dir, VALID_CV_TEXT + "\nOpen-source tool released under the MIT License")
        self.assertIs(res["passed"], True, res["errors"])

    def test_partial_slug_does_not_match_another_application(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        apps = Path(tmp.name)
        (apps / "acme_backend-engineer").mkdir()
        with patch("tools.gate_application.APPLICATIONS_DIR", apps):
            res = evaluate_gate("acme", profile=MOCK_PROFILE)
            self.assertIs(res["passed"], False)
            self.assertIsNone(res["app_folder"])
            self.assertTrue(any("not found" in e and "exact" in e for e in res["errors"]), res["errors"])
            exact = evaluate_gate("acme_backend-engineer", profile=MOCK_PROFILE)
            self.assertEqual(Path(exact["app_folder"]).name, "acme_backend-engineer")

    def test_markers_in_posting_and_brief_are_ignored(self):
        app_dir = self._make_ats_named_app_dir()
        (app_dir / "job_posting.md").write_text("TODO: candidates must [?] NEEDS_REVIEW", encoding="utf-8")
        (app_dir / "brief.md").write_text("Insight: TODO revisit", encoding="utf-8")
        res = self._run_with_cv_text(app_dir, VALID_CV_TEXT)
        self.assertIs(res["passed"], True)
        self.assertIs(res["needs_human_review"], False, res["warnings"])

    def test_markers_in_cv_source_and_form_answers_are_flagged(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "cv").mkdir()
        (root / "cover_letters").mkdir()
        app_dir = self._make_ats_named_app_dir()
        slug = app_dir.name
        (root / "cv" / f"main_{slug}.tex").write_text("% TODO confirm metric\n", encoding="utf-8")
        with patch("tools.gate_application.ROOT_DIR", root):
            res = self._run_with_cv_text(app_dir, VALID_CV_TEXT)
        self.assertIs(res["needs_human_review"], True)
        self.assertTrue(any(f"main_{slug}.tex" in w for w in res["warnings"]), res["warnings"])

        (root / "cv" / f"main_{slug}.tex").write_text("clean\n", encoding="utf-8")
        (app_dir / "application_fields.txt").write_text("Motivation: [?] ask user", encoding="utf-8")
        with patch("tools.gate_application.ROOT_DIR", root):
            res = self._run_with_cv_text(app_dir, VALID_CV_TEXT)
        self.assertIs(res["needs_human_review"], True)
        self.assertTrue(any("application_fields.txt" in w for w in res["warnings"]), res["warnings"])


if __name__ == "__main__":
    unittest.main()
