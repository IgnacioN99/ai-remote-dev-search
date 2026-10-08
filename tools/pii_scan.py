#!/usr/bin/env python3
"""Find candidate PII in files that are about to become framework code.

Used by tools/check_framework_immutable.py (warning on changed framework files) and
.githooks/pre-commit (blocks a commit whose staged files carry identity terms). A skill or
doc written by an agent in the main checkout can hardcode the candidate's name or contact
details; one `git add .` in a worktree or a config-mode commit would publish them.

Terms come from the same gitignored sources tools/report_issue.py redacts, read from the
MAIN checkout (also when run from a linked worktree), with the personal overlay honoured:

  block tier  identity: name (and its parts), email, phone (and its digits), LinkedIn/GitHub
              handles and URLs, street address, birth date - from the TOP-LEVEL keys of
              candidate_profile.json (a nested languages[].name is not the candidate), and
              the Name line of CLAUDE.md(.personal).
  warn tier   everything else report_issue.py redacts (city/location, employers, education,
              tracker companies, application folder names). Framework docs legitimately name
              countries and portals, so these only warn.

Output carries counts and repo-relative paths only - never the matched values.
Public terms are never reported: the `origin` remote owner (the fork owner's handle sits in
README links and clone URLs) and any line of the gitignored .agents/state/pii_allowlist.txt
(one user-approved public term per line, # comments).

No profile on disk (fresh clone) -> no terms -> nothing is ever reported. Stdlib only.

    python3 tools/pii_scan.py [paths...]     # exit 1 if any block-tier hit
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

MAX_BYTES = 2_000_000
_BLOCK_KEY = re.compile(
    r"name|email|mail|phone|mobile|tel|linkedin|github|gitlab|twitter|handle|address|street|"
    r"birth|zip|postal",
    re.IGNORECASE,
)
_WARN_KEY = re.compile(
    r"company|employer|organi[sz]ation|school|universit|institution|degree|thesis|education|"
    r"city|location|country|title|role",
    re.IGNORECASE,
)
_NAME_LINE = re.compile(r"^\s*-\s*\*\*Name:?\*\*:?\s*(?P<val>.+)$", re.MULTILINE)


def data_root(start: Path) -> Path:
    """The main checkout of the repo holding `start` (personal data lives only there)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           cwd=str(start), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return start
    common = Path((r.stdout or "").strip())
    if r.returncode != 0 or not common.is_absolute() or common.name != ".git":
        return start
    return common.parent


def _profile_terms(profile: Path) -> Tuple[List[str], List[str]]:
    """(block, warn). Block tier comes only from TOP-LEVEL identity keys ("name", "email",
    "phone", "linkedin", "github", ...): a nested "name" (languages[].name, education[].name)
    is a language or a school, not the candidate. Every other identity-hinted string warns."""
    import report_issue as ri

    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    block: List[str] = []
    warn: List[str] = []
    for _key, value in ri._walk_strings(data):
        value = value.strip()
        if value:
            warn.append(value)
    if not isinstance(data, dict):
        return [], warn
    for key, raw in data.items():
        key = str(key)
        if not _BLOCK_KEY.search(key) or _WARN_KEY.search(key):
            continue
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = [v for v in raw if isinstance(v, str)]
        else:
            values = []
        k = key.lower()
        for value in values:
            value = value.strip()
            if not value:
                continue
            block.append(value)
            if k in ri._NAME_KEYS:
                block.extend(ri._name_parts(value))
            if re.search(r"phone|mobile|tel", k):
                digits = re.sub(r"\D", "", value)
                if len(digits) >= 7:
                    block.append(digits)
            if re.match(r"https?://", value):
                handle = value.rstrip("/").rsplit("/", 1)[-1]
                if len(handle) >= 3:
                    block.append(handle)
    return block, warn


_REMOTE_OWNER = re.compile(r"^(?:[\w+.-]+://(?:[^@/]+@)?[^/]+/|[^@/:]+@[^:/]+:)/?(?P<owner>[^/]+)/")


def origin_owner(root: Path) -> Optional[str]:
    """Owner of the `origin` remote (git@host:Owner/repo.git, https://host/Owner/repo). The
    fork owner's handle appears legitimately in README links and clone URLs."""
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root),
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _REMOTE_OWNER.match((r.stdout or "").strip()) if r.returncode == 0 else None
    return m.group("owner") if m else None


ALLOWLIST = Path(".agents") / "state" / "pii_allowlist.txt"


