#!/usr/bin/env python3
"""PreToolUse guard: operator mode never edits framework files in the MAIN checkout.

Claude Code (.claude/settings.json, matcher Edit|Write|MultiEdit|NotebookEdit):
  stdin  {"tool_name", "tool_input": {"file_path"|"notebook_path", ...}, "cwd", ...}
  deny   stdout {"hookSpecificOutput": {"hookEventName": "PreToolUse",
               "permissionDecision": "deny", "permissionDecisionReason": "..."}}, exit 0
  other  no output, exit 0 (the normal permission flow decides)

Google Antigravity (.agents/hooks.json, `--antigravity`, matcher
write_to_file|replace_file_content|multi_replace_file_content):
  stdin  {"toolCall": {"name", "args": {"TargetFile", ...}}, "workspacePaths": [...], ...}
         (arg values may arrive JSON-encoded, e.g. '"/path"')
  stdout {"decision": "deny"|"ask", "reason": "..."}; ALWAYS exit 0. "ask" is the neutral
         answer: it keeps Antigravity's own permission flow (and its Always-Allow cache).

Decision (tools/framework_paths.py holds the shared rules):
  target outside any git repo, or inside a LINKED worktree  -> allowed (dev work happens there)
  main checkout, gitignored or non-framework path           -> allowed (user data / outputs)
  .agents/state/mode itself                                 -> denied (use tools/set_mode.py)
  personalization path allowed in the current mode          -> allowed
  any other tracked file / new file under a framework dir   -> denied, pointing to report_issue.py

Fails open (logs to stderr) on internal errors, never on a clear deny.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOOK_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HOOK_ROOT / "tools"))

ANTIGRAVITY_FILE_KEYS = ("TargetFile", "targetFile", "AbsolutePath", "FilePath", "file_path", "path")


def _decode(value, depth: int = 3):
    """Antigravity may JSON-encode argument values ('"/x"', 'true', '[...]'). Unwrap them."""
    for _ in range(depth):
        if not isinstance(value, str):
            return value
        s = value.strip()
        if not s or s[0] not in "\"[{":
            return value
        try:
            value = json.loads(s)
        except ValueError:
            return value
    return value


def _apply(old: str, target: str, replacement: str, replace_all: bool = False) -> str | None:
    if not target or target not in old:
        return None
    return old.replace(target, replacement) if replace_all else old.replace(target, replacement, 1)


def parse_claude(payload: dict) -> tuple[str | None, str, object]:
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}
    path = ti.get("file_path") or ti.get("notebook_path")
    return path, payload.get("cwd") or os.getcwd(), (payload.get("tool_name"), ti)


def parse_antigravity(payload: dict) -> tuple[str | None, str, object]:
    call = payload.get("toolCall")
    if not isinstance(call, dict):
        call = {}
    args = _decode(call.get("args")) or {}
    if not isinstance(args, dict):
        args = {}
    args = {k: _decode(v) for k, v in args.items()}
    path = next((args[k] for k in ANTIGRAVITY_FILE_KEYS if isinstance(args.get(k), str) and args[k]), None)
    if path is None:
        path = next(
            (v for k, v in args.items() if isinstance(v, str) and v and (k.endswith("File") or k.endswith("Path"))),
            None,
        )
    ws = payload.get("workspacePaths") or []
    base = ws[0] if ws and isinstance(ws[0], str) else os.getcwd()
    return path, base, (call.get("name"), args)


def proposed_content(old: str, tool: object) -> str | None:
    """New file content the tool call would produce, or None when it cannot be computed."""
    name, a = tool
    if name == "Write":
        return a.get("content") if isinstance(a.get("content"), str) else None
    if name == "Edit":
        return _apply(old, a.get("old_string", ""), a.get("new_string", ""), bool(a.get("replace_all")))
    if name == "MultiEdit":
        cur = old
        for e in a.get("edits") or []:
            if not isinstance(e, dict):
                return None
            cur = _apply(cur, e.get("old_string", ""), e.get("new_string", ""), bool(e.get("replace_all")))
            if cur is None:
                return None
        return cur
    if name == "write_to_file":
        return a.get("CodeContent") if isinstance(a.get("CodeContent"), str) else None
    if name == "replace_file_content":
        return _apply(old, a.get("TargetContent", ""), a.get("ReplacementContent", ""), a.get("AllowMultiple") in (True, "true", "True"))
    if name == "multi_replace_file_content":
        chunks = _decode(a.get("ReplacementChunks"))
        if not isinstance(chunks, list):
            return None
        cur = old
        for c in chunks:
            c = _decode(c)
            if not isinstance(c, dict):
                return None
            cur = _apply(cur, _decode(c.get("TargetContent", "")), _decode(c.get("ReplacementContent", "")),
                         c.get("AllowMultiple") in (True, "true", "True"))
            if cur is None:
                return None
        return cur
    return None


def decide(path: str | None, base: str, tool: object) -> tuple[str, str]:
    """('allow'|'deny', reason)."""
    import framework_paths as fp

    if not path:
        return "allow", "no file path in tool input"
    p = Path(path)
    if not p.is_absolute():
        p = Path(base) / p
    info = fp.repo_info(p.parent)
    if info is None:
        return "allow", "outside any git repository"
    if info.is_linked_worktree:
        return "allow", "linked worktree (framework development is allowed here)"
    rel = fp.relpath_in(info, p)
    if rel is None:
        return "allow", "outside the repository toplevel"
    if rel == fp.MODE_FILE:
        return "deny", (
            f"{rel} is the operator/config mode switch; change it only with "
            "`python3 tools/set_mode.py config|operator` as the config commands instruct."
        )
    if not fp.is_framework(info, rel):
        return "allow", "user data (gitignored or outside framework dirs)"
    mode = fp.read_mode(info.toplevel)
    change = None
    try:
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        new = proposed_content(old, tool)
        if new is not None:
            change = (old, new)
    except (OSError, UnicodeDecodeError):
        change = None
    ok, why = fp.personalization_allows(fp.load_personalization(info.toplevel), rel, mode, change)
    if ok:
        return "allow", why
    return "deny", (
        f"Operator mode: '{rel}' is a framework file in the main checkout (mode: {mode}). "
        f"Do not edit it here; {fp.ISSUE_HINT} If this is a /setup-style personalization, the "
        "command must run `python3 tools/set_mode.py config` first."
    )


def main(argv: list[str]) -> int:
    antigravity = "--antigravity" in argv
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
        path, base, tool = (parse_antigravity if antigravity else parse_claude)(payload)
        decision, reason = decide(path, base, tool)
    except Exception as exc:  # fail open: a broken guard must not wedge every edit
        print(f"guard_framework: internal error, allowing: {exc!r}", file=sys.stderr)
        decision, reason = "allow", ""
    if antigravity:
        out = {"decision": "deny" if decision == "deny" else "ask"}
        if reason:
            out["reason"] = reason
        print(json.dumps(out))
    elif decision == "deny":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
