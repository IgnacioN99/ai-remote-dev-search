#!/usr/bin/env python3
"""File a sanitized, deduplicated framework issue on the user's fork.

Operator-mode runs (/scrape, /rank, /apply, ...) must never edit the framework.
When they hit a tool failure, a broken portal, doc drift or an improvement idea,
they call this tool instead, and dev work happens later in a worktree.

Target repo:
  `git remote get-url origin` (ssh or https), overridable with the env var
  JOBSEARCH_ISSUES_REPO ("owner/repo" or a GitHub URL). The upstream template
  (MadsLorentzen/ai-job-search, plus whatever the `upstream` remote points at)
  is HARD-REFUSED at owner level: the fork is public and upstream is someone
  else's tracker. Every gh call passes `-R owner/repo` and GH_REPO, because
  without a default repo gh resolves to the upstream parent.

Privacy:
  Title and body are sanitized before anything leaves the machine or hits the
  offline queue: emails, phone numbers, URL query strings, LinkedIn handles,
  salary/currency amounts, home paths (-> ~, incl. WSL UNC paths), application
  file names, every identity string from the gitignored candidate_profile.json,
  filled-in CLAUDE.md Identity values, tracker companies/roles and
  documents/applications/ folder names (read from the main checkout, also
  when run from a linked worktree). Matching is accent-insensitive in both
  directions, treats `_`/`-` as word separators and adds squashed/CamelCase
  forms of multi-word companies. Epoch timestamps and repeated identical
  numbers are not mistaken for phones. Queued entries are re-sanitized on --flush.

Dedupe:
  The body carries `<!-- fp:<sha1> -->` (sha1 of kind|component|normalized
  title). An open issue with the same fingerprint (or exact title) gets a
  comment instead of a duplicate.

Offline:
  If gh is missing or fails, the sanitized issue is appended to
  documents/memory/pending_issues.jsonl (gitignored); `--flush` replays it.

Usage:
  python3 tools/report_issue.py --kind bug --component tools/doctor.py \\
      --title "doctor crashes when bun is missing" --body "Traceback ..."
  python3 tools/report_issue.py --kind portal-health --component scrape \\
      --title "jobnet-search broken: 0 results on sentinel query" --body-file /tmp/x.md
  python3 tools/report_issue.py --flush
  ... --dry-run   # resolve + sanitize + print, no gh calls at all
  ... --json      # machine-readable result

Exit codes:
  0  created, commented, queued, dry-run, or flush finished
  1  error (bad arguments, no resolvable origin, unreadable body file)
  2  refused (target is upstream, sanitizing left nothing to report, or
     --body-file has a cv/, cover_letters/ or documents/ path segment or is a .tex)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent


def main_checkout_root(root: Path = ROOT_DIR, runner: Optional[Callable[..., Any]] = None) -> Path:
    """The main checkout's root, also when this file runs from a linked worktree.

    Personal data (profile JSON, filled-in CLAUDE.md, tracker, applications/) is
    gitignored and lives only in the main checkout; a framework-dev worktree has
    none of it, so the sanitizer must read it from there. Uses
    `git rev-parse --path-format=absolute --git-common-dir` (git >= 2.31); any
    failure falls back to `root`.
    """
    runner = runner or subprocess.run
    try:
        proc = runner(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return root
    if proc is None or proc.returncode != 0:
        return root
    common = Path((proc.stdout or "").strip())
    if not common.is_absolute() or common.name != ".git" or not common.parent.is_dir():
        return root
    return common.parent


DATA_ROOT = main_checkout_root()
PENDING_FILE = ROOT_DIR / "documents" / "memory" / "pending_issues.jsonl"
PROFILE_JSON = DATA_ROOT / "candidate_profile.json"
CLAUDE_MD = DATA_ROOT / "CLAUDE.md"
TRACKER_CSV = DATA_ROOT / "job_search_tracker.csv"
APPLICATIONS_DIR = DATA_ROOT / "documents" / "applications"
# --body-file may not point into these (as any path segment), nor at a .tex
# file: an injected instruction could otherwise exfiltrate a CV, cover letter
# or application notes into a public issue.
PRIVATE_DIRS = ("cv", "cover_letters", "documents")
SKILL_MD = ROOT_DIR / ".claude" / "skills" / "job-application-assistant" / "SKILL.md"

ENV_REPO = "JOBSEARCH_ISSUES_REPO"
ENV_RUNTIME = "JOBSEARCH_RUNTIME"

# Owners whose trackers this tool must never write to, regardless of remotes.
UPSTREAM_DENYLIST = {"madslorentzen/ai-job-search"}

MAX_BODY_CHARS = 6000

KINDS = ("bug", "improvement", "portal-health", "drift", "doc")
KIND_LABELS = {
    "bug": "bug",
    "improvement": "enhancement",
    "portal-health": "portal-health",
    "drift": "framework",
    "doc": "documentation",
}
BASE_LABEL = "agent-reported"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

REDACTED = "[redacted]"

Runner = Callable[..., subprocess.CompletedProcess]


class Refused(Exception):
    """The request must not be filed (exit 2)."""


class ReportError(Exception):
    """Configuration or input error (exit 1)."""


# ---------------------------------------------------------------------------
# subprocess wrapper - the single mock point for tests
# ---------------------------------------------------------------------------

def _run(args: List[str], input_text: Optional[str] = None, repo: Optional[str] = None,
         timeout: int = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if repo:
        env["GH_REPO"] = repo
    env.setdefault("GH_PROMPT_DISABLED", "1")
    return subprocess.run(
        args,
        cwd=str(ROOT_DIR),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def _safe_run(args: List[str], **kwargs: Any) -> Optional[subprocess.CompletedProcess]:
    """Run, returning None when the binary is missing or the call times out."""
    try:
        return _run(args, **kwargs)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


# ---------------------------------------------------------------------------
# Target repo resolution
# ---------------------------------------------------------------------------

_SLUG_PATTERNS = [
    re.compile(r"^git@github\.com:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"),
    re.compile(r"^ssh://git@github\.com(?::\d+)?/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"),
    re.compile(r"^(?:https?|git)://(?:[^@/]+@)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"),
    re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)$"),
]


def parse_repo_slug(value: str) -> Optional[str]:
    """Return "owner/repo" from a GitHub remote URL or slug, else None."""
    value = (value or "").strip()
    for pattern in _SLUG_PATTERNS:
        match = pattern.match(value)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return None


def _remote_slug(name: str, runner: Runner) -> Optional[str]:
    try:
        proc = runner(["git", "remote", "get-url", name])
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if proc is None or proc.returncode != 0:
        return None
    return parse_repo_slug(proc.stdout.strip())


def denied_owners(runner: Runner) -> set:
    owners = {slug.split("/")[0].lower() for slug in UPSTREAM_DENYLIST}
    upstream = _remote_slug("upstream", runner)
    if upstream:
        owners.add(upstream.split("/")[0].lower())
    return owners


def check_not_upstream(repo: str, runner: Runner) -> None:
    owner = repo.split("/")[0].lower()
    if repo.lower() in UPSTREAM_DENYLIST or owner in denied_owners(runner):
        raise Refused(
            f"refusing to file on {repo}: that is the upstream template's tracker. "
            "Issues go to your fork only (set origin or JOBSEARCH_ISSUES_REPO)."
        )


def resolve_target_repo(runner: Runner = _run, environ: Optional[Dict[str, str]] = None) -> str:
    environ = os.environ if environ is None else environ
    override = (environ.get(ENV_REPO) or "").strip()
    if override:
        repo = parse_repo_slug(override)
        if not repo:
            raise ReportError(f"{ENV_REPO}={override!r} is not an owner/repo or GitHub URL")
    else:
        repo = _remote_slug("origin", runner)
        if not repo:
            raise ReportError(
                "could not resolve a GitHub repo from `git remote get-url origin`; "
                f"set {ENV_REPO}=owner/repo"
            )
    check_not_upstream(repo, runner)
    return repo


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

_PROFILE_KEY_HINT = re.compile(
    r"name|email|mail|phone|mobile|tel|linkedin|github|gitlab|website|portfolio|url|"
    r"twitter|handle|address|street|city|location|zip|postal|birth|nationality|citizenship|"
    r"salary|employer|company|education|school|university|institution|degree|thesis",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"\[[A-Z0-9_ ]+\]")
# Generic values a profile field can hold that are not identifying; redacting
# them would gut ordinary bug reports ("remote" filters, "global" config ...).
_GENERIC_TERMS = {
    "remote", "hybrid", "onsite", "on-site", "global", "worldwide", "none", "n/a",
    "candidate name", "candidate", "software engineer", "competitive local salary",
    "global / remote contractor", "none scheduled",
}
# Words that show up in application slugs / tracker roles but identify nobody.
# A company token or role equal to one of these is never added as a term.
_GENERIC_SLUG_WORDS = {
    "senior", "junior", "lead", "staff", "principal", "head", "chief", "intern", "sr", "jr",
    "engineer", "engineering", "developer", "dev", "devops", "backend", "frontend", "fullstack",
    "full", "stack", "software", "data", "scientist", "analyst", "manager", "architect",
    "consultant", "specialist", "remote", "hybrid", "python", "java", "node", "react", "web",
    "mobile", "cloud", "platform", "ml", "ai", "and", "the", "of", "for", "inc", "ltd", "llc",
    "aps", "gmbh", "sa", "srl", "corp", "co", "group", "labs", "lab", "tech", "technologies",
    "solutions", "systems", "digital", "global", "services", "consulting", "company", "io",
    "team", "product", "application", "applications", "analytics", "partners", "ventures",
    "studio", "studios", "networks", "media", "health", "bank", "capital", "holding", "holdings",
    "international", "foundation", "agency", "software",
}
_GENERIC_TERMS |= _GENERIC_SLUG_WORDS


def _walk_strings(value: Any, key: str = "", hinted: bool = False) -> Iterable[Tuple[str, str]]:
    """Yield (nearest key, string) for every string under an identity-hinted key."""
    if isinstance(value, dict):
        for k, item in value.items():
            k = str(k)
            yield from _walk_strings(item, k, hinted or bool(_PROFILE_KEY_HINT.search(k)))
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item, key, hinted)
    elif isinstance(value, str) and hinted:
        yield key, value


def _name_parts(value: str) -> List[str]:
    """"Jane Q. Doe" -> ["Jane", "Doe"]: a full name also leaks through its parts."""
    parts = []
    for part in value.split():
        part = part.strip(".,;:()\"'")
        if len(part) >= 3 and part[0].isalpha() and part.lower() not in _GENERIC_TERMS:
            parts.append(part)
    return parts


_NAME_KEYS = {"name", "full_name", "first_name", "last_name", "candidate_name", "preferred_name"}


def load_profile_strings(profile_path: Path = PROFILE_JSON) -> List[str]:
    """Identity strings from the gitignored candidate_profile.json (if present).

    Values are redacted as whole strings; only person-name fields are also split
    into words, so employer/education values like "State University" do not
    turn every "university" in a bug report into [redacted].
    """
    try:
        data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    terms: List[str] = []
    for key, value in _walk_strings(data):
        value = value.strip()
        if not value:
            continue
        terms.append(value)
        k = key.lower()
        if k in _NAME_KEYS:
            terms.extend(_name_parts(value))
        if re.search(r"phone|mobile|tel", k):
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 7:
                terms.append(digits)
        if re.match(r"https?://", value):
            handle = value.rstrip("/").rsplit("/", 1)[-1]
            if len(handle) >= 3:
                terms.append(handle)
    return terms


def load_claude_identity(claude_md: Path = CLAUDE_MD) -> List[str]:
    """Filled-in Name and Location from CLAUDE.md's Identity section.

    Only those two: the headline and status are generic career words ("Senior
    Backend Engineer", "Open to work") whose redaction would gut every report.
    Placeholders like [YOUR_NAME] are skipped.
    """
    try:
        text = Path(claude_md).read_text(encoding="utf-8")
    except OSError:
        return []
    match = re.search(r"^### Identity\s*\n(.*?)(?=^#{2,3} |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    values: List[str] = []
    for line in match.group(1).splitlines():
        item = re.match(r"^\s*-\s*\*\*(?P<key>[^*]+?):?\*\*:?\s*(?P<val>.+)$", line)
        if not item:
            continue
        key = item.group("key").strip().lower()
        val = re.sub(r"<!--.*?-->", "", item.group("val")).strip().strip('"').strip()
        if not val or _PLACEHOLDER.search(val):
            continue
        if key == "name":
            values.append(val)
            values.extend(_name_parts(val))
        elif key == "location":
            values.append(val)
            # "City, Country (constraints)" -> also redact City and Country
            pieces = re.split(r"[,()]", val)
            values.extend(piece.strip() for piece in pieces[:2] if piece.strip())
    return values


def strip_accents(text: str) -> str:
    """"José Peña" -> "Jose Pena" (NFKD, combining marks dropped)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _accent_classes() -> Dict[str, str]:
    """Base letter -> every Latin-1/Latin Extended-A letter that strips to it."""
    classes: Dict[str, str] = {}
    for code in range(0xC0, 0x180):
        ch = chr(code)
        base = strip_accents(ch).lower()
        if len(base) == 1 and base.isascii() and base.isalpha() and base != ch.lower():
            current = classes.get(base, base)
            classes[base] = current + "".join(c for c in (ch.lower(), ch.upper()) if c not in current)
    return classes


_ACCENT_CLASSES = _accent_classes()


def accent_insensitive_regex(term: str) -> str:
    """"Jose Pena" -> "J[oóòôöõø…]s[eéèêë…] P[eé…][nñ…]a": accented input matches plain terms."""
    out = []
    for ch in strip_accents(term):
        cls = _ACCENT_CLASSES.get(ch.lower())
        out.append(f"[{re.escape(cls)}]" if cls else re.escape(ch))
    return "".join(out)


def _all_generic(value: str) -> bool:
    words = [w for w in re.split(r"[\W_]+", value.lower()) if w]
    return not words or all(w in _GENERIC_SLUG_WORDS or len(w) < 3 for w in words)


def _company_variants(company: str) -> List[str]:
    """"Zentrix Analytics" -> ["ZentrixAnalytics", "zentrixanalytics"]: the forms a
    multi-word company takes in handles, domains and identifiers."""
    words = [w for w in re.split(r"[\W_]+", company) if w]
    if len(words) < 2 or _all_generic(company):
        return []
    camel = "".join(w[:1].upper() + w[1:] for w in words)
    return [camel, camel.lower()]


def _company_tokens(company: str) -> List[str]:
    """"Zentrix Analytics" -> ["Zentrix"]: a company also leaks through its parts."""
    return [t for t in re.split(r"[\W_]+", company)
            if len(t) >= 3 and t.lower() not in _GENERIC_SLUG_WORDS]


def load_tracker_terms(tracker_path: Path = TRACKER_CSV) -> List[str]:
    """Company (and non-generic role) values from the gitignored tracker CSV."""
    import csv

    try:
        lines = [l for l in Path(tracker_path).read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    except OSError:
        return []
    terms: List[str] = []
    try:
        for row in csv.DictReader(lines):
            row = {str(k or "").strip().lower(): (v or "") for k, v in row.items() if isinstance(v, str)}
            company = row.get("company", "").strip()
            if company and not _all_generic(company):
                terms.append(company)
                slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(company).lower()).strip("-")
                if slug:
                    terms.append(slug)
                terms.extend(_company_tokens(company))
                terms.extend(_company_variants(company))
            role = row.get("role", "").strip()
            if role and not _all_generic(role):
                terms.append(role)
    except csv.Error:
        pass
    return terms


def load_application_terms(applications_dir: Path = APPLICATIONS_DIR) -> List[str]:
    """Folder names under documents/applications/ (<company-slug>_<role-slug>).

    Adds the full slug, the company part, and its non-generic hyphen tokens.
    Role tokens are not added on their own: they are career words.
    """
    try:
        names = [p.name for p in Path(applications_dir).iterdir() if p.is_dir()]
    except OSError:
        return []
    terms: List[str] = []
    for name in names:
        if name.startswith("."):
            continue
        terms.append(name)
        company = name.split("_", 1)[0]
        if company and not _all_generic(company):
            terms.append(company)
            terms.append(company.replace("-", " "))
            terms.extend(_company_tokens(company))
            terms.extend(_company_variants(company))
    return terms


def _sensitive_terms(strings: Iterable[str]) -> List[str]:
    terms = set()
    for raw in strings:
        base = unicodedata.normalize("NFC", (raw or "").strip())
        for s in (base, strip_accents(base)):
            if len(s) < 3 or s.lower() in _GENERIC_TERMS or _PLACEHOLDER.fullmatch(s):
                continue
            terms.add(s)
    return sorted(terms, key=len, reverse=True)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_QUERY = re.compile(r"(https?://[^\s?#<>\"')]+)[?#][^\s<>\"')]*")
_SOCIAL = re.compile(r"((?:www\.)?(?:linkedin\.com/in|x\.com|twitter\.com)/)[\w.%-]+", re.I)
_PHONE = re.compile(
    r"(?<![\w.])\+\d[\d\s().-]{6,}\d(?!\w)"
    r"|(?<![\w.])\(?\d{2,4}\)?[\s.-]\d{3,4}[\s.-]\d{3,4}(?![\w-])"
)
# Unformatted runs ("1123456789") and space/hyphen groups ("011 15 1234-5678").
# Dots and colons are not separators, so versions, IPs, ports and times survive;
# the callback keeps anything under 9 digits and ISO dates.
_PHONE_GROUPS = re.compile(
    r"(?<![\w.:/#-])\d{10,13}(?![\w.])"
    r"|(?<![\w.:/#-])\(?\d{2,5}\)?(?:[ -]\(?\d{2,5}\)?){1,5}(?![\w:.-])"
)
_PHONE_INTL = re.compile(r"(?<![\w.])\+\d[\d\s().-]{6,}\d(?!\w)")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Unix timestamps in seconds (2017-2033) or milliseconds: log lines, not phones.
_EPOCH = re.compile(r"1[5-9]\d{8}(?:\d{3})?")


def _phone_group(match: "re.Match[str]") -> str:
    value = match.group(0)
    digits = re.sub(r"\D", "", value)
    if len(digits) < 9 or _ISO_DATE.search(value):
        return value
    if _EPOCH.fullmatch(value):
        return value
    if _repeated_groups(value):
        return value  # "12345 12345 12345": a repeated id/count list, not a phone
    return "[phone]"


def _repeated_groups(value: str) -> bool:
    groups = re.findall(r"\d+", value)
    return len(groups) >= 2 and len(set(groups)) == 1


def _phone_formatted(match: "re.Match[str]") -> str:
    return match.group(0) if _repeated_groups(match.group(0)) else "[phone]"


_NUM = r"\d(?:[\d.,]*\d)?"
_CURRENCY_CODES = r"USD|EUR|GBP|DKK|SEK|NOK|CHF|ARS|BRL|MXN|CAD|AUD|INR|JPY|PLN|kr\.?"
_MONEY = re.compile(
    rf"[$€£¥]\s?{_NUM}(?:\s?[kKmM]\b)?"
    rf"|\b(?:{_CURRENCY_CODES})\s?{_NUM}(?:\s?[kKmM]\b)?"
    rf"|\b{_NUM}\s?(?:[kKmM]\s?)?(?:{_CURRENCY_CODES})(?![A-Za-z])"
)
_SALARY_CONTEXT = re.compile(
    rf"\b(salary|compensation|pay|wage|løn|sueldo|salario)(\s*[:=]?\s*){_NUM}(?:\s?[kK]\b)?", re.I
)
# "4500usd", "4.500 pesos", "4500 dólares", "4500 per month", "4500 por mes"
_MONEY_WORDS = re.compile(
    rf"(?<![\w.]){_NUM}\s?(?:[kK]\s?)?(?:usd|eur|ars|d[oó]lares|dollars|pesos|euros)(?![^\W\d_])"
    rf"|(?<![\w.]){_NUM}(?=\s?(?:[kK]\s?)?(?:/\s?(?:month|mo|mes)\b|(?:per|a|al|por)\s+(?:month|mes)\b))",
    re.I,
)
_APP_FILE = re.compile(r"(?<![A-Za-z0-9])(main|cover)_[^\s/\\\"'`]+?\.(tex|pdf|log|aux)(?![\w.])")
_ATS_FILE = re.compile(
    r"(?<![^\s/\\\"'`(\[=:,;<>])[^\s/\\\"'`=:,;<>()\[\]]+?_(CV|CoverLetter)[^\s/\\\"'`=:,;<>()\[\]]*?\.pdf(?![\w.])"
)
_HOME_PATHS = [
    re.compile(r"[\\/]{2}wsl(?:\.localhost|\$)[\\/]+[^\\/\s]+[\\/]+home[\\/]+[^\\/\s\"'`]+", re.I),
    re.compile(r"/mnt/[a-zA-Z]/Users/[^/\s\"'`]+", re.I),
    re.compile(r"\b[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'`]+", re.I),
    re.compile(r"(?<![\w.\-])/home/[^/\s\"'`]+"),
    re.compile(r"(?<![\w.\-])/Users/[^/\s\"'`]+"),
]


class Sanitizer:
    def __init__(self, extra_terms: Iterable[str] = ()) -> None:
        self.terms = _sensitive_terms(extra_terms)
        # `_` and `-` count as separators, so "acme" is caught inside acme_dev.
        # Each term matches its accented and plain spellings alike, so a plain
        # "Jose Pena" still redacts "José Peña" in the text.
        sources: List[str] = []
        for term in self.terms:
            source = accent_insensitive_regex(term)
            if source.lower() not in {s.lower() for s in sources}:
                sources.append(source)
        self._term_patterns = [
            re.compile(r"(?<![^\W_])" + src + r"(?![^\W_])", re.IGNORECASE) for src in sources
        ]

    @classmethod
    def from_repo(cls, profile_path: Optional[Path] = None, claude_md: Optional[Path] = None,
                  tracker_path: Optional[Path] = None,
                  applications_dir: Optional[Path] = None) -> "Sanitizer":
        # Defaults resolve at call time (not def time) so tests can redirect them.
        return cls(
            load_profile_strings(profile_path or PROFILE_JSON)
            + load_claude_identity(claude_md or CLAUDE_MD)
            + load_tracker_terms(tracker_path or TRACKER_CSV)
            + load_application_terms(applications_dir or APPLICATIONS_DIR)
        )

    def clean(self, text: str) -> str:
        if not text:
            return ""
        out = unicodedata.normalize("NFC", text)
        # Application file names carry company/role and the candidate's name.
        out = _APP_FILE.sub(lambda m: f"{m.group(1)}_<company>_<role>.{m.group(2)}", out)
        out = _ATS_FILE.sub(lambda m: f"<CandidateName>_{m.group(1)}.pdf", out)
        # Paths first, so a username inside a path becomes ~ rather than [redacted].
        for pattern in _HOME_PATHS:
            out = pattern.sub("~", out)
        # Structured identifiers before profile terms, so a name inside an
        # email or handle cannot break the pattern and leak the remainder.
        out = _EMAIL.sub("[email]", out)
        out = _URL_QUERY.sub(r"\1?[query]", out)
        out = _SOCIAL.sub(r"\1[handle]", out)
        for pattern in self._term_patterns:
            out = pattern.sub(REDACTED, out)
        out = _SALARY_CONTEXT.sub(r"\1\2[amount]", out)
        out = _MONEY.sub("[amount]", out)
        out = _MONEY_WORDS.sub("[amount]", out)
        out = _PHONE_INTL.sub("[phone]", out)
        out = _PHONE_GROUPS.sub(_phone_group, out)
        out = _PHONE.sub(_phone_formatted, out)
        return out


def has_substance(text: str) -> bool:
    stripped = re.sub(r"\[(?:redacted|email|phone|amount|query|handle)\]", "", text or "")
    return bool(re.search(r"\w", stripped))


def truncate(text: str, limit: int = MAX_BODY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n…[truncated]"


# ---------------------------------------------------------------------------
# Issue assembly
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    # Accents are stripped rather than letters dropped, so "Búsqueda" and
    # "busqueda" share a fingerprint; ASCII titles normalize exactly as before.
    t = strip_accents(unicodedata.normalize("NFC", title)).lower()
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^\w#]+|_", " ", t)
    return " ".join(t.split())


def fingerprint(kind: str, component: str, title: str) -> str:
    raw = f"{kind}|{(component or '').strip().lower()}|{normalize_title(title)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def detect_runtime(environ: Optional[Dict[str, str]] = None) -> str:
    environ = os.environ if environ is None else environ
    override = (environ.get(ENV_RUNTIME) or "").strip()
    if override:
        return override
    if environ.get("CLAUDECODE") or environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    return "unknown"


def framework_version(skill_md: Path = SKILL_MD) -> str:
    try:
        text = Path(skill_md).read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"^framework_version:\s*['\"]?([\w.\-]+)", text, re.MULTILINE)
    return match.group(1) if match else "unknown"


def tool_versions(runner: Runner, offline: bool = False) -> Dict[str, str]:
    versions = {"python": platform.python_version(), "os": platform.system().lower()}
    if offline:
        return versions
    proc = None
    try:
        proc = runner(["gh", "--version"])
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0 and proc.stdout:
        m = re.search(r"(\d+\.\d+\.\d+)", proc.stdout)
        if m:
            versions["gh"] = m.group(1)
    try:
        proc = runner(["git", "rev-parse", "--short", "HEAD"])
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        versions["commit"] = proc.stdout.strip()
    return versions


FOOTER_START = "\n\n---\n_Filed automatically by"
SEEN_AGAIN_EXCERPT = 300


def build_footer(kind: str, component: str, fp: str, versions: Dict[str, str],
                 environ: Optional[Dict[str, str]] = None) -> str:
    vers = ", ".join(f"{k} {v}" for k, v in versions.items())
    return (
        "\n\n---\n"
        f"_Filed automatically by `tools/report_issue.py` (kind: `{kind}`"
        f"{f', component: `{component}`' if component else ''})._\n"
        f"runtime: {detect_runtime(environ)} · framework_version: {framework_version()} · {vers}\n"
        f"<!-- fp:{fp} -->\n"
    )


def build_labels(kind: str, extra: Optional[str]) -> List[str]:
    labels = [BASE_LABEL, KIND_LABELS[kind]]
    for label in (extra or "").split(","):
        label = label.strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def sanitize_labels(labels: List[str], sanitizer: Sanitizer) -> List[str]:
    """Drop any label the sanitizer would change: labels are public metadata too."""
    return [l for l in labels if sanitizer.clean(l) == l]


def prepare_issue(kind: str, title: str, body: str, component: str, labels: Optional[str],
                  sanitizer: Sanitizer, runner: Runner, offline: bool = False,
                  environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    clean_title = " ".join(sanitizer.clean(title).split())[:200]
    clean_component = sanitizer.clean(component or "").strip()
    clean_body = truncate(sanitizer.clean(body).strip())
    if not has_substance(clean_title):
        raise Refused("title is empty after sanitizing")
    if not has_substance(clean_body):
        raise Refused("body is empty after sanitizing - nothing reportable left")
    fp = fingerprint(kind, clean_component, clean_title)
    footer = build_footer(kind, clean_component, fp, tool_versions(runner, offline), environ)
    return {
        "kind": kind,
        "component": clean_component,
        "title": clean_title,
        "body": clean_body + footer,
        "labels": sanitize_labels(build_labels(kind, labels), sanitizer),
        "fingerprint": fp,
    }


# ---------------------------------------------------------------------------
# gh interactions
# ---------------------------------------------------------------------------

class GhFailure(Exception):
    """gh unavailable or failed for a non-label reason (-> offline queue)."""


def _gh(args: List[str], repo: str, runner: Runner, input_text: Optional[str] = None
        ) -> subprocess.CompletedProcess:
    try:
        proc = runner(["gh", *args], input_text=input_text, repo=repo)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise GhFailure(f"gh unavailable: {exc}") from exc
    if proc is None:
        raise GhFailure("gh unavailable")
    return proc


def find_existing(issue: Dict[str, Any], repo: str, runner: Runner) -> Optional[Dict[str, Any]]:
    fp_marker = f"fp:{issue['fingerprint']}"
    searches = [issue["fingerprint"] + " in:body", f'"{issue["title"].replace(chr(34), "")}" in:title']
    for query in searches:
        proc = _gh(
            ["issue", "list", "-R", repo, "--state", "open", "--search", query,
             "--json", "number,title,body,url", "--limit", "100"],
            repo, runner,
        )
        if proc.returncode != 0:
            raise GhFailure(f"gh issue list failed: {proc.stderr.strip()[:300]}")
        try:
            rows = json.loads(proc.stdout or "[]")
        except ValueError:
            rows = []
        for row in rows:
            if fp_marker in (row.get("body") or "") or (row.get("title") or "") == issue["title"]:
                return row
    return None


_LABEL_ERR = re.compile(r"label", re.I)
_LABEL_NAME = re.compile(r"""['"]([^'"]+)['"]\s+not found""", re.I)


def create_issue(issue: Dict[str, Any], repo: str, runner: Runner) -> Dict[str, Any]:
    labels = list(issue["labels"])
    for _attempt in range(len(labels) + 2):
        args = ["issue", "create", "-R", repo, "--title", issue["title"], "--body-file", "-"]
        for label in labels:
            args += ["--label", label]
        proc = _gh(args, repo, runner, input_text=issue["body"])
        if proc.returncode == 0:
            url = (proc.stdout or "").strip().splitlines()[-1:] or [""]
            number = None
            m = re.search(r"/issues/(\d+)", url[0])
            if m:
                number = int(m.group(1))
            return {"action": "created", "url": url[0], "number": number, "labels": labels}
        err = proc.stderr or ""
        if labels and _LABEL_ERR.search(err):
            missing = [n for n in _LABEL_NAME.findall(err) if n in labels]
            labels = [l for l in labels if l not in missing] if missing else []
            continue
        if "disabled issues" in err.lower() or "has disabled issues" in err.lower():
            raise GhFailure(
                f"issues are disabled on {repo}; run `gh repo edit {repo} --enable-issues`"
            )
        raise GhFailure(f"gh issue create failed: {err.strip()[:300]}")
    raise GhFailure("gh issue create kept failing on labels")


def comment_issue(issue: Dict[str, Any], existing: Dict[str, Any], repo: str,
                  runner: Runner) -> Dict[str, Any]:
    number = existing.get("number")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    excerpt = issue["body"].split(FOOTER_START, 1)[0].strip()
    if len(excerpt) > SEEN_AGAIN_EXCERPT:
        excerpt = excerpt[:SEEN_AGAIN_EXCERPT].rstrip() + "…"
    body = (f"Seen again at {stamp}.\n\n> " + excerpt.replace("\n", "\n> ")
            + f"\n\n<!-- fp:{issue['fingerprint']} -->\n")
    proc = _gh(["issue", "comment", str(number), "-R", repo, "--body-file", "-"],
               repo, runner, input_text=body)
    if proc.returncode != 0:
        raise GhFailure(f"gh issue comment failed: {proc.stderr.strip()[:300]}")
    return {"action": "commented", "number": number, "url": existing.get("url") or (proc.stdout or "").strip()}


def submit(issue: Dict[str, Any], repo: str, runner: Runner) -> Dict[str, Any]:
    existing = find_existing(issue, repo, runner)
    if existing:
        return comment_issue(issue, existing, repo, runner)
    return create_issue(issue, repo, runner)


# ---------------------------------------------------------------------------
# Offline queue
# ---------------------------------------------------------------------------

def enqueue(issue: Dict[str, Any], repo: str, reason: str, pending: Path = PENDING_FILE) -> None:
    pending = Path(pending)
    pending.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(issue)
    entry.update({
        "repo": repo,
        "queued_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reason": reason[:300],
    })
    with pending.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_queue(pending: Path = PENDING_FILE) -> List[Dict[str, Any]]:
    pending = Path(pending)
    if not pending.exists():
        return []
    entries = []
    for line in pending.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def write_queue(entries: List[Dict[str, Any]], pending: Path = PENDING_FILE) -> None:
    pending = Path(pending)
    if not entries:
        if pending.exists():
            pending.write_text("", encoding="utf-8")
        return
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8"
    )


_FP_MARKER = re.compile(r"<!-- fp:[0-9a-fA-F]+ -->")


def resanitize_entry(entry: Dict[str, Any], sanitizer: Sanitizer) -> Dict[str, Any]:
    """Re-clean a queued entry: terms may have been added since it was queued."""
    out = dict(entry)
    kind = entry.get("kind") if entry.get("kind") in KINDS else "bug"
    out["title"] = " ".join(sanitizer.clean(entry.get("title") or "").split())[:200]
    out["component"] = sanitizer.clean(entry.get("component") or "").strip()
    if not has_substance(out["title"]):
        raise Refused("queued title is empty after re-sanitizing")
    body = sanitizer.clean(entry.get("body") or "")
    if not has_substance(_FP_MARKER.sub("", body.split(FOOTER_START, 1)[0])):
        raise Refused("queued body is empty after re-sanitizing")
    fp = fingerprint(kind, out["component"], out["title"])
    marker = f"<!-- fp:{fp} -->"
    body = _FP_MARKER.sub(marker, body) if _FP_MARKER.search(body) else body + "\n" + marker + "\n"
    out["body"] = body
    out["fingerprint"] = fp
    out["labels"] = sanitize_labels([str(l) for l in entry.get("labels") or []], sanitizer)
    return out


def flush(runner: Runner = _run, pending: Path = PENDING_FILE,
          environ: Optional[Dict[str, str]] = None,
          sanitizer: Optional[Sanitizer] = None) -> Dict[str, Any]:
    entries = read_queue(pending)
    repo = resolve_target_repo(runner, environ)
    sanitizer = sanitizer or Sanitizer.from_repo()
    remaining, results = [], []
    for entry in entries:
        target = entry.get("repo") or repo
        try:
            check_not_upstream(target, runner)
        except Refused as exc:
            results.append({"action": "refused", "title": entry.get("title"), "reason": str(exc)})
            continue  # dropped: never replay toward upstream
        try:
            entry = resanitize_entry(entry, sanitizer)
        except Refused as exc:
            results.append({"action": "refused", "title": None, "reason": str(exc)})
            continue  # dropped: nothing safe left to send
        try:
            res = submit(entry, target, runner)
            res["title"] = entry.get("title")
            results.append(res)
        except GhFailure as exc:
            remaining.append(entry)
            results.append({"action": "queued", "title": entry.get("title"), "reason": str(exc)})
    write_queue(remaining, pending)
    return {"action": "flushed", "repo": repo, "processed": len(entries),
            "remaining": len(remaining), "results": results}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _relative_to(resolved: Path, root: Path) -> Optional[Path]:
    try:
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return None
    try:
        return resolved.relative_to(root_resolved)
    except ValueError:
        # Case-insensitive mounts (/mnt/c, Windows): compare casefolded.
        r, b = str(resolved).casefold(), str(root_resolved).casefold().rstrip("/\\") + os.sep
        if not r.startswith(b):
            return None
        return Path(str(resolved)[len(b):])


def check_body_file_allowed(path: Path, root: Optional[Path] = None,
                            data_root: Optional[Path] = None) -> None:
    """Refuse bodies read from CVs, cover letters, documents/ or .tex files (exfil guard).

    Inside the repo (this checkout or the main checkout) any segment of the
    repo-relative path counts; outside it, any segment of the path as given and
    as resolved. The repo's own location is not judged: it may well sit under a
    `Documents/CV/` folder.
    """
    roots = [Path(root or ROOT_DIR), Path(data_root or (DATA_ROOT if root is None else root))]
    given = Path(path).expanduser()
    if given.suffix.casefold() == ".tex":
        raise Refused("refusing --body-file pointing at a .tex file: CV and cover letter "
                      "sources hold personal data and must never be pasted into a public issue")
    try:
        resolved = given.resolve()
    except (OSError, RuntimeError):
        resolved = given
    if resolved.suffix.casefold() == ".tex":
        raise Refused("refusing --body-file pointing at a .tex file (symlink target)")
    rel = next((r for r in (_relative_to(resolved, base) for base in roots) if r is not None), None)
    if rel is not None:
        candidates = [rel.parts]
    else:
        candidates = [given.parts, resolved.parts]
    for parts in candidates:
        for part in parts:
            if part.casefold() in PRIVATE_DIRS:
                raise Refused(
                    f"refusing --body-file under {part}/: CVs, cover letters and documents/ "
                    "hold personal data and must never be pasted into a public issue"
                )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="File a sanitized, deduplicated framework issue on the user's fork (never upstream)."
    )
    p.add_argument("--kind", choices=KINDS, help="Issue kind (maps to a label)")
    p.add_argument("--title", help="Short issue title")
    body = p.add_mutually_exclusive_group()
    body.add_argument("--body", help="Issue body text")
    body.add_argument("--body-file", help="Read the body from a file ('-' = stdin)")
    p.add_argument("--labels", default="", help="Extra comma-separated labels")
    p.add_argument("--component", default="", help="Affected component, e.g. scrape, apply, tools/doctor.py")
    p.add_argument("--dry-run", action="store_true", help="Resolve and sanitize only; make no gh calls")
    p.add_argument("--flush", action="store_true", help="Replay documents/memory/pending_issues.jsonl")
    p.add_argument("--json", action="store_true", help="Print the result as JSON")
    return p


