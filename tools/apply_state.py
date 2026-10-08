#!/usr/bin/env python3
"""Mark an /apply run as in progress (or finished) for the Stop-hook quality gate.

/apply calls `start <slug>` once company and role are known and `done <slug>`
after the pre-submit gate passed. While the marker exists, the Stop hook
(.claude/hooks/apply_gate_stop.py, registered for Claude Code and Antigravity)
runs `tools/gate_application.py <slug>` whenever the agent tries to end its turn
and the slug's documents exist, and sends the agent back to fix a failing gate.

The marker is gitignored local state: .agents/state/apply.json
  {"slug": "<company>_<role>", "started_at": "<ISO-8601 UTC, microseconds>", "blocks": 0,
   "cwd": "<directory start ran in>", "session_id": "<owning session, when known>"}

Session ownership: only the owning session's stops are held. In Claude Code the
Bash tool exports CLAUDE_CODE_SESSION_ID, the same id the Stop hook receives as
`session_id`, so `start` records it directly. When it is unavailable (Antigravity
exports no equivalent), the hook claims the
marker for the first stopping session whose transcript shows this `start`
command (see .claude/hooks/apply_gate_stop.py). `cwd` lets the hook tell a stop
in the main checkout from one in a linked worktree under .claude/worktrees/.

Usage:
  python3 tools/apply_state.py start <slug>
  python3 tools/apply_state.py done <slug>
  python3 tools/apply_state.py status

Stdlib only. Exit 0 on success, 1 on a usage error.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
STATE_REL = Path(".agents") / "state" / "apply.json"


def state_path(root: Optional[Path] = None) -> Path:
    return Path(root or ROOT) / STATE_REL


def valid_slug(slug: str) -> bool:
    """A single path segment: no separators, no traversal, not empty."""
    return bool(slug) and slug not in (".", "..") and not any(c in slug for c in "/\\\0")


def load(root: Optional[Path] = None) -> Optional[dict]:
    """The current marker, or None when absent or unreadable."""
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not valid_slug(str(data.get("slug", ""))):
        return None
    return data


def save(data: dict, root: Optional[Path] = None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def clear(root: Optional[Path] = None) -> bool:
    try:
        state_path(root).unlink()
        return True
    except FileNotFoundError:
        return False


def now_iso() -> str:
    # Full precision: the Stop hook compares document mtimes against started_at, so a
    # redraft's old files (written before this run) never count as this run's documents.
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def session_from_env(env: Optional[dict] = None) -> Optional[str]:
    """The Claude Code session id exported to the Bash tool, or None outside Claude Code.

    It names the session's transcript (~/.claude/projects/<project>/<id>.jsonl) and is
    the `session_id` the Stop hook receives; inside a subagent it is the parent's id,
    which is still the session whose Stop event fires.
    """
    env = os.environ if env is None else env
    value = (env.get(SESSION_ENV) or "").strip()
    return value or None


def start(slug: str, root: Optional[Path] = None, session_id: Optional[str] = None,
          cwd: Optional[str] = None) -> dict:
    data = {"slug": slug, "started_at": now_iso(), "blocks": 0}
    if cwd:
        data["cwd"] = cwd
    if session_id:
        data["session_id"] = session_id
    save(data, root)
    return data


def main(argv: Optional[list] = None, root: Optional[Path] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "done"):
        sub.add_parser(action).add_argument("slug", help="<company>_<role>, as in documents/applications/")
    sub.add_parser("status")
    args = parser.parse_args(argv)

    if args.action in ("start", "done") and not valid_slug(args.slug):
        print(f"apply_state: invalid slug {args.slug!r} (one path segment, e.g. acme_backend-engineer)")
        return 1

    if args.action == "start":
        data = start(args.slug, root, session_id=session_from_env(), cwd=os.getcwd())
        print(f"apply_state: /apply in progress for {data['slug']} (started {data['started_at']})")
        return 0

    if args.action == "done":
        current = load(root)
        if current and current["slug"] != args.slug:
            print(f"apply_state: warning: marker was for {current['slug']!r}, not {args.slug!r}; clearing it anyway")
        cleared = clear(root)
        print("apply_state: /apply marker cleared" if cleared else "apply_state: no /apply in progress")
        return 0

    current = load(root)
    if not current:
        print("apply_state: no /apply in progress")
    else:
        print(json.dumps(current))
    return 0


if __name__ == "__main__":
    sys.exit(main())
