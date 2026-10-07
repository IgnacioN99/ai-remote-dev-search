"""Tests for the /apply quality-gate Stop hook and its state marker.

Covers .claude/hooks/apply_gate_stop.py (Claude Code and Antigravity Stop payloads)
and tools/apply_state.py, against throwaway repo roots in a temp dir. The gate
itself is never run: unit tests inject a fake gate callable, and the end-to-end
tests drop a stub tools/gate_application.py into the temp root.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "apply_gate_stop.py"
sys.path.insert(0, str(ROOT / "tools"))

import apply_state  # noqa: E402

_spec = importlib.util.spec_from_file_location("apply_gate_stop", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

SLUG = "zentrix_backend-engineer"
CLAUDE_PAYLOAD = {
    "session_id": "abc", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp", "hook_event_name": "Stop",
    "stop_hook_active": False, "last_assistant_message": "Done.",
}
AGY_PAYLOAD = {
    "executionNum": 1, "terminationReason": "model_stop", "error": "", "fullyIdle": True,
    "conversationId": "c", "workspacePaths": ["/tmp/ws"],
}
FAILING_OUTPUT = (
    "======\nDeterministic Application Gate: x\n======\n"
    "[FAIL]     ATS Naming : no <CandidateName>_CV.pdf\n\n"
    "[X] Gate Violations (Hard Failures):\n  - CV must be exactly 2 pages (found 3)\n"
    "----------\nGATE VERDICT: [FAILED] Invariants violated. Do NOT submit.\n----------\n"
)


class FakeGate:
    def __init__(self, returncode: int, stdout: str = FAILING_OUTPUT):
        self.returncode, self.stdout, self.calls = returncode, stdout, []

    def __call__(self, root, slug):
        self.calls.append(slug)
        return subprocess.CompletedProcess(["gate"], self.returncode, self.stdout, "")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def start(self, slug: str = SLUG, **extra) -> None:
        data = apply_state.start(slug, self.root)
        if extra:
            data.update(extra)
            apply_state.save(data, self.root)

    def write_docs(self, slug: str = SLUG) -> None:
        (self.root / "cv").mkdir(exist_ok=True)
        (self.root / "cv" / f"main_{slug}.tex").write_text("\\documentclass{moderncv}", encoding="utf-8")

    def state(self):
        return apply_state.load(self.root)

    def write_old_docs(self, slug: str = SLUG, age: float = 3600) -> None:
        """A previous run's CV, cover letter and exports, all modified before the marker."""
        self.write_docs(slug)
        (self.root / "cover_letters").mkdir(exist_ok=True)
        (self.root / "cover_letters" / f"cover_{slug}.tex").write_text("x", encoding="utf-8")
        app = self.root / "documents" / "applications" / slug
        app.mkdir(parents=True, exist_ok=True)
        (app / "Jane_Doe_CV.pdf").write_bytes(b"%PDF")
        started = hook.started_at(self.state()).timestamp()
        for path in (self.root / "cv" / f"main_{slug}.tex",
                     self.root / "cover_letters" / f"cover_{slug}.tex", app / "Jane_Doe_CV.pdf"):
            os.utime(path, (started - age, started - age))

    def decide(self, payload=None, antigravity=False, gate=None):
        gate = gate or FakeGate(1)
        payload = dict(payload or CLAUDE_PAYLOAD)
        if not antigravity and payload.get("cwd") == CLAUDE_PAYLOAD["cwd"]:
            payload["cwd"] = str(self.root)  # the stop happens inside this repo
        return hook.decide(payload, antigravity, self.root, gate), gate


