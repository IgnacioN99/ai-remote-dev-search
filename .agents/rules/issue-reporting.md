---
trigger: always_on
---

# Issue reporting (operator mode)

During /scrape, /rank, /apply and other operator runs, framework problems are **filed, not fixed**. Never edit tools/, .claude/, .agents/, templates or docs to work around them - file an issue and continue the user's task.

## File an issue when
- A framework tool crashes or misbehaves (traceback, wrong exit code, misleading OK) - `bug`
- A portal CLI is **broken** or **degraded** per /scrape Step 4.75 - `portal-health`
- State/profile drift caused by tooling, or a template compile/layout failure not caused by the drafted content - `drift` / `bug`
- A doc or skill contradicts the code or itself - `doc`
- A concrete improvement idea - `improvement`

## Do NOT file when
- The problem is specific to one application's content (a weak CV line, a gate failure on a draft) - fix the draft
- A portal check is inconclusive or rate-limited (429, block page, timeout)
- The report would need personal data to make sense (names, contacts, salaries, employers applied to, CV/CL text)

## How
```bash
python3 tools/report_issue.py --kind <bug|improvement|portal-health|drift|doc> \
  --component <scrape|rank|apply|tools/x.py|...> --title "<short, generic>" \
  --body "<what failed, command, exit code, error excerpt>"
```
- Use `--body-file <path>` for long output. The tool sanitizes, dedupes (comments on a matching open issue), and queues offline; it only ever targets the fork, never upstream.
- Exit 0 = created/commented/queued; 2 = refused (do not retry or work around); 1 = usage error.
- Mention the result in one line of your run summary. `--flush` replays queued issues later.
