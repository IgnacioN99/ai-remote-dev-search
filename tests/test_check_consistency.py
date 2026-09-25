"""Unit tests for tools/check_consistency.py (drift detection and reconciliation)."""

import csv
import json
from pathlib import Path
import pytest
from tools.check_consistency import (
    audit_consistency,
    reconcile_drift,
    has_drift_detected,
)


@pytest.fixture
def mock_workspace(tmp_path: Path):
    """Sets up a mock workspace with tracker, seen_jobs, and applications."""
    tracker_file = tmp_path / "job_search_tracker.csv"
    seen_file = tmp_path / "seen_jobs.json"
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir(parents=True)

    # Tracker CSV with 1 application
    headers = [
        "date", "company", "sector", "role", "role_type", "channel",
        "status", "contact_person", "fit_rating", "notes",
        "cv_file", "cover_letter_file", "source", "deadline"
    ]
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
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    # Mock cv and cover_letters dirs
    (tmp_path / "cv").mkdir()
    (tmp_path / "cv" / "main_acme-corp_senior-rails-engineer.tex").write_text("cv", encoding="utf-8")
    (tmp_path / "cover_letters").mkdir()
    (tmp_path / "cover_letters" / "cover_acme-corp_senior-rails-engineer.tex").write_text("cl", encoding="utf-8")

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
    (acme_dir / "IgnacioFlores_CV.pdf").write_text("mock pdf", encoding="utf-8")

    return {
        "tracker": tracker_file,
        "seen": seen_file,
        "apps_dir": apps_dir,
    }


def test_consistent_state_reports_zero_drift(mock_workspace):
    report = audit_consistency(
        tracker_path=mock_workspace["tracker"],
        seen_path=mock_workspace["seen"],
        apps_dir=mock_workspace["apps_dir"],
        repo_root=mock_workspace["tracker"].parent,
    )
    assert not has_drift_detected(report)
    assert len(report["orphan_application_folders"]) == 0
    assert len(report["missing_application_folders"]) == 0
    assert len(report["state_discrepancies"]) == 0


def test_detects_orphan_application_folder(mock_workspace):
    orphan_dir = mock_workspace["apps_dir"] / "orphan-inc_backend-dev"
    orphan_dir.mkdir()
    (orphan_dir / "job_posting.md").write_text("Orphan job", encoding="utf-8")
    (orphan_dir / "outcome.md").write_text("Drafted", encoding="utf-8")
    (orphan_dir / "IgnacioFlores_CV.pdf").write_text("mock pdf", encoding="utf-8")

    report = audit_consistency(
        tracker_path=mock_workspace["tracker"],
        seen_path=mock_workspace["seen"],
        apps_dir=mock_workspace["apps_dir"],
        repo_root=mock_workspace["tracker"].parent,
    )
    assert has_drift_detected(report)
    assert "orphan-inc_backend-dev" in report["orphan_application_folders"]


def test_detects_state_discrepancy(mock_workspace):
    # Alter seen_jobs to 'new' while CSV is 'applied'
    with open(mock_workspace["seen"], "r", encoding="utf-8") as f:
        data = json.load(f)
    data["seen"]["https://acme.com/jobs/123"]["status"] = "new"
    with open(mock_workspace["seen"], "w", encoding="utf-8") as f:
        json.dump(data, f)

    report = audit_consistency(
        tracker_path=mock_workspace["tracker"],
        seen_path=mock_workspace["seen"],
        apps_dir=mock_workspace["apps_dir"],
        repo_root=mock_workspace["tracker"].parent,
    )
    assert has_drift_detected(report)
    assert len(report["state_discrepancies"]) == 1
    assert report["state_discrepancies"][0]["csv_status"] == "applied"
    assert report["state_discrepancies"][0]["seen_status"] == "new"


def test_detects_missing_application_files(mock_workspace):
    incomplete = mock_workspace["apps_dir"] / "incomplete_role"
    incomplete.mkdir()
    # Missing job_posting.md and outcome.md

    report = audit_consistency(
        tracker_path=mock_workspace["tracker"],
        seen_path=mock_workspace["seen"],
        apps_dir=mock_workspace["apps_dir"],
        repo_root=mock_workspace["tracker"].parent,
    )
    assert has_drift_detected(report)
    missing_for_incomplete = [item for item in report["missing_application_files"] if item["folder"] == "incomplete_role"]
    assert len(missing_for_incomplete) == 1


def test_reconciliation_heals_drift(mock_workspace):
    # 1. Add orphan folder with status.md
    orphan_dir = mock_workspace["apps_dir"] / "bridgenext_sr-rails-dev"
    orphan_dir.mkdir()
    (orphan_dir / "status.md").write_text("Role: Sr Rails Dev\nStatus: drafted\nPosting URL: https://example.com/bn", encoding="utf-8")
    (orphan_dir / "job_posting.md").write_text("Posting text", encoding="utf-8")
    (orphan_dir / "IgnacioFlores_CV.pdf").write_text("mock", encoding="utf-8")

    # 2. Add state drift in seen_jobs
    with open(mock_workspace["seen"], "r", encoding="utf-8") as f:
        data = json.load(f)
    data["seen"]["https://acme.com/jobs/123"]["status"] = "new"
    with open(mock_workspace["seen"], "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Run reconcile
    actions = reconcile_drift(
        tracker_path=mock_workspace["tracker"],
        seen_path=mock_workspace["seen"],
        apps_dir=mock_workspace["apps_dir"],
        repo_root=mock_workspace["tracker"].parent,
    )
    assert len(actions) >= 2

    # Check that seen_jobs status was synced back to applied
    with open(mock_workspace["seen"], "r", encoding="utf-8") as f:
        updated_seen = json.load(f)
    assert updated_seen["seen"]["https://acme.com/jobs/123"]["status"] == "applied"

    # Check that orphan was added to tracker CSV
    with open(mock_workspace["tracker"], "r", encoding="utf-8") as f:
        rows = list(csv.DictReader([l for l in f if l.strip()]))
    assert len(rows) == 2
    assert any("bridgenext" in r["company"].lower() for r in rows)
