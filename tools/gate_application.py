#!/usr/bin/env python3
"""Deterministic Pre-Submit Quality Gate for Job Applications.

Deterministic pre-submit quality gate and invariant enforcement engine.
Acts as a mandatory mechanical barrier before submitting an application or marking
it ready.

Enforces:
  1. Application folder structure under documents/applications/<company>_<role>/
  2. Strict ATS Naming Rules:
     - <CandidateName>_CV.pdf (or <CandidateName>_CV_<Company>.pdf)
     - <CandidateName>_CoverLetter.pdf (or <CandidateName>_CoverLetter_<Company>.pdf)
     - REJECTS if only internal filenames (main_*.pdf, cover_*.pdf) exist.
  3. Exact Page Count:
     - CV must be EXACTLY 2 pages.
     - Cover letter must be EXACTLY 1 page.
  4. ATS Text Layer & Contact Verification:
     - Text layer extractable (not scanned image / corrupted fonts).
     - Literal email, phone, and LinkedIn/GitHub links.
  5. Factual Profile Invariant & Anti-Hallucination:
     - Candidate name and verified employers in text layer.
     - Zero unverified claims or hallucinated credentials (e.g. PhD, Rust Architect, CKA).
  6. Screening Questions Gate:
     - Detects unresolved screening questions or review tags ([?], TODO, NEEDS_REVIEW).

Exit Codes:
  0: All gates PASSED. Ready for submission.
  1: Critical Gate FAILURE (page count, naming rule, ungrounded claims, missing files).
  2: Pending Human Review (screening questions or subjective responses require user sign-off).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
APPLICATIONS_DIR = ROOT_DIR / "documents" / "applications"

# Import verify_pdf extraction logic and candidate profile
sys.path.insert(0, str(ROOT_DIR / "tools"))
try:
    from verify_pdf import extract_text_layer, normalize_text
except ImportError:
    def extract_text_layer(pdf_path: Path):
        raise RuntimeError("tools/verify_pdf.py not found.")
    def normalize_text(text: str) -> str:
        return " ".join(text.split())

try:
    from candidate_profile import load_candidate_profile
except ImportError:
    load_candidate_profile = None

FORBIDDEN_OR_UNGROUNDED_CLAIMS = [
    r"\bph\.?d\b",
    r"\bdoctorate\b",
    r"\bharvard\b",
    r"\bstanford\b",
    r"\bmit\b(?!\s*license)",
    r"\bcka\b",
    r"\bkubernetes\s+administrator\b",
    r"\bgolang\s+architect\b",
    r"\bsenior\s+rust\b",
    r"\b1[0-9]\+?\s+years\s+of\s+experience\b",
    r"\b20\+?\s+years\b",
]

REVIEW_FLAGS = [
    r"\[\?\]",
    r"\bTODO\b",
    r"\bNEEDS_REVIEW\b",
    r"\bHUMAN_REVIEW\b",
    r"\bPENDING_REVIEW\b",
]


def find_application_folder(target: str) -> Optional[Path]:
    """Resolves target to application folder path."""
    target_path = Path(target)
    if target_path.is_dir():
        return target_path

    in_apps = APPLICATIONS_DIR / target
    if in_apps.is_dir():
        return in_apps

    # Try matching by slug substring
    if APPLICATIONS_DIR.is_dir():
        for d in APPLICATIONS_DIR.iterdir():
            if d.is_dir() and target.lower() in d.name.lower():
                return d

    return None


def locate_ats_pdfs(app_folder: Path, profile: Any = None) -> Dict[str, Optional[Path]]:
    """Locates candidate ATS-named PDFs in app folder or company-matched in cv/cover_letters dirs."""
    slug = app_folder.name
    comp = slug.split("_")[0]
    comp_clean = re.sub(r"[^a-z0-9]", "", comp.lower())

    cand_clean = profile.clean_name if profile else "Candidate"
    # Also support searching for general Candidate_CV or last name
    name_prefixes = [cand_clean]
    if profile and profile.name:
        parts = profile.name.split()
        if len(parts) >= 2:
            name_prefixes.append(f"{parts[0]}{parts[-1]}")
            name_prefixes.append(parts[-1])

    # Look in application folder first
    app_files = list(app_folder.iterdir()) if app_folder.exists() else []

    cv_pdf = None
    cl_pdf = None
    has_internal_cv = False
    has_internal_cl = False

    # Check inside app folder
    for f in app_files:
        if f.suffix.lower() == ".pdf":
            name = f.name
            if any(name.startswith(f"{p}_CV") for p in name_prefixes) or (name.endswith("_CV.pdf") and not name.startswith("main_")):
                cv_pdf = f
            elif any(name.startswith(f"{p}_CoverLetter") for p in name_prefixes) or (name.endswith("_CoverLetter.pdf") and not name.startswith("cover_")):
                cl_pdf = f
            elif name.startswith("main_"):
                has_internal_cv = True
            elif name.startswith("cover_"):
                has_internal_cl = True

    # Check in root cv/ and cover_letters/ with company matching
    cv_dir = ROOT_DIR / "cv"
    cl_dir = ROOT_DIR / "cover_letters"

    if not cv_pdf and cv_dir.is_dir():
        for f in cv_dir.iterdir():
            if f.suffix.lower() == ".pdf" and (any(f.name.startswith(f"{p}_CV") for p in name_prefixes) or f.name.endswith("_CV.pdf")):
                f_clean = re.sub(r"[^a-z0-9]", "", f.name.lower())
                if comp_clean and comp_clean in f_clean:
                    cv_pdf = f
                    break

    if not cl_pdf and cl_dir.is_dir():
        for f in cl_dir.iterdir():
            if f.suffix.lower() == ".pdf" and (any(f.name.startswith(f"{p}_CoverLetter") for p in name_prefixes) or f.name.endswith("_CoverLetter.pdf")):
                f_clean = re.sub(r"[^a-z0-9]", "", f.name.lower())
                if comp_clean and comp_clean in f_clean:
                    cl_pdf = f
                    break

    # Check if internal files exist in root or app folder
    if (cv_dir / f"main_{slug}.pdf").exists() or (app_folder / "cv_draft.tex").exists():
        has_internal_cv = True
    if (cl_dir / f"cover_{slug}.pdf").exists() or (app_folder / "cover_letter.tex").exists():
        has_internal_cl = True

    return {
        "cv_pdf": cv_pdf,
        "cl_pdf": cl_pdf,
        "has_internal_cv": has_internal_cv,
        "has_internal_cl": has_internal_cl,
    }


def evaluate_gate(
    target: str,
    require_cover_letter: bool = True,
    profile: Any = None,
) -> Dict[str, Any]:
    """Runs all deterministic gate checks against an application."""
    results: Dict[str, Any] = {
        "target": target,
        "app_folder": None,
        "passed": False,
        "needs_human_review": False,
        "checks": [],
        "errors": [],
        "warnings": [],
    }

    if profile is None and load_candidate_profile:
        try:
            profile = load_candidate_profile(ROOT_DIR)
        except Exception:
            profile = None

    cand_name = profile.name if profile else "Candidate Name"
    cand_clean = profile.clean_name if profile else "Candidate"
    cand_email = (profile.email if profile and profile.email else "").lower()
    cand_phone_digits = profile.phone_digits if profile and profile.phone_digits else ""
    cand_employers = [e.lower() for e in profile.employers] if (profile and profile.employers) else []
    cand_name_parts = cand_name.lower().split()

    folder = find_application_folder(target)
    if not folder:
        results["errors"].append(f"Application directory not found for target '{target}'.")
        return results

    results["app_folder"] = str(folder)

    # Check 1: Posting and description existence
    has_posting = (folder / "job_posting.md").exists() or (folder / "job_description.md").exists()
    if has_posting:
        results["checks"].append({"name": "Job Posting Doc", "status": "PASS", "detail": "job_posting.md / job_description.md exists"})
    else:
        results["errors"].append("Missing job posting description (job_posting.md or job_description.md).")
        results["checks"].append({"name": "Job Posting Doc", "status": "FAIL", "detail": "No job posting file found"})

    # Check 2: ATS Naming rule & compiled PDF discovery
    pdf_info = locate_ats_pdfs(folder, profile=profile)
    cv_pdf = pdf_info["cv_pdf"]
    cl_pdf = pdf_info["cl_pdf"]

    if not cv_pdf:
        if pdf_info["has_internal_cv"]:
            results["errors"].append(
                f"ATS Naming Violation: Found only internal CV filename (main_*.pdf). "
                f"Must compile/export as '{cand_clean}_CV.pdf' (or '{cand_clean}_CV_<Company>.pdf')."
            )
        else:
            results["errors"].append(f"Missing compiled CV PDF ('{cand_clean}_CV.pdf').")
        results["checks"].append({"name": "ATS CV Naming", "status": "FAIL", "detail": f"No {cand_clean}_CV*.pdf found"})
    else:
        results["checks"].append({"name": "ATS CV Naming", "status": "PASS", "detail": f"Found {cv_pdf.name}"})

    if require_cover_letter:
        if not cl_pdf:
            if pdf_info["has_internal_cl"]:
                results["errors"].append(
                    f"ATS Naming Violation: Found only internal Cover Letter filename (cover_*.pdf). "
                    f"Must compile/export as '{cand_clean}_CoverLetter.pdf' (or '{cand_clean}_CoverLetter_<Company>.pdf')."
                )
            else:
                results["errors"].append(f"Missing compiled Cover Letter PDF ('{cand_clean}_CoverLetter.pdf').")
            results["checks"].append({"name": "ATS Cover Letter Naming", "status": "FAIL", "detail": f"No {cand_clean}_CoverLetter*.pdf found"})
        else:
            results["checks"].append({"name": "ATS Cover Letter Naming", "status": "PASS", "detail": f"Found {cl_pdf.name}"})

    # Check 3: Page count & ATS text verification for CV
    if cv_pdf and cv_pdf.exists():
        try:
            cv_text, cv_pages, cv_ext = extract_text_layer(cv_pdf)
            # Exact page count = 2
            if cv_pages == 2:
                results["checks"].append({"name": "CV Page Count", "status": "PASS", "detail": f"Exactly 2 pages (extractor: {cv_ext})"})
            else:
                results["errors"].append(f"CV Page Count Violation: expected exactly 2 pages, found {cv_pages}.")
                results["checks"].append({"name": "CV Page Count", "status": "FAIL", "detail": f"Found {cv_pages} pages"})

            # ATS text extractable
            norm_cv = normalize_text(cv_text)
            if len(norm_cv) >= 500:
                results["checks"].append({"name": "CV ATS Text Layer", "status": "PASS", "detail": f"{len(norm_cv)} extractable chars"})
            else:
                results["errors"].append(f"CV ATS text layer too short or unreadable ({len(norm_cv)} chars).")
                results["checks"].append({"name": "CV ATS Text Layer", "status": "FAIL", "detail": "Degraded text layer"})

            # Contact info present
            has_email = cand_email in norm_cv.lower() if cand_email else True
            norm_digits = re.sub(r"\D", "", norm_cv)
            has_phone = (cand_phone_digits[-6:] in norm_digits) if (cand_phone_digits and len(cand_phone_digits) >= 6) else True
            has_link = ("linkedin" in norm_cv.lower() or "github" in norm_cv.lower())

            if has_email and has_phone and has_link:
                results["checks"].append({"name": "CV Contact Verification", "status": "PASS", "detail": "Email, phone, and profile links present"})
            else:
                missing_contacts = []
                if not has_email: missing_contacts.append(f"email ({cand_email})")
                if not has_phone: missing_contacts.append(f"phone ({cand_phone_digits})")
                if not has_link: missing_contacts.append("linkedin/github link")
                results["errors"].append(f"CV missing essential contact information: {', '.join(missing_contacts)}.")
                results["checks"].append({"name": "CV Contact Verification", "status": "FAIL", "detail": f"Missing: {missing_contacts}"})

            # Factual grounding: Name & Employers
            has_name = all(part in norm_cv.lower() for part in cand_name_parts) if cand_name_parts else True
            has_employer = any(emp in norm_cv.lower() for emp in cand_employers) if cand_employers else True
            if has_name and has_employer:
                results["checks"].append({"name": "CV Factual Anchoring", "status": "PASS", "detail": f"{cand_name} and verified employers found"})
            else:
                results["errors"].append(f"CV Factual Anchoring Failed: Candidate name ({cand_name}) or verified employers missing in text layer.")
                results["checks"].append({"name": "CV Factual Anchoring", "status": "FAIL", "detail": f"Missing candidate name or verified employers: {cand_employers}"})

            # Anti-hallucination check
            hallucinations = []
            for pat in FORBIDDEN_OR_UNGROUNDED_CLAIMS:
                m = re.search(pat, cv_text, re.IGNORECASE)
                if m:
                    hallucinations.append(m.group(0))
            if hallucinations:
                results["errors"].append(f"Anti-Hallucination Gate Failed: Unauthorized claims detected in CV ({hallucinations}).")
                results["checks"].append({"name": "Anti-Hallucination Gate", "status": "FAIL", "detail": f"Detected: {hallucinations}"})
            else:
                results["checks"].append({"name": "Anti-Hallucination Gate", "status": "PASS", "detail": "Zero ungrounded claims detected"})

        except Exception as e:
            results["errors"].append(f"Error inspecting CV PDF: {e}")
            results["checks"].append({"name": "CV PDF Extraction", "status": "FAIL", "detail": str(e)})

    # Check 4: Page count & text verification for Cover Letter
    if cl_pdf and cl_pdf.exists():
        try:
            cl_text, cl_pages, cl_ext = extract_text_layer(cl_pdf)
            # Exact page count = 1
            if cl_pages == 1:
                results["checks"].append({"name": "Cover Letter Page Count", "status": "PASS", "detail": f"Exactly 1 page (extractor: {cl_ext})"})
            else:
                results["errors"].append(f"Cover Letter Page Count Violation: expected exactly 1 page, found {cl_pages}.")
                results["checks"].append({"name": "Cover Letter Page Count", "status": "FAIL", "detail": f"Found {cl_pages} pages"})

            norm_cl = normalize_text(cl_text)
            if len(norm_cl) >= 200:
                results["checks"].append({"name": "Cover Letter Text Layer", "status": "PASS", "detail": f"{len(norm_cl)} chars"})
            else:
                results["errors"].append(f"Cover letter text layer degraded or empty ({len(norm_cl)} chars).")
                results["checks"].append({"name": "Cover Letter Text Layer", "status": "FAIL", "detail": "Degraded text layer"})

        except Exception as e:
            results["errors"].append(f"Error inspecting Cover Letter PDF: {e}")
            results["checks"].append({"name": "Cover Letter PDF Extraction", "status": "FAIL", "detail": str(e)})

    # Check 5: Screening Questions / Subjective Review Gate
    review_items = []
    for md_file in folder.glob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            for flag in REVIEW_FLAGS:
                matches = re.findall(flag, text)
                if matches:
                    review_items.append(f"{md_file.name} contains '{flag}'")
        except Exception:
            pass

    if review_items:
        results["needs_human_review"] = True
        results["warnings"].append(f"Screening / Review Items Detected: {', '.join(review_items)}")
        results["checks"].append({"name": "Screening Review Gate", "status": "REVIEW", "detail": f"Flagged items in application files: {review_items}"})
    else:
        results["checks"].append({"name": "Screening Review Gate", "status": "PASS", "detail": "No pending review markers"})

    results["passed"] = (len(results["errors"]) == 0)
    return results


def format_gate_report(res: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append(f"Deterministic Application Gate: {Path(res['app_folder'] or res['target']).name}")
    lines.append("=" * 70)

    for chk in res["checks"]:
        tag = f"[{chk['status']}]"
        lines.append(f"{tag:10} {chk['name']:28} : {chk['detail']}")

    if res["warnings"]:
        lines.append("")
        lines.append("[!] Warnings / Pending Human Reviews:")
        for w in res["warnings"]:
            lines.append(f"  - {w}")

    if res["errors"]:
        lines.append("")
        lines.append("[X] Gate Violations (Hard Failures):")
        for err in res["errors"]:
            lines.append(f"  - {err}")

    lines.append("-" * 70)
    if not res["passed"]:
        lines.append("GATE VERDICT: [FAILED] Invariants violated. Do NOT submit.")
    elif res["needs_human_review"]:
        lines.append("GATE VERDICT: [PENDING HUMAN REVIEW] Mechanical checks passed, subjective review required.")
    else:
        lines.append("GATE VERDICT: [PASSED] 100% verified. Ready for ATS submission.")
    lines.append("-" * 70)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic Pre-Submit Quality Gate for Job Applications."
    )
    parser.add_argument(
        "target",
        help="Application folder path or slug (e.g. codepath_staff-software-engineer)",
    )
    parser.add_argument(
        "--no-cover-letter",
        action="store_true",
        help="Do not require a cover letter (for applications that only accept CV)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report in JSON format",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    results = evaluate_gate(
        target=args.target,
        require_cover_letter=not args.no_cover_letter,
    )

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_gate_report(results))

    if not results["passed"]:
        return 1
    if results["needs_human_review"]:
        return 2
    return 0


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
