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
`cv/main_example.tex` (the master CV) was personalized in the working tree rather
than at a commit, so its source is always the working-tree file.

"Personalized" means lines present in NO template version of the file: the file
as the overlay commit left it or as any later commit (HEAD included) left it. Measuring against the current template alone would read framework
text changed after the overlay as personal data.

For each affected file X:
  * X.personal missing  -> create it from the personalized content. The copy keeps
    the SOURCE framework_version, so `personal_overlay.py status` reports it stale
    when the template has gained framework rules since.
  * X.personal exists, same content -> nothing to do.
  * X.personal exists, different -> never overwritten. The personalized content
    is written to X.incoming.personal (also gitignored) and a manual merge is
    reported, with the count of genuinely personal lines still to move.
Every existing X.personal is backed up to documents/memory/backup-<timestamp>/
(gitignored) before anything is written. `--apply` is idempotent: when nothing
would change it writes nothing and creates no backup folder.

Resolved merges are remembered in .agents/state/personal_migration.json
(gitignored; paths and content hashes only), keyed by file with the source
revision and the sha256 of the source content. A file is resolved when
  * `--apply` wrote X.incoming.personal, and later that file is gone while
    X.personal exists (the user merged it and deleted it) - detected automatically;
  * or the user says so: `--resolved X` / `--resolved-all`.
A resolved file is reported `[resolved]` and never gets a new incoming copy. If
the source content changes (different hash), the file is open again.

Dry-run by default; `--apply` writes. Stdlib only.

Usage:
  python3 tools/migrate_personal_overlay.py                 # show the plan
  python3 tools/migrate_personal_overlay.py --apply         # write it
  python3 tools/migrate_personal_overlay.py --resolved-all  # after merging by hand
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import hashlib
import json
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
STATE_REL = ".agents/state/personal_migration.json"

_SKILL = ".claude/skills/job-application-assistant"
# Files the overlay change turned back into templates (plus the profile files
# /setup always personalized). A file whose content at the source revision has
# no lines beyond every template version is skipped - there is nothing to carry.
AFFECTED = [
    "CLAUDE.md",
    f"{_SKILL}/01-candidate-profile.md",
    f"{_SKILL}/02-behavioral-profile.md",
    f"{_SKILL}/04-job-evaluation.md",
    f"{_SKILL}/05-cv-templates.md",
    f"{_SKILL}/06-cover-letter-templates.md",
    f"{_SKILL}/07-interview-prep.md",
    ".claude/skills/job-scraper/search-queries.md",
    "cv/main_example.tex",
]
# Personalized in the working tree, never at a commit: always read from WORKTREE.
WORKTREE_SOURCED = {"cv/main_example.tex"}


def _git(root: Path, *args: str) -> Tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    except OSError:
        return 1, ""
    return r.returncode, r.stdout


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def overlay_commit(root: Path) -> Optional[str]:
    """The commit that added tools/personal_overlay.py, or None."""
    rc, out = _git(root, "log", "--diff-filter=A", "--format=%H", "--", OVERLAY_TOOL)
    commits = out.split()
    return commits[-1] if rc == 0 and commits else None


def auto_rev(root: Path) -> Optional[str]:
    """First parent of the commit that added tools/personal_overlay.py, or None."""
    commit = overlay_commit(root)
    if not commit:
        return None
    rc, out = _git(root, "rev-parse", "--verify", "--quiet", commit + "^")
    return out.strip() if rc == 0 and out.strip() else None


def content_at(root: Path, rev: str, rel: str) -> Optional[str]:
    if rev == WORKTREE:
        p = root / rel
        return _norm(p.read_text(encoding="utf-8")) if p.is_file() else None
    rc, out = _git(root, "show", f"{rev}:{rel}")
    return _norm(out) if rc == 0 else None


_VERSION_LINE = re.compile(r"^framework_version:")


