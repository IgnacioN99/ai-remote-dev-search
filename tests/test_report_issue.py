"""Tests for tools/report_issue.py - sanitized issue filing on the user's fork.

The fork is public and the upstream template belongs to someone else, so the
two properties that matter most are pinned first: the tool can never target
upstream, and nothing personal survives the sanitizer. gh is never invoked
for real - every subprocess call goes through a fake runner.
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import report_issue  # noqa: E402

FORK_SSH = "git@github.com:IgnacioN99/ai-remote-dev-search.git"
UPSTREAM_HTTPS = "https://github.com/MadsLorentzen/ai-job-search.git"

# Fictional candidate, in the same spirit as the Jane Doe fixtures used by the
# onboarding/privacy tests: realistic shapes, no real person.
PROFILE = {
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "phone": "+45 12 34 56 78",
    "linkedin": "https://www.linkedin.com/in/janedoe-dk",
    "github": "https://github.com/janedoe",
    "location": "Remote",
    "employers": ["Acme Widgets ApS"],
    "experience": [{"company": "Globex Nordic", "title": "Engineer"}],
    "primary_skills": ["Python", "Kubernetes"],
}


def cp(args, rc=0, out="", err=""):
    return subprocess.CompletedProcess(args, rc, stdout=out, stderr=err)


class FakeRunner:
    """Records every call; answers git/gh from a small script."""

    def __init__(self, origin=FORK_SSH, upstream=UPSTREAM_HTTPS, existing=None,
                 create_errors=None, gh_missing=False, list_rc=0):
        self.calls = []
        self.origin = origin
        self.upstream = upstream
        self.existing = existing or []
        self.create_errors = list(create_errors or [])
        self.gh_missing = gh_missing
        self.list_rc = list_rc

    def __call__(self, args, input_text=None, repo=None, timeout=60):
        self.calls.append({"args": list(args), "input": input_text, "repo": repo})
        if args[:3] == ["git", "remote", "get-url"]:
            url = {"origin": self.origin, "upstream": self.upstream}.get(args[3])
            return cp(args, 0 if url else 2, out=(url or "") + "\n")
        if args[0] == "git":
            return cp(args, 0, out="abc1234\n")
        if args[0] == "gh":
            if self.gh_missing:
                raise FileNotFoundError("gh")
            if args[1] == "--version":
                return cp(args, 0, out="gh version 2.45.0 (2024-03-04)\n")
            if args[1:3] == ["issue", "list"]:
                return cp(args, self.list_rc, out=json.dumps(self.existing), err="network down")
            if args[1:3] == ["issue", "create"]:
                if self.create_errors:
                    return cp(args, 1, err=self.create_errors.pop(0))
                return cp(args, 0, out="https://github.com/IgnacioN99/ai-remote-dev-search/issues/7\n")
            if args[1:3] == ["issue", "comment"]:
                return cp(args, 0, out="https://github.com/IgnacioN99/ai-remote-dev-search/issues/3#issuecomment-1\n")
        raise AssertionError(f"unexpected call {args}")

    def gh_writes(self):
        return [c for c in self.calls if c["args"][:1] == ["gh"]
                and c["args"][1:3] in (["issue", "create"], ["issue", "comment"])]

    def gh_calls(self):
        return [c for c in self.calls if c["args"][:1] == ["gh"]]


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.pending = self.tmp / "pending_issues.jsonl"
        profile = self.tmp / "candidate_profile.json"
        profile.write_text(json.dumps(PROFILE), encoding="utf-8")
        self.sanitizer = report_issue.Sanitizer.from_repo(profile, self.tmp / "missing_CLAUDE.md")

    def invoke(self, argv, runner, environ=None):
        out = io.StringIO()
        code = report_issue.run(argv, runner=runner, sanitizer=self.sanitizer,
                                pending=self.pending, environ=environ or {}, stream=out)
        return code, out.getvalue()

    def base_args(self, *extra):
        return ["--kind", "bug", "--title", "doctor crashes", "--body", "Traceback here",
                "--component", "tools/doctor.py", *extra]


class NeverTargetsUpstream(Base):
    def test_parse_ssh_and_https(self):
        self.assertEqual(report_issue.parse_repo_slug(FORK_SSH), "IgnacioN99/ai-remote-dev-search")
        self.assertEqual(report_issue.parse_repo_slug(UPSTREAM_HTTPS), "MadsLorentzen/ai-job-search")
        self.assertEqual(report_issue.parse_repo_slug("ssh://git@github.com/o/r.git"), "o/r")
        self.assertEqual(report_issue.parse_repo_slug("https://github.com/o/r"), "o/r")

    def assert_refused(self, runner, environ=None):
        code, out = self.invoke(self.base_args("--json"), runner, environ)
        self.assertEqual(code, 2, out)
        self.assertEqual(json.loads(out)["action"], "refused")
        self.assertEqual(runner.gh_calls(), [], "no gh call may happen once upstream is detected")

    def test_origin_ssh_pointing_upstream_is_refused(self):
        self.assert_refused(FakeRunner(origin="git@github.com:MadsLorentzen/ai-job-search.git"))

    def test_origin_https_pointing_upstream_is_refused(self):
        self.assert_refused(FakeRunner(origin=UPSTREAM_HTTPS))

    def test_env_override_pointing_upstream_is_refused(self):
        self.assert_refused(FakeRunner(), {"JOBSEARCH_ISSUES_REPO": "MadsLorentzen/ai-job-search"})

    def test_env_override_url_pointing_upstream_is_refused(self):
        self.assert_refused(FakeRunner(), {"JOBSEARCH_ISSUES_REPO": UPSTREAM_HTTPS})

    def test_owner_of_upstream_remote_is_refused_even_for_another_repo(self):
        runner = FakeRunner(origin="git@github.com:SomeoneElse/other.git",
                            upstream="git@github.com:SomeoneElse/template.git")
        self.assert_refused(runner)

    def test_hardcoded_denylist_applies_without_upstream_remote(self):
        self.assert_refused(FakeRunner(origin=UPSTREAM_HTTPS, upstream=None))

    def test_dry_run_to_upstream_is_still_refused(self):
        runner = FakeRunner(origin=UPSTREAM_HTTPS)
        code, _ = self.invoke(self.base_args("--dry-run"), runner)
        self.assertEqual(code, 2)

    def test_every_gh_call_pins_the_fork(self):
        runner = FakeRunner()
        code, _ = self.invoke(self.base_args(), runner)
        self.assertEqual(code, 0)
        for call in runner.gh_calls():
            if call["args"][1] == "--version":
                continue
            self.assertIn("-R", call["args"])
            self.assertEqual(call["args"][call["args"].index("-R") + 1], "IgnacioN99/ai-remote-dev-search")
            self.assertEqual(call["repo"], "IgnacioN99/ai-remote-dev-search")

    def test_queued_entry_toward_upstream_is_dropped_on_flush(self):
        self.pending.write_text(json.dumps({
            "kind": "bug", "title": "t", "body": "b <!-- fp:x -->", "labels": [],
            "fingerprint": "x", "repo": "MadsLorentzen/ai-job-search"}) + "\n", encoding="utf-8")
        runner = FakeRunner()
        code, _ = self.invoke(["--flush"], runner)
        self.assertEqual(code, 0)
        self.assertEqual(runner.gh_writes(), [])


class SanitizerRemovesPII(Base):
    LEAKY = (
        "Jane Doe ran /scrape. Contact jane.doe@example.com or +45 12 34 56 78 / (555) 123-4567. "
        "Profile https://www.linkedin.com/in/janedoe-dk and https://github.com/janedoe. "
        "Fetched https://jobs.example.com/view?id=9&token=SECRET123. "
        "Offer was salary: 85000, i.e. 85k EUR or $120,000 or DKK 55.000. "
        "Last at Acme Widgets ApS and Globex Nordic. "
        "Files: /home/janedoe/ai-job-search/tools/x.py /mnt/c/Users/JaneD/Documents/cv.tex "
        "C:\\Users\\JaneD\\cv\\main.tex /Users/janed/repo"
    )

    def test_pii_is_removed(self):
        clean = self.sanitizer.clean(self.LEAKY)
        for needle in ("Jane", "Doe", "jane.doe", "example.com/view?id", "SECRET123",
                       "12 34 56 78", "123-4567", "janedoe", "85000", "85k", "120,000",
                       "55.000", "Acme", "Globex", "JaneD", "janed"):
            self.assertNotIn(needle, clean, f"{needle!r} leaked: {clean}")
        self.assertIn("~/ai-job-search/tools/x.py", clean)
        self.assertIn("~/Documents/cv.tex", clean)

    def test_benign_text_survives(self):
        text = "Remote Python job, exit 429 on 2026-10-07, gh 2.45.0, Kubernetes."
        self.assertEqual(self.sanitizer.clean(text), text)

    def test_end_to_end_body_and_title_sanitized(self):
        runner = FakeRunner()
        code, out = self.invoke(["--kind", "portal-health", "--title", "Jane Doe portal broke",
                                 "--body", self.LEAKY, "--dry-run", "--json"], runner)
        self.assertEqual(code, 0, out)
        result = json.loads(out)
        self.assertNotIn("Jane", result["title"])
        self.assertNotIn("jane.doe@example.com", result["body"])
        self.assertIn("<!-- fp:", result["body"])

    def test_claude_md_identity_values_redacted_but_placeholders_skipped(self):
        md = self.tmp / "CLAUDE.md"
        md.write_text("### Identity\n- **Name:** Jane Q Public\n- **Location:** Springfield, Freedonia\n"
                      "- **Status:** [YOUR_EMPLOYMENT_STATUS]\n### Education\n", encoding="utf-8")
        values = report_issue.load_claude_identity(md)
        self.assertIn("Jane Q Public", values)
        self.assertIn("Springfield", values)
        self.assertFalse(any("[YOUR_" in v for v in values))

    def test_body_emptied_by_sanitizer_is_refused(self):
        code, out = self.invoke(["--kind", "bug", "--title", "x", "--body", "jane.doe@example.com Jane Doe",
                                 "--json"], FakeRunner())
        self.assertEqual(code, 2, out)

    def test_body_truncated_but_fingerprint_kept(self):
        runner = FakeRunner()
        code, out = self.invoke(["--kind", "bug", "--title", "x", "--body", "a" * 20000,
                                 "--dry-run", "--json"], runner)
        body = json.loads(out)["body"]
        self.assertLess(len(body), report_issue.MAX_BODY_CHARS + 600)
        self.assertIn("[truncated]", body)
        self.assertIn("<!-- fp:", body)


class DedupeAndLabels(Base):
    def test_existing_fingerprint_comments_instead_of_creating(self):
        fp = report_issue.fingerprint("bug", "tools/doctor.py", "doctor crashes")
        runner = FakeRunner(existing=[{"number": 3, "title": "older", "url": "u",
                                       "body": f"old\n<!-- fp:{fp} -->"}])
        code, out = self.invoke(self.base_args("--json"), runner)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["action"], "commented")
        writes = runner.gh_writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["args"][1:4], ["issue", "comment", "3"])

    def test_exact_title_fallback_comments(self):
        runner = FakeRunner(existing=[{"number": 5, "title": "doctor crashes", "body": "no fp"}])
        code, out = self.invoke(self.base_args("--json"), runner)
        self.assertEqual(json.loads(out)["number"], 5)
        self.assertEqual(runner.gh_writes()[0]["args"][2], "comment")

    def test_fingerprint_is_stable_across_numbers(self):
        self.assertEqual(report_issue.fingerprint("bug", "c", "Failed 3 times"),
                         report_issue.fingerprint("bug", "c", "failed 12 times!"))

    def test_creates_with_default_labels(self):
        runner = FakeRunner()
        code, out = self.invoke(self.base_args("--labels", "operator-mode", "--json"), runner)
        result = json.loads(out)
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["number"], 7)
        args = runner.gh_writes()[0]["args"]
        labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
        self.assertEqual(labels, ["agent-reported", "bug", "operator-mode"])

    def test_kind_label_mapping(self):
        self.assertEqual(report_issue.build_labels("improvement", "")[1], "enhancement")
        self.assertEqual(report_issue.build_labels("drift", "")[1], "framework")
        self.assertEqual(report_issue.build_labels("doc", "")[1], "documentation")

    def test_missing_label_is_dropped_and_retried(self):
        runner = FakeRunner(create_errors=["could not add label: 'operator-mode' not found"])
        code, out = self.invoke(self.base_args("--labels", "operator-mode", "--json"), runner)
        self.assertEqual(code, 0, out)
        writes = runner.gh_writes()
        self.assertEqual(len(writes), 2)
        self.assertNotIn("operator-mode", writes[1]["args"])
        self.assertIn("agent-reported", writes[1]["args"])

    def test_unparseable_label_error_retries_without_labels(self):
        runner = FakeRunner(create_errors=["label error of some new shape"])
        code, out = self.invoke(self.base_args("--json"), runner)
        self.assertEqual(json.loads(out)["action"], "created")
        self.assertNotIn("--label", runner.gh_writes()[1]["args"])


class DryRunAndOffline(Base):
    def test_dry_run_makes_no_gh_calls(self):
        runner = FakeRunner()
        code, out = self.invoke(self.base_args("--dry-run"), runner)
        self.assertEqual(code, 0)
        self.assertEqual(runner.gh_calls(), [])
        self.assertIn("IgnacioN99/ai-remote-dev-search", out)
        self.assertFalse(self.pending.exists())

    def test_gh_missing_queues_sanitized_entry(self):
        runner = FakeRunner(gh_missing=True)
        code, out = self.invoke(["--kind", "bug", "--title", "t", "--body",
                                 "mail jane.doe@example.com", "--json"], runner)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["action"], "queued")
        raw = self.pending.read_text(encoding="utf-8")
        self.assertNotIn("jane.doe@example.com", raw)
        self.assertEqual(json.loads(raw)["repo"], "IgnacioN99/ai-remote-dev-search")

    def test_gh_failure_queues(self):
        runner = FakeRunner(list_rc=1)
        code, out = self.invoke(self.base_args("--json"), runner)
        self.assertEqual(json.loads(out)["action"], "queued")
        self.assertEqual(len(report_issue.read_queue(self.pending)), 1)

    def test_flush_replays_and_empties_queue(self):
        self.invoke(self.base_args(), FakeRunner(gh_missing=True))
        self.assertEqual(len(report_issue.read_queue(self.pending)), 1)
        runner = FakeRunner()
        code, out = self.invoke(["--flush", "--json"], runner)
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(len(runner.gh_writes()), 1)
        self.assertEqual(report_issue.read_queue(self.pending), [])

    def test_flush_keeps_entries_while_still_offline(self):
        self.invoke(self.base_args(), FakeRunner(gh_missing=True))
        code, out = self.invoke(["--flush", "--json"], FakeRunner(gh_missing=True))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["remaining"], 1)
        self.assertEqual(len(report_issue.read_queue(self.pending)), 1)

    def test_missing_args_is_error(self):
        code, _ = self.invoke(["--kind", "bug"], FakeRunner())
        self.assertEqual(code, 1)

    def test_real_subprocess_wrapper_sets_gh_repo(self):
        with mock.patch.object(report_issue.subprocess, "run", return_value=cp([], 0)) as run:
            report_issue._run(["gh", "--version"], repo="o/r")
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["GH_REPO"], "o/r")


class CheckConsistencyHook(unittest.TestCase):
    def test_drift_issue_body_is_counts_only(self):
        import check_consistency

        report = {"state_discrepancies": [{"company": "Acme Widgets", "role": "Engineer"}],
                  "orphan_application_folders": ["acme_engineer"]}
        with mock.patch.object(check_consistency.subprocess, "run", return_value=cp([], 0)) as run:
            check_consistency.report_drift_issue(report)
        cmd = run.call_args.args[0]
        body = cmd[cmd.index("--body") + 1]
        self.assertIn("state_discrepancies: 1", body)
        self.assertNotIn("Acme", body)
        self.assertNotIn("acme_engineer", body)
        self.assertEqual(cmd[cmd.index("--kind") + 1], "drift")


if __name__ == "__main__":
    unittest.main()
