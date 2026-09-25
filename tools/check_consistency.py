#!/usr/bin/env python3
"""Audit synchronization and drift among tracker, seen jobs, and application archives.

Deterministic verification, invariant enforcement, and state drift detection.
Cross-audits:
  - job_search_tracker.csv
  - job_scraper/seen_jobs.json
  - documents/applications/<company>_<role>/

Detects:
  1. Applications with folders in documents/applications/ but no row in CSV (or vice versa).
  2. State discrepancies between tracker CSV and seen_jobs.json.
  3. Missing files in application folders (job_posting.md/job_description.md, outcome.md/status.md, PDFs).
  4. Broken references in CSV (cv_file or cover_letter_file pointing to missing paths).

Options:
  --fix / --reconcile: Automatically reconcile minor state drift (sync seen_jobs statuses,
                       normalize CSV formatting/headers, and register orphan applications).
  --json: Output report as structured JSON.

Exit Codes:
  0: Fully consistent (or successfully reconciled with --fix).
  1: Drift / inconsistencies detected.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
TRACKER_CSV = ROOT_DIR / "job_search_tracker.csv"
SEEN_JOBS_JSON = ROOT_DIR / "job_scraper" / "seen_jobs.json"
APPLICATIONS_DIR = ROOT_DIR / "documents" / "applications"


def slugify(text: str) -> str:
    """Normalize text into an alphanumeric slug."""
    if not text:
        return ""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")


def extract_linkedin_id(url: str) -> Optional[str]:
    """Extract numeric LinkedIn job id from URL if present."""
    if not url or "linkedin" not in url:
        return None
    match = re.search(r"(\d{8,12})", url)
    return match.group(1) if match else None


def load_tracker_csv(csv_path: Path = TRACKER_CSV) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
    """Loads tracker CSV, returning (headers, rows, raw_lines)."""
    if not csv_path.exists():
        return [], [], []

    raw_lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    non_empty_lines = [line for line in raw_lines if line.strip()]
    if not non_empty_lines:
        return [], [], raw_lines

    reader = csv.DictReader(non_empty_lines)
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)
    return fieldnames, rows, raw_lines


def load_seen_jobs(json_path: Path = SEEN_JOBS_JSON) -> Dict[str, Any]:
    """Loads seen_jobs.json."""
    if not json_path.exists():
        return {"seen": {}}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "seen" not in data or not isinstance(data["seen"], dict):
                data["seen"] = {}
            return data
    except Exception as e:
        print(f"Error reading {json_path}: {e}", file=sys.stderr)
        return {"seen": {}}


def derive_row_slug(row: Dict[str, str]) -> str:
    """Derive folder slug from row's cv_file, cover_letter_file, or company+role."""
    cv_file = row.get("cv_file", "").strip()
    if cv_file:
        m = re.search(r"main_(.*?)\.(?:tex|pdf)", cv_file)
        if m:
            return m.group(1)

    cl_file = row.get("cover_letter_file", "").strip()
    if cl_file:
        m = re.search(r"cover_(.*?)\.(?:tex|pdf)", cl_file)
        if m:
            return m.group(1)

    comp = slugify(row.get("company", ""))
    role = slugify(row.get("role", ""))
    return f"{comp}_{role}".strip("_")


