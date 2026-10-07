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
        # Every source is explicit: never fall through to the real tracker/apps.
        self.sanitizer = report_issue.Sanitizer.from_repo(
            profile, self.tmp / "missing_CLAUDE.md", self.tmp / "missing_tracker.csv",
            self.tmp / "missing_applications")

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

    def test_generic_career_words_are_not_over_redacted(self):
        md = self.tmp / "CLAUDE.md"
        md.write_text("### Identity\n- **Name:** Jane Q Public\n- **Status:** Open to work\n"
                      '- **LinkedIn headline:** "Senior Backend Engineer | Python"\n### Education\n',
                      encoding="utf-8")
        profile = self.tmp / "p.json"
        profile.write_text(json.dumps({"name": "Jane Doe", "education": ["State University of Computer Science"],
                                       "employers": ["Acme Widgets ApS"]}), encoding="utf-8")
        sanitizer = report_issue.Sanitizer.from_repo(profile, md)
        text = "work on Senior backend issue at a University with Computer Science grads"
        self.assertEqual(sanitizer.clean(text), text)
        self.assertNotIn("Public", sanitizer.clean("Jane Q Public filed it"))
        self.assertNotIn("Acme Widgets ApS", sanitizer.clean("at Acme Widgets ApS"))

    def test_digits_only_phone_from_profile_is_redacted(self):
        self.assertNotIn("4512345678", self.sanitizer.clean("call 4512345678 now"))

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


# Fictional tracker rows / application folders - no real company is used.
FAKE_TRACKER = (
    "date,company,role,status,cv_file\n"
    "\n"
    "2026-01-05,Zentrix Analytics,Senior Backend Engineer,applied,main_zentrix-analytics_backend.tex\n"
    "2026-01-06,Nubéfera,Quokka Platform Wrangler,interview,\n"
)
FAKE_APP_FOLDERS = ("vortalix-data_senior-backend-engineer", "data-labs_developer")


class TrackerAndApplicationTerms(Base):
    def setUp(self):
        super().setUp()
        self.tracker = self.tmp / "job_search_tracker.csv"
        self.tracker.write_text(FAKE_TRACKER, encoding="utf-8")
        self.apps = self.tmp / "applications"
        for name in FAKE_APP_FOLDERS:
            (self.apps / name).mkdir(parents=True)
        (self.apps / "stray_file.txt").write_text("x", encoding="utf-8")
        self.s = report_issue.Sanitizer.from_repo(
            self.tmp / "candidate_profile.json", self.tmp / "missing_CLAUDE.md",
            self.tracker, self.apps)

    def test_tracker_company_and_specific_role_redacted(self):
        clean = self.s.clean("Zentrix Analytics rejected; zentrix-analytics slug; Quokka Platform Wrangler; Nubefera")
        for needle in ("Zentrix", "zentrix", "Quokka", "Nubefera"):
            self.assertNotIn(needle, clean, clean)
        self.assertNotIn("Zentrix", self.s.clean("the Zentrix posting 404s"))
        self.assertIn("analytics", self.s.clean("analytics dashboard"))

    def test_generic_role_is_not_a_term(self):
        text = "Senior Backend Engineer filter broke for developer roles in data labs"
        self.assertEqual(self.s.clean(text), text)

    def test_application_folder_slug_and_company_redacted(self):
        clean = self.s.clean("see documents/applications/vortalix-data_senior-backend-engineer/notes.md "
                             "and Vortalix Data and vortalix_corp")
        self.assertNotIn("vortalix", clean.lower(), clean)
        self.assertIn("documents/applications/[redacted]/notes.md", clean)

    def test_all_generic_company_slug_adds_no_generic_tokens(self):
        terms = [t.lower() for t in self.s.terms]
        self.assertNotIn("data", terms)
        self.assertNotIn("labs", terms)

    def test_missing_sources_are_harmless(self):
        self.assertEqual(report_issue.load_tracker_terms(self.tmp / "nope.csv"), [])
        self.assertEqual(report_issue.load_application_terms(self.tmp / "nope"), [])

    def test_from_repo_defaults_resolve_at_call_time(self):
        with mock.patch.object(report_issue, "TRACKER_CSV", self.tracker), \
                mock.patch.object(report_issue, "APPLICATIONS_DIR", self.apps), \
                mock.patch.object(report_issue, "PROFILE_JSON", self.tmp / "none.json"), \
                mock.patch.object(report_issue, "CLAUDE_MD", self.tmp / "none.md"):
            s = report_issue.Sanitizer.from_repo()
        self.assertNotIn("Zentrix", s.clean("Zentrix Analytics"))