class DecideTests(Base):
    def test_no_apply_in_progress_allows_without_running_gate(self):
        self.write_docs()
        reason, gate = self.decide()
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])

    def test_apply_without_documents_allows(self):
        # Fit evaluation still running, or the user declined after it.
        self.start()
        reason, gate = self.decide()
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])
        self.assertIsNotNone(self.state(), "marker stays until done/gate pass")

    def test_gate_failure_blocks_with_violations_and_counts(self):
        self.start()
        self.write_docs()
        reason, gate = self.decide()
        self.assertEqual(gate.calls, [SLUG])
        self.assertIn("quality gate FAILED", reason)
        self.assertIn("CV must be exactly 2 pages (found 3)", reason)
        self.assertIn("GATE VERDICT: [FAILED]", reason)
        self.assertIn(f"python3 tools/gate_application.py {SLUG}", reason)
        self.assertIn(f"python3 tools/apply_state.py done {SLUG}", reason)
        self.assertNotIn("==========", reason)
        self.assertEqual(self.state()["blocks"], 1)

    def test_gate_pass_allows_and_clears_marker(self):
        self.start()
        self.write_docs()
        reason, gate = self.decide(gate=FakeGate(0, "GATE VERDICT: [PASSED]"))
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [SLUG])
        self.assertIsNone(self.state())

    def test_pending_human_review_allows_and_keeps_marker(self):
        self.start()
        self.write_docs()
        reason, _ = self.decide(gate=FakeGate(2, "GATE VERDICT: [PENDING HUMAN REVIEW]"))
        self.assertIsNone(reason)
        self.assertIsNotNone(self.state())

    def test_retry_cap_allows_with_warning_and_clears(self):
        self.start(blocks=hook.MAX_BLOCKS)
        self.write_docs()
        reason, gate = self.decide()
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [], "cap reached: the gate is not re-run")
        self.assertIsNone(self.state())

    def test_blocks_accumulate_up_to_the_cap(self):
        self.start()
        self.write_docs()
        for expected in range(1, hook.MAX_BLOCKS + 1):
            reason, _ = self.decide()
            self.assertIsNotNone(reason)
            self.assertIn(f"{expected}/{hook.MAX_BLOCKS}", reason)
        reason, _ = self.decide()
        self.assertIsNone(reason)

    def test_stop_hook_active_after_a_block_allows(self):
        self.start(blocks=1)
        self.write_docs()
        reason, gate = self.decide(dict(CLAUDE_PAYLOAD, stop_hook_active=True))
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])

    def test_stop_hook_active_without_own_block_still_enforces(self):
        # Another Stop hook blocked first; this one has not enforced yet.
        self.start()
        self.write_docs()
        reason, _ = self.decide(dict(CLAUDE_PAYLOAD, stop_hook_active=True))
        self.assertIsNotNone(reason)

    def test_antigravity_error_termination_allows(self):
        self.start()
        self.write_docs()
        for why in ("error", "max_steps_exceeded"):
            reason, gate = self.decide(dict(AGY_PAYLOAD, terminationReason=why), antigravity=True)
            self.assertIsNone(reason, why)
            self.assertEqual(gate.calls, [])

    def test_antigravity_model_stop_enforces(self):
        self.start()
        self.write_docs()
        reason, _ = self.decide(AGY_PAYLOAD, antigravity=True)
        self.assertIsNotNone(reason)

    def test_stale_marker_is_ignored_and_cleared(self):
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(hours=hook.STALE_HOURS + 1)).isoformat()
        self.start(started_at=old)
        self.write_docs()
        reason, gate = self.decide()
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])
        self.assertIsNone(self.state())

    def test_documents_detection(self):
        self.assertFalse(hook.documents_exist(self.root, SLUG))
        (self.root / "cover_letters").mkdir()
        (self.root / "cover_letters" / f"cover_{SLUG}.pdf").write_bytes(b"%PDF")
        self.assertTrue(hook.documents_exist(self.root, SLUG))
        other = self.root / "documents" / "applications" / "acme_dev"
        other.mkdir(parents=True)
        (other / "job_posting.md").write_text("posting", encoding="utf-8")
        self.assertFalse(hook.documents_exist(self.root, "acme_dev"), "posting alone is not a document")
        (other / "Jane_Doe_CV.pdf").write_bytes(b"%PDF")
        self.assertTrue(hook.documents_exist(self.root, "acme_dev"))

    def test_redraft_with_stale_failing_docs_at_step1_allows_and_keeps_marker(self):
        # Step 6b item 4 redraft: last run's files exist; this run is at the consent STOP.
        self.start()
        self.write_old_docs()
        reason, gate = self.decide()
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [], "old files must not trigger the gate")
        self.assertIsNotNone(self.state(), "marker kept: the redraft has not run yet")

    def test_redraft_with_stale_passing_docs_does_not_clear_marker(self):
        self.start()
        self.write_old_docs()
        reason, gate = self.decide(gate=FakeGate(0, "GATE VERDICT: [PASSED]"))
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])
        self.assertIsNotNone(self.state())

    def test_redraft_new_docs_after_start_failing_blocks(self):
        self.start()
        self.write_old_docs()
        (self.root / "cv" / f"main_{SLUG}.tex").write_text("redrafted", encoding="utf-8")
        reason, gate = self.decide()
        self.assertEqual(gate.calls, [SLUG])
        self.assertIn("quality gate FAILED", reason)

    def test_redraft_new_docs_after_start_passing_allows_and_clears(self):
        self.start()
        self.write_old_docs()
        (self.root / "cv" / f"main_{SLUG}.tex").write_text("redrafted", encoding="utf-8")
        reason, gate = self.decide(gate=FakeGate(0, "GATE VERDICT: [PASSED]"))
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [SLUG])
        self.assertIsNone(self.state())

    def test_started_at_keeps_sub_second_precision(self):
        self.start()
        self.assertIn(".", self.state()["started_at"], "microseconds are stored")

    def test_glob_metacharacters_in_slug_are_literal(self):
        self.start("acme_[dev]")
        (self.root / "cv").mkdir()
        (self.root / "cv" / "main_acme_d.tex").write_text("other", encoding="utf-8")
        reason, gate = self.decide()
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])
        (self.root / "cv" / "main_acme_[dev].tex").write_text("mine", encoding="utf-8")
        reason, gate = self.decide()
        self.assertEqual(gate.calls, ["acme_[dev]"])

    def test_stop_from_foreign_cwd_allows(self):
        self.start()
        self.write_docs()
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        reason, gate = self.decide(dict(CLAUDE_PAYLOAD, cwd=str(other)))
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])
        self.assertIsNotNone(self.state())

    def test_stop_from_repo_subdirectory_enforces(self):
        self.start()
        self.write_docs()
        reason, _ = self.decide(dict(CLAUDE_PAYLOAD, cwd=str(self.root / "cv")))
        self.assertIsNotNone(reason)

    def test_first_block_records_session_and_other_sessions_are_ignored(self):
        self.start()
        self.write_docs()
        reason, _ = self.decide(dict(CLAUDE_PAYLOAD, session_id="sess-a"))
        self.assertIsNotNone(reason)
        self.assertEqual(self.state()["session_id"], "sess-a")
        reason, gate = self.decide(dict(CLAUDE_PAYLOAD, session_id="sess-b"))
        self.assertIsNone(reason)
        self.assertEqual(gate.calls, [])
        self.assertEqual(self.state()["blocks"], 1, "other session's stop changes nothing")
        reason, _ = self.decide(dict(CLAUDE_PAYLOAD, session_id="sess-a"))
        self.assertIsNotNone(reason)

    def test_save_state_is_atomic_and_leaves_no_temp_files(self):
        hook.save_state(self.root, {"slug": SLUG, "started_at": apply_state.now_iso(), "blocks": 2})
        state_dir = self.root / ".agents" / "state"
        self.assertEqual([p.name for p in state_dir.iterdir()], ["apply.json"])
        self.assertEqual(self.state()["blocks"], 2)

    def test_traversal_slug_in_marker_is_ignored(self):
        apply_state.save({"slug": "../x", "started_at": apply_state.now_iso(), "blocks": 0}, self.root)
        self.assertIsNone(hook.load_state(self.root))


