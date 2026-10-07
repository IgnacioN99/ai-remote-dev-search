"""Tests for tools/sync_agent_skills.py - the .claude/ -> .agents/skills generator.

Each fixture test copies the script into a throwaway repo root (the script
resolves ROOT from its own location) and runs it as a subprocess, so the real
.agents/skills tree is never touched. The last class checks the real repo.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "sync_agent_skills.py"
LINTER = REPO_ROOT / "tools" / "lint_skills.py"

APPLY_SRC = (
    "# /apply - Drafter-Reviewer Job Application Workflow\n\n"
    "The posting is `$ARGUMENTS`.\n\n"
    "- If `$ARGUMENTS` looks like a URL, use `WebFetch` to retrieve it.\n"
    "- Research with WebSearch.\n"
    "Use the **Agent tool** to spawn a `general-purpose` reviewer agent.\n"
    "Ask with AskUserQuestion.\n"
    "Read `.claude/skills/job-application-assistant/04-job-evaluation.md` and `04-job-evaluation.md`.\n"
    "See `.claude/commands/rank.md` for ranking.\n"
)
GMAIL_SRC = (
    "# /gmail-sync - Sync\n\n"
    "Confirm the Gmail MCP tools (`mcp__claude_ai_Gmail__*`) are available.\n"
    "Call `mcp__claude_ai_Gmail__search_threads` then mcp__gmail__get_thread.\n"
    "Check tool names starting with `mcp__notion__` or similar; use mcp__notion__notion-search.\n"
    "Also mcp__claude_ai_Slack__slack_send_message and `mcp__playwright__*`.\n"
    "Then read both PDFs via the Read tool and verify.\n"
    "Read the PDF with the Read tool. Use the Read tool on the PDF output.\n"
    "Do NOT use the Read tool on the draft files.\n"
)
RANK_SRC = "# /rank - Triage\n\nDispatch parallel `general-purpose` agents via the **Agent tool**.\n"
SCRAPER_SRC = (
    "---\nname: scrape\ndescription: >\n  Finds jobs.\n"
    "allowed-tools: Read, WebFetch, Agent\nmodel: opus\n---\n\n"
    "# Job Scraper\n\nRead `search-queries.md` (this directory) for the search strategy.\n"
    "Run CLIs in parallel using the Agent tool.\n"
)
ASSISTANT_SRC = (
    "---\nname: job-application-assistant\ndescription: >\n  Assists.\n"
    "allowed-tools: Read\nframework_version: 1.3.4\n---\n\n"
    "# Job Application Assistant\n\nFollow `/apply` Step 6b (`.claude/commands/apply.md`).\n"
    "| `01-candidate-profile.md` | profile |\n"
)
UPSKILL_SRC = "---\nname: upskill\ndescription: Gaps.\n---\n\n# Upskill\n\nUse WebSearch.\n"
PORTAL_SRC = "---\nname: linkedin-search\ndescription: LinkedIn.\n---\n\n# LinkedIn\n"


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


class FixtureRepo(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "tools").mkdir()
        shutil.copy(SCRIPT, self.root / "tools" / "sync_agent_skills.py")
        claude = self.root / ".claude"
        write(claude / "commands" / "apply.md", APPLY_SRC)
        write(claude / "commands" / "rank.md", RANK_SRC)
        write(claude / "commands" / "gmail-sync.md", GMAIL_SRC)
        write(claude / "skills" / "job-scraper" / "SKILL.md", SCRAPER_SRC)
        write(claude / "skills" / "job-scraper" / "search-queries.md", "# queries\n")
        write(claude / "skills" / "job-application-assistant" / "SKILL.md", ASSISTANT_SRC)
        write(claude / "skills" / "job-application-assistant" / "01-candidate-profile.md", "# p\n")
        write(claude / "skills" / "job-application-assistant" / "04-job-evaluation.md", "# e\n")
        write(claude / "skills" / "upskill" / "SKILL.md", UPSKILL_SRC)
        self.portal = self.root / ".agents" / "skills" / "linkedin-search" / "SKILL.md"
        write(self.portal, PORTAL_SRC)
        self.skills = self.root / ".agents" / "skills"

    def run_sync(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.root / "tools" / "sync_agent_skills.py"), *args],
            capture_output=True, text=True, encoding="utf-8",
        )

    def generated(self, name: str) -> str:
        return (self.skills / name / "SKILL.md").read_text(encoding="utf-8")


class GenerationTests(FixtureRepo):
    def test_generates_every_command_and_skill(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("apply", "rank", "gmail-sync", "scrape", "job-application-assistant", "upskill"):
            self.assertTrue((self.skills / name / "SKILL.md").is_file(), name)
        # job-scraper is published under its `name:`, not its folder.
        self.assertFalse((self.skills / "job-scraper").exists())

    def test_frontmatter_and_header(self):
        self.run_sync()
        text = self.generated("apply")
        self.assertTrue(text.startswith("---\nname: apply\ndescription: >-\n"))
        self.assertIn("framework_version: 1.0.0\n", text)
        self.assertIn("GENERATED by tools/sync_agent_skills.py", text)
        self.assertIn("Source: .claude/commands/apply.md", text)
        self.assertIn("Invoked as `/apply`", text)
        self.assertIn("`$ARGUMENTS`", text)
        # Source framework_version is carried over.
        self.assertIn("framework_version: 1.3.4\n", self.generated("job-application-assistant"))

    def test_claude_only_frontmatter_is_dropped(self):
        self.run_sync()
        text = self.generated("scrape")
        frontmatter = text.split("\n---\n", 1)[0]
        self.assertNotIn("allowed-tools", frontmatter)
        self.assertNotIn("model:", frontmatter)
        self.assertIn("name: scrape", frontmatter)

    def test_tool_and_path_rewrites(self):
        self.run_sync()
        apply_md = self.generated("apply")
        self.assertNotIn("WebFetch", apply_md)
        self.assertNotIn("WebSearch", apply_md)
        self.assertNotIn("AskUserQuestion", apply_md)
        self.assertNotIn("Agent tool", apply_md)
        self.assertIn("use `read_url_content` to retrieve it", apply_md)
        self.assertIn("Research with search_web", apply_md)
        self.assertIn("Use `invoke_subagent` (if available; otherwise do the work inline yourself)", apply_md)
        self.assertIn("ask the user in chat", apply_md)
        self.assertIn("`.agents/skills/rank/SKILL.md`", apply_md)
        # Bare data-file names are qualified; already-qualified ones are not doubled.
        self.assertEqual(apply_md.count("`.claude/skills/job-application-assistant/04-job-evaluation.md`"), 2)
        self.assertNotIn(".claude/skills/job-application-assistant/.claude", apply_md)

        scrape = self.generated("scrape")
        self.assertIn("Read `.claude/skills/job-scraper/search-queries.md` for", scrape)
        self.assertNotIn("(this directory)", scrape)
        self.assertIn("`.agents/skills/apply/SKILL.md`", self.generated("job-application-assistant"))
        self.assertIn("general-purpose subagents via `invoke_subagent`", self.generated("rank"))

    def test_mcp_tool_names_are_rewritten(self):
        self.run_sync()
        text = self.generated("gmail-sync")
        self.assertNotIn("mcp__", text)
        self.assertIn("Confirm the Gmail MCP tools are available.", text)
        self.assertIn("Call the Gmail MCP tools (search_threads) then the Gmail MCP tools (get_thread).", text)
        self.assertIn("tool names from the Notion MCP server or similar", text)
        self.assertIn("use the Notion MCP tools (notion-search)", text)
        self.assertIn("the Slack MCP tool `slack_send_message`", text)
        self.assertIn("the playwright MCP tools.", text)

    def test_pdf_read_tool_phrases_become_visual_inspection(self):
        self.run_sync()
        text = self.generated("gmail-sync")
        self.assertIn("Then open both compiled PDFs and inspect each page visually "
                      "(render to images if your runtime cannot view PDFs) and verify.", text)
        self.assertIn("Open the compiled PDF and inspect each page visually", text)
        self.assertIn("cannot view PDFs). Open the compiled PDF and inspect each page visually", text)
        self.assertNotIn("Read tool on the PDF", text)
        # A Read-tool mention that is not about a PDF is left alone.
        self.assertIn("Do NOT use the Read tool on the draft files.", text)

    def test_allowed_tools_become_a_neutral_tools_line(self):
        self.run_sync()
        scrape = self.generated("scrape")
        self.assertIn("> Tools this skill needs: read and search files; fetch URLs (read_url_content); "
                      "subagents (`invoke_subagent` if available, otherwise inline).", scrape)
        self.assertIn("> Tools this skill needs: read and search files.", self.generated("job-application-assistant"))
        self.assertNotIn("Tools this skill needs", self.generated("apply"))

    def test_bash_allowed_tools_list_their_commands(self):
        write(self.root / ".claude" / "skills" / "upskill" / "SKILL.md",
              "---\nname: upskill\ndescription: Gaps.\n"
              "allowed-tools: Read, Bash(python3 tools/job_key.py:*), Bash(bun run x/cli.ts *), AskUserQuestion\n"
              "---\n\n# Upskill\n")
        self.run_sync()
        self.assertIn("> Tools this skill needs: read and search files; terminal "
                      "(`python3 tools/job_key.py`, `bun run x/cli.ts`); ask the user in chat.",
                      self.generated("upskill"))

    def test_every_description_names_its_slash_command(self):
        self.run_sync()
        for name in ("apply", "rank", "gmail-sync", "scrape", "job-application-assistant", "upskill"):
            with self.subTest(name=name):
                front = self.generated(name).split("\n---\n", 1)[0]
                desc = " ".join(line.strip() for line in front.split("description: >-\n", 1)[1]
                                .split("\nframework_version:", 1)[0].splitlines())
                self.assertTrue(desc.endswith(f"Also triggered by /{name}."), desc)
                self.assertLessEqual(len(desc), 1024)

    def test_data_files_are_not_copied(self):
        self.run_sync()
        self.assertFalse((self.skills / "job-application-assistant" / "01-candidate-profile.md").exists())
        self.assertFalse((self.skills / "scrape" / "search-queries.md").exists())

    def test_portal_skill_untouched_and_gets_skillignore(self):
        self.run_sync()
        self.assertEqual(self.portal.read_text(encoding="utf-8"), PORTAL_SRC)
        ignore = (self.portal.parent / ".skillignore").read_text(encoding="utf-8")
        for pattern in ("node_modules/", "**/node_modules/**", "bun.lock", "package-lock.json", "dist/"):
            self.assertIn(pattern, ignore.splitlines())
        self.assertFalse((self.skills / "apply" / ".skillignore").exists())

    def test_refuses_to_overwrite_hand_written_skill(self):
        write(self.root / ".claude" / "commands" / "linkedin-search.md", "# /linkedin-search - X\n")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite hand-written skill", result.stdout + result.stderr)
        self.assertEqual(self.portal.read_text(encoding="utf-8"), PORTAL_SRC)

    def test_missing_description_fails_loudly(self):
        write(self.root / ".claude" / "commands" / "brand-new.md", "# /brand-new - X\n")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no description for 'brand-new'", result.stdout + result.stderr)


class CheckAndIdempotencyTests(FixtureRepo):
    def test_check_fails_before_generation_and_passes_after(self):
        before = self.run_sync("--check")
        self.assertEqual(before.returncode, 1)
        self.assertIn("missing: .agents/skills/apply/SKILL.md", before.stdout)
        self.assertFalse((self.skills / "apply").exists(), "--check must not write")
        self.run_sync()
        after = self.run_sync("--check")
        self.assertEqual(after.returncode, 0, after.stdout)

    def test_source_edit_is_drift(self):
        self.run_sync()
        write(self.root / ".claude" / "commands" / "rank.md", RANK_SRC + "New step.\n")
        result = self.run_sync("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("drifted: .agents/skills/rank/SKILL.md", result.stdout)

    def test_hand_edit_of_generated_copy_is_drift(self):
        self.run_sync()
        target = self.skills / "apply" / "SKILL.md"
        target.write_text(target.read_text(encoding="utf-8") + "hand edit\n", encoding="utf-8")
        self.assertEqual(self.run_sync("--check").returncode, 1)
        self.run_sync()
        self.assertNotIn("hand edit", target.read_text(encoding="utf-8"))

    def test_second_run_is_a_no_op(self):
        self.run_sync()
        snapshot = {p: p.read_bytes() for p in self.skills.rglob("*") if p.is_file()}
        result = self.run_sync()
        self.assertIn("0 written, 0 removed", result.stdout)
        self.assertEqual(snapshot, {p: p.read_bytes() for p in self.skills.rglob("*") if p.is_file()})

    def test_crlf_sources_and_outputs_do_not_flap(self):
        self.run_sync()
        lf_output = self.generated("apply")
        # Windows checkouts (core.autocrlf) see CRLF in both sources and outputs.
        write(self.root / ".claude" / "commands" / "apply.md", APPLY_SRC, newline="\r\n")
        target = self.skills / "apply" / "SKILL.md"
        target.write_bytes(lf_output.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.run_sync("--check").returncode, 0)

    def test_removed_command_leaves_stale_copy_that_is_cleaned(self):
        self.run_sync()
        (self.root / ".claude" / "commands" / "rank.md").unlink()
        check = self.run_sync("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("stale (source removed): .agents/skills/rank/SKILL.md", check.stdout)
        self.run_sync()
        self.assertFalse((self.skills / "rank").exists())
        self.assertTrue(self.portal.is_file())


class ForbiddenTokenTests(FixtureRepo):
    def test_unrewritable_token_fails_check_and_write(self):
        self.run_sync()
        write(self.root / ".claude" / "commands" / "rank.md", RANK_SRC + "Tools are prefixed mcp__ in Claude.\n")
        check = self.run_sync("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("still contain Claude-only tokens", check.stdout)
        self.assertIn(".agents/skills/rank/SKILL.md: mcp__", check.stdout)
        before = self.generated("rank")
        result = self.run_sync()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.generated("rank"), before, "a leaking skill must not be written")


class LintIntegrationTests(FixtureRepo):
    def test_lint_skills_fails_on_drift(self):
        shutil.copy(LINTER, self.root / "tools" / "lint_skills.py")
        (self.root / "tools" / "yaml.py").write_text(
            "class YAMLError(Exception):\n    pass\n\n"
            "def safe_load(text):\n    result = {}\n"
            "    for line in (text or '').splitlines():\n"
            "        if ':' in line and not line.startswith(' '):\n"
            "            key, _, value = line.partition(':')\n"
            "            result[key.strip()] = value.strip() or 'x'\n"
            "    return result\n",
            encoding="utf-8",
        )
        write(self.root / ".claude" / "settings.json", '{"permissions": {"allow": []}}')
        lint = [sys.executable, str(self.root / "tools" / "lint_skills.py")]
        drift = subprocess.run(lint, capture_output=True, text=True)
        self.assertEqual(drift.returncode, 1, drift.stdout)
        self.assertIn("generated Antigravity skills drifted", drift.stdout)
        self.run_sync()
        clean = subprocess.run(lint, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0, clean.stdout)


class RealRepoTests(unittest.TestCase):
    def test_repo_is_in_sync(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_sources_leave_no_claude_only_constructs(self):
        commands = sorted(p.stem for p in (REPO_ROOT / ".claude" / "commands").glob("*.md"))
        names = commands + ["scrape", "upskill", "job-application-assistant"]
        for name in names:
            with self.subTest(name=name):
                text = (REPO_ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                for construct in ("WebFetch", "WebSearch", "AskUserQuestion", "Agent tool", "mcp__"):
                    self.assertNotIn(construct, text)
                frontmatter = text.split("\n---\n", 1)[0]
                self.assertNotIn("allowed-tools", frontmatter)
                body = text.split("-->", 1)[1]  # past the header's Source: comment
                self.assertNotIn(".claude/commands/", body)


if __name__ == "__main__":
    unittest.main()
