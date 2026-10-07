"""Unit tests for tools/check_consistency.py (drift detection and reconciliation).

Written for `python3 -m unittest discover -s tests` (what CI runs) - stdlib only.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_consistency import (  # noqa: E402
    audit_consistency,
    has_drift_detected,
    reconcile_drift,
)

TRACKER_HEADERS = [
    "date", "company", "sector", "role", "role_type", "channel",
    "status", "contact_person", "fit_rating", "notes",
    "cv_file", "cover_letter_file", "source", "deadline"
]


def build_mock_workspace(root: Path) -> dict:
    """Sets up a mock workspace with tracker, seen_jobs, and applications."""
    tracker_file = root / "job_search_tracker.csv"
    seen_file = root / "seen_jobs.json"
    apps_dir = root / "applications"
    apps_dir.mkdir(parents=True)

    # Tracker CSV with 1 application
    rows = [
        {
            "date": "2026-09-20",
            "company": "Acme Corp",
            "sector": "Tech",
            "role": "Senior Rails Engineer",
            "role_type": "Full-time",
            "channel": "portal",
            "status": "applied",
            "contact_person": "",
            "fit_rating": "90",
            "notes": "Applied",
            "cv_file": "cv/main_acme-corp_senior-rails-engineer.tex",
            "cover_letter_file": "cover_letters/cover_acme-corp_senior-rails-engineer.tex",
            "source": "https://acme.com/jobs/123",
            "deadline": "",
        }
    ]
    with open(tracker_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    # Mock cv and cover_letters dirs
    (root / "cv").mkdir()
    (root / "cv" / "main_acme-corp_senior-rails-engineer.tex").write_text("cv", encoding="utf-8")
    (root / "cover_letters").mkdir()
    (root / "cover_letters" / "cover_acme-corp_senior-rails-engineer.tex").write_text("cl", encoding="utf-8")

    # Matching seen_jobs
    seen_data = {
        "seen": {
            "https://acme.com/jobs/123": {
                "company": "Acme Corp",
                "title": "Senior Rails Engineer",
                "url": "https://acme.com/jobs/123",
                "status": "applied",
            }
        }
    }
    with open(seen_file, "w", encoding="utf-8") as f:
        json.dump(seen_data, f, indent=2)

    # Matching app folder
    acme_dir = apps_dir / "acme-corp_senior-rails-engineer"
    acme_dir.mkdir()
    (acme_dir / "job_posting.md").write_text("Acme rails posting", encoding="utf-8")
    (acme_dir / "outcome.md").write_text("Applied", encoding="utf-8")
    (acme_dir / "Candidate_CV.pdf").write_text("mock pdf", encoding="utf-8")

    return {
        "tracker": tracker_file,
        "seen": seen_file,
        "apps_dir": apps_dir,
    }


class CheckConsistencyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = build_mock_workspace(Path(self._tmp.name))

    def _paths(self) -> dict:
        return dict(
            tracker_path=self.ws["tracker"],
            seen_path=self.ws["seen"],
            apps_dir=self.ws["apps_dir"],
            repo_root=self.ws["tracker"].parent,
        )

    def _set_seen_status(self, status: str) -> None:
        with open(self.ws["seen"], "r", encoding="utf-8") as f:
            data = json.load(f)
        data["seen"]["https://acme.com/jobs/123"]["status"] = status
        with open(self.ws["seen"], "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_consistent_state_reports_zero_drift(self):
        report = audit_consistency(**self._paths())
        self.assertFalse(has_drift_detected(report))
        self.assertEqual(len(report["orphan_application_folders"]), 0)
        self.assertEqual(len(report["missing_application_folders"]), 0)
        self.assertEqual(len(report["state_discrepancies"]), 0)

    def test_detects_orphan_application_folder(self):
        orphan_dir = self.ws["apps_dir"] / "orphan-inc_backend-dev"
        orphan_dir.mkdir()
        (orphan_dir / "job_posting.md").write_text("Orphan job", encoding="utf-8")
        (orphan_dir / "outcome.md").write_text("Drafted", encoding="utf-8")
        (orphan_dir / "Candidate_CV.pdf").write_text("mock pdf", encoding="utf-8")

        report = audit_consistency(**self._paths())
        self.assertTrue(has_drift_detected(report))
        self.assertIn("orphan-inc_backend-dev", report["orphan_application_folders"])

    def test_detects_state_discrepancy(self):
        # Alter seen_jobs to 'new' while CSV is 'applied'
        self._set_seen_status("new")

        report = audit_consistency(**self._paths())
        self.assertTrue(has_drift_detected(report))
        self.assertEqual(len(report["state_discrepancies"]), 1)
        self.assertEqual(report["state_discrepancies"][0]["csv_status"], "applied")
        self.assertEqual(report["state_discrepancies"][0]["seen_status"], "new")

    def test_detects_missing_application_files(self):
        incomplete = self.ws["apps_dir"] / "incomplete_role"
        incomplete.mkdir()
        # Missing job_posting.md and outcome.md

        report = audit_consistency(**self._paths())
        self.assertTrue(has_drift_detected(report))
        missing_for_incomplete = [
            item for item in report["missing_application_files"] if item["folder"] == "incomplete_role"
        ]
        self.assertEqual(len(missing_for_incomplete), 1)

    def test_reconciliation_heals_drift(self):
        # 1. Add orphan folder with status.md
        orphan_dir = self.ws["apps_dir"] / "initech_sr-rails-dev"
        orphan_dir.mkdir()
        (orphan_dir / "status.md").write_text(
            "Role: Sr Rails Dev\nStatus: drafted\nPosting URL: https://example.com/bn", encoding="utf-8"
        )
        (orphan_dir / "job_posting.md").write_text("Posting text", encoding="utf-8")
        (orphan_dir / "Candidate_CV.pdf").write_text("mock", encoding="utf-8")

        # 2. Add state drift in seen_jobs
        self._set_seen_status("new")

        # Run reconcile
        actions = reconcile_drift(**self._paths())
        self.assertGreaterEqual(len(actions), 2)

        # Check that seen_jobs status was synced back to applied
        with open(self.ws["seen"], "r", encoding="utf-8") as f:
            updated_seen = json.load(f)
        self.assertEqual(updated_seen["seen"]["https://acme.com/jobs/123"]["status"], "applied")

        # Check that orphan was added to tracker CSV
        with open(self.ws["tracker"], "r", encoding="utf-8") as f:
            rows = list(csv.DictReader([line for line in f if line.strip()]))
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("initech" in r["company"].lower() for r in rows))


if __name__ == "__main__":
    unittest.main()