def _emit(result: Dict[str, Any], as_json: bool, stream=None) -> None:
    stream = stream or sys.stdout
    if as_json:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return
    action = result.get("action")
    if action == "dry-run":
        stream.write(f"[dry-run] target: {result['repo']}\n")
        stream.write(f"[dry-run] title: {result['title']}\n")
        stream.write(f"[dry-run] labels: {', '.join(result['labels'])}\n")
        stream.write(f"[dry-run] fingerprint: {result['fingerprint']}\n")
        stream.write("[dry-run] body:\n" + result["body"] + "\n")
    elif action == "flushed":
        stream.write(
            f"flush: {result['processed']} queued, {result['remaining']} still pending "
            f"(target {result['repo']})\n"
        )
        for r in result["results"]:
            stream.write(f"  - {r['action']}: {r.get('title')} {r.get('url') or r.get('reason') or ''}\n")
    elif action in ("created", "commented"):
        stream.write(f"{action} issue #{result.get('number')} on {result['repo']}: {result.get('url', '')}\n")
    elif action == "queued":
        stream.write(f"queued offline ({result.get('reason')}); replay with --flush\n")
    else:
        stream.write(f"{action}: {result.get('reason', '')}\n")


def run(argv: Optional[List[str]] = None, runner: Runner = _run,
        sanitizer: Optional[Sanitizer] = None, pending: Path = PENDING_FILE,
        environ: Optional[Dict[str, str]] = None, stream=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.flush:
            result = flush(runner, pending, environ, sanitizer)
            _emit(result, args.json, stream)
            return EXIT_OK

        if not args.kind or not args.title or (args.body is None and args.body_file is None):
            raise ReportError("--kind, --title and one of --body/--body-file are required (or --flush)")

        if args.body_file is not None:
            if args.body_file != "-":
                check_body_file_allowed(Path(args.body_file))
            try:
                body = sys.stdin.read() if args.body_file == "-" else Path(args.body_file).read_text(encoding="utf-8")
            except OSError as exc:
                raise ReportError(f"cannot read --body-file: {exc}") from exc
        else:
            body = args.body

        repo = resolve_target_repo(runner, environ)
        sanitizer = sanitizer or Sanitizer.from_repo()
        issue = prepare_issue(args.kind, args.title, body, args.component, args.labels,
                              sanitizer, runner, offline=args.dry_run, environ=environ)

        if args.dry_run:
            result = {"action": "dry-run", "repo": repo, **issue}
            _emit(result, args.json, stream)
            return EXIT_OK

        try:
            res = submit(issue, repo, runner)
        except GhFailure as exc:
            enqueue(issue, repo, str(exc), pending)
            res = {"action": "queued", "reason": str(exc)}
        result = {"repo": repo, "fingerprint": issue["fingerprint"], "title": issue["title"],
                  "labels": issue["labels"], **res}
        _emit(result, args.json, stream)
        return EXIT_OK
    except Refused as exc:
        _emit({"action": "refused", "reason": str(exc)}, args.json, stream)
        return EXIT_REFUSED
    except ReportError as exc:
        _emit({"action": "error", "reason": str(exc)}, args.json, stream)
        return EXIT_ERROR


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
