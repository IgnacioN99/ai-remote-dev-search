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

Antigravity shell commands (matcher run_command, same `--antigravity` command):
  stdin  {"toolCall": {"name": "run_command", "args": {"CommandLine", "Cwd", ...}}, ...}
  The command line is tokenized (shlex) and only OBVIOUS write targets are checked with the
  same decision rules: output redirections (> >> &> >|), tee, sed -i / perl -i, cp/mv/install/ln
  destinations, touch/truncate, dd of=. Anything it cannot see (python -c, scripts, heredocs
  fed to an interpreter, variables, installers) stays "ask"; check_framework_immutable.py is
  the backstop. Deliberately conservative: a parse error never denies.

Debug log (to confirm the IDE really runs the hook): set GUARD_FRAMEWORK_LOG=<file> (or =1),
or create .agents/state/guard_framework.debug in the repo. One JSON line per call (time,
runtime, tool, target paths, decision, workspace) goes to that file or to
.agents/state/guard_framework.log (gitignored); never file contents. Capped at 1 MB.

`--only-this-repo` (for a machine-wide ~/.gemini/config/hooks.json, see SETUP.md): targets
outside the repository that holds this script get the neutral answer, so other projects
are never affected.

Decision (tools/framework_paths.py holds the shared rules):
  target inside a git dir (.git/config, .git/hooks/*, ...)  -> denied (any checkout)
  .claude/settings.local.json (user's own permissions)     -> denied (any checkout)
  target outside any git repo, or inside a LINKED worktree  -> allowed (dev work happens there)
  main checkout, gitignored or non-framework path           -> allowed (user data / outputs)
  .agents/state/mode itself                                 -> denied (use tools/set_mode.py)
  personalization path allowed in the current mode          -> allowed
  any other tracked file / new file under a framework dir   -> denied, pointing to report_issue.py

Fails open (logs to stderr) on internal errors, never on a clear deny.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import re
import shlex
import sys
from pathlib import Path

HOOK_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HOOK_ROOT / "tools"))

LOCAL_SETTINGS = ".claude/settings.local.json"
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


# --- run_command: obvious shell write targets ------------------------------------------

SHELL_TOOLS = ("run_command",)
_PUNCT = ";&|<>()\n"
_OPS = re.compile(r"&>>?|>\||>>?&?|<<<|<<-?|<>|<&?|&&|\|\||\|&?|;;?|&|[()\n]")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][\w.-]*)\1")
_WRAPPERS = {"sudo", "env", "command", "nohup", "time", "exec", "builtin", "nice", "stdbuf"}
_GLOB_CHARS = set("*?[")


def _strip_heredocs(text: str) -> str:
    """Drop heredoc bodies (their lines are data, not commands); keep the opening line."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in _HEREDOC.finditer(line):
            while i < len(lines) and lines[i].strip() != m.group(2):
                i += 1
            i += 1
    return "\n".join(out)


def _tokens(text: str) -> list[str]:
    """Shell words and operators. Raises ValueError on unbalanced quotes."""
    lex = shlex.shlex(_strip_heredocs(text.replace("\\\n", " ")), posix=True, punctuation_chars=_PUNCT)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    out: list[str] = []
    for tok in lex:
        if tok and all(ch in _PUNCT for ch in tok):
            out.extend(_OPS.findall(tok) or [tok])
        else:
            out.append(tok)
    return out


def _is_op(tok: str) -> bool:
    return bool(tok) and all(ch in _PUNCT for ch in tok)


def _positional(args: list[str], takes_value: tuple[str, ...] = ()) -> list[str]:
    """Non-option arguments; options listed in `takes_value` consume the next word."""
    out, skip, ended = [], False, False
    for a in args:
        if skip:
            skip = False
            continue
        if ended or not a.startswith("-") or a == "-":
            out.append(a)
        elif a == "--":
            ended = True
        elif a in takes_value:
            skip = True
    return out


def _option_value(args: list[str], short: str, long: str) -> str | None:
    for i, a in enumerate(args):
        if a == short or a == long:
            return args[i + 1] if i + 1 < len(args) else None
        if a.startswith(long + "="):
            return a.split("=", 1)[1]
    return None


def _command_targets(argv: list[str]) -> list[str]:
    """Paths a simple command obviously writes. Unknown commands -> []."""
    while argv and (re.match(r"^[A-Za-z_]\w*=", argv[0]) or os.path.basename(argv[0]) in _WRAPPERS):
        argv = argv[1:]
        while argv and argv[0].startswith("-"):  # wrapper options (sudo -u x is rare enough)
            argv = argv[1:]
    if not argv:
        return []
    name, args = os.path.basename(argv[0]), argv[1:]
    if name == "tee":
        return _positional(args)
    if name in ("cp", "mv", "install", "ln"):
        tdir = _option_value(args, "-t", "--target-directory")
        pos = _positional(args, ("-t", "-S", "-m", "-o", "-g"))
        if tdir:
            return [os.path.join(tdir, os.path.basename(s.rstrip("/"))) for s in pos] or [tdir]
        if name == "ln" and len(pos) == 1:
            return [os.path.basename(pos[0].rstrip("/"))]
        if len(pos) < 2:
            return []
        return [pos[-1]] + [os.path.join(pos[-1], os.path.basename(s.rstrip("/"))) for s in pos[:-1]]
    if name == "sed":
        if not any(a.startswith("-i") or a.startswith("--in-place") or
                   (a.startswith("-") and not a.startswith("--") and "i" in a[1:])
                   for a in args):
            return []
        pos = _positional(args, ("-e", "-f", "--expression", "--file", "-l"))
        has_script = any(a in ("-e", "-f") or a.startswith(("--expression", "--file")) for a in args)
        return pos if has_script else pos[1:]
    if name == "perl":
        if not any(a.startswith("-") and not a.startswith("--") and "i" in a[1:] for a in args):
            return []
        pos = _positional(args, ("-e", "-E", "-M", "-I"))
        return pos if any(a in ("-e", "-E") or re.match(r"^-\w*[eE]$", a) for a in args) else pos[1:]
    if name == "touch":
        return _positional(args, ("-d", "-t", "-r"))
    if name == "truncate":
        return _positional(args, ("-s", "-r"))
    if name == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    return []


def shell_write_targets(command: str, cwd: str) -> list[str]:
    """Absolute paths the command line obviously writes (best effort, conservative)."""
    toks = _tokens(command)
    targets: list[str] = []
    argv: list[str] = []
    here = cwd

    def resolve(word: str) -> list[str]:
        if not word or "$" in word or "`" in word:
            return []
        word = os.path.expanduser(word)
        p = word if os.path.isabs(word) else os.path.join(here, word)
        if _GLOB_CHARS & set(word):
            return glob.glob(p) or []
        return [p]

    def flush():
        nonlocal here, argv
        if argv and argv[0] == "cd" and len(argv) >= 2:
            dest = resolve(argv[1])
            if dest:
                here = dest[0]
        else:
            for t in _command_targets(argv):
                targets.extend(resolve(t))
        argv = []

    i = 0
    while i < len(toks):
        tok = toks[i]
        if not _is_op(tok):
            argv.append(tok)
            i += 1
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) and not _is_op(toks[i + 1]) else None
        if ">" in tok:
            if argv and argv[-1].isdigit() and len(argv[-1]) <= 2:
                argv.pop()  # "2>/dev/null": the fd number is not an argument
            if nxt is not None and not (tok.endswith("&") and (nxt.isdigit() or nxt == "-")):
                targets.extend(resolve(nxt))
            i += 2 if nxt is not None else 1
        elif tok.startswith("<"):
            i += 2 if nxt is not None else 1
        else:
            flush()
            i += 1
    flush()
    return targets


def parse_antigravity_shell(payload: dict) -> tuple[list[str], str, object]:
    call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    args = _decode(call.get("args")) or {}
    if not isinstance(args, dict):
        args = {}
    args = {k: _decode(v) for k, v in args.items()}
    ws = payload.get("workspacePaths") or []
    cwd = args.get("Cwd") or args.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = ws[0] if ws and isinstance(ws[0], str) else os.getcwd()
    command = args.get("CommandLine") or args.get("commandLine") or args.get("command") or ""
    if not isinstance(command, str):
        command = ""
    return shell_write_targets(command, cwd), cwd, (call.get("name"), {})


def in_this_repo(path: str, base: str) -> bool:
    """True when `path` lies in the repository (any checkout) that holds this script."""
    import framework_paths as fp

    p = Path(path) if os.path.isabs(path) else Path(base) / path
    here, there = fp.repo_info(HOOK_ROOT), fp.repo_info(p.parent)
    return bool(here and there and os.path.realpath(here.common_dir) == os.path.realpath(there.common_dir))


# --- debug log --------------------------------------------------------------------------

LOG_CAP = 1_000_000


def _log_target(environ=None) -> Path | None:
    environ = os.environ if environ is None else environ
    val = (environ.get("GUARD_FRAMEWORK_LOG") or "").strip()
    state = HOOK_ROOT / ".agents" / "state"
    if val and val not in ("0", "false", "no"):
        return state / "guard_framework.log" if val in ("1", "true", "yes") else Path(val).expanduser()
    if (state / "guard_framework.debug").exists():
        return state / "guard_framework.log"
    return None


def debug_log(record: dict, environ=None) -> None:
    """Append one JSON line when debugging is on. Never raises."""
    try:
        target = _log_target(environ)
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > LOG_CAP:
            target.write_text("", encoding="utf-8")
        record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), **record}
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # debugging must never break the guard
        pass


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


def _in_git_dir(real: Path, base: str, fp) -> bool:
    """True when `real` is inside a .git directory, or inside the git dir / common dir of the
    repository holding the session (covers worktrees whose common dir is <main>/.git)."""
    if ".git" in real.parts:
        return True
    info = fp.repo_info(base) if base else None
    if info is None:
        return False
    for d in (info.git_dir, info.common_dir):
        try:
            real.relative_to(d)
            return True
        except ValueError:
            continue
    return False


def decide(path: str | None, base: str, tool: object) -> tuple[str, str]:
    """('allow'|'deny', reason)."""
    import framework_paths as fp

    if not path:
        return "allow", "no file path in tool input"
    p = Path(path)
    if not p.is_absolute():
        p = Path(base) / p
    real = Path(os.path.realpath(p))
    if _in_git_dir(real, base, fp):
        return "deny", (
            "Writing inside a git directory (.git/config, .git/hooks/*, ...) is never allowed from "
            "an agent session: it can disable the operator-mode guard or run code on the next git "
            f"command. Change git configuration by hand; {fp.ISSUE_HINT}"
        )
    info = fp.repo_info(p.parent)
    if info is None:
        return "allow", "outside any git repository"
    if fp.relpath_in(info, p) == LOCAL_SETTINGS:
        return "deny", (
            f"{LOCAL_SETTINGS} holds your personal Claude Code permissions; agents must not edit it "
            "(widening it would pre-approve commands). Edit it yourself or use /permissions."
        )
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


def _decide_shell(payload: dict, only_this_repo: bool) -> tuple[str, str, list[str], str, object]:
    targets, base, tool = parse_antigravity_shell(payload)
    for t in targets:
        if only_this_repo and not in_this_repo(t, base):
            continue
        decision, reason = decide(t, base, tool)
        if decision == "deny":
            return "deny", f"Shell command writes {os.path.basename(t)!r}: {reason}", targets, base, tool
    return "allow", "", targets, base, tool


def main(argv: list[str]) -> int:
    antigravity = "--antigravity" in argv
    only_this_repo = "--only-this-repo" in argv
    record: dict = {"runtime": "antigravity" if antigravity else "claude-code"}
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
        call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
        name = call.get("name") if antigravity else payload.get("tool_name")
        record.update(tool=name, workspacePaths=payload.get("workspacePaths"),
                      conversationId=payload.get("conversationId"), cwd=os.getcwd())
        if antigravity and name in SHELL_TOOLS:
            decision, reason, targets, base, _ = _decide_shell(payload, only_this_repo)
            record["targets"] = targets
        else:
            path, base, tool = (parse_antigravity if antigravity else parse_claude)(payload)
            record["targets"] = [path] if path else []
            if only_this_repo and path and not in_this_repo(path, base):
                decision, reason = "allow", "outside this repository"
            else:
                decision, reason = decide(path, base, tool)
    except Exception as exc:  # fail open: a broken guard must not wedge every edit
        print(f"guard_framework: internal error, allowing: {exc!r}", file=sys.stderr)
        decision, reason = "allow", ""
        record["error"] = repr(exc)
    record["decision"] = decision
    debug_log(record)
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