class FileNamesAndBoundaries(Base):
    def test_application_file_names_replaced(self):
        clean = self.sanitizer.clean(
            "lualatex main_globex-nordic_backend.tex -> main_globex-nordic_backend.pdf, "
            "cover_acme_dev.log, cover_acme_dev.aux, path cv/main_acme_dev.tex")
        self.assertNotIn("globex", clean.lower())
        self.assertNotIn("acme", clean.lower())
        self.assertIn("main_<company>_<role>.tex", clean)
        self.assertIn("main_<company>_<role>.pdf", clean)
        self.assertIn("cover_<company>_<role>.log", clean)
        self.assertIn("cover_<company>_<role>.aux", clean)
        self.assertIn("cv/main_<company>_<role>.tex", clean)

    def test_ats_pdf_names_replaced(self):
        clean = self.sanitizer.clean("uploaded Jane_Doe_CV_Acme.pdf and file=JaneDoe_CoverLetter_Globex.pdf")
        self.assertNotIn("Jane", clean)
        self.assertIn("uploaded <CandidateName>_CV.pdf", clean)
        self.assertIn("file=<CandidateName>_CoverLetter.pdf", clean)

    def test_file_name_replacement_is_idempotent(self):
        once = self.sanitizer.clean("main_acme_dev.tex Jane_CV.pdf")
        self.assertEqual(self.sanitizer.clean(once), once)

    def test_underscore_and_hyphen_are_separators(self):
        s = report_issue.Sanitizer(["Zentrix"])
        clean = s.clean("dir zentrix_backend, zentrix-dev, x_ZENTRIX_y")
        self.assertNotIn("zentrix", clean.lower(), clean)

    def test_term_inside_a_longer_word_survives(self):
        s = report_issue.Sanitizer(["Zentrix"])
        self.assertEqual(s.clean("Zentrixology and preZentrix"), "Zentrixology and preZentrix")


class AccentInsensitive(Base):
    def test_accented_term_matches_plain_and_decomposed_input(self):
        s = report_issue.Sanitizer(["José Peña", "Nubéfera"])
        for text in ("José Peña", "Jose Pena", "JOSE PENA", "Jose\u0301 Pen\u0303a", "Nubefera", "NUBÉFERA"):
            self.assertEqual(s.clean(text), "[redacted]", text)

    def test_plain_term_matches_its_own_form(self):
        s = report_issue.Sanitizer(["Jose Pena"])
        self.assertEqual(s.clean("Jose Pena"), "[redacted]")


class SalaryAndPhoneExtras(Base):
    def test_spanish_and_lowercase_currency_amounts(self):
        clean = self.sanitizer.clean(
            "wants 4500 dólares, 4500 dolares, 4.500 pesos, 4500usd, 4500 USD, "
            "expected 4500 per month, 3000 por mes, 2000/month, 2500 a month")
        for needle in ("4500", "4.500", "3000", "2000", "2500"):
            self.assertNotIn(needle, clean, clean)

    def test_unformatted_and_grouped_phones(self):
        clean = self.sanitizer.clean("call 1123456789 or 011 15 1234-5678 or +54 9 11 2345-6789")
        for needle in ("1123456789", "011", "1234-5678", "2345", "+54"):
            self.assertNotIn(needle, clean, clean)
        self.assertEqual(clean.count("[phone]"), 3)

    def test_numbers_that_are_not_phones_survive(self):
        text = ("exit 429 on 2026-10-07 12:30, issue #431, gh 2.45.0, v1.2.3, port 8080, "
                "127.0.0.1:5432, 192.168.10.100, year 2025, 2026-10-07T12:30:00Z, pid 12345, "
                "3 of 10 jobs, commit abc1234, sha 1a2b3c4d5e6f7a8b9c0d")
        self.assertEqual(self.sanitizer.clean(text), text)


class WslPaths(Base):
    def test_unc_paths_collapse_to_home(self):
        clean = self.sanitizer.clean(
            r"\\wsl.localhost\Ubuntu\home\fakeuser\repo\x.py and \\wsl$\Debian\home\otheruser\y "
            "and //wsl.localhost/Ubuntu/home/thirduser/q")
        for needle in ("fakeuser", "otheruser", "thirduser", "Ubuntu", "Debian"):
            self.assertNotIn(needle, clean, clean)
        self.assertIn(r"~\repo\x.py", clean)
        self.assertIn("~/q", clean)


