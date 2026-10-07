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
  salary/currency amounts, home paths (-> ~), every identity string from the
  gitignored candidate_profile.json, and filled-in CLAUDE.md Identity values.

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
  2  refused (target is upstream, or sanitizing left nothing to report)
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
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
PENDING_FILE = ROOT_DIR / "documents" / "memory" / "pending_issues.jsonl"
PROFILE_JSON = ROOT_DIR / "candidate_profile.json"
CLAUDE_MD = ROOT_DIR / "CLAUDE.md"
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


def _walk_strings(value: Any, key_hint: bool = False) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, key_hint or bool(_PROFILE_KEY_HINT.search(str(key))))
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item, key_hint)
    elif isinstance(value, str) and key_hint:
        yield value


def load_profile_strings(profile_path: Path = PROFILE_JSON) -> List[str]:
    """Identity strings from the gitignored candidate_profile.json (if present)."""
    try:
        data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(_walk_strings(data))


def load_claude_identity(claude_md: Path = CLAUDE_MD) -> List[str]:
    """Filled-in values from CLAUDE.md's Identity section (placeholders skipped)."""
    try:
        text = Path(claude_md).read_text(encoding="utf-8")
    except OSError:
        return []
    match = re.search(r"^### Identity\s*\n(.*?)(?=^#{2,3} |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    values = []
    for line in match.group(1).splitlines():
        item = re.match(r"^\s*-\s*\*\*(?P<key>[^*]+?):?\*\*:?\s*(?P<val>.+)$", line)
        if not item:
            continue
        if item.group("key").strip().lower().startswith(("languages", "cv language")):
            continue
        val = re.sub(r"<!--.*?-->", "", item.group("val")).strip().strip('"').strip()
        if not val or _PLACEHOLDER.search(val):
            continue
        values.append(val)
        # "City, Country (constraints)" -> also redact the pieces
        values.extend(p.strip() for p in re.split(r"[,()]", val) if p.strip())
    return values


def _sensitive_terms(strings: Iterable[str]) -> List[str]:
    terms = set()
    for raw in strings:
        s = (raw or "").strip()
        if len(s) < 3 or s.lower() in _GENERIC_TERMS or _PLACEHOLDER.fullmatch(s):
            continue
        terms.add(s)
        # A full name also leaks through its parts ("Jane Doe" -> "Jane", "Doe").
        if " " in s and len(s) <= 60 and "@" not in s and "/" not in s:
            for part in s.split():
                part = part.strip(".,;:()\"'")
                if len(part) >= 3 and part[0].isalpha() and part.lower() not in _GENERIC_TERMS:
                    terms.add(part)
    return sorted(terms, key=len, reverse=True)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_QUERY = re.compile(r"(https?://[^\s?#<>\"')]+)[?#][^\s<>\"')]*")
_SOCIAL = re.compile(r"((?:www\.)?(?:linkedin\.com/in|github\.com|x\.com|twitter\.com)/)[\w.%-]+", re.I)
_PHONE = re.compile(
    r"(?<![\w.])\+\d[\d\s().-]{6,}\d(?!\w)"
    r"|(?<![\w.])\(?\d{2,4}\)?[\s.-]\d{3,4}[\s.-]\d{3,4}(?![\w-])"
)
_NUM = r"\d(?:[\d.,]*\d)?"
_CURRENCY_CODES = r"USD|EUR|GBP|DKK|SEK|NOK|CHF|ARS|BRL|MXN|CAD|AUD|INR|JPY|PLN|kr\.?"
_MONEY = re.compile(
    rf"[$€£¥]\s?{_NUM}(?:\s?[kKmM]\b)?"
    rf"|\b(?:{_CURRENCY_CODES})\s?{_NUM}(?:\s?[kKmM]\b)?"
    rf"|\b{_NUM}\s?(?:[kKmM]\s?)?(?:{_CURRENCY_CODES})(?![A-Za-z])"
)
_SALARY_CONTEXT = re.compile(
    rf"\b(salary|compensation|pay|wage|løn)(\s*[:=]?\s*){_NUM}(?:\s?[kK]\b)?", re.I
)
_HOME_PATHS = [
    re.compile(r"/mnt/[a-zA-Z]/Users/[^/\s\"'`]+", re.I),
    re.compile(r"\b[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'`]+", re.I),
    re.compile(r"(?<![\w.\-])/home/[^/\s\"'`]+"),
    re.compile(r"(?<![\w.\-])/Users/[^/\s\"'`]+"),
]


class Sanitizer:
    def __init__(self, extra_terms: Iterable[str] = ()) -> None:
        self.terms = _sensitive_terms(extra_terms)
        self._term_patterns = [
            re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.IGNORECASE) for t in self.terms
        ]

    @classmethod
    def from_repo(cls, profile_path: Path = PROFILE_JSON, claude_md: Path = CLAUDE_MD) -> "Sanitizer":
        return cls(load_profile_strings(profile_path) + load_claude_identity(claude_md))

    def clean(self, text: str) -> str:
        if not text:
            return ""
        out = text
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
        out = _PHONE.sub("[phone]", out)
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
    t = title.lower()
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^a-z#]+", " ", t)
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
        "labels": build_labels(kind, labels),
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
    searches = [issue["fingerprint"] + " in:body", f'"{issue["title"]}" in:title']
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
    body = "Seen again.\n\n" + issue["body"]
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


def flush(runner: Runner = _run, pending: Path = PENDING_FILE,
          environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    entries = read_queue(pending)
    repo = resolve_target_repo(runner, environ)
    remaining, results = [], []
    for entry in entries:
        target = entry.get("repo") or repo
        try:
            check_not_upstream(target, runner)
        except Refused as exc:
            results.append({"action": "refused", "title": entry.get("title"), "reason": str(exc)})
            continue  # dropped: never replay toward upstream
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
            result = flush(runner, pending, environ)
            _emit(result, args.json, stream)
            return EXIT_OK

        if not args.kind or not args.title or (args.body is None and args.body_file is None):
            raise ReportError("--kind, --title and one of --body/--body-file are required (or --flush)")

        if args.body_file is not None:
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
