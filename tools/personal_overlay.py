#!/usr/bin/env python3
"""Personal overlay: keep candidate data out of tracked framework files.

The tracked profile/data files (CLAUDE.md, the job-application-assistant
01-09 files, job-scraper/search-queries.md, the master CV cv/main_example.tex)
are TEMPLATES with [PLACEHOLDER]
tokens. A candidate's real version of any of them lives next to it as
`<file>.personal` (gitignored by the `*.personal` rule in .gitignore), so a
public fork never publishes personal data.

The rule (replace semantics, not merge):

  * read:  if `X.personal` exists, read it INSTEAD of `X` (it is a complete
           copy of the file, not a patch); otherwise read `X`.
  * write: profile/data updates go to `X.personal`; if it does not exist yet,
           create it as a copy of `X` first, then edit the copy. The tracked
           `X` stays a template.

Because a `.personal` file is a full copy, framework text inside it (scoring
rules, checklists) does not follow later template updates on its own.
`status` flags every overlay whose template carries a newer
`framework_version` than the copy, so the user knows to merge.

Usage:
  python3 tools/personal_overlay.py resolve <path>   # print the path to READ
  python3 tools/personal_overlay.py ensure <path>    # create X.personal if missing, print the path to WRITE
  python3 tools/personal_overlay.py status           # list overlay files; exit 1 if a copy is stale

Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

ROOT = Path(__file__).resolve().parent.parent
SUFFIX = ".personal"

_SKILL = ".claude/skills/job-application-assistant"
# Repo-relative paths of every file the overlay applies to.
OVERLAY_FILES: List[str] = [
    "CLAUDE.md",
    f"{_SKILL}/01-candidate-profile.md",
    f"{_SKILL}/02-behavioral-profile.md",
    f"{_SKILL}/03-writing-style.md",
    f"{_SKILL}/04-job-evaluation.md",
    f"{_SKILL}/05-cv-templates.md",
    f"{_SKILL}/06-cover-letter-templates.md",
    f"{_SKILL}/07-interview-prep.md",
    f"{_SKILL}/08-application-forms.md",
    f"{_SKILL}/09-web-research.md",
    ".claude/skills/job-scraper/search-queries.md",
    # The master CV. LaTeX never compiles the .personal copy in place: /apply
    # copies the resolved file to cv/main_<company>_<role>.tex first.
    "cv/main_example.tex",
]

PathLike = Union[str, Path]


def _abs(path: PathLike, root: Optional[Path] = None) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (root or ROOT) / p


def personal_path(path: PathLike, root: Optional[Path] = None) -> Path:
    """`X` -> `X.personal` (same directory)."""
    p = _abs(path, root)
    return p.with_name(p.name + SUFFIX)


def resolve(path: PathLike, root: Optional[Path] = None) -> Path:
    """The file to READ for `path`: `X.personal` when it exists, else `X`."""
    p = _abs(path, root)
    if p.name.endswith(SUFFIX):
        return p
    overlay = personal_path(p)
    return overlay if overlay.is_file() else p


def read_text(path: PathLike, root: Optional[Path] = None) -> str:
    """Read the resolved file as UTF-8 with CRLF normalized to LF."""
    return resolve(path, root).read_text(encoding="utf-8").replace("\r\n", "\n")


def ensure_personal(path: PathLike, root: Optional[Path] = None) -> Path:
    """The file to WRITE for `path`: create `X.personal` from `X` if missing.

    Never overwrites an existing `X.personal`.
    """
    p = _abs(path, root)
    if p.name.endswith(SUFFIX):
        return p
    overlay = personal_path(p)
    if not overlay.exists():
        if p.is_file():
            # Drop the template's own import of the overlay (CLAUDE.md carries
            # `@CLAUDE.md.personal`) so the copy never imports itself.
            text = p.read_text(encoding="utf-8")
            self_import = "@" + overlay.name
            kept = [ln for ln in text.splitlines(keepends=True) if ln.strip() != self_import]
            overlay.write_text("".join(kept), encoding="utf-8", newline="")
        else:
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text("", encoding="utf-8")
    return overlay


_VERSION = re.compile(r"^framework_version:\s*['\"]?([0-9]+(?:\.[0-9]+)*)", re.MULTILINE)


def framework_version(text: str) -> Optional[str]:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    match = _VERSION.search(text[: end if end != -1 else len(text)])
    return match.group(1) if match else None


def _ver_tuple(v: Optional[str]) -> tuple:
    return tuple(int(x) for x in v.split(".")) if v else ()


def status(root: Optional[Path] = None) -> List[Dict[str, object]]:
    """One row per overlay file: which copy is read and whether it is stale."""
    base = root or ROOT
    rows: List[Dict[str, object]] = []
    for rel in OVERLAY_FILES:
        tracked = base / rel
        overlay = personal_path(tracked)
        t_ver = p_ver = None
        if tracked.is_file():
            t_ver = framework_version(tracked.read_text(encoding="utf-8").replace("\r\n", "\n"))
        if overlay.is_file():
            p_ver = framework_version(overlay.read_text(encoding="utf-8").replace("\r\n", "\n"))
        stale = bool(overlay.is_file() and t_ver and _ver_tuple(t_ver) > _ver_tuple(p_ver))
        rows.append({
            "path": rel,
            "has_personal": overlay.is_file(),
            "reads": (rel + SUFFIX) if overlay.is_file() else rel,
            "template_version": t_ver,
            "personal_version": p_ver,
            "stale": stale,
        })
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("resolve", "ensure"):
        sp = sub.add_parser(name)
        sp.add_argument("path")
    sub.add_parser("status")
    args = ap.parse_args(argv)

    if args.cmd == "resolve":
        print(resolve(args.path).relative_to(ROOT).as_posix()
              if _abs(args.path).is_relative_to(ROOT) else resolve(args.path))
        return 0
    if args.cmd == "ensure":
        target = ensure_personal(args.path)
        print(target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else target)
        return 0

    rows = status()
    stale = [r for r in rows if r["stale"]]
    for r in rows:
        flag = "  STALE: template is newer - merge framework changes into the .personal copy" if r["stale"] else ""
        versions = f"template {r['template_version'] or '-'} / personal {r['personal_version'] or '-'}" if r["has_personal"] else ""
        print(f"{'personal' if r['has_personal'] else 'template'}  {r['reads']}  {versions}{flag}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