class EndToEndTests(Base):
    """Run the hook as the runtimes do: JSON on stdin, JSON on stdout."""

    def setUp(self):
        super().setUp()
        (self.root / "tools").mkdir()
        (self.root / "tools" / "gate_application.py").write_text(
            "import os, sys\nprint('  - CV must be exactly 2 pages (found 3)')\n"
            "print('GATE VERDICT: [FAILED]')\nsys.exit(int(os.environ.get('FAKE_GATE_RC', '1')))\n",
            encoding="utf-8",
        )

    def run_hook(self, payload, *args, rc=1, raw=None):
        env = dict(os.environ, APPLY_GATE_ROOT=str(self.root), FAKE_GATE_RC=str(rc))
        if isinstance(payload, dict) and "cwd" in payload:
            payload = dict(payload, cwd=str(self.root))
        proc = subprocess.run(
            [sys.executable, str(HOOK), *args],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(self.root),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout), proc.stderr

    def test_claude_code_block_format(self):
        self.start()
        self.write_docs()
        out, _ = self.run_hook(CLAUDE_PAYLOAD)
        self.assertEqual(out["decision"], "block")
        self.assertIn("CV must be exactly 2 pages", out["reason"])

    def test_antigravity_continue_format(self):
        self.start()
        self.write_docs()
        out, _ = self.run_hook(AGY_PAYLOAD, "--antigravity")
        self.assertEqual(out["decision"], "continue")
        self.assertIn("CV must be exactly 2 pages", out["reason"])

    def test_antigravity_payload_is_sniffed_without_flag(self):
        self.start()
        self.write_docs()
        out, _ = self.run_hook(AGY_PAYLOAD)
        self.assertEqual(out["decision"], "continue")

    def test_allow_prints_empty_object_in_both_runtimes(self):
        for args, payload in (((), CLAUDE_PAYLOAD), (("--antigravity",), AGY_PAYLOAD)):
            out, _ = self.run_hook(payload, *args)
            self.assertEqual(out, {})

    def test_gate_pass_clears_marker(self):
        self.start()
        self.write_docs()
        out, _ = self.run_hook(CLAUDE_PAYLOAD, rc=0)
        self.assertEqual(out, {})
        self.assertIsNone(self.state())

    def test_malformed_stdin_fails_open(self):
        self.start()
        self.write_docs()
        out, _ = self.run_hook(None, raw="{not json")
        self.assertEqual(out, {})

    def test_missing_gate_script_fails_open_with_warning(self):
        (self.root / "tools" / "gate_application.py").unlink()
        self.start()
        self.write_docs()
        out, err = self.run_hook(CLAUDE_PAYLOAD)
        self.assertEqual(out, {})
        self.assertIn("internal error, allowing", err)


