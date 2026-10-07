"""Unit tests for tools/remember.py (deterministic append-only memory ledger).

Written for `python3 -m unittest discover -s tests` (what CI runs) - stdlib only.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.remember import (  # noqa: E402
    get_active_insights,
    read_all_raw_entries,
    record_insight,
    tombstone_insight,
)


class RememberTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = Path(self._tmp.name) / "insights.jsonl"

    def test_record_insight_creates_valid_entry(self):
        entry = record_insight(
            text="Acmepay prioritizes high-throughput transaction experience",
            tags=["node", "fintech", "nest"],
            company="Acmepay",
            source="interview",
            memory_file=self.ledger,
        )

        self.assertTrue(entry["id"].startswith("ins_"))
        self.assertEqual(entry["text"], "Acmepay prioritizes high-throughput transaction experience")
        self.assertEqual(entry["tags"], ["node", "fintech", "nest"])
        self.assertEqual(entry["company"], "acmepay")
        self.assertEqual(entry["source"], "interview")
        self.assertIs(entry["superseded"], False)

        raw = read_all_raw_entries(self.ledger)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["id"], entry["id"])

    def test_append_only_guarantee_and_tombstones(self):
        ledger = self.ledger
        ins1 = record_insight("Insight 1", tags=["rails"], memory_file=ledger)
        ins2 = record_insight("Insight 2", tags=["react"], memory_file=ledger)

        self.assertEqual(len(read_all_raw_entries(ledger)), 2)
        self.assertEqual(len(get_active_insights(memory_file=ledger)), 2)

        # Tombstone ins1
        tb = tombstone_insight(ins1["id"], reason="Outdated stack", memory_file=ledger)
        self.assertIs(tb["superseded"], True)
        self.assertEqual(tb["superseded_id"], ins1["id"])

        # File MUST have 3 entries (strictly append-only, line never deleted)
        raw = read_all_raw_entries(ledger)
        self.assertEqual(len(raw), 3)
        self.assertEqual(raw[2]["superseded_id"], ins1["id"])

        # Active insights must only show ins2
        active = get_active_insights(memory_file=ledger)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], ins2["id"])

    def test_filtering_by_tag_company_query(self):
        ledger = self.ledger
        record_insight("Perry Street values dry-monads", tags=["ruby", "dry-monads"], company="perry-street-software", memory_file=ledger)
        record_insight("Globex uses an in-house travel AI", tags=["python", "ai"], company="globex", memory_file=ledger)
        record_insight("TechCorp microservices architecture", tags=["backend", "distributed"], company="techcorp", memory_file=ledger)

        # Filter by company
        res_comp = get_active_insights(memory_file=ledger, company="globex")
        self.assertEqual(len(res_comp), 1)
        self.assertEqual(res_comp[0]["company"], "globex")

        # Filter by tag
        res_tag = get_active_insights(memory_file=ledger, tag="dry-monads")
        self.assertEqual(len(res_tag), 1)
        self.assertIn("dry-monads", res_tag[0]["tags"])

        # Filter by query substring
        res_query = get_active_insights(memory_file=ledger, query="in-house travel")
        self.assertEqual(len(res_query), 1)
        self.assertEqual(res_query[0]["company"], "globex")

    def test_invalid_arguments_raise_errors(self):
        ledger = self.ledger
        with self.assertRaises(ValueError):
            record_insight("   ", memory_file=ledger)

        with self.assertRaises(FileNotFoundError):
            tombstone_insight("ins_nonexistent", memory_file=ledger)

        record_insight("Valid insight", memory_file=ledger)
        with self.assertRaises(KeyError):
            tombstone_insight("ins_not_found_123", memory_file=ledger)


if __name__ == "__main__":
    unittest.main()
