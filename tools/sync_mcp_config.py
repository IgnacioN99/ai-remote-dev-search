#!/usr/bin/env python3
"""Generate Antigravity's MCP config from Claude Code's `.mcp.json`.

`.mcp.json` (repo root) is the single source of truth for project MCP servers.
Google Antigravity reads a different schema from `mcp_config.json`:

  * stdio servers: `command`, `args`, `env`, `cwd`, `disabled`, `disabledTools`
  * remote servers: `serverUrl` (not `url` / `httpUrl`, and no `type` field)

This tool translates one into the other and writes `.agents/mcp_config.json`
(the workspace customization root). `--check` exits 1 when the generated file
is missing or has drifted from `.mcp.json`, so CI and `tools/doctor.py` can catch
a hand-edited or stale copy.

Usage:
  python3 tools/sync_mcp_config.py            # write .agents/mcp_config.json
  python3 tools/sync_mcp_config.py --check    # exit 1 on drift
  python3 tools/sync_mcp_config.py --stdout   # print the generated config
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE = ROOT_DIR / ".mcp.json"
TARGET = ROOT_DIR / ".agents" / "mcp_config.json"

STDIO_FIELDS = ("command", "args", "env", "cwd", "disabled", "disabledTools")
REMOTE_URL_FIELDS = ("serverUrl", "url", "httpUrl")


def translate_server(name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Translate one Claude Code server entry into Antigravity's schema."""
    if not isinstance(spec, dict):
        raise ValueError(f"server '{name}': entry must be an object")

    url = next((spec[k] for k in REMOTE_URL_FIELDS if spec.get(k)), None)
    if url is not None:
        out: Dict[str, Any] = {"serverUrl": url}
        for key in ("disabled", "disabledTools"):
            if key in spec:
                out[key] = spec[key]
        return out

    if spec.get("type") in ("http", "sse", "streamable-http"):
        raise ValueError(f"server '{name}': remote type '{spec['type']}' without a url")
    if "command" not in spec:
        raise ValueError(f"server '{name}': needs either 'command' (stdio) or 'url' (remote)")

    return {key: spec[key] for key in STDIO_FIELDS if key in spec}


def build_antigravity_config(mcp: Dict[str, Any]) -> Dict[str, Any]:
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError("source config has no 'mcpServers' object")
    return {"mcpServers": {name: translate_server(name, spec) for name, spec in servers.items()}}


def render(config: Dict[str, Any]) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_sync(source: Path = SOURCE, target: Path = TARGET) -> Tuple[bool, str]:
    """Return (in_sync, message). Compares parsed JSON, not bytes."""
    if not source.exists():
        return False, f"{source.name} not found"
    try:
        expected = build_antigravity_config(load_json(source))
    except (ValueError, json.JSONDecodeError) as e:
        return False, f"cannot translate {source.name}: {e}"
    if not target.exists():
        return False, f"{_rel(target)} missing - run python3 tools/sync_mcp_config.py"
    try:
        actual = load_json(target)
    except json.JSONDecodeError as e:
        return False, f"{_rel(target)} is not valid JSON: {e}"
    if actual != expected:
        return False, f"{_rel(target)} drifted from {source.name} - run python3 tools/sync_mcp_config.py"
    return True, f"{_rel(target)} in sync with {source.name} ({len(expected['mcpServers'])} servers)"


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return str(path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate .agents/mcp_config.json from .mcp.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 if the generated file is missing or drifted")
    mode.add_argument("--stdout", action="store_true", help="print the generated config instead of writing it")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args(argv)

    if args.check:
        ok, msg = check_sync(args.source, args.target)
        print(("OK: " if ok else "DRIFT: ") + msg)
        return 0 if ok else 1

    try:
        config = build_antigravity_config(load_json(args.source))
    except FileNotFoundError:
        print(f"ERROR: {args.source} not found", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    text = render(config)
    if args.stdout:
        sys.stdout.write(text)
        return 0
    args.target.parent.mkdir(parents=True, exist_ok=True)
    with open(args.target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"Wrote {_rel(args.target)} ({len(config['mcpServers'])} servers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
