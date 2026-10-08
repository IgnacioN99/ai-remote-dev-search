"""Unit tests for tools/doctor.py (environment and toolchain diagnostic).

Written for `python3 -m unittest discover -s tests` (what CI runs). Every
network/git-backed check goes through `tools.doctor._run`, which is mocked here so
the suite is offline-safe and never hangs on `npm view` / `gh api`.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import doctor  # noqa: E402
from tools.doctor import (  # noqa: E402
    _github_slug,
    _rule_trigger,
    check_antigravity,
    check_browser_automation,
    check_framework_integrity,
    check_github_cli,
    check_js_runtime,
    check_latex_compilers,
    check_playwright_mcp,
    check_python,
    format_doctor_report,
    run_doctor,
)


def _cp(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_run(table):
    """Build a `_run` replacement: first key (tuple prefix of argv) that matches wins."""

    def runner(cmd, timeout=10, cwd=None):
        for prefix, result in table.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                return result
        raise AssertionError(f"unexpected command: {cmd}")

    return runner


def _by_name(results, name):
    return next(r for r in results if r["name"] == name)


class CoreChecksTests(unittest.TestCase):
    def test_check_python_passes(self):
        res = check_python()
        self.assertEqual(res["status"], "OK")
        self.assertTrue(res["critical"])
        self.assertIn("Python", res["detail"])

    def test_detects_missing_critical_tool(self):
        with patch("tools.doctor.check_command", return_value=(False, "Not found on PATH")):
            lua = [c for c in check_latex_compilers() if "LuaLaTeX" in c["name"]][0]
        self.assertEqual(lua["status"], "FAIL")
        self.assertTrue(lua["critical"])

    def test_js_runtime_detection(self):
        with patch("tools.doctor.check_command", side_effect=[(False, "x"), (True, "/usr/bin/node (v20)")]):
            res = check_js_runtime()
        self.assertEqual(res["status"], "OK")
        self.assertIn("node", res["detail"])

    def test_full_run_structure_offline(self):
        with patch("tools.doctor._run", return_value=None), patch("tools.doctor._npx_cache_has", return_value=False):
            res = run_doctor()
        self.assertIn("checks", res)
        self.assertIn("summary", res)
        critical_fail = any(c["status"] == "FAIL" and c.get("critical", True) for c in res["checks"])
        self.assertEqual(res["healthy"], not critical_fail)
        # Offline, the new network-backed checks degrade to WARN, never FAIL.
        for c in res["checks"]:
            if c["name"].startswith(("Playwright MCP", "GitHub", "Antigravity", "Framework", "Git hooks")):
                self.assertNotEqual(c["status"], "FAIL", c)
                self.assertFalse(c["critical"], c)

    def test_format_doctor_report(self):
        report = format_doctor_report({
            "checks": [
                {"name": "Python", "status": "OK", "detail": "3.12"},
                {"name": "Typst", "status": "WARN", "detail": "Optional"},
                {"name": "Hooks", "status": "SKIP", "detail": "Skipped: none"},
            ],
            "summary": {"OK": 1, "WARN": 1, "FAIL": 0, "SKIP": 1},
            "healthy": True,
        })
        self.assertIn("[OK]", report)
        self.assertIn("[WARN]", report)
        self.assertIn("[SKIP]", report)
        self.assertIn("1 skipped", report)
        self.assertIn("HEALTH VERDICT: [OK]", report)


class PlaywrightMcpTests(unittest.TestCase):
    def test_npx_alone_is_not_ok(self):
        """Regression: doctor used to report OK just because `npx` existed."""
        with patch("tools.doctor.shutil.which", return_value="/usr/bin/npx"), \
                patch("tools.doctor._npx_cache_has", return_value=False), \
                patch("tools.doctor._run", return_value=None):
            res = check_playwright_mcp()
        self.assertEqual(res["status"], "WARN")

    def test_registry_404_is_warn(self):
        with patch("tools.doctor.shutil.which", return_value="/usr/bin/npx"), \
                patch("tools.doctor._npx_cache_has", return_value=False), \
                patch("tools.doctor._run", return_value=_cp(returncode=1, stderr="npm error 404 Not Found")):
            res = check_playwright_mcp()
        self.assertEqual(res["status"], "WARN")
        self.assertIn("404", res["detail"])

    def test_resolvable_package_is_ok(self):
        with patch("tools.doctor.shutil.which", return_value="/usr/bin/npx"), \
                patch("tools.doctor._npx_cache_has", return_value=False), \
                patch("tools.doctor._run", return_value=_cp("0.0.83\n")) as run:
            res = check_playwright_mcp()
        self.assertEqual(res["status"], "OK")
        self.assertIn("0.0.83", res["detail"])
        self.assertIn("@playwright/mcp", run.call_args[0][0])

    def test_cached_package_is_ok_without_network(self):
        with patch("tools.doctor.shutil.which", return_value="/usr/bin/npx"), \
                patch("tools.doctor._npx_cache_has", return_value=True), \
                patch("tools.doctor._run", side_effect=AssertionError("no network expected")):
            self.assertEqual(check_playwright_mcp()["status"], "OK")

    def test_no_npx_is_warn(self):
        with patch("tools.doctor.shutil.which", return_value=None):
            self.assertEqual(check_playwright_mcp()["status"], "WARN")

    def test_local_library_check_never_mentions_npx(self):
        with patch.dict(sys.modules, {"playwright": None}), \
                patch("tools.doctor.check_command", return_value=(False, "Not found on PATH")):
            res = check_browser_automation()
        self.assertEqual(res["status"], "WARN")


class GithubCliTests(unittest.TestCase):
    ORIGIN = "git@github.com:me/fork.git"

    def _table(self, default="me/fork", has_issues="true", auth_rc=0):
        return {
            ("gh", "auth", "status"): _cp(returncode=auth_rc),
            ("git", "remote", "get-url", "origin"): _cp(self.ORIGIN + "\n"),
            ("gh", "repo", "set-default", "--view"): _cp(default + "\n") if default else _cp(returncode=1),
            ("gh", "api"): _cp(has_issues + "\n"),
        }

    def _check(self, table):
        with patch("tools.doctor.shutil.which", return_value="/usr/bin/gh"), \
                patch("tools.doctor._run", side_effect=_fake_run(table)):
            return check_github_cli()

    def test_all_good(self):
        res = self._check(self._table())
        self.assertTrue(all(r["status"] == "OK" for r in res), res)

    def test_default_repo_unset_warns_upstream(self):
        res = _by_name(self._check(self._table(default=None)), "GitHub default repo")
        self.assertEqual(res["status"], "WARN")
        self.assertIn("upstream", res["detail"])
        self.assertIn("gh repo set-default me/fork", res["detail"])

    def test_default_repo_is_upstream_warns(self):
        res = _by_name(self._check(self._table(default="Upstream/repo")), "GitHub default repo")
        self.assertEqual(res["status"], "WARN")

    def test_issues_disabled_gives_fix_command(self):
        res = _by_name(self._check(self._table(has_issues="false")), "GitHub issues on origin")
        self.assertEqual(res["status"], "WARN")
        self.assertIn("gh repo edit me/fork --enable-issues", res["detail"])

    def test_not_authenticated_warns(self):
        res = _by_name(self._check(self._table(auth_rc=1)), "GitHub CLI auth")
        self.assertEqual(res["status"], "WARN")

    def test_timeouts_are_warn_not_fail(self):
        with patch("tools.doctor.shutil.which", return_value="/usr/bin/gh"), \
                patch("tools.doctor._run", return_value=None):
            res = check_github_cli()
        self.assertTrue(res)
        self.assertTrue(all(r["status"] == "WARN" and not r["critical"] for r in res), res)

    def test_gh_missing_is_warn(self):
        with patch("tools.doctor.shutil.which", return_value=None):
            res = check_github_cli()
        self.assertEqual([r["status"] for r in res], ["WARN"])

    def test_github_slug_parsing(self):
        self.assertEqual(_github_slug("git@github.com:a/b.git"), "a/b")
        self.assertEqual(_github_slug("https://github.com/a/b.git"), "a/b")
        self.assertEqual(_github_slug("https://github.com/a/b"), "a/b")
        self.assertEqual(_github_slug("ssh://git@github.com/a/b.git"), "a/b")
        self.assertIsNone(_github_slug("https://gitlab.com/a/b.git"))


class AntigravityAndIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "tools").mkdir()
        self.patcher = patch("tools.doctor.ROOT_DIR", self.root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_rule_trigger_parser(self):
        self.assertEqual(_rule_trigger("---\ntrigger: always_on\n---\nbody"), "always_on")
        self.assertEqual(_rule_trigger("---\ndescription: x\ntrigger: 'model_decision'\n---\n"), "model_decision")
        self.assertIsNone(_rule_trigger("# no frontmatter\ntrigger: always_on"))
        self.assertIsNone(_rule_trigger("---\ndescription: x\n---\ntrigger: always_on"))

    def test_mcp_drift_and_bad_rule_warn(self):
        self._write(".mcp.json", '{"mcpServers": {"f": {"command": "uvx"}}}')
        self._write(".agents/rules/good.md", "---\ntrigger: always_on\n---\n")
        self._write(".agents/rules/bad.md", "---\ntrigger: sometimes\n---\n")
        res = check_antigravity()
        self.assertEqual(_by_name(res, "Antigravity MCP config")["status"], "WARN")
        rules = _by_name(res, "Antigravity rules frontmatter")
        self.assertEqual(rules["status"], "WARN")
        self.assertIn("bad.md", rules["detail"])
        self.assertNotIn("good.md", rules["detail"])
        self.assertEqual(_by_name(res, "Antigravity generated skills")["status"], "SKIP")

    def test_in_sync_and_valid_rules_ok(self):
        self._write(".mcp.json", '{"mcpServers": {"f": {"command": "uvx"}}}')
        self._write(".agents/mcp_config.json", '{"mcpServers": {"f": {"command": "uvx"}}}')
        self._write(".agents/rules/core.md", "---\ntrigger: always_on\n---\n")
        res = check_antigravity()
        self.assertEqual(_by_name(res, "Antigravity MCP config")["status"], "OK")
        self.assertEqual(_by_name(res, "Antigravity rules frontmatter")["status"], "OK")

    def test_optional_tools_run_when_present(self):
        self._write("tools/sync_agent_skills.py", "")
        self._write("tools/check_framework_immutable.py", "")
        with patch("tools.doctor._run", return_value=_cp(returncode=1, stdout="drift: x.md\n")) as run:
            skills = _by_name(check_antigravity(), "Antigravity generated skills")
            immut = _by_name(check_framework_integrity(), "Framework immutability")
        self.assertEqual(skills["status"], "WARN")
        self.assertEqual(immut["status"], "WARN")
        self.assertIn("drift: x.md", immut["detail"])
        argvs = [c[0][0] for c in run.call_args_list]
        self.assertTrue(any("--check" in a for a in argvs))

    def test_run_helper_handles_missing_binary(self):
        self.assertIsNone(doctor._run(["definitely-not-a-real-binary-xyz"]))


class HooksPathTests(unittest.TestCase):
    """core.hooksPath is resolved like git does and compared as a real path."""

    NAME = "Git hooks (core.hooksPath)"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "repo"
        (self.root / ".githooks").mkdir(parents=True)
        (self.root / ".githooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
        self.patcher = patch("tools.doctor.ROOT_DIR", self.root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _status(self, configured, toplevel=None, common=None):
        table = {
            ("git", "config", "core.hooksPath"): _cp(configured + "\n" if configured else "", 0 if configured else 1),
            ("git", "rev-parse", "--show-toplevel"): _cp(f"{toplevel or self.root}\n"),
            ("git", "rev-parse", "--git-common-dir"): _cp(f"{common or self.root / '.git'}\n"),
        }
        with patch("tools.doctor._run", side_effect=_fake_run(table)):
            return _by_name(check_framework_integrity(), self.NAME)

    def test_no_githooks_dir_skips(self):
        with patch("tools.doctor.ROOT_DIR", self.base / "empty"):
            self.assertEqual(_by_name(check_framework_integrity(), self.NAME)["status"], "SKIP")

    def test_unset_warns_with_fix_hint(self):
        res = self._status("")
        self.assertEqual(res["status"], "WARN")
        self.assertIn("unset", res["detail"])
        self.assertIn("fix: git config core.hooksPath .githooks", res["detail"])

    def test_relative_ok(self):
        for value in (".githooks", ".githooks/", "./.githooks"):
            self.assertEqual(self._status(value)["status"], "OK", value)

    def test_absolute_ok(self):
        self.assertEqual(self._status(str(self.root / ".githooks"))["status"], "OK")

    def test_tilde_ok(self):
        with patch.dict("os.environ", {"HOME": str(self.base), "USERPROFILE": str(self.base)}):
            self.assertEqual(self._status("~/repo/.githooks")["status"], "OK")

    def test_mismatch_warns(self):
        other = self.base / "elsewhere" / ".githooks"
        other.mkdir(parents=True)
        res = self._status(str(other))
        self.assertEqual(res["status"], "WARN")
        self.assertIn("fix: git config core.hooksPath .githooks", res["detail"])
        self.assertEqual(self._status("hooks")["status"], "WARN")

    def _main_checkout(self, with_pre_commit=True):
        main = self.base / "main"
        (main / ".git").mkdir(parents=True)
        (main / ".githooks").mkdir()
        if with_pre_commit:
            (main / ".githooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
        return main

    def test_linked_worktree_accepts_main_checkout_hooks(self):
        main = self._main_checkout()
        common = main / ".git"
        self.assertEqual(self._status(str(main / ".githooks"), common=common)["status"], "OK")
        # A relative value resolves against the worktree's own top level.
        self.assertEqual(self._status(".githooks", common=common)["status"], "OK")

    def test_linked_worktree_rejects_main_hooks_without_pre_commit(self):
        main = self._main_checkout(with_pre_commit=False)
        self.assertEqual(self._status(str(main / ".githooks"), common=main / ".git")["status"], "WARN")


if __name__ == "__main__":
    unittest.main()
