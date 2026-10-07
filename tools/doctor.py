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
  5. Browser automation (local Playwright library; Playwright MCP package resolvable)
  6. GitHub CLI (auth, default repo = origin, issues enabled on origin)
  7. Antigravity (.agents/mcp_config.json in sync, rules frontmatter, generated skills)
  8. Framework integrity (immutability tool if present, git hooks path)
  9. Workspace state files (seen_jobs.json, job_search_tracker.csv, profile files)

New checks 5-8 are WARN-level: they never fail the run, and network timeouts
degrade to WARN.

Exit Codes:
  0: All critical requirements satisfied (warnings allowed).
  1: Critical tool or environment dependency missing.
"""

import argparse
import csv
import json
import os
import re
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


def _run(cmd: List[str], timeout: float = 10, cwd: Optional[Path] = None) -> Optional[subprocess.CompletedProcess]:
    """Run a command without a shell; None when it is missing or times out.

    Single choke point for the network/git-backed checks so they degrade to WARN
    (never FAIL, never hang) offline, and so tests can mock one function.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd or ROOT_DIR),
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _warn(name: str, detail: str) -> Dict[str, Any]:
    return {"name": name, "status": "WARN", "detail": detail, "critical": False}


def _ok(name: str, detail: str) -> Dict[str, Any]:
    return {"name": name, "status": "OK", "detail": detail, "critical": False}


def _skip(name: str, detail: str) -> Dict[str, Any]:
    """Check not applicable here (optional tool/dir absent) - reported, never counted as OK."""
    return {"name": name, "status": "SKIP", "detail": f"Skipped: {detail}", "critical": False}


def check_browser_automation() -> Dict[str, Any]:
    """Local Playwright library (python module or CLI). Not the MCP server."""
    name = "Playwright Library (local)"
    try:
        import playwright  # noqa: F401
        return _ok(name, "Python playwright module installed")
    except ImportError:
        pass
    cli_playwright, cli_detail = check_command("playwright", "--version")
    if cli_playwright:
        return _ok(name, f"Playwright CLI: {cli_detail}")
    return _warn(name, "Not installed locally (optional; the Playwright MCP server is checked separately)")


PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp"


def _npx_cache_has(package: str) -> bool:
    cache = Path.home() / ".npm" / "_npx"
    if not cache.is_dir():
        return False
    parts = package.split("/")
    try:
        return any((d / "node_modules").joinpath(*parts).is_dir() for d in cache.iterdir() if d.is_dir())
    except OSError:
        return False


def check_playwright_mcp() -> Dict[str, Any]:
    """OK only when the MCP package actually resolves - never from mere `npx` presence."""
    name = f"Playwright MCP ({PLAYWRIGHT_MCP_PACKAGE})"
    if not shutil.which("npx"):
        return _warn(name, "npx not found on PATH; the MCP server cannot be launched")
    if _npx_cache_has(PLAYWRIGHT_MCP_PACKAGE):
        return _ok(name, "Package present in the npx cache (~/.npm/_npx)")
    res = _run([shutil.which("npm") or "npm", "view", PLAYWRIGHT_MCP_PACKAGE, "version"], timeout=10)
    if res is None:
        return _warn(name, "Could not resolve package (npm missing or registry timed out)")
    if res.returncode != 0:
        last = (res.stderr or res.stdout or "").strip().splitlines()[-1:] or ["unknown error"]
        return _warn(name, f"npm view failed: {last[0]}")
    return _ok(name, f"Resolvable on npm registry (latest {res.stdout.strip()})")


def _github_slug(url: str) -> Optional[str]:
    """owner/repo from an https or ssh GitHub remote URL."""
    m = re.match(
        r"^(?:https?://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?$",
        url.strip(),
    )
    return f"{m.group(1)}/{m.group(2)}" if m else None


def check_github_cli() -> List[Dict[str, Any]]:
    """gh installed + authenticated, default repo = origin, issues enabled on origin."""
    if not shutil.which("gh"):
        return [_warn("GitHub CLI (gh)", "Not found on PATH; issue reporting is unavailable")]

    results: List[Dict[str, Any]] = []
    auth = _run(["gh", "auth", "status"], timeout=10)
    if auth is None:
        results.append(_warn("GitHub CLI auth", "gh auth status timed out"))
    elif auth.returncode != 0:
        results.append(_warn("GitHub CLI auth", "Not authenticated - run: gh auth login"))
    else:
        results.append(_ok("GitHub CLI auth", "Authenticated"))

    remote = _run(["git", "remote", "get-url", "origin"], timeout=5)
    origin = _github_slug(remote.stdout) if remote is not None and remote.returncode == 0 else None
    if not origin:
        results.append(_warn("GitHub repo: origin", "No GitHub 'origin' remote found"))
        return results

    default = _run(["gh", "repo", "set-default", "--view"], timeout=10)
    current = (default.stdout or "").strip() if default is not None and default.returncode == 0 else ""
    if current.lower() == origin.lower():
        results.append(_ok("GitHub default repo", f"{current} (= origin)"))
    else:
        results.append(_warn(
            "GitHub default repo",
            f"{current or 'unset'} != origin {origin}; issues would go to upstream"
            f" - fix: gh repo set-default {origin}",
        ))

    issues = _run(["gh", "api", f"repos/{origin}", "--jq", ".has_issues"], timeout=10)
    if issues is None or issues.returncode != 0:
        results.append(_warn("GitHub issues on origin", f"Could not query repos/{origin} (offline or unauthenticated)"))
    elif issues.stdout.strip() == "true":
        results.append(_ok("GitHub issues on origin", f"Enabled on {origin}"))
    else:
        results.append(_warn(
            "GitHub issues on origin",
            f"Disabled on {origin} - fix: gh repo edit {origin} --enable-issues",
        ))
    return results