def _lines(text: str) -> set:
    """Non-blank stripped lines, minus framework_version stamps: a copy stamped with
    another version (e.g. by an earlier migration) differs there without holding data."""
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not _VERSION_LINE.match(ln.strip())}


def template_lines(root: Path, rel: str) -> set:
    """Every line any template version of `rel` has carried: at the overlay commit,
    and at each later commit that touched it (HEAD included). Before the overlay
    the tracked file held personal data, so earlier versions never count; the
    working tree is never a template either - it may hold uncommitted personal
    edits (the master CV always did). Outside git, the working tree is all there is."""
    lines: set = set()
    base = overlay_commit(root)
    if not base:
        head = content_at(root, "HEAD", rel)
        if head is None and (root / rel).is_file():
            head = _norm((root / rel).read_text(encoding="utf-8"))
        return _lines(head or "")
    rc, out = _git(root, "log", "--format=%H", f"{base}..HEAD", "--", rel)
    for rev in {base, "HEAD", *(out.split() if rc == 0 else [])}:
        text = content_at(root, rev, rel)
        if text is not None:
            lines |= _lines(text)
    return lines


def _strip_self_import(rel: str, text: str) -> str:
    me = "@" + Path(rel).name + SUFFIX
    return "".join(ln for ln in text.splitlines(keepends=True) if ln.strip() != me)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_state(root: Path) -> dict:
    try:
        data = json.loads((root / STATE_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"files": {}}
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return {"files": {}}
    return data


def save_state(root: Path, state: dict) -> None:
    path = root / STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record(state: dict, rel: str, key: str, row: dict, how: str = "") -> None:
    entry = {"source": row["source"], "sha256": row["sha256"],
             "at": datetime.datetime.now().isoformat(timespec="seconds")}
    if how:
        entry["how"] = how
    state.setdefault("files", {}).setdefault(rel, {})[key] = entry


def _matches(state: dict, rel: str, key: str, sha: str) -> bool:
    entry = state.get("files", {}).get(rel, {}).get(key)
    return isinstance(entry, dict) and entry.get("sha256") == sha


def incoming_path(root: Path, rel: str) -> Path:
    tracked = root / rel
    return tracked.with_name(tracked.name + INCOMING_SUFFIX)


def plan(root: Path, rev: str, files: List[str], state: Optional[dict] = None) -> List[dict]:
    state = state if state is not None else {"files": {}}
    rows = []
    for rel in files:
        file_rev = WORKTREE if rel in WORKTREE_SOURCED else rev
        src = content_at(root, file_rev, rel)
        tracked = root / rel
        templates = template_lines(root, rel)
        personal = tracked.with_name(tracked.name + SUFFIX)
        incoming = incoming_path(root, rel)
        cur = _norm(personal.read_text(encoding="utf-8")) if personal.is_file() else None
        row = {"path": rel, "personal_exists": cur is not None, "action": "skip",
               "src_lines": 0, "personal_lines": 0, "only_src": 0, "only_personal": 0,
               "src_missing_from_personal": 0, "reason": "", "src": None,
               "incoming_personal_lines": None, "source": file_rev, "sha256": None,
               "needs_merge": False, "auto_resolved": False}
        if incoming.is_file():
            # Lines of an existing .incoming.personal found in no template version
            # and not in .personal: what a manual merge would still have to move.
            row["incoming_personal_lines"] = len(
                _lines(_norm(incoming.read_text(encoding="utf-8"))) - templates - _lines(cur or ""))
        if src is None:
            row["reason"] = f"not present at {file_rev}"
            rows.append(row)
            continue
        src = _strip_self_import(rel, src)
        row["src"] = src
        row["sha256"] = _sha(src)
        row["src_lines"] = len(src.splitlines())
        personal_lines = _lines(src) - templates
        if cur is None:
            if not personal_lines:
                row["reason"] = "no content beyond the template versions"
            else:
                row["action"] = "create"
                row["reason"] = f"{len(personal_lines)} line(s) found in no template version"
            rows.append(row)
            continue
        row["personal_lines"] = len(cur.splitlines())
        if cur == src:
            row["reason"] = "already identical"
            rows.append(row)
            continue
        diff = list(difflib.unified_diff(cur.splitlines(), src.splitlines(), lineterm="", n=0))
        row["only_src"] = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        row["only_personal"] = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        row["src_missing_from_personal"] = len(personal_lines - _lines(cur))
        if row["src_missing_from_personal"] == 0:
            row["reason"] = "differs, but every personalized line is already in .personal"
            rows.append(row)
            continue
        row["needs_merge"] = True
        missing = row["src_missing_from_personal"]
        if _matches(state, rel, "resolved", row["sha256"]):
            row["action"] = "resolved"
            row["reason"] = f"merge marked resolved ({missing} source line(s) deliberately not carried over)"
        elif not incoming.is_file() and _matches(state, rel, "incoming_written", row["sha256"]):
            # --apply wrote the incoming copy and the user has since deleted it:
            # they merged what they wanted. Persisted on the next write.
            row["action"] = "resolved"
            row["auto_resolved"] = True
            row["reason"] = "merged: the .incoming.personal written by --apply has been deleted"
        elif incoming.is_file() and _norm(incoming.read_text(encoding="utf-8")) == src:
            row["reason"] = (f"{row['src_missing_from_personal']} personalized line(s) missing from "
                             ".personal - already in .incoming.personal, merge pending")
        else:
            row["action"] = "incoming"
            row["reason"] = (f"{row['src_missing_from_personal']} personalized line(s) missing from "
                             ".personal - manual merge needed")
        rows.append(row)
    return rows


def apply(root: Path, rows: List[dict], stamp: str, state: Optional[dict] = None) -> Optional[Path]:
    """Write the planned copies. Returns the backup folder, or None when nothing
    needed writing (then nothing is touched and no backup folder is created).
    Each incoming copy written is recorded in `state` (the caller saves it)."""
    writes = [r for r in rows if r["action"] in ("create", "incoming")]
    if not writes:
        return None
    backup = root / "documents" / "memory" / f"backup-{stamp}"
    for row in rows:
        tracked = root / row["path"]
        personal = tracked.with_name(tracked.name + SUFFIX)
        if personal.is_file():
            dest = backup / (row["path"] + SUFFIX)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(personal, dest)
    for row in writes:
        rel = row["path"]
        tracked = root / rel
        # The source keeps its own framework_version: the template may have gained
        # framework rules since, and `personal_overlay.py status` must then report
        # the copy stale so the user merges them in.
        if row["action"] == "create":
            tracked.with_name(tracked.name + SUFFIX).write_text(row["src"], encoding="utf-8", newline="")
        else:
            incoming_path(root, rel).write_text(row["src"], encoding="utf-8", newline="")
            if state is not None:
                _record(state, rel, "incoming_written", row)
    return backup


def mark_resolved(root: Path, rows: List[dict], state: dict, names: List[str],
                  all_open: bool) -> List[str]:
    """Record the explicitly resolved files in `state`; return the messages to print.
    `--resolved-all` covers every file that still needs a merge, but leaves alone
    one whose .incoming.personal still exists (name it with --resolved instead)."""
    msgs = []
    by_path = {r["path"]: r for r in rows}
    targets = list(dict.fromkeys(names))
    if all_open:
        targets += [r["path"] for r in rows
                    if r["needs_merge"] and r["action"] != "resolved" and r["path"] not in targets]
    for rel in targets:
        row = by_path[rel]
        if not row["needs_merge"]:
            msgs.append(f"{rel}: nothing to resolve ({row['reason'] or row['action']})")
            continue
        if rel not in names and incoming_path(root, rel).is_file():
            msgs.append(f"{rel}: {rel}{INCOMING_SUFFIX} still exists - merge it and delete it, "
                        f"or pass --resolved {rel}")
            continue
        _record(state, rel, "resolved", row, how="explicit")
        row["action"] = "resolved"
        row["auto_resolved"] = False
        row["reason"] = "merge marked resolved"
        msgs.append(f"{rel}: marked resolved")
    return msgs


def _rel_arg(name: str) -> str:
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    return name


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
    ap.add_argument("--resolved", action="append", default=[], metavar="FILE",
                    help="record FILE's manual merge as done so it is never flagged again (repeatable)")
    ap.add_argument("--resolved-all", action="store_true",
                    help="record every pending manual merge whose .incoming.personal is gone as done")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--files", nargs="*", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    files = args.files or AFFECTED
    resolved_names = [_rel_arg(n) for n in args.resolved]
    unknown = [n for n in resolved_names if n not in files]
    if unknown:
        print(f"error: --resolved: not a migrated file: {', '.join(unknown)} "
              f"(choose from: {', '.join(files)})", file=sys.stderr)
        return 2
    rev = args.from_rev
    if rev == "auto":
        rev = auto_rev(root) or WORKTREE
    print(f"Source of personalized content: {rev}")
    state = load_state(root)
    rows = plan(root, rev, files, state)
    state_dirty = False
    if resolved_names or args.resolved_all:
        for msg in mark_resolved(root, rows, state, resolved_names, args.resolved_all):
            print(f"resolved: {msg}")
        state_dirty = True
    if args.apply or state_dirty:
        # Persist what the plan detected: an incoming copy --apply wrote is gone.
        for r in rows:
            if r["auto_resolved"]:
                _record(state, r["path"], "resolved", r, how="incoming deleted")
                state_dirty = True
    for r in rows:
        counts = (f"tracked@src {r['src_lines']} lines, .personal {r['personal_lines'] if r['personal_exists'] else '-'} lines")
        if r["action"] == "incoming":
            counts += f", diff +{r['only_src']}/-{r['only_personal']}"
        print(f"[{r['action']:8}] {r['path']}  ({counts}) - {r['reason']}")
        if r["action"] != "incoming" and r["incoming_personal_lines"] is not None:
            n = r["incoming_personal_lines"]
            note = ("likely safe to delete" if n == 0
                    else "merge them into .personal, then delete it")
            print(f"           existing {r['path']}{INCOMING_SUFFIX}: {n} genuinely personal "
                  f"line(s) not yet in .personal - {note}")
    merges = [r for r in rows if r["action"] == "incoming"]
    hint = ("If you already merged these by hand (kept your .personal wording and deleted the "
            ".incoming.personal copies), run `python3 tools/migrate_personal_overlay.py "
            "--resolved-all` once and they are never flagged again.")

    if not args.apply:
        if state_dirty:
            save_state(root, state)
            print(f"\nRecorded in {STATE_REL}. No other file written.")
        else:
            print("\nDry run - nothing written. Re-run with --apply to write.")
        if merges:
            print(hint)
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = apply(root, rows, stamp, state)
    if merges:
        state_dirty = True
    if state_dirty:
        save_state(root, state)
    if backup is None:
        print("\nNothing to write - already migrated.")
    else:
        print(f"\nBackups of existing .personal files: "
              f"{backup.relative_to(root).as_posix() if backup.exists() else '(none needed)'}")
    if merges:
        print("Manual merge needed: for each file below, merge <file>.incoming.personal into "
              "<file>.personal, then delete the .incoming.personal file. Genuinely personal lines "
              "(in no template version, not yet in .personal):")
        for r in merges:
            print(f"  {r['path']}: {r['src_missing_from_personal']}")
        print("Lines you deliberately leave out are fine: once a .incoming.personal file is "
              "deleted, the next run reports that file [resolved] and never recreates it.")
    if any(r["path"] in WORKTREE_SOURCED and r["action"] == "create" for r in rows):
        print("cv/main_example.tex.personal now holds your master CV. Once you have checked it, "
              "restore the tracked placeholder template (discard your working-tree edits to "
              "cv/main_example.tex) so it is never committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