class LabelsCommentsFlushTitles(Base):
    def test_labels_with_pii_are_dropped(self):
        code, out = self.invoke(self.base_args("--labels", "operator-mode,jane-doe,acme widgets aps",
                                               "--dry-run", "--json"), FakeRunner())
        self.assertEqual(json.loads(out)["labels"], ["agent-reported", "bug", "operator-mode"])

    def test_seen_again_comment_is_short(self):
        fp = report_issue.fingerprint("bug", "tools/doctor.py", "doctor crashes")
        runner = FakeRunner(existing=[{"number": 3, "title": "older", "url": "u",
                                       "body": f"old\n<!-- fp:{fp} -->"}])
        code, _ = self.invoke(["--kind", "bug", "--title", "doctor crashes", "--component",
                               "tools/doctor.py", "--body", "x" * 2000 + " TAILMARK"], runner)
        self.assertEqual(code, 0)
        comment = runner.gh_writes()[0]["input"]
        self.assertTrue(comment.startswith("Seen again at "))
        self.assertIn(f"<!-- fp:{fp} -->", comment)
        self.assertNotIn("TAILMARK", comment)
        self.assertNotIn("Filed automatically", comment)
        self.assertLess(len(comment), 450)

    def test_flush_resanitizes_queued_entries(self):
        # Queued by an older sanitizer: raw PII inside.
        old_fp = "0" * 40
        self.pending.write_text(json.dumps({
            "kind": "bug", "component": "scrape", "title": "Jane Doe portal broke",
            "body": "mail jane.doe@example.com at Acme Widgets ApS\n\n---\n_Filed automatically by x_\n"
                    f"<!-- fp:{old_fp} -->\n",
            "labels": ["agent-reported", "jane-doe"], "fingerprint": old_fp,
            "repo": "IgnacioN99/ai-remote-dev-search"}) + "\n", encoding="utf-8")
        runner = FakeRunner()
        code, out = self.invoke(["--flush", "--json"], runner)
        self.assertEqual(code, 0, out)
        writes = runner.gh_writes()
        self.assertEqual(len(writes), 1)
        sent = " ".join(writes[0]["args"]) + (writes[0]["input"] or "")
        for needle in ("Jane", "jane", "Acme", old_fp):
            self.assertNotIn(needle, sent, sent)
        self.assertIn("<!-- fp:", writes[0]["input"])

    def test_flush_drops_entry_emptied_by_resanitizing(self):
        self.pending.write_text(json.dumps({
            "kind": "bug", "title": "ok title", "body": "Jane Doe jane.doe@example.com",
            "labels": [], "fingerprint": "x", "repo": "IgnacioN99/ai-remote-dev-search"}) + "\n",
            encoding="utf-8")
        runner = FakeRunner()
        code, out = self.invoke(["--flush", "--json"], runner)
        self.assertEqual(code, 0)
        self.assertEqual(runner.gh_writes(), [])
        self.assertEqual(json.loads(out)["results"][0]["action"], "refused")

    def test_non_ascii_titles_keep_letters(self):
        self.assertEqual(report_issue.normalize_title("Búsqueda falló 3 veces"), "busqueda fallo # veces")
        self.assertNotEqual(report_issue.fingerprint("bug", "c", "Búsqueda rota"),
                            report_issue.fingerprint("bug", "c", "Descarga rota"))
        self.assertEqual(report_issue.fingerprint("bug", "c", "Búsqueda rota"),
                         report_issue.fingerprint("bug", "c", "busqueda rota"))

    def test_ascii_fingerprint_unchanged(self):
        import hashlib
        expected = hashlib.sha1(b"bug|tools/doctor.py|doctor crashes when bun is missing ##").hexdigest()
        self.assertEqual(report_issue.fingerprint("bug", "tools/doctor.py",
                                                  "Doctor crashes when bun_is missing (#12)!"), expected)


class BodyFileGuard(Base):
    def test_body_file_under_private_dirs_is_refused(self):
        for rel in ("cv/main_x.tex", "cover_letters/cover_x.tex", "documents/applications/a/notes.md",
                    "Documents/memory/insights.jsonl"):
            runner = FakeRunner()
            code, out = self.invoke(["--kind", "bug", "--title", "t", "--body-file",
                                     str(report_issue.ROOT_DIR / rel), "--dry-run", "--json"], runner)
            self.assertEqual(code, 2, (rel, out))
            self.assertIn("refusing --body-file", json.loads(out)["reason"])
            self.assertEqual(runner.gh_calls(), [])

    def test_traversal_into_private_dir_is_refused(self):
        sneaky = report_issue.ROOT_DIR / "tools" / ".." / "cv" / "x.tex"
        with self.assertRaises(report_issue.Refused):
            report_issue.check_body_file_allowed(sneaky)

    def test_body_file_elsewhere_is_allowed(self):
        body = self.tmp / "body.md"
        body.write_text("Traceback: boom", encoding="utf-8")
        code, out = self.invoke(["--kind", "bug", "--title", "t", "--body-file", str(body),
                                 "--dry-run", "--json"], FakeRunner())
        self.assertEqual(code, 0, out)
        self.assertIn("Traceback: boom", json.loads(out)["body"])


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
