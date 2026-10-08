"""Tests for the operator-mode framework guard.

Covers .claude/hooks/guard_framework.py (Claude Code and Antigravity I/O), tools/set_mode.py,
tools/check_framework_immutable.py and .githooks/pre-commit against throwaway git repos
(main checkout + linked worktree) built in a temp dir. Never touches this repo's git config.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "guard_framework.py"
SET_MODE = ROOT / "tools" / "set_mode.py"
CHECK = ROOT / "tools" / "check_framework_immutable.py"
PRE_COMMIT_DIR = ROOT / ".githooks"

PROFILE = ".claude/skills/job-application-assistant/01-candidate-profile.md"
EVALUATION = ".claude/skills/job-application-assistant/04-job-evaluation.md"
PORTAL = ".agents/skills/demo-search/SKILL.md"
PORTAL_TEXT = "---\nname: demo-search\nenabled: true\n---\n\n# Demo portal\n\nSearch demo jobs.\n"


def git_env() -> dict:
    env = dict(os.environ)
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Jane Doe",
        GIT_AUTHOR_EMAIL="jane@example.com",
        GIT_COMMITTER_NAME="Jane Doe",
        GIT_COMMITTER_EMAIL="jane@example.com",
    )
    env.pop("ALLOW_FRAMEWORK_COMMIT", None)
    return env


class GuardFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(os.path.realpath(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)
        self.env = git_env()
        self.main = self.tmp / "main"
        self.main.mkdir()
        self.git("init", "-q", "-b", "master")
        files = {
            "tools/x.py": "print('framework')\n",
            "tools/framework_paths.py": (ROOT / "tools" / "framework_paths.py").read_text(encoding="utf-8"),
            "tools/personalization_paths.json": (ROOT / "tools" / "personalization_paths.json").read_text(encoding="utf-8"),
            "CLAUDE.md": "# Profile for [YOUR_NAME]\n",
            "README.md": "readme\n",
            PROFILE: "# Candidate\n\n- Python\n",
            EVALUATION: "# Evaluation\n\nStrong: [SKILLS]\n",
            PORTAL: PORTAL_TEXT,
            ".gitignore": "tools/new_jobs_summary.*\n.agents/state/\n.claude/worktrees/\n",
        }
        for rel, text in files.items():
            self.write(self.main / rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.wt = self.tmp / "wt"
        self.git("worktree", "add", "-q", str(self.wt), "-b", "dev")

    # helpers ---------------------------------------------------------------
    def git(self, *args, cwd=None, check=True, env=None):
        r = subprocess.run(["git", *args], cwd=str(cwd or self.main), env=env or self.env,
                           capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(f"git {args} failed: {r.stderr}")
        return r

    @staticmethod
    def write(path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_hook(self, payload, antigravity=False, raw=None):
        args = [sys.executable, str(HOOK)] + (["--antigravity"] if antigravity else [])
        stdin = raw if raw is not None else json.dumps(payload)
        r = subprocess.run(args, input=stdin, capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def claude(self, tool, path, cwd=None, **tool_input):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(cwd or self.main),
                   "tool_input": {key: str(path), **tool_input}}
        r = self.run_hook(payload)
        if not r.stdout.strip():
            return "allow", ""
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        return out["permissionDecision"], out["permissionDecisionReason"]

    def agy(self, name, args, workspace=None):
        payload = {"toolCall": {"name": name, "args": args}, "stepIdx": 3,
                   "conversationId": "c1", "workspacePaths": [str(workspace or self.main)]}
        out = json.loads(self.run_hook(payload, antigravity=True).stdout)
        return out["decision"], out.get("reason", "")

    def set_mode(self, mode):
        r = subprocess.run([sys.executable, str(SET_MODE), mode], cwd=str(self.main), env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout


class ClaudeHookTests(GuardFixture):
    def test_tracked_framework_file_in_main_is_denied(self):
        decision, reason = self.claude("Edit", self.main / "tools/x.py", old_string="framework", new_string="hack")
        self.assertEqual(decision, "deny")
        self.assertIn("Operator mode", reason)
        self.assertIn("tools/report_issue.py", reason)
        self.assertIn("worktree", reason)

    def test_same_file_in_linked_worktree_is_allowed(self):
        self.assertEqual(self.claude("Edit", self.wt / "tools/x.py", cwd=self.wt,
                                     old_string="framework", new_string="fix")[0], "allow")
        self.assertEqual(self.claude("Write", self.wt / "tools/brand_new.py", cwd=self.wt, content="x")[0], "allow")

    def test_gitignored_output_inside_framework_dir_is_allowed(self):
        self.assertEqual(self.claude("Write", self.main / "tools/new_jobs_summary.md", content="jobs")[0], "allow")

    def test_new_file_in_framework_dir_is_denied_but_user_dir_allowed(self):
        self.assertEqual(self.claude("Write", self.main / "tools/yc_profile_filler.py", content="x")[0], "deny")
        self.assertEqual(self.claude("Write", self.main / ".claude/skills/new/SKILL.md", content="x")[0], "deny")
        self.assertEqual(self.claude("Write", self.main / "notes/today.md", content="x")[0], "allow")

    def test_relative_path_resolves_against_cwd(self):
        self.assertEqual(self.claude("Write", "tools/x.py", content="x")[0], "deny")
        self.assertEqual(self.claude("Write", "tools/x.py", cwd=self.wt, content="x")[0], "allow")

    def test_outside_any_repo_is_allowed(self):
        outside = self.tmp / "loose"
        outside.mkdir()
        self.assertEqual(self.claude("Write", outside / "a.txt", cwd=outside, content="x")[0], "allow")

    def test_notebook_and_multiedit_paths(self):
        self.write(self.main / "tools/nb.ipynb", "{}")
        self.git("add", "tools/nb.ipynb")
        self.assertEqual(self.claude("NotebookEdit", self.main / "tools/nb.ipynb", new_source="x")[0], "deny")
        self.assertEqual(self.claude("MultiEdit", self.main / "tools/x.py",
                                     edits=[{"old_string": "framework", "new_string": "y"}])[0], "deny")

    def test_config_mode_unlocks_only_personalization_paths(self):
        new_portal = self.main / ".agents/skills/new-portal/SKILL.md"
        self.assertEqual(self.claude("Write", new_portal, content="x")[0], "deny")
        self.assertIn("config", self.set_mode("config"))
        self.assertEqual(self.claude("Write", new_portal, content="x")[0], "allow")
        # Config mode never unlocks framework code, nor the profile/data templates:
        # candidate data goes to their gitignored .personal copies.
        self.assertEqual(self.claude("Write", self.main / "tools/x.py", content="x")[0], "deny")
        self.assertEqual(self.claude("Write", self.main / EVALUATION, content="x")[0], "deny")
        self.assertEqual(self.claude("Write", self.main / "CLAUDE.md", content="x")[0], "deny")
        self.set_mode("operator")
        self.assertEqual(self.claude("Write", new_portal, content="x")[0], "deny")

    def test_expired_config_mode_falls_back_to_operator(self):
        self.write(self.main / ".agents/state/mode",
                   json.dumps({"mode": "config", "since": int(time.time()) - 5 * 3600}))
        self.assertEqual(self.claude("Write", self.main / EVALUATION, content="x")[0], "deny")

    def test_tracked_profile_template_is_denied_in_operator_mode(self):
        # Regression: 01 used to be an 'always' grant. Facts now go to 01-*.md.personal.
        self.assertEqual(self.claude("Edit", self.main / PROFILE, old_string="- Python", new_string="- Python, Go")[0], "deny")

    def test_portal_enabled_toggle_only(self):
        self.assertEqual(self.claude("Edit", self.main / PORTAL, old_string="enabled: true",
                                     new_string="enabled: false")[0], "allow")
        self.assertEqual(self.claude("Write", self.main / PORTAL,
                                     content=PORTAL_TEXT.replace("enabled: true", "enabled: false"))[0], "allow")
        self.assertEqual(self.claude("Edit", self.main / PORTAL, old_string="Search demo jobs.",
                                     new_string="Search everything.")[0], "deny")
        self.assertEqual(self.claude("Edit", self.main / PORTAL, old_string="enabled: true",
                                     new_string="enabled: false\nallowed-tools: Bash")[0], "deny")

    def test_mode_file_cannot_be_edited_directly(self):
        decision, reason = self.claude("Write", self.main / ".agents/state/mode", content="config")
        self.assertEqual(decision, "deny")
        self.assertIn("set_mode.py", reason)

    def test_git_dir_writes_are_denied(self):
        for target in [self.main / ".git/config", self.main / ".git/hooks/pre-commit",
                       self.main / ".git/hooks/post-checkout"]:
            with self.subTest(target=str(target)):
                decision, reason = self.claude("Write", target, content="x")
                self.assertEqual(decision, "deny")
                self.assertIn("git directory", reason)
        # Also from a linked worktree session: its common dir is the main checkout's .git.
        self.assertEqual(self.claude("Write", self.main / ".git/config", cwd=self.wt, content="x")[0], "deny")
        # A symlink inside the work tree that resolves into .git is caught on its real path.
        link = self.main / "notes" / "cfg"
        link.parent.mkdir()
        try:
            link.symlink_to(self.main / ".git" / "config")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(self.claude("Write", link, content="x")[0], "deny")

    def test_local_settings_is_denied_everywhere(self):
        for root, cwd in [(self.main, self.main), (self.wt, self.wt)]:
            with self.subTest(root=str(root)):
                decision, reason = self.claude("Write", root / ".claude/settings.local.json", cwd=cwd,
                                               content='{"permissions": {"allow": ["Bash"]}}')
                self.assertEqual(decision, "deny")
                self.assertIn("settings.local.json", reason)
        self.assertEqual(self.agy("write_to_file", {"TargetFile": str(self.main / ".claude/settings.local.json"),
                                                    "CodeContent": "{}"})[0], "deny")

    def test_git_failure_warns_before_failing_open(self):
        if os.name == "nt":
            self.skipTest("fake git is a POSIX shell script")
        fake = self.tmp / "fakebin"
        fake.mkdir()
        script = fake / "git"
        script.write_text("#!/bin/sh\necho 'error: unknown option path-format' >&2\nexit 129\n", encoding="utf-8")
        script.chmod(0o755)
        env = dict(self.env, PATH=f"{fake}{os.pathsep}{self.env.get('PATH', '')}")
        payload = {"tool_name": "Write", "cwd": str(self.main),
                   "tool_input": {"file_path": str(self.main / "tools/x.py"), "content": "x"}}
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True,
                           text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("deny", r.stdout)
        self.assertIn("NOT enforced", r.stderr)

    def test_malformed_input_fails_open(self):
        for raw in ["", "not json", "[1, 2]"]:
            with self.subTest(raw=raw):
                r = self.run_hook(None, raw=raw)
                self.assertNotIn("deny", r.stdout)


class AntigravityHookTests(GuardFixture):
    def test_write_to_file_json_encoded_target_denied(self):
        decision, reason = self.agy("write_to_file", {
            "TargetFile": json.dumps(str(self.main / "tools/x.py")),
            "CodeContent": json.dumps("print('hack')\n"), "Overwrite": "true"})
        self.assertEqual(decision, "deny")
        self.assertIn("report_issue.py", reason)

    def test_neutral_answer_is_ask_not_allow(self):
        self.assertEqual(self.agy("write_to_file", {"TargetFile": str(self.main / "notes/a.md"),
                                                    "CodeContent": "x"})[0], "ask")
        self.assertEqual(self.agy("write_to_file", {"TargetFile": str(self.wt / "tools/x.py"),
                                                    "CodeContent": "x"}, workspace=self.wt)[0], "ask")

    def test_replace_file_content_enabled_toggle(self):
        args = {"TargetFile": str(self.main / PORTAL), "TargetContent": "enabled: true",
                "ReplacementContent": "enabled: false", "AllowMultiple": "false"}
        self.assertEqual(self.agy("replace_file_content", args)[0], "ask")
        args["ReplacementContent"] = "enabled: false\nextra: 1"
        self.assertEqual(self.agy("replace_file_content", args)[0], "deny")

    def test_multi_replace_on_framework_denied(self):
        chunks = [{"TargetContent": "framework", "ReplacementContent": "y"}]
        self.assertEqual(self.agy("multi_replace_file_content", {
            "TargetFile": str(self.main / "tools/x.py"), "ReplacementChunks": json.dumps(chunks)})[0], "deny")

    def test_relative_target_uses_workspace(self):
        self.assertEqual(self.agy("write_to_file", {"TargetFile": "tools/x.py", "CodeContent": "x"})[0], "deny")

    def test_malformed_input_answers_ask(self):
        out = json.loads(self.run_hook(None, antigravity=True, raw="garbage").stdout)
        self.assertEqual(out["decision"], "ask")


class CheckFrameworkImmutableTests(GuardFixture):
    def check(self, *extra, repo=None):
        return subprocess.run([sys.executable, str(CHECK), "--repo", str(repo or self.main), *extra],
                              capture_output=True, text=True, env=self.env, timeout=120)

    def test_clean_checkout_passes(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_modified_and_new_framework_files_fail(self):
        self.write(self.main / "tools/x.py", "changed\n")
        self.write(self.main / "tools/sub/new_tool.py", "new\n")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("tools/x.py", r.stdout)
        self.assertIn("tools/sub/new_tool.py", r.stdout)
        self.assertIn("git restore", r.stdout)

    def test_user_data_and_always_paths_pass(self):
        self.write(self.main / "tools/new_jobs_summary.md", "ignored\n")
        self.write(self.main / "notes/today.md", "user notes\n")
        self.write(self.main / PORTAL, PORTAL_TEXT.replace("enabled: true", "enabled: false"))
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_operator_write_to_tracked_profile_is_drift(self):
        self.write(self.main / PROFILE, "# Candidate\n\n- Python\n- Rust\n")
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(PROFILE, r.stdout)

    def test_setup_output_in_personal_copies_is_not_drift_in_any_mode(self):
        # /setup writes CLAUDE.md.personal and the skill files' .personal copies; once back
        # in operator mode, no /scrape|/rank|/apply drift check may report them.
        with open(self.main / ".gitignore", "a", encoding="utf-8") as fh:
            fh.write("*.personal\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore personal")
        self.set_mode("config")
        self.write(self.main / (EVALUATION + ".personal"), "# Evaluation\n\nStrong: Python\n")
        self.write(self.main / "CLAUDE.md.personal", "# Profile for Jane Doe\n")
        self.assertEqual(self.check().returncode, 0)
        self.set_mode("operator")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        # ...while the tracked templates themselves are framework: editing one is drift.
        self.write(self.main / "CLAUDE.md", "# Profile for Jane Doe\n")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("CLAUDE.md", r.stdout)
        self.assertNotIn("CLAUDE.md.personal", r.stdout)

    def test_existing_portal_and_template_code_changes_are_drift(self):
        # Regression: the personalization globs .agents/skills/** and templates/** must not hide
        # shell patches to existing portal CLI code from the backstop.
        self.write(self.main / ".agents/skills/demo-search/cli/src/cli.ts", "// patched by sed\n")
        self.write(self.main / PORTAL, PORTAL_TEXT + "\nallowed-tools: Bash(*)\n")
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(".agents/skills/demo-search/cli/src/cli.ts", r.stdout)
        self.assertIn(PORTAL, r.stdout)

    def test_brand_new_portal_and_template_dirs_are_not_drift(self):
        # /add-portal and /add-template create whole new directories; uncommitted, they are config.
        self.write(self.main / ".agents/skills/newboard-search/SKILL.md", "---\nname: newboard-search\n---\n")
        self.write(self.main / ".agents/skills/newboard-search/cli/src/cli.ts", "// new portal\n")
        self.write(self.main / "templates/cv/fancy/main.tex", "% template\n")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        # ...but a new file dropped into an EXISTING portal dir is drift.
        self.write(self.main / ".agents/skills/demo-search/cli/src/hack.ts", "// new file\n")
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("demo-search/cli/src/hack.ts", r.stdout)

    def test_enabled_toggle_with_trailing_comment_is_not_drift(self):
        commented = PORTAL_TEXT.replace("enabled: true", "enabled: true  # set to false to disable")
        self.write(self.main / PORTAL, commented)
        self.git("commit", "-qam", "comment")
        self.write(self.main / PORTAL, commented.replace("enabled: true ", "enabled: false "))
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_linked_worktree_always_passes(self):
        self.write(self.wt / "tools/x.py", "dev change\n")
        r = self.check(repo=self.wt)
        self.assertEqual(r.returncode, 0)
        self.assertIn("linked worktree", r.stdout)

    def test_report_calls_report_issue_with_paths_only(self):
        log = self.tmp / "report_args.json"
        self.write(self.main / "tools/report_issue.py",
                   "import json, sys\n"
                   f"open({str(log)!r}, 'w').write(json.dumps(sys.argv[1:]))\n")
        self.git("add", "tools/report_issue.py")
        self.git("commit", "-q", "-m", "stub")
        self.write(self.main / "tools/x.py", "secret content jane@example.com\n")
        r = self.check("--report")
        self.assertEqual(r.returncode, 1)
        args = json.loads(log.read_text())
        self.assertEqual(args[args.index("--kind") + 1], "drift")
        body = args[args.index("--body") + 1]
        self.assertIn("tools/x.py", body)
        self.assertNotIn("jane@example.com", body)

    def test_report_without_report_issue_tool_still_exits_1(self):
        self.write(self.main / "tools/x.py", "changed\n")
        r = self.check("--report")
        self.assertEqual(r.returncode, 1)
        self.assertIn("report_issue.py not available", r.stderr)


class PreCommitHookTests(GuardFixture):
    def setUp(self):
        super().setUp()
        # Only the throwaway repo's config is touched, never the real one.
        self.git("config", "core.hooksPath", str(PRE_COMMIT_DIR))

    def test_hook_is_executable(self):
        self.assertTrue((PRE_COMMIT_DIR / "pre-commit").stat().st_mode & stat.S_IXUSR)
        # A CRLF checkout would break the shebang; .gitattributes pins eol=lf.
        self.assertIn(".githooks/* text eol=lf", (ROOT / ".gitattributes").read_text(encoding="utf-8"))

    def test_framework_commit_in_main_rejected(self):
        self.write(self.main / "tools/x.py", "changed\n")
        self.git("add", "tools/x.py")
        r = self.git("commit", "-q", "-m", "hack", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tools/x.py", r.stderr)

    def test_override_env_allows(self):
        self.write(self.main / "tools/x.py", "changed\n")
        self.git("add", "tools/x.py")
        env = dict(self.env, ALLOW_FRAMEWORK_COMMIT="1")
        self.assertEqual(self.git("commit", "-q", "-m", "merge", env=env, check=False).returncode, 0)

    def test_personalization_commit_in_main_allowed(self):
        self.write(self.main / PORTAL, PORTAL_TEXT.replace("enabled: true", "enabled: false"))
        self.git("add", PORTAL)
        self.assertEqual(self.git("commit", "-q", "-m", "toggle portal", check=False).returncode, 0)

    def test_profile_template_commit_in_main_rejected(self):
        # Personal data in a tracked template would be published by a push.
        self.write(self.main / "CLAUDE.md", "# Profile for Jane Doe\n")
        self.git("add", "CLAUDE.md")
        r = self.git("commit", "-q", "-m", "profile", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("CLAUDE.md", r.stderr)

    def test_framework_commit_in_worktree_allowed(self):
        self.write(self.wt / "tools/x.py", "fix\n")
        self.git("add", "tools/x.py", cwd=self.wt)
        r = self.git("commit", "-q", "-m", "fix", cwd=self.wt, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)


class RegistrationTests(unittest.TestCase):
    def test_claude_settings_registers_allowlisted_hook(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import security_guards

        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        groups = settings["hooks"]["PreToolUse"]
        self.assertEqual(groups[0]["matcher"], "Edit|Write|MultiEdit|NotebookEdit")
        command = groups[0]["hooks"][0]["command"]
        self.assertIn(".claude/hooks/guard_framework.py", command)
        self.assertIn(f"PreToolUse:{command}", security_guards.ALLOWED_HOOKS)
        for entry in ["Bash(git commit:*)", "Bash(git push:*)", "Bash(git reset:*)", "Bash(git checkout --:*)"]:
            self.assertIn(entry, settings["permissions"]["ask"])

    def test_antigravity_hooks_json(self):
        data = json.loads((ROOT / ".agents" / "hooks.json").read_text(encoding="utf-8"))
        group = data["operator-mode-framework-guard"]["PreToolUse"][0]
        for tool in ["write_to_file", "replace_file_content", "multi_replace_file_content"]:
            self.assertIn(tool, group["matcher"])
        # Antigravity runs hook commands from the directory holding hooks.json (.agents/).
        self.assertEqual(group["hooks"][0]["command"], "python3 ../.claude/hooks/guard_framework.py --antigravity")

    def test_state_and_worktrees_are_gitignored(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".claude/worktrees/", lines)
        self.assertIn(".agents/state/", lines)

    def test_framework_dev_agent_uses_worktree_isolation(self):
        text = (ROOT / ".claude" / "agents" / "framework-dev.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        self.assertIn("isolation: worktree", front)
        self.assertIn("name: framework-dev", front)

    def test_config_commands_switch_mode(self):
        for name in ["setup", "reset", "expand", "add-portal", "add-template"]:
            with self.subTest(command=name):
                text = (ROOT / ".claude" / "commands" / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn("python3 tools/set_mode.py config", text)
                self.assertIn("python3 tools/set_mode.py operator", text)

    def test_operator_commands_end_with_drift_check(self):
        for rel in [".claude/commands/rank.md", ".claude/commands/apply.md", ".claude/skills/job-scraper/SKILL.md",
                    ".claude/commands/interview.md", ".claude/commands/outcome.md",
                    ".claude/commands/linkedin-apply.md"]:
            with self.subTest(path=rel):
                self.assertIn("python3 tools/check_framework_immutable.py --report",
                              (ROOT / rel).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
