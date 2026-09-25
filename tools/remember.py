#!/usr/bin/env python3
"""Deterministic append-only memory ledger for job search insights.

Deterministic append-only memory ledger and immutable learning store.
Maintains an immutable, append-only log of learnings from interviews,
rejections, recruiter feedback, ATS quirks, and company-specific requirements.

Storage:
  documents/memory/insights.jsonl (Strictly Append-Only)

Tombstones:
  Entries are NEVER deleted. Deselecting/retiring an insight appends a
  tombstone record with {"superseded_id": "<id>", "superseded": true}.

Usage:
  # Record insight
  python3 tools/remember.py "MODO requires explicit mention of NestJS and high concurrency" --tags node,nest,fintech --company modo --source screening

  # List active insights
  python3 tools/remember.py --list
  python3 tools/remember.py --list --company modo
  python3 tools/remember.py --list --tag ruby

  # Retire / tombstone an insight
  python3 tools/remember.py --tombstone ins_20260925_abc123 --reason "No longer applicable"
"""

import argparse
import datetime
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_FILE = ROOT_DIR / "documents" / "memory" / "insights.jsonl"


def generate_insight_id() -> str:
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_suffix = uuid.uuid4().hex[:6]
    return f"ins_{now_str}_{rand_suffix}"


def normalize_slug(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def record_insight(
    text: str,
    tags: Optional[List[str]] = None,
    company: Optional[str] = None,
    source: Optional[str] = None,
    memory_file: Path = DEFAULT_MEMORY_FILE,
) -> Dict[str, Any]:
    """Appends an insight record to the append-only ledger."""
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Insight text cannot be empty.")

    memory_file = Path(memory_file)
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    tag_list = [normalize_slug(t) for t in (tags or []) if t.strip()]
    company_slug = normalize_slug(company) if company else None

    entry = {
        "id": generate_insight_id(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "text": cleaned_text,
        "tags": tag_list,
        "company": company_slug,
        "source": source.strip() if source else "user",
        "superseded": False,
    }

    with open(memory_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def tombstone_insight(
    target_id: str,
    reason: str = "",
    memory_file: Path = DEFAULT_MEMORY_FILE,
) -> Dict[str, Any]:
    """Appends a tombstone record marking target_id as superseded. Never deletes lines."""
    target_id = target_id.strip()
    if not target_id:
        raise ValueError("Target insight ID cannot be empty.")

    memory_file = Path(memory_file)
    if not memory_file.exists():
        raise FileNotFoundError(f"Memory file {memory_file} does not exist.")

    # Validate target exists
    all_raw = read_all_raw_entries(memory_file)
    exists = any(item.get("id") == target_id for item in all_raw)
    if not exists:
        raise KeyError(f"Insight ID '{target_id}' not found in ledger.")

    tombstone = {
        "id": generate_insight_id(),
        "superseded_id": target_id,
        "superseded": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reason": reason.strip() or "superseded",
    }

    with open(memory_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(tombstone, ensure_ascii=False) + "\n")

    return tombstone


def read_all_raw_entries(memory_file: Path = DEFAULT_MEMORY_FILE) -> List[Dict[str, Any]]:
    """Reads all raw entries from the ledger in order."""
    memory_file = Path(memory_file)
    if not memory_file.exists():
        return []

    entries = []
    with open(memory_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                entries.append(json.loads(line_str))
            except json.JSONDecodeError as e:
                print(f"Warning: corrupt JSON line {line_num} in {memory_file}: {e}", file=sys.stderr)
    return entries


def get_active_insights(
    memory_file: Path = DEFAULT_MEMORY_FILE,
    tag: Optional[str] = None,
    company: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Evaluates the append-only ledger and returns active (non-tombstoned) insights."""
    raw_entries = read_all_raw_entries(memory_file)

    superseded_ids = set()
    # First pass: collect tombstoned IDs
    for item in raw_entries:
        if item.get("superseded") is True and item.get("superseded_id"):
            superseded_ids.add(item["superseded_id"])
        elif item.get("superseded") is True and item.get("id"):
            superseded_ids.add(item["id"])

    target_tag = normalize_slug(tag) if tag else None
    target_company = normalize_slug(company) if company else None
    target_query = query.lower().strip() if query else None

    active = []
    for item in raw_entries:
        # Ignore tombstones themselves and items marked superseded
        if item.get("superseded") is True:
            continue
        item_id = item.get("id")
        if not item_id or item_id in superseded_ids:
            continue

        # Filters
        if target_tag:
            item_tags = item.get("tags") or []
            if not any(target_tag in normalize_slug(t) for t in item_tags):
                continue

        if target_company:
            item_company = normalize_slug(item.get("company"))
            if target_company not in item_company:
                continue

        if target_query:
            text = (item.get("text") or "").lower()
            tags_str = " ".join(item.get("tags") or []).lower()
            comp = (item.get("company") or "").lower()
            if target_query not in text and target_query not in tags_str and target_query not in comp:
                continue

        active.append(item)

    return active


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic append-only memory ledger for job search insights."
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Insight message to record in the ledger",
    )
    parser.add_argument(
        "--tags",
        help="Comma-separated tags (e.g. ruby,rspec,salary)",
    )
    parser.add_argument(
        "--company",
        help="Company name associated with the insight (e.g. despegar, modo)",
    )
    parser.add_argument(
        "--source",
        default="user",
        help="Source of the insight (e.g. interview, recruiter_call, rejection, screening)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List active insights matching optional filters",
    )
    parser.add_argument(
        "--tag",
        help="Filter listed insights by tag",
    )
    parser.add_argument(
        "--query",
        help="Filter listed insights by text substring",
    )
    parser.add_argument(
        "--tombstone",
        "--forget",
        dest="tombstone_id",
        help="Tombstone (supersede) an insight by its ID",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Reason for tombstoning an insight",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    parser.add_argument(
        "--memory-file",
        type=Path,
        default=DEFAULT_MEMORY_FILE,
        help=f"Path to memory JSONL file (default: {DEFAULT_MEMORY_FILE})",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.tombstone_id:
            res = tombstone_insight(args.tombstone_id, reason=args.reason, memory_file=args.memory_file)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"[OK] Tombstoned insight '{args.tombstone_id}'. Ledger remains append-only.")
            return 0

        if args.list:
            insights = get_active_insights(
                memory_file=args.memory_file,
                tag=args.tag,
                company=args.company,
                query=args.query,
            )
            if args.json:
                print(json.dumps(insights, indent=2, ensure_ascii=False))
            else:
                if not insights:
                    print("No active insights found.")
                    return 0
                print(f"Active Insights ({len(insights)}):")
                print("-" * 70)
                for item in insights:
                    tags_repr = ", ".join(item.get("tags") or []) or "none"
                    comp_repr = item.get("company") or "general"
                    date_repr = (item.get("timestamp") or "")[:10]
                    print(f"[{item['id']}] [{date_repr}] ({comp_repr} | tags: {tags_repr})")
                    print(f"  {item['text']}")
                    print()
            return 0

        if args.text:
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            res = record_insight(
                text=args.text,
                tags=tags,
                company=args.company,
                source=args.source,
                memory_file=args.memory_file,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"[OK] Recorded insight {res['id']} in {args.memory_file}")
            return 0

        parser.print_help()
        return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
