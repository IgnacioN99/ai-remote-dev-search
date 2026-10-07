"""Tests for tools/sync_mcp_config.py (.mcp.json -> .agents/mcp_config.json)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.sync_mcp_config import (  # noqa: E402
    build_antigravity_config,
    check_sync,
    render,
    translate_server,
)

SCRIPT = ROOT / "tools" / "sync_mcp_config.py"


class TranslateTests(unittest.TestCase):
    def test_stdio_fields_kept_and_unknown_dropped(self):
        spec = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
            "env": {"A": "1"},
            "cwd": "/tmp",
            "disabled": False,
            "disabledTools": ["x"],
            "somethingElse": 1,
        }
        out = translate_server("p", spec)
        self.assertEqual(
            out,
            {
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest"],
                "env": {"A": "1"},
                "cwd": "/tmp",
                "disabled": False,
                "disabledTools": ["x"],
            },
        )

    def test_remote_url_variants_become_serverUrl(self):
        for spec in (
            {"type": "http", "url": "https://x/mcp"},
            {"type": "sse", "url": "https://x/mcp"},
            {"httpUrl": "https://x/mcp"},
            {"serverUrl": "https://x/mcp"},
        ):
            with self.subTest(spec=spec):
                self.assertEqual(translate_server("r", spec), {"serverUrl": "https://x/mcp"})

    def test_remote_keeps_disabled(self):
        out = translate_server("r", {"url": "https://x", "disabled": True})
        self.assertEqual(out, {"serverUrl": "https://x", "disabled": True})

    def test_invalid_entries_raise(self):
        with self.assertRaises(ValueError):
            translate_server("bad", {"args": []})
        with self.assertRaises(ValueError):
            translate_server("bad", {"type": "http"})
        with self.assertRaises(ValueError):
            build_antigravity_config({"servers": {}})


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = self.dir / ".mcp.json"
        self.dst = self.dir / ".agents" / "mcp_config.json"
        self.src.write_text(json.dumps({"mcpServers": {"f": {"command": "uvx", "args": ["mcp-server-fetch"]}}}))

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source", str(self.src), "--target", str(self.dst), *args],
            capture_output=True,
            text=True,
        )

    def test_missing_target_is_drift(self):
        ok, msg = check_sync(self.src, self.dst)
        self.assertFalse(ok)
        self.assertIn("missing", msg)
        self.assertEqual(self._run("--check").returncode, 1)

    def test_write_then_check_passes(self):
        self.assertEqual(self._run().returncode, 0)
        self.assertTrue(self.dst.exists())
        self.assertEqual(self._run("--check").returncode, 0)

    def test_hand_edit_is_drift(self):
        self._run()
        data = json.loads(self.dst.read_text())
        data["mcpServers"]["f"]["args"] = ["something-else"]
        self.dst.write_text(json.dumps(data))
        self.assertEqual(self._run("--check").returncode, 1)

    def test_source_change_is_drift(self):
        self._run()
        self.src.write_text(json.dumps({"mcpServers": {"g": {"url": "https://x"}}}))
        result = self._run("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DRIFT", result.stdout)


class RepoConfigTests(unittest.TestCase):
    """The committed configs themselves."""

    def test_repo_mcp_json_uses_real_playwright_package(self):
        cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        args = cfg["mcpServers"]["playwright"]["args"]
        self.assertTrue(any(a.startswith("@playwright/mcp") for a in args), args)
        self.assertNotIn("@modelcontextprotocol/server-playwright", json.dumps(cfg))

    def test_repo_antigravity_config_in_sync(self):
        ok, msg = check_sync(ROOT / ".mcp.json", ROOT / ".agents" / "mcp_config.json")
        self.assertTrue(ok, msg)

    def test_render_is_stable(self):
        cfg = build_antigravity_config(json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8")))
        self.assertTrue(render(cfg).endswith("}\n"))
        self.assertEqual(json.loads(render(cfg)), cfg)


if __name__ == "__main__":
    unittest.main()