class ApplyStateCliTests(Base):
    def cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return apply_state.main(list(args), root=self.root)

    def test_start_status_done_cycle(self):
        self.assertEqual(self.cli("start", SLUG), 0)
        data = self.state()
        self.assertEqual(data["slug"], SLUG)
        self.assertEqual(data["blocks"], 0)
        self.assertTrue(data["started_at"])
        self.assertEqual(self.cli("status"), 0)
        self.assertEqual(self.cli("done", SLUG), 0)
        self.assertIsNone(self.state())
        self.assertEqual(self.cli("done", SLUG), 0, "done without a marker is harmless")

    def test_start_resets_block_counter(self):
        self.start(blocks=3)
        self.cli("start", SLUG)
        self.assertEqual(self.state()["blocks"], 0)

    def test_done_with_other_slug_clears_anyway(self):
        self.start("acme_dev")
        self.assertEqual(self.cli("done", SLUG), 0)
        self.assertIsNone(self.state())

    def test_invalid_slug_rejected(self):
        for bad in ("../etc", "a/b", "a\\b", ".."):
            self.assertEqual(self.cli("start", bad), 1, bad)
        self.assertIsNone(self.state())

    def test_state_path_is_gitignored(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".agents/state/", lines)
        self.assertEqual(apply_state.STATE_REL.as_posix(), ".agents/state/apply.json")


class RegistrationTests(unittest.TestCase):
    def test_claude_settings_registers_stop_hook_and_permissions(self):
        import security_guards

        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertIn(".claude/hooks/apply_gate_stop.py", command)
        self.assertIn(f"Stop:{command}", security_guards.ALLOWED_HOOKS)
        for entry in ("Bash(python tools/apply_state.py:*)", "Bash(python3 tools/apply_state.py:*)"):
            self.assertIn(entry, settings["permissions"]["allow"])
            self.assertIn(entry, security_guards.ALLOWED_PERMISSIONS)

    def test_antigravity_hooks_json_registers_flat_stop_hook(self):
        data = json.loads((ROOT / ".agents" / "hooks.json").read_text(encoding="utf-8"))
        handler = data["apply-quality-gate"]["Stop"][0]
        # Stop is a flat handler list; commands run from .agents/.
        self.assertNotIn("matcher", handler)
        self.assertEqual(handler["command"], "python3 ../.claude/hooks/apply_gate_stop.py --antigravity")
        self.assertGreaterEqual(handler["timeout"], 60)

    def test_apply_command_marks_start_and_done(self):
        text = (ROOT / ".claude" / "commands" / "apply.md").read_text(encoding="utf-8")
        step0 = text.split("## Step 0", 1)[1].split("## Step 1", 1)[0]
        self.assertIn("python3 tools/apply_state.py start <company>_<role>", step0)
        self.assertIn("python3 tools/apply_state.py done <company>_<role>", text.rstrip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
