#!/usr/bin/env python3
"""Stop hook: do not let an /apply run end while its quality gate fails.

Registered for Claude Code (.claude/settings.json, `Stop`) and Google
Antigravity (.agents/hooks.json, `Stop`, with `--antigravity`; Antigravity runs
it from .agents/, so every path here resolves from this file, never the cwd).

When the agent tries to stop:
  1. No /apply marker (.agents/state/apply.json, written by
     tools/apply_state.py) -> allow.
  2. The stop comes from another project (payload `cwd` outside this repo) or
     another session (payload session id differs from the one stored at the
     first block) -> allow.
  3. Marker present but this run has not written the slug's documents yet
     (cv/main_<slug>.*, cover_letters/cover_<slug>.*, or PDFs under
     documents/applications/<slug>/, counted only when modified at or after the
     marker's started_at, so a redraft's old files do not count) -> allow: the
     run is still at fit evaluation, or the user declined.
  4. Otherwise run `tools/gate_application.py <slug>`:
       exit 0 -> allow and clear the marker;
       exit 2 (pending human review) -> allow, the agent must ask the user;
       exit 1 -> block with the gate's violations as the reason.

Loop guards: at most MAX_BLOCKS blocks per /apply run (counter in the marker,
then allow with a stderr warning and clear the marker); in Claude Code, when
`stop_hook_active` is true (the turn is already continuing because a Stop hook
blocked) and this hook has blocked at least once, allow. A marker older than
STALE_HOURS is ignored and cleared. Any internal error fails open (allow) with
a warning on stderr.

Output: Claude Code blocks with {"decision": "block", "reason": ...};
Antigravity with {"decision": "continue", "reason": ...}. Allowing prints {}.

Stdlib only.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

MAX_BLOCKS = 3
STALE_HOURS = 12
GATE_TIMEOUT = 100
MAX_REASON_CHARS = 3000
# File mtimes come from the kernel's coarse clock (milliseconds behind time.time())
# and FAT/SMB mounts round to 2 s, so a document written right after `start` can
# carry an mtime slightly before started_at. Old files from a previous run are
# minutes older than that.
MTIME_SLACK_SECONDS = 2.0
ENV_ROOT = "APPLY_GATE_ROOT"  # test override for the repository root


def repo_root() -> Path:
    override = os.environ.get(ENV_ROOT)
    return Path(override) if override else Path(__file__).resolve().parent.parent.parent


def warn(message: str) -> None:
    print(f"apply_gate_stop: {message}", file=sys.stderr)


def load_state(root: Path) -> Optional[dict]:
    path = root / ".agents" / "state" / "apply.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        warn(f"unreadable /apply marker, ignoring it: {exc!r}")
        return None
    slug = str(data.get("slug", "")) if isinstance(data, dict) else ""
    if not slug or slug in (".", "..") or any(c in slug for c in "/\\\0"):
        return None
    return data


def save_state(root: Path, data: dict) -> None:
    path = root / ".agents" / "state" / "apply.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"apply.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def clear_state(root: Path) -> None:
    try:
        (root / ".agents" / "state" / "apply.json").unlink()
    except FileNotFoundError:
        pass


def started_at(data: dict) -> Optional[datetime.datetime]:
    try:
        started = datetime.datetime.fromisoformat(str(data.get("started_at")))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=datetime.timezone.utc)
    return started


def is_stale(data: dict, now: Optional[datetime.datetime] = None) -> bool:
    started = started_at(data)
    if started is None:
        return False
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now - started > datetime.timedelta(hours=STALE_HOURS)


def documents_exist(root: Path, slug: str, since: Optional[float] = None) -> bool:
    """True once /apply has written the slug's CV or cover letter (source or PDF).

    With `since` (a POSIX timestamp, the marker's started_at), only files modified
    at or after it (less MTIME_SLACK_SECONDS) count: on a redraft the previous run's files already exist, and
    counting them would run the gate at the Step 1 consent STOP.
    """
    esc = glob.escape(slug)
    app = root / "documents" / "applications" / slug
    candidates = [
        *(root / "cv").glob(f"main_{esc}.*"),
        *(root / "cover_letters").glob(f"cover_{esc}.*"),
        *(root / "cover_letters").glob(f"Cover_{esc}.*"),
        *(app.glob("*.pdf") if app.is_dir() else ()),
    ]
    for path in candidates:
        if since is None:
            return True
        try:
            if path.stat().st_mtime >= since - MTIME_SLACK_SECONDS:
                return True
        except OSError:
            continue
    return False


def foreign_cwd(payload: dict, root: Path) -> bool:
    """True when the payload names a working directory outside this repository."""
    cwd = payload.get("cwd")
    if not cwd or not isinstance(cwd, str):
        return False
    try:
        Path(cwd).resolve().relative_to(root.resolve())
        return False
    except ValueError:
        return True


def session_of(payload: dict) -> Optional[str]:
    value = payload.get("session_id") or payload.get("conversationId")
    return str(value) if value else None


def run_gate(root: Path, slug: str) -> subprocess.CompletedProcess:
    script = root / "tools" / "gate_application.py"
    if not script.is_file():
        # python exits 2 on a missing script, which would read as "pending review".
        raise FileNotFoundError(f"{script} not found")
    return subprocess.run(
        [sys.executable, str(script), slug],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GATE_TIMEOUT,
    )


def gate_excerpt(output: str) -> str:
    """The gate's violation and verdict lines, falling back to its tail."""
    lines = [l for l in output.splitlines() if l.strip()]
    keep = [l for l in lines if l.lstrip().startswith(("- ", "[FAIL]", "[X]", "GATE VERDICT"))]
    text = "\n".join(keep or lines[-15:])
    return text[:MAX_REASON_CHARS]


def block_reason(slug: str, output: str, blocks: int) -> str:
    return (
        f"/apply quality gate FAILED for '{slug}' (stop blocked {blocks}/{MAX_BLOCKS}). "
        f"`python3 tools/gate_application.py {slug}` reported:\n{gate_excerpt(output)}\n\n"
        "Fix the violations, then re-run that exact command and quote its exit code and "
        "verdict. Typical fixes: copy the compiled PDFs to the ATS names inside "
        f"documents/applications/{slug}/ (<CandidateName>_CV.pdf, "
        "<CandidateName>_CoverLetter.pdf), write job_posting.md there, recompile until the "
        "CV is exactly 2 pages and the cover letter exactly 1. If you cannot fix it, or "
        "you are waiting on the user's decision, say so explicitly and ask the user. Run "
        f"`python3 tools/apply_state.py done {slug}` only after the gate passes."
    )


def decide(payload: dict, antigravity: bool, root: Path,
           gate: Callable[[Path, str], subprocess.CompletedProcess] = run_gate) -> Optional[str]:
    """Return a block reason, or None to allow the stop."""
    if antigravity:
        reason = payload.get("terminationReason") or "model_stop"
        if reason != "model_stop":
            return None  # errors / max steps: never trap the agent in a loop
    if foreign_cwd(payload, root):
        return None  # a stop in another project: this repo's marker is not its concern
    state = load_state(root)
    if not state:
        return None
    slug = str(state["slug"])
    session = session_of(payload)
    owner = state.get("session_id")
    if owner and session and owner != session:
        return None  # another session's stop; the /apply run belongs to `owner`
    if is_stale(state):
        warn(f"ignoring stale /apply marker for {slug} (older than {STALE_HOURS}h); cleared")
        clear_state(root)
        return None
    started = started_at(state)
    if not documents_exist(root, slug, started.timestamp() if started else None):
        return None
    blocks = int(state.get("blocks") or 0)
    if blocks >= MAX_BLOCKS:
        warn(f"gate for {slug} still failing after {blocks} blocked stops; allowing the stop "
             "and clearing the /apply marker - run tools/gate_application.py yourself")
        clear_state(root)
        return None
    if not antigravity and payload.get("stop_hook_active") and blocks >= 1:
        warn(f"stop_hook_active: not blocking again for {slug}; the gate may still be failing")
        return None

    result = gate(root, slug)
    if result.returncode == 0:
        clear_state(root)
        return None
    if result.returncode == 2:
        return None  # mechanical checks passed; human review pending - the agent asks the user
    state["blocks"] = blocks + 1
    if session and not owner:
        state["session_id"] = session
    save_state(root, state)
    return block_reason(slug, (result.stdout or "") + (result.stderr or ""), blocks + 1)


def main(argv: list) -> int:
    antigravity = "--antigravity" in argv
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        if not antigravity and "executionNum" in payload and "hook_event_name" not in payload:
            antigravity = True
        reason = decide(payload, antigravity, repo_root())
    except Exception as exc:  # fail open: a broken hook must never wedge the agent
        warn(f"internal error, allowing the stop: {exc!r}")
        reason = None
    if reason is None:
        print("{}")
    elif antigravity:
        print(json.dumps({"decision": "continue", "reason": reason}))
    else:
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
