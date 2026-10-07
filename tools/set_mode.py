#!/usr/bin/env python3
"""Switch the main checkout between operator and config mode.

    python3 tools/set_mode.py config [--by /setup]   # personalization commands, at their start
    python3 tools/set_mode.py operator               # ...and at their end (also the default)
    python3 tools/set_mode.py show

The state lives in the gitignored file .agents/state/mode because PreToolUse hooks do not
inherit environment variables the agent sets. No file means operator mode; a config state
older than 4 hours is treated as operator, so an abandoned /setup cannot leave the framework
writable. Config mode only unlocks the paths listed in tools/personalization_paths.json -
it never unlocks tools/, tests/ or other framework code.

Stdlib only. Exit 0 on success, 2 on bad usage, 1 when not inside a git repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import framework_paths as fp  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["config", "operator", "show"])
    ap.add_argument("--by", default="", help="command that switched the mode (for the record)")
    args = ap.parse_args(argv)

    info = fp.repo_info(Path.cwd())
    if info is None:
        info = fp.repo_info(Path(__file__).resolve().parent)
    if info is None:
        print("set_mode: not inside a git repository", file=sys.stderr)
        return 1
    if args.mode == "show":
        where = "linked worktree (guard inactive)" if info.is_linked_worktree else "main checkout"
        print(f"mode: {fp.read_mode(info.toplevel)} ({where})")
        return 0
    path = fp.write_mode(info.toplevel, args.mode, args.by)
    print(f"mode: {args.mode} (state file: {path.relative_to(info.toplevel).as_posix()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
