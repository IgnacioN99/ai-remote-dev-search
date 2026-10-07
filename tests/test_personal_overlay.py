"""Tests for the personal overlay (tools/personal_overlay.py) and its migration
(tools/migrate_personal_overlay.py), plus the specs and tools that honor it.

Stdlib only; every fixture lives in a temp dir with fictional data.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools import migrate_personal_overlay as mig  # noqa: E402
from tools import personal_overlay as po  # noqa: E402
from tools.candidate_profile import load_candidate_profile  # noqa: E402
import report_issue  # noqa: E402
from tests.test_guard_framework import GuardFixture, git_env  # noqa: E402

SKILL = ".claude/skills/job-application-assistant"
EVAL = f"{SKILL}/04-job-evaluation.md"
BEHAV = f"{SKILL}/02-behavioral-profile.md"
QUERIES = ".claude/skills/job-scraper/search-queries.md"
COVER = f"{SKILL}/06-cover-letter-templates.md"
MASTER_CV = "cv/main_example.tex"


class OverlayHelperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.tracked = self.root / EVAL
        self.tracked.parent.mkdir(parents=True)
        self.tracked.write_text("---\nframework_version: 1.2.0\n---\nStrong: [YOUR_PRIMARY_SKILLS]\n", encoding="utf-8")

    def test_resolve_prefers_personal_only_when_it_exists(self):
        self.assertEqual(po.resolve(EVAL, self.root), self.tracked)
        personal = po.personal_path(EVAL, self.root)
        personal.write_text("Strong: Fortran\r\n", encoding="utf-8", newline="")
        self.assertEqual(po.resolve(EVAL, self.root), personal)
        self.assertEqual(po.read_text(EVAL, self.root), "Strong: Fortran\n")
        self.assertEqual(po.resolve(personal), personal)

    def test_ensure_copies_template_once_and_never_overwrites(self):
        target = po.ensure_personal(EVAL, self.root)
        self.assertEqual(target.name, "04-job-evaluation.md.personal")
        self.assertEqual(target.read_text(encoding="utf-8"), self.tracked.read_text(encoding="utf-8"))
        target.write_text("mine\n", encoding="utf-8")
        po.ensure_personal(EVAL, self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "mine\n")

    def test_ensure_drops_claude_md_self_import(self):
        (self.root / "CLAUDE.md").write_text("# Profile\n@CLAUDE.md.personal\n- **Name:** [YOUR_NAME]\n",
                                             encoding="utf-8")
        text = po.ensure_personal("CLAUDE.md", self.root).read_text(encoding="utf-8")
        self.assertNotIn("@CLAUDE.md.personal", text)
        self.assertIn("[YOUR_NAME]", text)

    def test_status_flags_stale_personal_copy(self):
        rows = {r["path"]: r for r in po.status(self.root)}
        self.assertFalse(rows[EVAL]["has_personal"])
        po.personal_path(EVAL, self.root).write_text("---\nframework_version: 1.1.9\n---\nx\n", encoding="utf-8")
        row = {r["path"]: r for r in po.status(self.root)}[EVAL]
        self.assertTrue(row["has_personal"])
        self.assertTrue(row["stale"])
        self.assertEqual(row["reads"], EVAL + ".personal")
        po.personal_path(EVAL, self.root).write_text("---\nframework_version: 1.2.0\n---\nx\n", encoding="utf-8")
        self.assertFalse({r["path"]: r for r in po.status(self.root)}[EVAL]["stale"])

    def test_candidate_profile_reads_claude_md_personal(self):
        (self.root / "CLAUDE.md").write_text("### Identity\n- **Name:** [YOUR_NAME]\n", encoding="utf-8")
        (self.root / "CLAUDE.md.personal").write_text(
            "### Identity\n- **Name:** Jane Q Public\n- **Email:** jane@example.com\n", encoding="utf-8")
        self.assertEqual(load_candidate_profile(self.root).name, "Jane Q Public")

    def test_report_issue_identity_reads_personal(self):
        md = self.root / "CLAUDE.md"
        md.write_text("### Identity\n- **Name:** [YOUR_NAME]\n### Education\n", encoding="utf-8")
        self.assertEqual(report_issue.load_claude_identity(md), [])
        (self.root / "CLAUDE.md.personal").write_text(
            "### Identity\n- **Name:** Jane Q Public\n### Education\n", encoding="utf-8")
        self.assertIn("Jane Q Public", report_issue.load_claude_identity(md))


class MigrationTests(unittest.TestCase):
    """Throwaway repo: commit A has personalized tracked files, commit B adds the
    overlay tool and turns them back into templates (the state after pulling)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(os.path.realpath(self._tmp.name))
        self.env = git_env()
        self.git("init", "-q", "-b", "master")
        self.write(".gitignore", "*.personal\ndocuments/memory/**\n")
        self.write(EVAL, "---\nframework_version: 1.0.0\n---\nScoring\nStrong: Fortran, COBOL\n")
        self.write(BEHAV, "Overview: steady\n")
        self.write(QUERIES, "Queries\nsite:example.org fortran\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "personalized")
        self.write(EVAL, "---\nframework_version: 1.0.1\n---\nScoring\nStrong: [YOUR_PRIMARY_SKILLS]\n")
        self.write(BEHAV, "Overview: [SUMMARY]\n")
        self.write(QUERIES, "Queries\nsite:[YOUR_JOB_BOARD]\n")
        self.write("tools/personal_overlay.py", "# overlay\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "overlay")

    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=str(self.root), env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def run_mig(self, *args, files=(EVAL, BEHAV, QUERIES)):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = mig.main(["--root", str(self.root), "--files", *files, *args])
        self.assertEqual(rc, 0)
        return out.getvalue()

    def test_auto_rev_is_commit_before_overlay(self):
        first = self.git("rev-list", "--max-parents=0", "HEAD").strip()
        self.assertEqual(mig.auto_rev(self.root), first)

    def test_dry_run_writes_nothing(self):
        out = self.run_mig()
        self.assertIn("[create  ] " + EVAL, out)
        self.assertIn("Dry run", out)
        self.assertFalse((self.root / (EVAL + ".personal")).exists())
        self.assertFalse((self.root / "documents").exists())

    def test_apply_creates_missing_and_never_overwrites_existing(self):
        self.write(QUERIES + ".personal", "Queries\nsite:example.net cobol\n")  # user's own, different
        self.write(BEHAV + ".personal", "Overview: steady\n")  # already identical
        out = self.run_mig("--apply")
        # Personal content carried over with its SOURCE version, so status flags it
        # stale until the framework changes in the newer template are merged in.
        self.assertEqual((self.root / (EVAL + ".personal")).read_text(encoding="utf-8"),
                         "---\nframework_version: 1.0.0\n---\nScoring\nStrong: Fortran, COBOL\n")
        row = {r["path"]: r for r in po.status(self.root)}[EVAL]
        self.assertTrue(row["stale"], row)
        self.assertEqual((self.root / (QUERIES + ".personal")).read_text(encoding="utf-8"),
                         "Queries\nsite:example.net cobol\n")
        incoming = self.root / (QUERIES.replace(".md", ".md.incoming.personal"))
        self.assertEqual(incoming.read_text(encoding="utf-8"), "Queries\nsite:example.org fortran\n")
        self.assertIn("Manual merge needed", out)
        self.assertFalse((self.root / (BEHAV + ".incoming.personal")).exists())
        backups = list((self.root / "documents" / "memory").glob("backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / (QUERIES + ".personal")).is_file())
        # Everything written is gitignored: nothing personal can be committed.
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_crlf_only_difference_is_identical(self):
        p = self.root / (BEHAV + ".personal")
        p.write_text("Overview: steady\r\n", encoding="utf-8", newline="")
        out = self.run_mig()
        self.assertIn("already identical", out)

    def test_framework_text_changed_after_overlay_is_not_personal(self):
        # 06 held no personal data: identical at the source and at the overlay; a
        # later framework commit rewrote its rules. Nothing must be carried.
        self.git("checkout", "-q", "HEAD~1")
        self.write(COVER, "Cover rules v1\nKeep it short\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "cover at source")
        source = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "master")
        self.write(COVER, "Cover rules v1\nKeep it short\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "cover at overlay era")
        self.write(COVER, "Cover rules v2\nKeep it to one page\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "framework update")
        out = self.run_mig("--apply", "--from-rev", source, files=(COVER,))
        self.assertIn("[skip    ] " + COVER, out)
        self.assertFalse((self.root / (COVER + ".personal")).exists())
        self.assertFalse((self.root / (COVER + ".incoming.personal")).exists())

    def test_framework_changes_after_overlay_do_not_count_as_personal_lines(self):
        self.write(EVAL, "---\nframework_version: 1.1.0\n---\nScoring v2\nStrong: [YOUR_PRIMARY_SKILLS]\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "framework update")
        out = self.run_mig(files=(EVAL,))
        # Only "Strong: Fortran, COBOL" and the old version line are outside every template.
        self.assertIn("[create  ] " + EVAL, out)
        self.assertNotIn("Scoring", "".join(
            sorted(mig._lines("Scoring\n") - mig.template_lines(self.root, EVAL))))

    def test_apply_is_idempotent(self):
        self.write(QUERIES + ".personal", "Queries\nsite:example.net cobol\n")
        self.run_mig("--apply")
        incoming = self.root / (QUERIES + ".incoming.personal")
        backups = sorted((self.root / "documents" / "memory").glob("backup-*"))
        self.assertEqual(len(backups), 1)
        older = incoming.stat().st_mtime_ns - 10**9
        os.utime(incoming, ns=(older, older))
        out = self.run_mig("--apply")
        self.assertIn("Nothing to write", out)
        self.assertEqual(incoming.stat().st_mtime_ns, older, "incoming must not be rewritten")
        self.assertEqual(sorted((self.root / "documents" / "memory").glob("backup-*")), backups)

    def test_stale_incoming_with_only_template_text_is_reported_safe(self):
        self.write(EVAL + ".personal", "---\nframework_version: 1.0.0\n---\nScoring\nStrong: Fortran, COBOL\n")
        self.write(EVAL + ".incoming.personal",
                   "---\nframework_version: 1.0.1\n---\nScoring\nStrong: [YOUR_PRIMARY_SKILLS]\n")
        out = self.run_mig(files=(EVAL,))
        self.assertIn("0 genuinely personal line(s)", out)
        self.assertIn("likely safe to delete", out)

    def test_master_cv_is_carried_from_the_working_tree(self):
        self.write(MASTER_CV, "\\name{[First]}{[Last]}\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "master cv template")
        self.write(MASTER_CV, "\\name{Jane}{Public}\n")  # /setup edited it in place, uncommitted
        out = self.run_mig("--apply", files=(MASTER_CV,))
        self.assertIn("[create  ] " + MASTER_CV, out)
        self.assertEqual((self.root / (MASTER_CV + ".personal")).read_text(encoding="utf-8"),
                         "\\name{Jane}{Public}\n")
        self.assertIn(MASTER_CV, po.OVERLAY_FILES)

    def test_template_only_file_is_skipped(self):
        self.write(f"{SKILL}/03-writing-style.md", "Rules\n")
        out = io.StringIO()
        with redirect_stdout(out):
            mig.main(["--root", str(self.root), "--files", f"{SKILL}/03-writing-style.md"])
        self.assertIn("not present at", out.getvalue())


class GuardAllowsPersonalFiles(GuardFixture):
    def setUp(self):
        super().setUp()
        with open(self.main / ".gitignore", "a", encoding="utf-8") as fh:
            fh.write("*.personal\n*.personal.md\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "ignore personal")

    def test_personal_overlay_writable_in_operator_mode(self):
        for rel in ("CLAUDE.md.personal", f"{SKILL}/04-job-evaluation.md.personal",
                    f"{SKILL}/04-job-evaluation.md.incoming.personal"):
            self.assertEqual(self.claude("Write", self.main / rel, content="x")[0], "allow", rel)

    def test_personal_files_are_not_drift(self):
        self.write(self.main / "CLAUDE.md.personal", "# Real profile\n")
        self.write(self.main / f"{SKILL}/04-job-evaluation.md.personal", "Strong: Fortran\n")
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_framework_immutable.py")],
                           cwd=str(self.main), env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class SpecsHonorOverlay(unittest.TestCase):
    CONSUMERS = [
        ".claude/commands/apply.md", ".claude/commands/interview.md", ".claude/commands/expand.md",
        ".claude/commands/rank.md", ".claude/commands/outcome.md", ".claude/commands/add-template.md",
        ".claude/commands/add-portal.md", ".claude/commands/setup.md", ".claude/commands/reset.md",
        ".claude/skills/job-scraper/SKILL.md", ".claude/skills/upskill/SKILL.md",
        f"{SKILL}/SKILL.md", "AGENTS.md", ".agents/rules/core.md", "CLAUDE.md",
    ]

    def test_every_consumer_states_the_rule(self):
        for rel in self.CONSUMERS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(".personal", text, rel)
            self.assertIn("instead", text, rel)

    def test_generated_copies_carry_the_rule(self):
        for name in ("apply", "setup", "scrape", "job-application-assistant"):
            text = (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("**Personal overlay:**", text, name)
            self.assertIn("<file>.personal", text, name)

    def test_claude_md_imports_the_overlay(self):
        lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
        self.assertIn("@CLAUDE.md.personal", [ln.strip() for ln in lines])

    def test_personal_suffixes_are_gitignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("*.personal", ignore)

    def test_tracked_templates_keep_placeholders(self):
        expected = {
            f"{SKILL}/02-behavioral-profile.md": "[PROFILE_TYPE]",
            f"{SKILL}/04-job-evaluation.md": "[YOUR_PRIMARY_SKILLS]",
            f"{SKILL}/05-cv-templates.md": "[YOUR_PROFILE_STATEMENT_TEMPLATE_1]",
            f"{SKILL}/07-interview-prep.md": "[PROJECT_NAME]",
            QUERIES: "[YOUR_JOB_BOARD]",
        }
        for rel, token in expected.items():
            self.assertIn(token, (ROOT / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    unittest.main()
