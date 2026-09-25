#!/usr/bin/env python3
"""Environment and Toolchain Diagnostic.

Deterministic environment audits and toolchain health verification.
Verifies the complete toolchain required for scraping, ATS compiling,
PDF geometric verification, and state tracking.

Checks:
  1. Python runtime (>= 3.10) and package manager (uv)
  2. LaTeX toolchain (lualatex, xelatex, pdflatex) / typst
  3. Poppler utilities (pdftotext, pdfinfo)
  4. JavaScript runtimes (bun, node) for skill portal CLIs
  5. Browser automation (Playwright / Chromium headless)
  6. Workspace state files (seen_jobs.json, job_search_tracker.csv, profile files)

Exit Codes:
  0: All critical requirements satisfied (warnings allowed).
  1: Critical tool or environment dependency missing.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent


def check_command(cmd: str, version_arg: str = "--version") -> Tuple[bool, str]:
    """Checks if command is available on PATH and captures version string."""
    binary = shutil.which(cmd)
    if not binary:
        return False, "Not found on PATH"
    try:
        res = subprocess.run(
            [cmd, version_arg],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        output = (res.stdout or res.stderr or "").strip().splitlines()
        v_str = output[0] if output else "Available"
        return True, f"{binary} ({v_str})"
    except Exception as e:
        return True, f"{binary} (found, error getting version: {e})"


def check_python() -> Dict[str, Any]:
    v = sys.version_info
    v_str = f"{v.major}.{v.minor}.{v.micro}"
    passed = v.major == 3 and v.minor >= 10
    return {
        "name": "Python 3 (>= 3.10)",
        "status": "OK" if passed else "FAIL",
        "detail": f"{sys.executable} (Python {v_str})",
        "critical": True,
    }


def check_uv() -> Dict[str, Any]:
    ok, detail = check_command("uv")
    return {
        "name": "uv Package Manager",
        "status": "OK" if ok else "FAIL",
        "detail": detail,
        "critical": True,
    }


def check_latex_compilers() -> List[Dict[str, Any]]:
    results = []
    # lualatex (required for moderncv)
    lua_ok, lua_detail = check_command("lualatex", "-v")
    results.append({
        "name": "LuaLaTeX (moderncv)",
        "status": "OK" if lua_ok else "FAIL",
        "detail": lua_detail,
        "critical": True,
    })

    # xelatex (required for cover.cls)
    xe_ok, xe_detail = check_command("xelatex", "-v")
    results.append({
        "name": "XeLaTeX (cover.cls)",
        "status": "OK" if xe_ok else "FAIL",
        "detail": xe_detail,
        "critical": True,
    })

    # typst (optional alternative compiler)
    typst_ok, typst_detail = check_command("typst")
    results.append({
        "name": "Typst (optional alternative)",
        "status": "OK" if typst_ok else "WARN",
        "detail": typst_detail if typst_ok else "Optional: modern typst compiler not found",
        "critical": False,
    })

    return results


def check_poppler() -> List[Dict[str, Any]]:
    results = []
    txt_ok, txt_detail = check_command("pdftotext", "-v")
    results.append({
        "name": "Poppler pdftotext (ATS Text Layer)",
        "status": "OK" if txt_ok else "FAIL",
        "detail": txt_detail,
        "critical": True,
    })

    info_ok, info_detail = check_command("pdfinfo", "-v")
    results.append({
        "name": "Poppler pdfinfo (Page Geometry)",
        "status": "OK" if info_ok else "FAIL",
        "detail": info_detail,
        "critical": True,
    })

    return results


def check_js_runtime() -> Dict[str, Any]:
    bun_ok, bun_detail = check_command("bun", "--version")
    node_ok, node_detail = check_command("node", "--version")

    if bun_ok:
        return {
            "name": "JavaScript Runtime (bun / node)",
            "status": "OK",
            "detail": f"bun: {bun_detail}",
            "critical": True,
        }
    elif node_ok:
        return {
            "name": "JavaScript Runtime (bun / node)",
            "status": "OK",
            "detail": f"node: {node_detail}",
            "critical": True,
        }
    else:
        return {
            "name": "JavaScript Runtime (bun / node)",
            "status": "FAIL",
            "detail": "Neither bun nor node found on PATH. Required for .agents/skills/ portal CLIs.",
            "critical": True,
        }


def check_browser_automation() -> Dict[str, Any]:
    # Check if python playwright or playwright CLI is available, or MCP playwright
    py_playwright = False
    try:
        import playwright
        py_playwright = True
    except ImportError:
        pass

    cli_playwright, cli_detail = check_command("playwright", "--version")
    npx_ok, _ = check_command("npx", "--version")

    if py_playwright:
        return {
            "name": "Playwright Browser Automation",
            "status": "OK",
            "detail": "Python playwright module installed",
            "critical": False,
        }
    elif cli_playwright:
        return {
            "name": "Playwright Browser Automation",
            "status": "OK",
            "detail": f"Playwright CLI: {cli_detail}",
            "critical": False,
        }
    elif npx_ok:
        return {
            "name": "Playwright Browser Automation",
            "status": "OK",
            "detail": "Available via npx playwright / MCP Playwright Server",
            "critical": False,
        }
    else:
        return {
            "name": "Playwright Browser Automation",
            "status": "WARN",
            "detail": "Playwright not found locally; MCP Playwright Server can still be used.",
            "critical": False,
        }


def check_workspace_files() -> List[Dict[str, Any]]:
    results = []

    # 1. seen_jobs.json
    seen_path = ROOT_DIR / "job_scraper" / "seen_jobs.json"
    if seen_path.exists():
        try:
            with open(seen_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                seen_count = len(data.get("seen", {}))
                results.append({
                    "name": "State: job_scraper/seen_jobs.json",
                    "status": "OK",
                    "detail": f"Valid JSON with {seen_count} tracked vacancies",
                    "critical": True,
                })
        except Exception as e:
            results.append({
                "name": "State: job_scraper/seen_jobs.json",
                "status": "FAIL",
                "detail": f"Corrupt JSON: {e}",
                "critical": True,
            })
    else:
        results.append({
            "name": "State: job_scraper/seen_jobs.json",
            "status": "FAIL",
            "detail": "File missing",
            "critical": True,
        })

    # 2. job_search_tracker.csv
    tracker_path = ROOT_DIR / "job_search_tracker.csv"
    if tracker_path.exists():
        try:
            with open(tracker_path, "r", encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
                reader = csv.DictReader(lines)
                rows = list(reader)
                results.append({
                    "name": "State: job_search_tracker.csv",
                    "status": "OK",
                    "detail": f"Valid CSV with {len(rows)} tracked applications",
                    "critical": True,
                })
        except Exception as e:
            results.append({
                "name": "State: job_search_tracker.csv",
                "status": "FAIL",
                "detail": f"Corrupt CSV: {e}",
                "critical": True,
            })
    else:
        results.append({
            "name": "State: job_search_tracker.csv",
            "status": "FAIL",
            "detail": "File missing",
            "critical": True,
        })

    # 3. Canonical Profile: CLAUDE.md
    claude_md = ROOT_DIR / "CLAUDE.md"
    results.append({
        "name": "Profile: CLAUDE.md",
        "status": "OK" if claude_md.exists() else "FAIL",
        "detail": f"{claude_md.stat().st_size} bytes" if claude_md.exists() else "Missing",
        "critical": True,
    })

    # 4. Candidate Profile Skill
    skill_profile = ROOT_DIR / ".claude" / "skills" / "job-application-assistant" / "01-candidate-profile.md"
    results.append({
        "name": "Profile: 01-candidate-profile.md",
        "status": "OK" if skill_profile.exists() else "FAIL",
        "detail": f"{skill_profile.stat().st_size} bytes" if skill_profile.exists() else "Missing",
        "critical": True,
    })

    # 5. Applications directory writable
    apps_dir = ROOT_DIR / "documents" / "applications"
    if apps_dir.exists() and os.access(apps_dir, os.W_OK):
        app_count = len([d for d in apps_dir.iterdir() if d.is_dir()])
        results.append({
            "name": "Directory: documents/applications/",
            "status": "OK",
            "detail": f"Writable directory containing {app_count} application archives",
            "critical": True,
        })
    else:
        results.append({
            "name": "Directory: documents/applications/",
            "status": "FAIL",
            "detail": "Directory does not exist or is not writable",
            "critical": True,
        })

    # 6. Memory ledger
    mem_dir = ROOT_DIR / "documents" / "memory"
    mem_file = mem_dir / "insights.jsonl"
    mem_status = "OK" if (mem_file.exists() or mem_dir.exists()) else "WARN"
    detail_mem = f"insights.jsonl present ({mem_file.stat().st_size} bytes)" if mem_file.exists() else "Will be initialized on first insight"
    results.append({
        "name": "Memory Ledger: documents/memory/insights.jsonl",
        "status": mem_status,
        "detail": detail_mem,
        "critical": False,
    })

    return results


def run_doctor() -> Dict[str, Any]:
    checks = []
    checks.append(check_python())
    checks.append(check_uv())
    checks.extend(check_latex_compilers())
    checks.extend(check_poppler())
    checks.append(check_js_runtime())
    checks.append(check_browser_automation())
    checks.extend(check_workspace_files())

    counts = {"OK": 0, "WARN": 0, "FAIL": 0}
    has_critical_failure = False

    for c in checks:
        st = c["status"]
        counts[st] = counts.get(st, 0) + 1
        if st == "FAIL" and c.get("critical", True):
            has_critical_failure = True

    return {
        "checks": checks,
        "summary": counts,
        "healthy": not has_critical_failure,
    }


def format_doctor_report(res: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("AI Job Search Toolchain & Environment Diagnostic (Doctor)")
    lines.append("=" * 70)

    for chk in res["checks"]:
        tag = f"[{chk['status']}]"
        lines.append(f"{tag:8} {chk['name']:40} : {chk['detail']}")

    lines.append("-" * 70)
    sum_str = f"Summary: {res['summary']['OK']} passed, {res['summary']['WARN']} warnings, {res['summary']['FAIL']} failures."
    lines.append(sum_str)

    if res["healthy"]:
        lines.append("HEALTH VERDICT: [OK] Toolchain and environment ready for operations.")
    else:
        lines.append("HEALTH VERDICT: [FAIL] Critical dependencies missing. Address failures before proceeding.")
    lines.append("-" * 70)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Environment and Toolchain Diagnostic for AI Job Search."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostic results as structured JSON",
    )
    return parser


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    res = run_doctor()

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(format_doctor_report(res))

    return 0 if res["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
