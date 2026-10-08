#!/usr/bin/env python3
"""Backstop for operator mode: list framework files changed in the MAIN checkout.

    python3 tools/check_framework_immutable.py            # print drift, exit 1 if any
    python3 tools/check_framework_immutable.py --report   # ...and file a 'drift' issue (paths only)
    python3 tools/check_framework_immutable.py --hook     # Antigravity Stop hook: report on stderr,
                                                          # print {} and always exit 0

Edit-time hooks (.claude/hooks/guard_framework.py) do not see shell writes, and Antigravity's
hooks are best-effort, so operator commands (/scrape, /rank, /apply) run this as their final
step. Drift = `git status` entries on framework paths (tracked files, or new non-ignored files
under tools/, .claude/, .agents/, tests/, .github/, .githooks/, templates/, AGENTS.md, CLAUDE.md)
that tools/personalization_paths.json does not exempt via 'drift_exempt' (profile/config docs, enabled:
toggles, brand-new portal/template dirs). Changes to existing portal/template code are drift.

PII scan (tools/pii_scan.py): every new/modified file under a framework dir (drift or not,
main checkout or worktree) is scanned for candidate identity terms from the gitignored profile;
hits print a loud WARNING with counts and paths only. It does not change the exit code;
.githooks/pre-commit is what blocks such a commit.

Exit 0: clean, or running in a linked worktree (framework work belongs there).
Exit 1: drift found. Exit 2: not a git repository / git failed.
The issue body carries only repo-relative paths and status codes - never file contents.
Stdlib only.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import framework_paths as fp  # noqa: E402


def porcelain_entries(info: fp.RepoInfo) -> list[tuple[str, str]]:
    """[(XY status, path)] from `git status --porcelain=v1 -z -uall` (rename -> new path)."""
    r = fp._git(["status", "--porcelain=v1", "-z", "-uall"], info.toplevel)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git status failed")
    items = r.stdout.split("\0")
    out, i = [], 0
    while i < len(items):
        rec = items[i]
        i += 1
        if len(rec) < 4:
            continue
        xy, path = rec[:2], rec[3:]
        if "R" in xy or "C" in xy:
            i += 1  # the original path follows as its own NUL-terminated field
        out.append((xy, path))
    return out


def find_drift(info: fp.RepoInfo) -> list[tuple[str, str]]:
    entries = fp.load_personalization(info.toplevel)
    drift = []
    for xy, rel in porcelain_entries(info):
        untracked = xy == "??"
        # Tracked (or staged) entries are framework by definition; ignored files never show up.
        if untracked and not fp.in_framework_dir(rel):
            continue
        # User config written by /setup-style commands (profile docs, enabled: toggles, a
        # brand-new portal/template dir) is not drift in any mode; edits to existing portal or
        # template code are, even though the edit hook allows them in config mode.
        if fp.drift_exempt(info, entries, rel, untracked):
            continue
        drift.append((xy, rel))
    return drift


def report(drift: list[tuple[str, str]], root: Path) -> int:
    tool = root / "tools" / "report_issue.py"
    if not tool.exists():
        print("report_issue.py not available; drift not filed (fix it by hand).", file=sys.stderr)
        return 1
    body = (
        "Operator mode left framework files modified in the main checkout.\n\n"
        + "\n".join(f"- `{xy.strip() or 'M'}` {rel}" for xy, rel in drift)
        + "\n\nSuggested fix: move any wanted change into a linked worktree and commit it there, "
        "then `git restore <path>` (or delete the new file) in the main checkout."
    )
    cmd = [sys.executable, str(tool), "--kind", "drift", "--title",
           f"Framework drift in main checkout ({len(drift)} path(s))", "--body", body,
           "--component", "operator-mode"]
    try:
        r = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"report_issue.py failed to run: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode


def changed_framework_files(info: fp.RepoInfo) -> list[str]:
    """Existing new/modified files under framework paths (tracked or not), for the PII scan."""
    out = []
    for xy, rel in porcelain_entries(info):
        if "D" in xy:
            continue
        if xy == "??" and not fp.in_framework_dir(rel):
            continue
        out.append(rel)
    return out


def pii_warning(info: fp.RepoInfo) -> int:
    """Print a loud warning for identity terms in changed framework files. Returns the number
    of files with identity (block-tier) hits. Never raises."""
    try:
        import pii_scan

        scanner = pii_scan.PiiScanner.from_repo(info.toplevel)
        if scanner.empty:
            return 0
        hits = scanner.scan_files(info.toplevel, changed_framework_files(info))
    except Exception as exc:  # the drift check must not fail on the PII pass
        print(f"check_framework_immutable: PII scan skipped ({exc!r})", file=sys.stderr)
        return 0
    loud = [h for h in hits if h[1]]
    if loud:
        print("!" * 72)
        print(f"WARNING: candidate PII (name/contact/handle) in {len(loud)} changed framework file(s).")
        print("Values are not shown. Remove them before any commit; personal data belongs in the")
        print("gitignored candidate_profile.json / *.personal overlays, never in framework files.")
        print("\n".join(pii_scan.format_hits(loud)))
        print("!" * 72)
    soft = [h for h in hits if not h[1]]
    if soft:
        print(f"note: {len(soft)} changed framework file(s) mention other profile terms "
              "(location, employers, tracker companies) - review before committing:")
        print("\n".join(pii_scan.format_hits(soft)))
    return len(loud)


def run(args: argparse.Namespace) -> int:
    start = Path(args.repo) if args.repo else Path(__file__).resolve().parent
    info = fp.repo_info(start)
    if info is None:
        print("check_framework_immutable: not inside a git repository", file=sys.stderr)
        return 2
    if info.is_linked_worktree:
        print("check_framework_immutable: linked worktree - framework edits are allowed here (OK)")
        pii_warning(info)
        return 0
    try:
        drift = find_drift(info)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"check_framework_immutable: {exc}", file=sys.stderr)
        return 2
    pii_warning(info)
    if not drift:
        print(f"check_framework_immutable: OK (main checkout, mode: {fp.read_mode(info.toplevel)})")
        return 0
    print(f"check_framework_immutable: {len(drift)} framework path(s) changed in the main checkout:")
    for xy, rel in drift:
        print(f"  {xy} {rel}")
    print(
        "Operator mode must not change the framework. Move wanted changes to a linked worktree "
        "(git worktree add ../ai-job-search-issue-<n> -b fix/issue-<n>), then `git restore <path>` "
        "here (delete untracked files). Report it with --report or tools/report_issue.py --kind drift."
    )
    if args.report:
        rc = report(drift, info.toplevel)
        print(f"report_issue.py exit code: {rc} (0 filed/queued, 2 refused, 1 error)")
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="List framework drift in the main checkout.")
    ap.add_argument("--report", action="store_true", help="file a 'drift' issue via tools/report_issue.py")
    ap.add_argument("--repo", default=None, help="repository path (default: this script's repo)")
    ap.add_argument("--hook", action="store_true",
                    help="Antigravity Stop hook: report on stderr, print {} on stdout, always exit 0")
    args = ap.parse_args(argv)
    if not args.hook:
        return run(args)
    # Report-only and non-blocking: never files an issue, never keeps the agent running.
    args.report = False
    try:
        with contextlib.redirect_stdout(sys.stderr):
            rc = run(args)
        if rc == 1:
            print("check_framework_immutable: framework drift at session end (see above); run "
                  "python3 tools/check_framework_immutable.py for details.", file=sys.stderr)
    except Exception as exc:  # a Stop hook must never break the session
        print(f"check_framework_immutable: hook error {exc!r}", file=sys.stderr)
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
