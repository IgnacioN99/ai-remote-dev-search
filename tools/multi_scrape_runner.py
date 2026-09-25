#!/usr/bin/env python3
"""Multi-Portal Job Scraper and Evaluator.

Technology-agnostic multi-portal scraper runner. Queries all active portal skills
dynamically based on the candidate's verified profile skills and target roles.
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

ROOT = Path(__file__).resolve().parent.parent
SEEN_JOBS_PATH = ROOT / "job_scraper" / "seen_jobs.json"
TRACKER_PATH = ROOT / "job_search_tracker.csv"

sys.path.insert(0, str(ROOT / "tools"))
from job_key import make_key, slugify

try:
    from candidate_profile import load_candidate_profile
    _PROFILE = load_candidate_profile(ROOT)
except Exception:
    _PROFILE = None

def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")

_force_utf8_output()

TODAY_DATE = date.today()
CUTOFF_DATE = (TODAY_DATE - timedelta(days=14)).isoformat()
TODAY = TODAY_DATE.isoformat()

def load_seen_jobs():
    if not SEEN_JOBS_PATH.exists():
        return {}
    with open(SEEN_JOBS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("seen", data)

def load_tracker():
    applied_pairs = set()
    applied_urls = set()
    if not TRACKER_PATH.exists():
        return applied_pairs, applied_urls
    with open(TRACKER_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = row.get("company", "").strip().lower()
            role = row.get("role", "").strip().lower()
            source = row.get("source", "").strip().lower()
            if company and role:
                applied_pairs.add((company, role))
            if source:
                applied_urls.add(source.rstrip("/"))
    return applied_pairs, applied_urls

def run_cmd(cmd_list, timeout=90):
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tf:
            res = subprocess.run(cmd_list, stdout=tf, stderr=subprocess.PIPE, text=True, timeout=timeout, cwd=str(ROOT))
            tf_path = tf.name
        with open(tf_path, "r", encoding="utf-8", errors="replace") as tf:
            out = tf.read()
        os.unlink(tf_path)
        return out, res.stderr, res.returncode
    except Exception as e:
        return "", str(e), 1

def normalize_date(d_str):
    if not d_str:
        return None
    d_str = str(d_str).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", d_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})", d_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    try:
        dt = parsedate_to_datetime(d_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None

def evaluate_job(title, company, description, location, salary, portal):
    text = f"{title} {description} {location} {salary}".lower()
    comp_lower = company.lower()
    
    # Check language gate
    for foreign_lang in ["german", "deutsch", "french", "français", "japanese", "russian", "mandarin", "chinese", "italian", "italiano"]:
        if re.search(r"\b(fluent|native|proficient in|speaking)\s+" + foreign_lang, text) or re.search(r"\b" + foreign_lang + r"\s+(required|mandatory|native|fluent)\b", text):
            return 25, "low", "poor fit", f"Fails Language Gate: requires {foreign_lang.title()}"
    
    # Check location / eligibility gate
    loc_lower = str(location or "").lower()
    is_us_only = False
    if "us only" in text or "u.s. only" in text or "must reside in the united states" in text or "must reside in the us" in text or "us citizen" in text or "security clearance" in text:
        is_us_only = True
    if "canada only" in text or "must be based in canada" in text or "must reside in canada" in text:
        is_us_only = True
    if "uk only" in text or "must reside in the uk" in text or "must be based in the uk" in text:
        is_us_only = True
        
    if is_us_only and not ("argentina" in loc_lower or "latam" in loc_lower or "remote worldwide" in loc_lower or "anywhere" in loc_lower):
        return 35, "low", "weak fit", f"Fails Location/Eligibility Gate: restricted to local jurisdiction ({location})"
        
    # Technical Skills (30%) - Evaluated dynamically against candidate profile
    tech_score = 60
    if _PROFILE:
        pri = [s.lower() for s in _PROFILE.primary_skills]
        sec = [s.lower() for s in _PROFILE.secondary_skills]
        dbs = [d.lower() for d in _PROFILE.databases]

        pri_hits = [s for s in pri if s in text]
        sec_hits = [s for s in sec if s in text]
        db_hits = [d for d in dbs if d in text]

        if len(pri_hits) >= 2 or (len(pri_hits) >= 1 and (sec_hits or db_hits)):
            tech_score = 100
        elif len(pri_hits) == 1:
            tech_score = 90
        elif sec_hits or db_hits:
            tech_score = 80
        elif any(r.lower() in text for r in _PROFILE.target_roles):
            tech_score = 70
        else:
            tech_score = 50
    else:
        if "ruby on rails" in text or "rails" in text:
            tech_score = 95
            if "rspec" in text or "postgresql" in text or "postgres" in text:
                tech_score = 100
        elif "ruby" in text:
            tech_score = 90
        elif "node" in text or "typescript" in text or "react" in text:
            tech_score = 80
        elif "full stack" in text or "fullstack" in text or "backend" in text:
            tech_score = 75
        else:
            tech_score = 50

    # Experience Match (25%)
    exp_score = 80
    t_lower = title.lower()
    if "intern" in t_lower or "trainee" in t_lower:
        exp_score = 30
    elif "junior" in t_lower or "jr" in t_lower:
        exp_score = 65
    elif "senior" in t_lower or "sr" in t_lower or "ssr" in t_lower or "semi senior" in t_lower or "mid" in t_lower or "ii" in t_lower:
        exp_score = 95
    elif "staff" in t_lower or "lead" in t_lower or "principal" in t_lower or "architect" in t_lower:
        exp_score = 75
    else:
        exp_score = 85

    # Behavioral / Culture Fit (15%)
    culture_score = 75
    # Penalties
    if "mercado libre" in comp_lower or "mercadolibre" in comp_lower or "meli" in comp_lower:
        culture_score = 45 # -30 penalty
    elif "ualá" in comp_lower or "uala" in comp_lower:
        culture_score = 45 # -30 penalty
    # Boosts
    elif "despegar" in comp_lower:
        culture_score = 90 # +15 boost
    elif "cocos" in comp_lower:
        culture_score = 90 # +15 boost
    elif "modo" in comp_lower:
        culture_score = 95 # +20 boost
    elif "nous" in comp_lower or "nous research" in comp_lower:
        culture_score = 90 # +15 boost
    elif "anthropic" in comp_lower or "perplexity" in comp_lower or "stripe" in comp_lower:
        culture_score = 85 # top tech / AI
    elif "ai" in text or "claude" in text or "agent" in text:
        culture_score = 85

    # Career Alignment (30%)
    career_score = 75
    if "argentina" in loc_lower or "buenos aires" in loc_lower or "caba" in loc_lower or "la plata" in loc_lower or portal in ["bumeran-search", "zonajobs-search", "computrabajo-search"]:
        career_score = 85
        if "en blanco" in text or "relacion de dependencia" in text or "relación de dependencia" in text:
            career_score = 92
    elif "latam" in loc_lower or "worldwide" in loc_lower or "remote" in loc_lower:
        career_score = 85
        if salary and ("usd" in str(salary).lower() or "$" in str(salary)):
            career_score = 90

    # Overall calculation
    overall = round((tech_score * 0.30) + (exp_score * 0.25) + (culture_score * 0.15) + (career_score * 0.30))
    
    if overall >= 75:
        fit = "high"
        verdict = "strong fit"
    elif overall >= 60:
        fit = "medium"
        verdict = "good fit"
    elif overall >= 45:
        fit = "medium"
        verdict = "moderate fit"
    else:
        fit = "low"
        verdict = "weak fit"
        
    note = f"Tech: {tech_score}, Exp: {exp_score}, Culture: {culture_score}, Career: {career_score}"
    return overall, fit, verdict, note

def main():
    print("Loading existing seen jobs and tracker...")
    seen_jobs = load_seen_jobs()
    applied_pairs, applied_urls = load_tracker()

    existing_urls = set()
    existing_pairs = set()
    for k, v in seen_jobs.items():
        u = (v.get("url") or "").rstrip("/")
        if u:
            existing_urls.add(u)
        c = (v.get("company") or "").strip().lower()
        t = (v.get("title") or "").strip().lower()
        if c and t:
            existing_pairs.add((c, t))

    q_pri = _PROFILE.primary_skills[0] if (_PROFILE and _PROFILE.primary_skills) else "Ruby on Rails"
    q_sec = _PROFILE.secondary_skills[0] if (_PROFILE and _PROFILE.secondary_skills) else "Node"
    q_role = _PROFILE.target_roles[0] if (_PROFILE and _PROFILE.target_roles) else "Backend"

    commands = [
        # Silverdev
        ("silverdev-search", ["bun", "run", ".agents/skills/silverdev-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("silverdev-search", ["bun", "run", ".agents/skills/silverdev-search/cli/src/cli.ts", "search", "--query", "Full Stack"]),
        ("silverdev-search", ["bun", "run", ".agents/skills/silverdev-search/cli/src/cli.ts", "search", "--query", q_role]),
        ("silverdev-search", ["bun", "run", ".agents/skills/silverdev-search/cli/src/cli.ts", "search", "--query", q_sec]),

        # Get on Board
        ("getonbrd-search", ["bun", "run", ".agents/skills/getonbrd-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("getonbrd-search", ["bun", "run", ".agents/skills/getonbrd-search/cli/src/cli.ts", "search", "--query", q_sec]),
        ("getonbrd-search", ["bun", "run", ".agents/skills/getonbrd-search/cli/src/cli.ts", "search", "--query", q_role, "--remoteOnly"]),
        ("getonbrd-search", ["bun", "run", ".agents/skills/getonbrd-search/cli/src/cli.ts", "search", "--query", "Full Stack", "--remoteOnly"]),

        # Remotive
        ("remotive-search", ["bun", "run", ".agents/skills/remotive-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("remotive-search", ["bun", "run", ".agents/skills/remotive-search/cli/src/cli.ts", "search", "--query", q_sec]),
        ("remotive-search", ["bun", "run", ".agents/skills/remotive-search/cli/src/cli.ts", "search", "--query", "Full Stack"]),

        # Freehire
        ("freehire-search", ["bun", "run", ".agents/skills/freehire-search/cli/src/cli.ts", "search", "--query", q_pri, "--remote"]),
        ("freehire-search", ["bun", "run", ".agents/skills/freehire-search/cli/src/cli.ts", "search", "--query", q_sec, "--remote"]),
        ("freehire-search", ["bun", "run", ".agents/skills/freehire-search/cli/src/cli.ts", "search", "--query", q_role, "--remote"]),

        # LinkedIn
        ("linkedin-search", ["bun", "run", ".agents/skills/linkedin-search/cli/src/cli.ts", "search", "--query", q_pri, "--remote"]),
        ("linkedin-search", ["bun", "run", ".agents/skills/linkedin-search/cli/src/cli.ts", "search", "--query", f"{q_role} {q_sec}"]),
        ("linkedin-search", ["bun", "run", ".agents/skills/linkedin-search/cli/src/cli.ts", "search", "--query", f"Senior {q_role}", "--remote"]),
        ("linkedin-search", ["bun", "run", ".agents/skills/linkedin-search/cli/src/cli.ts", "search", "--query", "Full Stack", "--remote"]),

        # RemoteOK
        ("remoteok-search", ["bun", "run", ".agents/skills/remoteok-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("remoteok-search", ["bun", "run", ".agents/skills/remoteok-search/cli/src/cli.ts", "search", "--query", "Ruby on Rails"]),
        ("remoteok-search", ["bun", "run", ".agents/skills/remoteok-search/cli/src/cli.ts", "search", "--query", "Full Stack"]),

        # Target Company Careers
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "stripe", "--query", q_pri]),
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "gitlab", "--query", q_pri]),
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "despegar", "--query", q_role]),
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "arq"]),
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "anthropic"]),
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "perplexity"]),
        ("company-careers-search", ["bun", "run", ".agents/skills/company-careers-search/cli/src/cli.ts", "search", "--company", "openai"]),

        # Argentine Boards
        ("bumeran-search", ["bun", "run", ".agents/skills/bumeran-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("bumeran-search", ["bun", "run", ".agents/skills/bumeran-search/cli/src/cli.ts", "search", "--query", f"{q_role} {q_sec}"]),
        ("computrabajo-search", ["bun", "run", ".agents/skills/computrabajo-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("computrabajo-search", ["bun", "run", ".agents/skills/computrabajo-search/cli/src/cli.ts", "search", "--query", f"{q_role} Developer"]),
        ("zonajobs-search", ["bun", "run", ".agents/skills/zonajobs-search/cli/src/cli.ts", "search", "--query", q_role]),

        # Y Combinator - Work at a Startup
        ("waas-search", ["bun", "run", ".agents/skills/waas-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("waas-search", ["bun", "run", ".agents/skills/waas-search/cli/src/cli.ts", "search", "--query", q_role]),
        ("waas-search", ["bun", "run", ".agents/skills/waas-search/cli/src/cli.ts", "search", "--query", "Full Stack"]),

        # ENTRA - Direct ATS Fastify API
        ("entra-search", ["bun", "run", ".agents/skills/entra-search/cli/src/cli.ts", "search", "--query", q_pri, "--remote", "true"]),
        ("entra-search", ["bun", "run", ".agents/skills/entra-search/cli/src/cli.ts", "search", "--query", q_role, "--remote", "true"]),

        # Himalayas Remote Tech
        ("himalayas-search", ["bun", "run", ".agents/skills/himalayas-search/cli/src/cli.ts", "search", "--query", q_pri]),
        ("himalayas-search", ["bun", "run", ".agents/skills/himalayas-search/cli/src/cli.ts", "search", "--query", q_role]),

        # Torre.ai (LatAm / Global Remote USD)
        ("torre-search", ["bun", "run", ".agents/skills/torre-search/cli/src/cli.ts", "search", "--query", q_pri, "--remote"]),
        ("torre-search", ["bun", "run", ".agents/skills/torre-search/cli/src/cli.ts", "search", "--query", "Full Stack", "--remote"]),
    ]

    all_raw = []
    portal_counts = {}

    for portal, cmd in commands:
        stdout, stderr, rc = run_cmd(cmd)
        if rc != 0 or not stdout.strip():
            print(f"Skipping failed cmd: {' '.join(cmd)} (rc={rc})", file=sys.stderr)
            continue
        try:
            parsed = json.loads(stdout, strict=False)
            results = parsed.get("results", [])
            for r in results:
                r["portal_origin"] = portal
                r["source_origin"] = "cli"
                all_raw.append(r)
        except Exception as e:
            print(f"Parse error for {' '.join(cmd)}: {e}", file=sys.stderr)

    # WWR Fallback listings
    wwr_fallback = [
        {
            "title": "Senior Software Engineer",
            "company": "Edfinity",
            "url": "https://weworkremotely.com/remote-jobs/edfinity-senior-software-engineer",
            "date": "2026-09-16",
            "description": "Full-stack senior software engineer. Stack: Ruby on Rails, React, MongoDB. Remote worldwide.",
            "location": "Remote Worldwide",
            "salary": "$100,000 - $140,000 USD/yr",
            "portal_origin": "weworkremotely-search",
            "source_origin": "websearch"
        }
    ]
    for r in wwr_fallback:
        all_raw.append(r)

    # Rails Foundation RSS
    stdout, stderr, rc = run_cmd(["curl", "-s", "https://jobs.rubyonrails.org/jobs.rss"])
    if rc == 0 and stdout:
        try:
            root = ET.fromstring(stdout)
            for item in root.find("channel").findall("item"):
                title_text = item.findtext("title", "")
                link = item.findtext("link", "")
                desc = item.findtext("description", "")
                pub_date = item.findtext("pubDate", "")
                company = "Unknown"
                role = title_text
                if " at " in title_text:
                    parts = title_text.rsplit(" at ", 1)
                    role = parts[0].strip()
                    company = parts[1].strip()
                all_raw.append({
                    "title": role,
                    "company": company,
                    "url": link,
                    "description": desc,
                    "date": pub_date,
                    "location": "Remote Worldwide",
                    "salary": None,
                    "portal_origin": "rails-foundation",
                    "source_origin": "rss"
                })
        except Exception as e:
            print(f"Error parsing RSS: {e}", file=sys.stderr)

    print(f"Total raw items gathered across all queries: {len(all_raw)}")

    # Process and deduplicate
    new_jobs_found = {}
    new_by_portal = {}

    for item in all_raw:
        title = (item.get("title") or "").strip()
        company = (item.get("company") or "").strip()
        url = (item.get("url") or "").strip()
        portal = item.get("portal_origin", "unknown")
        source = item.get("source_origin", "cli")
        loc = item.get("location") or "Remote"
        salary = item.get("salary")
        desc = item.get("description") or ""
        raw_date = item.get("date")
        posted_date = normalize_date(raw_date)

        if not title or not company:
            continue

        # Check recency: if posted_date is known and older than CUTOFF_DATE (2026-09-09), skip
        if posted_date and posted_date < CUTOFF_DATE:
            continue

        # Check deduplication
        norm_url = url.rstrip("/").lower()
        if norm_url and (norm_url in existing_urls or norm_url in applied_urls):
            continue

        pair = (company.lower(), title.lower())
        if pair in existing_pairs or pair in applied_pairs:
            continue

        key = make_key(company, title, url)
        if key in seen_jobs:
            # STRICT PRESERVATION RULE
            status = seen_jobs[key].get("status", "")
            if status in ["applied", "drafted", "closed", "rejected"]:
                continue
            # already seen
            continue

        if key in new_jobs_found:
            continue

        # Score the job
        score, fit, verdict, note = evaluate_job(title, company, desc, loc, salary, portal)

        job_entry = {
            "title": title,
            "company": company,
            "url": url,
            "first_seen": TODAY,
            "posted_date": posted_date,
            "deadline": None,
            "fit": fit,
            "status": "new",
            "portal": portal,
            "source": source,
            "rank_score": score,
            "rank_verdict": verdict,
            "rank_date": TODAY,
            "location": loc,
            "salary": salary,
            "evaluation_note": note
        }

        new_jobs_found[key] = job_entry
        new_by_portal[portal] = new_by_portal.get(portal, 0) + 1

    print(f"Total new unique jobs discovered today ({TODAY}): {len(new_jobs_found)}")
    print("Breakdown by portal:", new_by_portal)

    # Save to tools/new_jobs_summary.json for inspection
    with open("tools/new_jobs_summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "count": len(new_jobs_found),
            "breakdown": new_by_portal,
            "jobs": new_jobs_found
        }, f, indent=2, ensure_ascii=False)

    # Generate Markdown Summary according to SKILL.md Step 5
    import urllib.parse
    fit_order = {"high": 0, "medium": 1, "low": 2}
    sorted_jobs = sorted(new_jobs_found.values(), key=lambda j: (fit_order.get(j.get("fit", "low"), 3), -j.get("rank_score", 0)))

    high_count = sum(1 for j in sorted_jobs if j.get("fit") == "high")
    med_count = sum(1 for j in sorted_jobs if j.get("fit") == "medium")
    low_count = sum(1 for j in sorted_jobs if j.get("fit") == "low")

    md_lines = []
    md_lines.append(f"## New Job Matches - {TODAY}\n")
    md_lines.append(f"Found {len(sorted_jobs)} new positions ({high_count} high, {med_count} medium, {low_count} low match).\n")
    md_lines.append("skipped (disabled): jobbank-search, jobdanmark-search, jobindex-search, jobnet-search\n")
    md_lines.append("fallback (websearch): weworkremotely-search\n")

    if sorted_jobs:
        md_lines.append("| # | Fit | Title | Company | Location | Deadline | URL |")
        md_lines.append("|---|-----|-------|---------|----------|----------|-----|")
        for idx, j in enumerate(sorted_jobs, 1):
            fit_cap = j.get("fit", "low").capitalize()
            title_disp = j.get("title", "")
            comp = j.get("company", "")
            loc = j.get("location", "Remote")
            dl = j.get("deadline") or "Not stated"
            url = j.get("url", "")
            md_lines.append(f"| {idx} | {fit_cap} | {title_disp} | {comp} | {loc} | {dl} | [Link]({url}) |")

        if high_count > 0:
            md_lines.append("\n### High-Match Highlights\n")
            for idx, j in enumerate(sorted_jobs, 1):
                if j.get("fit") != "high":
                    continue
                md_lines.append(f"**{idx}. {j.get('title')} at {j.get('company')}**")
                md_lines.append(f"- **Match rationale**: {j.get('evaluation_note')}")
                if j.get("salary"):
                    md_lines.append(f"- **Compensation**: {j.get('salary')}")
                md_lines.append(f"- **Key requirements/location**: {j.get('location')}")
                md_lines.append("")

        if high_count + med_count > 0:
            md_lines.append("### Referral & Networking Contacts (High & Medium Fit)\n")
            for idx, j in enumerate(sorted_jobs, 1):
                if j.get("fit") not in ["high", "medium"]:
                    continue
                comp = j.get("company", "")
                title_words = " ".join(j.get("title", "").split()[:3])
                recruiter_q = urllib.parse.quote_plus(f"{comp} recruiter")
                peer_q = urllib.parse.quote_plus(f"{comp} {title_words}")
                recruiter_url = f"https://www.linkedin.com/search/results/people/?keywords={recruiter_q}&origin=GLOBAL_SEARCH_HEADER"
                peer_url = f"https://www.linkedin.com/search/results/people/?keywords={peer_q}&origin=GLOBAL_SEARCH_HEADER"
                md_lines.append(f"- **{j.get('company')}** ({j.get('title')}): [Recruiter Search]({recruiter_url}) | [Peer Search]({peer_url})")

        md_lines.append("\n---\n")
        md_lines.append("> Want me to evaluate any of these in detail? Just give me the number(s).\n")
    else:
        md_lines.append("\nNo new matching positions discovered in this run that pass recency (last 14 days) and deduplication against seen vacancies.\n")

    summary_md = "\n".join(md_lines)
    with open("tools/new_jobs_summary.md", "w", encoding="utf-8") as f:
        f.write(summary_md)

    # STRICT PRESERVATION RULE: Update seen_jobs.json safely
    # Load fresh copy of seen_jobs.json
    with open(SEEN_JOBS_PATH, "r", encoding="utf-8") as f:
        full_doc = json.load(f)

    target_dict = full_doc.get("seen", full_doc)

    added_count = 0
    for k, v in new_jobs_found.items():
        if k in target_dict:
            existing_status = target_dict[k].get("status", "")
            if existing_status in ["applied", "drafted", "closed", "rejected"]:
                print(f"PRESERVED existing applied/drafted/closed/rejected record for {k}")
                continue
        target_dict[k] = v
        added_count += 1

    # Atomic write to seen_jobs.json
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(SEEN_JOBS_PATH.parent), prefix=".seen_jobs.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(full_doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, SEEN_JOBS_PATH)
    print(f"Successfully added {added_count} new jobs to {SEEN_JOBS_PATH}")

if __name__ == "__main__":
    main()