def load_allowlist(root: Path) -> List[str]:
    """User-approved public terms (gitignored file, one per line, # comments)."""
    try:
        lines = (Path(root) / ALLOWLIST).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _drop_public(terms: Iterable[str], public: Sequence[str]) -> List[str]:
    """Drop terms equal to a public term, and profile URLs whose last segment is one
    (https://github.com/<owner> also matches inside every repo link)."""
    pub = {p.strip().lower() for p in public if p and p.strip()}
    if not pub:
        return list(terms)
    out = []
    for t in terms:
        low = t.strip().lower()
        if low in pub:
            continue
        if re.match(r"https?://", low) and low.rstrip("/").rsplit("/", 1)[-1] in pub:
            continue
        out.append(t)
    return out


def _claude_name(claude_md: Path) -> List[str]:
    import report_issue as ri

    overlay = claude_md.with_name(claude_md.name + ".personal")
    path = overlay if overlay.is_file() else claude_md
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    m = _NAME_LINE.search(text)
    if not m:
        return []
    val = re.sub(r"<!--.*?-->", "", m.group("val")).strip().strip('"').strip()
    if not val or ri._PLACEHOLDER.search(val):
        return []
    return [val] + ri._name_parts(val)


class PiiScanner:
    def __init__(self, block_terms: Iterable[str] = (), warn_terms: Iterable[str] = ()) -> None:
        import report_issue as ri

        self._block = ri.Sanitizer(block_terms)
        blocked = {t.lower() for t in self._block.terms}
        self._warn = ri.Sanitizer([t for t in warn_terms if t.lower() not in blocked])

    @classmethod
    def from_repo(cls, start: Path, include_warn: bool = True) -> "PiiScanner":
        """include_warn=False loads only the block tier (identity terms): the pre-commit hook
        uses it to stay fast, since it only ever blocks on identity hits."""
        import report_issue as ri

        root = data_root(Path(start))
        block, warn = _profile_terms(root / "candidate_profile.json")
        block += _claude_name(root / "CLAUDE.md")
        if include_warn:
            warn += ri.load_claude_identity(root / "CLAUDE.md")
            warn += ri.load_tracker_terms(root / "job_search_tracker.csv")
            warn += ri.load_application_terms(root / "documents" / "applications")
        else:
            warn = []
        public = load_allowlist(root)
        owner = origin_owner(Path(start))
        if owner:
            public.append(owner)
        return cls(_drop_public(block, public), _drop_public(warn, public))

    @property
    def empty(self) -> bool:
        return not self._block.terms and not self._warn.terms

    @staticmethod
    def _count(san, text: str) -> int:
        return sum(len(p.findall(text)) for p in san._term_patterns)

    def scan_text(self, text: str) -> Tuple[int, int]:
        """(block-tier hits, warn-tier hits)."""
        if not text or self.empty:
            return 0, 0
        return self._count(self._block, text), self._count(self._warn, text)

    def scan_bytes(self, data: bytes) -> Tuple[int, int]:
        if not data or len(data) > MAX_BYTES or b"\0" in data[:8192]:
            return 0, 0
        return self.scan_text(data.decode("utf-8", errors="ignore"))

    def scan_files(self, root: Path, rels: Sequence[str]) -> List[Tuple[str, int, int]]:
        """[(rel, block, warn)] for working-tree files with at least one hit. Skips symlinks,
        directories, missing and binary files."""
        out = []
        if self.empty:
            return out
        for rel in rels:
            p = Path(root) / rel
            try:
                if p.is_symlink() or not p.is_file():
                    continue
                b, w = self.scan_bytes(p.read_bytes())
            except OSError:
                continue
            if b or w:
                out.append((rel, b, w))
        return out


def format_hits(hits: Sequence[Tuple[str, int, int]]) -> List[str]:
    return [f"  {rel}: {b} identity match(es), {w} other profile match(es)" for rel, b, w in hits]


def main(argv: Optional[List[str]] = None) -> int:
    paths = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    scanner = PiiScanner.from_repo(root)
    hits = scanner.scan_files(root, paths)
    if not hits:
        print("pii_scan: no candidate PII found" + (" (no profile terms on disk)" if scanner.empty else ""))
        return 0
    print(f"pii_scan: candidate PII in {len(hits)} file(s) (values not shown):")
    print("\n".join(format_hits(hits)))
    return 1 if any(b for _, b, _ in hits) else 0


if __name__ == "__main__":
    sys.exit(main())
