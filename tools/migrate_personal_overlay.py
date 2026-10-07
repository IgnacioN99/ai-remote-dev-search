#!/usr/bin/env python3
"""Move personal data out of tracked files into the gitignored `.personal` overlay.

Before the personal overlay (tools/personal_overlay.py) existed, /setup wrote the
candidate's data straight into tracked framework files. The overlay change turns
those files back into placeholder templates; this script carries each user's
personalized version over to `<file>.personal` so nothing is lost.

Source of the personalized content: the file as it was at `--from-rev`. The
default, `auto`, is the commit just before tools/personal_overlay.py was added
(the first parent of the commit that introduced it), so the script works after
pulling the template change - which is the only time it exists. Pass a commit
explicitly to override, or `--from-rev WORKTREE` to read the working-tree file.

For each affected file X:
  * X.personal missing  -> create it from the personalized content.
  * X.personal exists, same content -> nothing to do.
  * X.personal exists, different -> never overwritten. The personalized content
    is written to X.incoming.personal (also gitignored) and a manual merge is
    reported, with line counts.
Every existing X.personal is backed up to documents/memory/backup-<timestamp>/
(gitignored) before anything is written.

Dry-run by default; `--apply` writes. Stdlib only.

Usage:
  python3 tools/migrate_personal_overlay.py            # show the plan
  python3 tools/migrate_personal_overlay.py --apply    # write it
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SUFFIX = ".personal"
INCOMING_SUFFIX = ".incoming.personal"
OVERLAY_TOOL = "tools/personal_overlay.py"
WORKTREE = "WORKTREE"

_SKILL = ".claude/skills/job-application-assistant"
# Files the overlay change turned back into templates (plus the profile files
# /setup always personalized). A file whose content at the source revision has
# no lines beyond the current template is skipped - there is nothing to carry.
AFFECTED = [
    "CLAUDE.md",
    f"{_SKILL}/01-candidate-profile.md",
    f"{_SKILL}/02-behavioral-profile.md",
    f"{_SKILL}/04-job-evaluation.md",
    f"{_SKILL}/05-cv-templates.md",
    f"{_SKILL}/06-cover-letter-templates.md",
    f"{_SKILL}/07-interview-prep.md",
    ".claude/skills/job-scraper/search-queries.md",
]


def _git(root: Path, *args: str) -> Tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    except OSError:
        return 1, ""
    return r.returncode, r.stdout


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def auto_rev(root: Path) -> Optional[str]:
    """First parent of the commit that added tools/personal_overlay.py, or None."""
    rc, out = _git(root, "log", "--diff-filter=A", "--format=%H", "--", OVERLAY_TOOL)
    commits = out.split()
    if rc != 0 or not commits:
        return None
    rc, out = _git(root, "rev-parse", "--verify", "--quiet", commits[-1] + "^")
    return out.strip() if rc == 0 and out.strip() else None


def content_at(root: Path, rev: str, rel: str) -> Optional[str]:
    if rev == WORKTREE:
        p = root / rel
        return _norm(p.read_text(encoding="utf-8")) if p.is_file() else None
    rc, out = _git(root, "show", f"{rev}:{rel}")
    return _norm(out) if rc == 0 else None


def _lines(text: str) -> set:
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


def _strip_self_import(rel: str, text: str) -> str:
    me = "@" + Path(rel).name + SUFFIX
    return "".join(ln for ln in text.splitlines(keepends=True) if ln.strip() != me)


def _version(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    m = re.match(r"---\n(?:.*\n)*?framework_version:\s*['\"]?([0-9.]+)", _norm(path.read_text(encoding="utf-8")))
    return m.group(1) if m else None


def plan(root: Path, rev: str, files: List[str]) -> List[dict]:
    rows = []
    for rel in files:
        src = content_at(root, rev, rel)
        tracked = root / rel
        template = _norm(tracked.read_text(encoding="utf-8")) if tracked.is_file() else ""
        personal = tracked.with_name(tracked.name + SUFFIX)
        row = {"path": rel, "personal_exists": personal.is_file(), "action": "skip",
               "src_lines": 0, "personal_lines": 0, "only_src": 0, "only_personal": 0,
               "src_missing_from_personal": 0, "reason": ""}
        if src is None:
            row["reason"] = f"not present at {rev}"
            rows.append(row)
            continue
        src = _strip_self_import(rel, src)
        row["src_lines"] = len(src.splitlines())
        personal_lines_vs_template = _lines(src) - _lines(template)
        if not row["personal_exists"]:
            if not personal_lines_vs_template:
                row["reason"] = "no content beyond the current template"
            else:
                row["action"] = "create"
                row["reason"] = f"{len(personal_lines_vs_template)} line(s) beyond the template"
            rows.append(row)
            continue
        cur = _norm(personal.read_text(encoding="utf-8"))
        row["personal_lines"] = len(cur.splitlines())
        if cur == src:
            row["reason"] = "already identical"
            rows.append(row)
            continue
        diff = list(difflib.unified_diff(cur.splitlines(), src.splitlines(), lineterm="", n=0))
        row["only_src"] = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        row["only_personal"] = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        row["src_missing_from_personal"] = len(personal_lines_vs_template - _lines(cur))
        if row["src_missing_from_personal"] == 0:
            row["reason"] = "differs, but every personalized line is already in .personal"
        else:
            row["action"] = "incoming"
            row["reason"] = (f"{row['src_missing_from_personal']} personalized line(s) missing from "
                             ".personal - manual merge needed")
        rows.append(row)
    return rows


def apply(root: Path, rev: str, rows: List[dict], stamp: str) -> Path:
    backup = root / "documents" / "memory" / f"backup-{stamp}"
    for row in rows:
        rel = row["path"]
        tracked = root / rel
        personal = tracked.with_name(tracked.name + SUFFIX)
        if personal.is_file():
            dest = backup / (rel + SUFFIX)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(personal, dest)
        if row["action"] == "skip":
            continue
        src = _strip_self_import(rel, content_at(root, rev, rel) or "")
        # The template only lost its personal sections since `rev`, so the copy
        # is current with it: carry the template's version so
        # `personal_overlay.py status` does not report it stale.
        template_version = _version(tracked)
        if template_version:
            src = re.sub(r"(?m)^framework_version:.*$", f"framework_version: {template_version}", src, count=1)
        if row["action"] == "create":
            personal.write_text(src, encoding="utf-8", newline="")
        elif row["action"] == "incoming":
            tracked.with_name(tracked.name + INCOMING_SUFFIX).write_text(src, encoding="utf-8", newline="")
    return backup


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Move personal data from tracked files into *.personal overlays.")
    ap.add_argument("--apply", action="store_true", help="write files (default: dry run)")
    ap.add_argument("--from-rev", default="auto",
                    help="revision holding the personalized files (default: auto = commit before the overlay; "
                         f"'{WORKTREE}' = working tree)")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--files", nargs="*", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    rev = args.from_rev
    if rev == "auto":
        rev = auto_rev(root) or WORKTREE
    print(f"Source of personalized content: {rev}")
    rows = plan(root, rev, args.files or AFFECTED)
    needs_merge = False
    for r in rows:
        counts = (f"tracked@src {r['src_lines']} lines, .personal {r['personal_lines'] if r['personal_exists'] else '-'} lines")
        if r["action"] == "incoming":
            needs_merge = True
            counts += f", diff +{r['only_src']}/-{r['only_personal']}"
        print(f"[{r['action']:8}] {r['path']}  ({counts}) - {r['reason']}")

    if not args.apply:
        print("\nDry run - nothing written. Re-run with --apply to write.")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = apply(root, rev, rows, stamp)
    print(f"\nBackups of existing .personal files: {backup.relative_to(root).as_posix() if backup.exists() else '(none needed)'}")
    if needs_merge:
        print("Manual merge needed: for each [incoming] file, merge <file>.incoming.personal into "
              "<file>.personal, then delete the .incoming.personal file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