def find_matching_seen_job(
    row: Dict[str, str],
    slug: str,
    seen_dict: Dict[str, Any],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Finds the corresponding entry in seen_jobs.json by exact key, URL, LinkedIn ID, or company."""
    source_url = row.get("source", "").strip()
    linkedin_id = extract_linkedin_id(source_url)

    # 1. Exact key match
    if slug in seen_dict:
        return slug, seen_dict[slug]

    # 2. Exact URL match
    for k, v in seen_dict.items():
        v_url = (v.get("url") or "").strip()
        if source_url and (k == source_url or v_url == source_url):
            return k, v

    # 3. LinkedIn ID match
    if linkedin_id:
        for k, v in seen_dict.items():
            v_url = (v.get("url") or "").strip()
            if linkedin_id in k or linkedin_id in v_url:
                return k, v

    # 4. Normalized company + role match
    row_comp = slugify(row.get("company", ""))
    row_role = slugify(row.get("role", ""))
    for k, v in seen_dict.items():
        v_comp = slugify(v.get("company", ""))
        v_title = slugify(v.get("title", ""))
        if row_comp and row_comp == v_comp:
            if row_role and (row_role in v_title or v_title in row_role):
                return k, v

    return None


def audit_consistency(
    tracker_path: Path = TRACKER_CSV,
    seen_path: Path = SEEN_JOBS_JSON,
    apps_dir: Path = APPLICATIONS_DIR,
    repo_root: Path = ROOT_DIR,
) -> Dict[str, Any]:
    """Conducts full consistency audit across tracker, seen_jobs, and applications."""
    headers, rows, raw_lines = load_tracker_csv(tracker_path)
    seen_data = load_seen_jobs(seen_path)
    seen_jobs = seen_data.get("seen", {})

    report: Dict[str, Any] = {
        "tracker_rows_count": len(rows),
        "seen_jobs_count": len(seen_jobs),
        "orphan_application_folders": [],
        "missing_application_folders": [],
        "state_discrepancies": [],
        "missing_application_files": [],
        "broken_file_references": [],
        "csv_formatting_issues": [],
    }

    # Check CSV formatting issues
    if any(line == "" for line in raw_lines):
        report["csv_formatting_issues"].append("Blank lines found in tracker CSV")
    if headers and "deadline" not in headers:
        report["csv_formatting_issues"].append("Tracker CSV header missing 'deadline' column")

    # Get application folders
    existing_folders = set()
    if apps_dir.exists():
        existing_folders = {d.name for d in apps_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}

    # Map rows to slugs
    row_slugs: Dict[str, Dict[str, str]] = {}
    for r in rows:
        slug = derive_row_slug(r)
        row_slugs[slug] = r

    # 1. Audit Folders vs CSV Rows
    for folder_name in sorted(existing_folders):
        folder_path = apps_dir / folder_name
        # Match with row slugs
        matched_row = None
        for s, r in row_slugs.items():
            if s == folder_name or s.replace("-", "") == folder_name.replace("-", "") or folder_name.startswith(s):
                matched_row = r
                break

        if not matched_row:
            report["orphan_application_folders"].append(folder_name)

        # Audit files inside application folder
        files = {f.name for f in folder_path.iterdir() if f.is_file()}
        missing_in_folder = []
        has_posting = any(name in files for name in ["job_posting.md", "job_description.md"])
        if not has_posting:
            missing_in_folder.append("job_posting.md (or job_description.md)")

        has_outcome = any(name in files for name in ["outcome.md", "status.md"])
        folder_status = matched_row.get("status", "").strip().lower() if matched_row else ""
        if not has_outcome and folder_status not in ["drafted"]:
            missing_in_folder.append("outcome.md (or status.md)")

        has_cv_pdf = any(
            name.endswith(".pdf") and ("IgnacioFlores_CV" in name or name.startswith("main_"))
            for name in files
        ) or any([
            (repo_root / "cv" / f"main_{folder_name}.pdf").exists(),
            (repo_root / "cv" / "IgnacioFlores_CV.pdf").exists(),
        ])
        if not has_cv_pdf:
            missing_in_folder.append("compiled CV PDF (IgnacioFlores_CV.pdf)")

        if missing_in_folder:
            report["missing_application_files"].append({
                "folder": folder_name,
                "missing": missing_in_folder,
            })

    # Check for rows missing folders
    for slug, row in row_slugs.items():
        status = row.get("status", "").strip()
        # Drafted rows might not yet have an archive folder, but applied/interview/closed should
        folder_exists = any(
            f == slug or f.replace("-", "") == slug.replace("-", "") or f.startswith(slug)
            for f in existing_folders
        )
        if not folder_exists and status not in ["drafted"]:
            report["missing_application_folders"].append({
                "slug": slug,
                "company": row.get("company"),
                "role": row.get("role"),
                "status": status,
            })

    # 2. Audit State Discrepancies between CSV and seen_jobs.json
    for slug, row in row_slugs.items():
        csv_status = row.get("status", "").strip().lower()
        matched_seen = find_matching_seen_job(row, slug, seen_jobs)
        if matched_seen:
            seen_key, seen_entry = matched_seen
            seen_status = (seen_entry.get("status") or "").strip().lower()

            # Normalise comparison
            # E.g., CSV 'applied' vs seen 'new'/'standby'
            # E.g., CSV 'rejected' vs seen 'applied'
            if csv_status and seen_status:
                mismatch = False
                if csv_status in ["applied", "interview", "offer", "hired"] and seen_status in ["new", "standby"]:
                    mismatch = True
                elif csv_status in ["rejected", "no_response", "withdrawn", "closed"] and seen_status in ["new", "applied", "standby"]:
                    mismatch = True
                elif csv_status == "drafted" and seen_status == "new":
                    mismatch = True

                if mismatch:
                    report["state_discrepancies"].append({
                        "company": row.get("company"),
                        "role": row.get("role"),
                        "seen_key": seen_key,
                        "csv_status": csv_status,
                        "seen_status": seen_status,
                    })

    # 3. Broken File References in CSV
    for row in rows:
        cv_path_str = row.get("cv_file", "").strip()
        if cv_path_str:
            cv_p = repo_root / cv_path_str
            if not cv_p.exists():
                report["broken_file_references"].append({
                    "company": row.get("company"),
                    "field": "cv_file",
                    "path": cv_path_str,
                })

        cl_path_str = row.get("cover_letter_file", "").strip()
        if cl_path_str:
            cl_p = repo_root / cl_path_str
            if not cl_p.exists():
                report["broken_file_references"].append({
                    "company": row.get("company"),
                    "field": "cover_letter_file",
                    "path": cl_path_str,
                })

    return report


def reconcile_drift(
    tracker_path: Path = TRACKER_CSV,
    seen_path: Path = SEEN_JOBS_JSON,
    apps_dir: Path = APPLICATIONS_DIR,
    repo_root: Path = ROOT_DIR,
) -> List[str]:
    """Auto-heals minor state drift and returns actions taken."""
    actions: List[str] = []
    headers, rows, raw_lines = load_tracker_csv(tracker_path)
    seen_data = load_seen_jobs(seen_path)
    seen_jobs = seen_data.get("seen", {})

    modified_csv = False
    modified_seen = False

    # 1. Normalize CSV lines and headers
    cleaned_lines = [l for l in raw_lines if l.strip()]
    if len(cleaned_lines) != len(raw_lines):
        raw_lines = cleaned_lines
        modified_csv = True
        actions.append("Removed blank lines from job_search_tracker.csv")

    if headers and "deadline" not in headers:
        headers.append("deadline")
        # Update header line in raw_lines
        raw_lines[0] = ",".join(headers)
        modified_csv = True
        actions.append("Appended 'deadline' column to job_search_tracker.csv header")

    # 2. Sync state in seen_jobs to match CSV
    row_slugs: Dict[str, Dict[str, str]] = {}
    for r in rows:
        row_slugs[derive_row_slug(r)] = r

    for slug, row in row_slugs.items():
        csv_status = row.get("status", "").strip().lower()
        matched = find_matching_seen_job(row, slug, seen_jobs)
        if matched:
            seen_key, seen_entry = matched
            seen_status = (seen_entry.get("status") or "").strip().lower()
            if csv_status and csv_status != seen_status:
                # Update seen_jobs status to match authoritative CSV
                seen_jobs[seen_key]["status"] = csv_status
                modified_seen = True
                actions.append(f"Synced seen_jobs[{seen_key}] status '{seen_status}' -> '{csv_status}'")

    # 3. Reconcile orphan application folders (e.g. bridgenext)
    existing_folders = set()
    if apps_dir.exists():
        existing_folders = {d.name for d in apps_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}

    for folder_name in sorted(existing_folders):
        matched = any(
            s == folder_name or s.replace("-", "") == folder_name.replace("-", "") or folder_name.startswith(s)
            for s in row_slugs
        )
        if not matched:
            folder_path = apps_dir / folder_name
            # Try to read status.md or job_description.md or job_posting.md
            status_file = folder_path / "status.md"
            posting_file = folder_path / "job_description.md"
            if not posting_file.exists():
                posting_file = folder_path / "job_posting.md"

            comp_name = folder_name.split("_")[0].replace("-", " ").title()
            role_name = " ".join(folder_name.split("_")[1:]).replace("-", " ").title()
            source_url = ""
            row_status = "drafted"
            date_str = "2026-09-23"

            if status_file.exists():
                st_text = status_file.read_text(encoding="utf-8")
                m_url = re.search(r"Posting URL:\s*(\S+)", st_text)
                if m_url:
                    source_url = m_url.group(1)
                m_role = re.search(r"Role:\s*(.*)", st_text)
                if m_role:
                    role_name = m_role.group(1).strip()
                m_stat = re.search(r"Status:\s*(\w+)", st_text)
                if m_stat:
                    row_status = m_stat.group(1).strip().lower()

            # Check seen_jobs for additional data
            for sk, sv in seen_jobs.items():
                if folder_name in sk or (source_url and sv.get("url") == source_url):
                    comp_name = sv.get("company", comp_name)
                    role_name = sv.get("title", role_name)
                    source_url = sv.get("url", source_url)
                    date_str = sv.get("first_seen", date_str)
                    break

            # Map status
            if row_status in ["standby"]:
                row_status = "drafted"

            cv_file = f"cv/main_{folder_name}.tex"
            cl_file = f"cover_letters/cover_{folder_name}.tex"
            if not (repo_root / cv_file).exists():
                cv_file = f"documents/applications/{folder_name}/IgnacioFlores_CV.pdf"
            if not (repo_root / cl_file).exists():
                cl_file = f"documents/applications/{folder_name}/IgnacioFlores_CoverLetter.pdf"

            new_row = {
                "date": date_str,
                "company": comp_name,
                "sector": "IT Services",
                "role": role_name,
                "role_type": "Full-time",
                "channel": "portal",
                "status": row_status,
                "contact_person": "",
                "fit_rating": "90",
                "notes": f"Reconciled from {folder_name} archive.",
                "cv_file": cv_file,
                "cover_letter_file": cl_file,
                "source": source_url,
            }
            if "deadline" in headers:
                new_row["deadline"] = ""

            rows.append(new_row)
            modified_csv = True
            actions.append(f"Registered orphan application folder '{folder_name}' into tracker CSV")

    # Write changes if any
    if modified_csv:
        fieldnames = headers or [
            "date", "company", "sector", "role", "role_type", "channel",
            "status", "contact_person", "fit_rating", "notes",
            "cv_file", "cover_letter_file", "source", "deadline"
        ]
        with open(tracker_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    if modified_seen:
        with open(seen_path, "w", encoding="utf-8") as f:
            json.dump(seen_data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return actions


def format_audit_report(report: Dict[str, Any]) -> str:
    """Formats the audit report into a human-readable summary."""
    lines = []
    lines.append("=" * 70)
    lines.append("Job Search State Consistency & Drift Audit")
    lines.append("=" * 70)
    lines.append(f"Tracker applications: {report['tracker_rows_count']}")
    lines.append(f"Seen jobs in scraper: {report['seen_jobs_count']}")
    lines.append("")

    has_drift = False

    if report["orphan_application_folders"]:
        has_drift = True
        lines.append(f"[DRIFT] Orphan Application Folders (in documents/applications/ but missing in CSV) ({len(report['orphan_application_folders'])}):")
        for f in report["orphan_application_folders"]:
            lines.append(f"  - {f}")
        lines.append("")

    if report["missing_application_folders"]:
        has_drift = True
        lines.append(f"[DRIFT] Missing Application Folders (in CSV but no archive folder) ({len(report['missing_application_folders'])}):")
        for m in report["missing_application_folders"]:
            lines.append(f"  - {m['company']} | {m['role']} ({m['status']}) -> expected: {m['slug']}")
        lines.append("")

    if report["state_discrepancies"]:
        has_drift = True
        lines.append(f"[DRIFT] State Discrepancies (CSV vs seen_jobs.json) ({len(report['state_discrepancies'])}):")
        for d in report["state_discrepancies"]:
            lines.append(f"  - {d['company']} ({d['role']}): CSV status='{d['csv_status']}' != seen_jobs['{d['seen_key']}'] status='{d['seen_status']}'")
        lines.append("")

    if report["missing_application_files"]:
        has_drift = True
        lines.append(f"[WARN] Missing Required Application Files ({len(report['missing_application_files'])}):")
        for mf in report["missing_application_files"]:
            lines.append(f"  - {mf['folder']}: missing {', '.join(mf['missing'])}")
        lines.append("")

    if report["broken_file_references"]:
        has_drift = True
        lines.append(f"[DRIFT] Broken File References in CSV ({len(report['broken_file_references'])}):")
        for br in report["broken_file_references"]:
            lines.append(f"  - {br['company']}: field '{br['field']}' points to non-existent path '{br['path']}'")
        lines.append("")

    if report["csv_formatting_issues"]:
        has_drift = True
        lines.append(f"[WARN] CSV Formatting Issues ({len(report['csv_formatting_issues'])}):")
        for ci in report["csv_formatting_issues"]:
            lines.append(f"  - {ci}")
        lines.append("")

    lines.append("-" * 70)
    if not has_drift:
        lines.append("RESULT: [OK] State is fully synchronized and consistent across all stores.")
    else:
        lines.append("RESULT: [FAIL] Drift detected. Run with `--fix` to auto-heal minor discrepancies.")
    lines.append("-" * 70)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit synchronization and drift among tracker, seen jobs, and application archives."
    )
    parser.add_argument(
        "--fix",
        "--reconcile",
        action="store_true",
        dest="fix",
        help="Auto-reconcile minor state drift (sync seen_jobs statuses, fix CSV formatting, register orphans)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as structured JSON",
    )
    parser.add_argument(
        "--tracker",
        type=Path,
        default=TRACKER_CSV,
        help="Path to job_search_tracker.csv",
    )
    parser.add_argument(
        "--seen-jobs",
        type=Path,
        default=SEEN_JOBS_JSON,
        help="Path to seen_jobs.json",
    )
    parser.add_argument(
        "--applications-dir",
        type=Path,
        default=APPLICATIONS_DIR,
        help="Path to documents/applications directory",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.fix:
        actions = reconcile_drift(
            tracker_path=args.tracker,
            seen_path=args.seen_jobs,
            apps_dir=args.applications_dir,
        )
        if actions:
            print("Reconciliation Actions Performed:")
            for a in actions:
                print(f"  [FIXED] {a}")
            print()
        else:
            print("No auto-reconcilable drift detected.")

    report = audit_consistency(
        tracker_path=args.tracker,
        seen_path=args.seen_jobs,
        apps_dir=args.applications_dir,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_audit_report(report))

    has_critical_drift = bool(
        report["orphan_application_folders"]
        or report["missing_application_folders"]
        or report["state_discrepancies"]
        or report["broken_file_references"]
    )

    return 1 if has_drift_detected(report) else 0


def has_drift_detected(report: Dict[str, Any]) -> bool:
    return bool(
        report["orphan_application_folders"]
        or report["missing_application_folders"]
        or report["state_discrepancies"]
        or report["missing_application_files"]
        or report["broken_file_references"]
        or report["csv_formatting_issues"]
    )


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
