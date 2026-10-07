#!/usr/bin/env python3
"""Shared classification for the operator-mode framework guard.

Used by .claude/hooks/guard_framework.py (edit-time hook), tools/check_framework_immutable.py
(after-the-fact drift check), tools/set_mode.py and .githooks/pre-commit.

Definitions:
- Main checkout: a repository whose git-dir equals its git-common-dir. A linked worktree
  (`git worktree add`, `claude -w`) has a git-dir under <common>/worktrees/<name> and is where
  framework development happens - nothing here restricts it.
- Framework file: tracked by git, or untracked-and-not-ignored under a framework dir
  (FRAMEWORK_PREFIXES). Gitignored outputs are user data even inside tools/ or .claude/skills/.
- Personalization paths (tools/personalization_paths.json): tracked files commands write by
  design. 'config' entries are allowed only while .agents/state/mode is 'config'; 'always'
  entries in any mode (optionally restricted to changed lines matching a regex).

Stdlib only.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

FRAMEWORK_PREFIXES = (
    "tools/",
    ".claude/",
    ".agents/",
    "tests/",
    ".github/",
    ".githooks/",
    "templates/",
)
FRAMEWORK_ROOT_FILES = {"AGENTS.md", "CLAUDE.md", ".gitignore", ".gitattributes", ".worktreeinclude"}

MODE_FILE = ".agents/state/mode"
PERSONALIZATION_FILE = "tools/personalization_paths.json"
# A config session that never ran `set_mode.py operator` (crash, abandoned chat) must not
# leave the framework writable forever.
CONFIG_TTL_SECONDS = 4 * 3600

ISSUE_HINT = (
    "file an issue instead: python3 tools/report_issue.py --kind <bug|improvement|drift|doc> "
    "--title \"...\" --body \"...\" (paths and symptoms only, no personal data); or do the "
    "change in a linked worktree (Claude Code: the framework-dev agent / `claude -w issue-<n>`; "
    "Antigravity: git worktree add ../ai-job-search-issue-<n> -b fix/issue-<n>)."
)


def _git(args: list[str], cwd: str | os.PathLike) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=15
    )


def _warn(msg: str) -> None:
    print(f"framework_paths: warning: {msg}", file=sys.stderr)


@dataclass
class RepoInfo:
    toplevel: Path
    git_dir: Path
    common_dir: Path

    @property
    def is_linked_worktree(self) -> bool:
        return self.git_dir != self.common_dir


def repo_info(start: str | os.PathLike) -> RepoInfo | None:
    """Git identity of the repo containing `start` (nearest existing ancestor dir), or None."""
    d = Path(start)
    while not d.is_dir():
        if d.parent == d:
            return None
        d = d.parent
    try:
        r = _git(
            ["rev-parse", "--path-format=absolute", "--show-toplevel", "--git-dir", "--git-common-dir"],
            d,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _warn(f"could not run git ({exc}); operator-mode guard is NOT enforced for {d}")
        return None
    if r.returncode != 0:
        err = r.stderr.strip()
        # "not a git repository" is the expected answer outside a repo. Anything else (git older
        # than 2.31 without --path-format, a broken install, a safe.directory refusal) means the
        # guard cannot classify the path, so say so before failing open.
        if "not a git repository" not in err.lower():
            _warn(f"git rev-parse failed in {d} ({err or 'exit ' + str(r.returncode)}); "
                  "operator-mode guard is NOT enforced here (it needs git >= 2.31)")
        return None
    lines = r.stdout.splitlines()
    if len(lines) < 3:
        _warn(f"unexpected git rev-parse output in {d}; operator-mode guard is NOT enforced here")
        return None
    top, gd, cd = (Path(os.path.realpath(x)) for x in lines[:3])
    return RepoInfo(top, gd, cd)


def relpath_in(info: RepoInfo, path: str | os.PathLike) -> str | None:
    """POSIX path of `path` relative to the toplevel, or None if outside it."""
    real = Path(os.path.realpath(path))
    try:
        rel = real.relative_to(info.toplevel)
    except ValueError:
        return None
    return rel.as_posix()


def is_tracked(info: RepoInfo, rel: str) -> bool:
    return _git(["ls-files", "--error-unmatch", "--", rel], info.toplevel).returncode == 0


def is_ignored(info: RepoInfo, rel: str) -> bool:
    return _git(["check-ignore", "-q", "--", rel], info.toplevel).returncode == 0


def in_framework_dir(rel: str) -> bool:
    return rel in FRAMEWORK_ROOT_FILES or rel.startswith(FRAMEWORK_PREFIXES)


def is_framework(info: RepoInfo, rel: str) -> bool:
    if is_tracked(info, rel):
        return True
    if is_ignored(info, rel):
        return False
    return in_framework_dir(rel)


# ---------------------------------------------------------------- personalization + mode

def glob_to_regex(glob: str) -> re.Pattern:
    out, i = [], 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = glob.find("]", i)
            if j == -1:
                out.append(re.escape(c))
            else:
                out.append(glob[i : j + 1])
                i = j + 1
                continue
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def load_personalization(toplevel: Path) -> list[dict]:
    path = Path(toplevel) / PERSONALIZATION_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("paths", []) if isinstance(data, dict) else []
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("glob"), str)]


def read_mode(toplevel: Path) -> str:
    """'config' or 'operator'. Absent, unreadable, unknown or expired state -> 'operator'."""
    path = Path(toplevel) / MODE_FILE
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "operator"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"mode": raw}
    if not isinstance(data, dict) or data.get("mode") != "config":
        return "operator"
    since = data.get("since")
    if not isinstance(since, (int, float)) or time.time() - since > CONFIG_TTL_SECONDS:
        return "operator"
    return "config"


def write_mode(toplevel: Path, mode: str, by: str = "") -> Path:
    path = Path(toplevel) / MODE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mode": mode, "since": int(time.time()), "by": by}) + "\n", encoding="utf-8")
    return path


def changed_lines(old: str, new: str) -> list[str]:
    diff = difflib.ndiff(old.splitlines(), new.splitlines())
    return [d[2:] for d in diff if d[:2] in ("- ", "+ ")]


def personalization_allows(
    entries: list[dict], rel: str, mode: str, change: tuple[str, str] | None
) -> tuple[bool, str]:
    """(allowed, reason). `change` is (old_content, new_content) when computable, else None."""
    for entry in entries:
        if not glob_to_regex(entry["glob"]).match(rel):
            continue
        emode = entry.get("mode")
        if emode == "config" and mode == "config":
            return True, f"config mode: {entry['glob']}"
        if emode == "always":
            lines_re = entry.get("lines")
            if not lines_re:
                return True, f"always-allowed personalization path: {entry['glob']}"
            if change is None:
                continue
            pat = re.compile(lines_re)
            delta = changed_lines(*change)
            if delta and all(pat.match(line) for line in delta):
                return True, f"only '{lines_re}' lines changed in {entry['glob']}"
    return False, ""


def matches_personalization(entries: list[dict], rel: str) -> bool:
    """Any personalization glob matches, regardless of mode (used for commits of user config)."""
    return any(glob_to_regex(e["glob"]).match(rel) for e in entries)