RULE_TRIGGERS = {"always_on", "model_decision", "glob", "manual"}


def _rule_trigger(text: str) -> Optional[str]:
    """Value of `trigger:` in a leading YAML frontmatter block, else None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"""^trigger:\s*['"]?([A-Za-z_]+)['"]?\s*$""", line.strip())
        if m:
            return m.group(1)
    return None


def _run_check_tool(script: Path, name: str, args: List[str]) -> Dict[str, Any]:
    """Run an optional repo tool built by another workstream; skip if absent, WARN on drift."""
    rel = script.relative_to(ROOT_DIR).as_posix()
    if not script.exists():
        return _skip(name, f"{rel} not present")
    res = _run([sys.executable, str(script), *args], timeout=60)
    if res is None:
        return _warn(name, f"{rel} timed out")
    if res.returncode != 0:
        tail = (res.stdout or res.stderr or "").strip().splitlines()[-1:] or ["drift detected"]
        return _warn(name, f"{rel} reported drift: {tail[0]}")
    return _ok(name, f"{rel} clean")


def check_antigravity() -> List[Dict[str, Any]]:
    """Antigravity workspace config: MCP sync, rules frontmatter, generated skills."""
    results: List[Dict[str, Any]] = []

    try:
        from sync_mcp_config import check_sync  # tools/ is on sys.path when run as a script
    except ImportError:
        from tools.sync_mcp_config import check_sync
    ok, msg = check_sync(ROOT_DIR / ".mcp.json", ROOT_DIR / ".agents" / "mcp_config.json")
    results.append(_ok("Antigravity MCP config", msg) if ok else _warn("Antigravity MCP config", msg))

    rules_dir = ROOT_DIR / ".agents" / "rules"
    rule_files = sorted(rules_dir.glob("*.md")) if rules_dir.is_dir() else []
    if not rule_files:
        results.append(_skip("Antigravity rules frontmatter", "no .agents/rules/*.md"))
    else:
        bad = []
        for f in rule_files:
            trig = _rule_trigger(f.read_text(encoding="utf-8", errors="replace"))
            if trig not in RULE_TRIGGERS:
                bad.append(f"{f.name} (trigger={trig})")
        if bad:
            results.append(_warn(
                "Antigravity rules frontmatter",
                f"Invalid/missing trigger in: {', '.join(bad)} (expected one of {sorted(RULE_TRIGGERS)})",
            ))
        else:
            results.append(_ok("Antigravity rules frontmatter", f"{len(rule_files)} rule file(s) valid"))

    results.append(_run_check_tool(
        ROOT_DIR / "tools" / "sync_agent_skills.py", "Antigravity generated skills", ["--check"]
    ))
    return results


def check_framework_integrity() -> List[Dict[str, Any]]:
    """Framework immutability tool (if present) and git hooks path."""
    results = [_run_check_tool(ROOT_DIR / "tools" / "check_framework_immutable.py", "Framework immutability", [])]

    if not (ROOT_DIR / ".githooks").is_dir():
        results.append(_skip("Git hooks (core.hooksPath)", "no .githooks/ directory"))
        return results
    res = _run(["git", "config", "core.hooksPath"], timeout=5)
    current = (res.stdout or "").strip() if res is not None else ""
    if current.rstrip("/") == ".githooks":
        results.append(_ok("Git hooks (core.hooksPath)", "core.hooksPath = .githooks"))
    else:
        results.append(_warn(
            "Git hooks (core.hooksPath)",
            f"core.hooksPath = {current or 'unset'} - fix: git config core.hooksPath .githooks",
        ))
    return results


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

    # 4b. Personal overlay: stale .personal copies (template has a newer framework_version)
    try:
        from personal_overlay import status as overlay_status  # tools/ on sys.path as a script
    except ImportError:
        from tools.personal_overlay import status as overlay_status
    rows = overlay_status(ROOT_DIR)
    personal = [r for r in rows if r["has_personal"]]
    stale = [str(r["reads"]) for r in rows if r["stale"]]
    results.append({
        "name": "Personal overlay (*.personal)",
        "status": "WARN" if stale else "OK",
        "detail": (
            f"stale copies (template is newer, merge framework changes): {', '.join(stale)}"
            if stale else f"{len(personal)} personal file(s) in use"
        ),
        "critical": False,
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
    checks.append(check_playwright_mcp())
    checks.extend(check_github_cli())
    checks.extend(check_antigravity())
    checks.extend(check_framework_integrity())
    checks.extend(check_workspace_files())

    counts = {"OK": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
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
    summary = res["summary"]
    sum_str = (
        f"Summary: {summary.get('OK', 0)} passed, {summary.get('WARN', 0)} warnings, "
        f"{summary.get('FAIL', 0)} failures, {summary.get('SKIP', 0)} skipped."
    )
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
