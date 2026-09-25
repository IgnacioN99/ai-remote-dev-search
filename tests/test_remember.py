"""Unit tests for tools/remember.py (deterministic append-only memory ledger)."""

import json
from pathlib import Path
import pytest
from tools.remember import (
    record_insight,
    tombstone_insight,
    get_active_insights,
    read_all_raw_entries,
)


def test_record_insight_creates_valid_entry(tmp_path: Path):
    ledger = tmp_path / "insights.jsonl"
    entry = record_insight(
        text="MODO prioritizes high-throughput transaction experience",
        tags=["node", "fintech", "nest"],
        company="MODO",
        source="interview",
        memory_file=ledger,
    )

    assert entry["id"].startswith("ins_")
    assert entry["text"] == "MODO prioritizes high-throughput transaction experience"
    assert entry["tags"] == ["node", "fintech", "nest"]
    assert entry["company"] == "modo"
    assert entry["source"] == "interview"
    assert entry["superseded"] is False

    raw = read_all_raw_entries(ledger)
    assert len(raw) == 1
    assert raw[0]["id"] == entry["id"]


def test_append_only_guarantee_and_tombstones(tmp_path: Path):
    ledger = tmp_path / "insights.jsonl"
    ins1 = record_insight("Insight 1", tags=["rails"], memory_file=ledger)
    ins2 = record_insight("Insight 2", tags=["react"], memory_file=ledger)

    assert len(read_all_raw_entries(ledger)) == 2
    assert len(get_active_insights(memory_file=ledger)) == 2

    # Tombstone ins1
    tb = tombstone_insight(ins1["id"], reason="Outdated stack", memory_file=ledger)
    assert tb["superseded"] is True
    assert tb["superseded_id"] == ins1["id"]

    # File MUST have 3 entries (strictly append-only, line never deleted)
    raw = read_all_raw_entries(ledger)
    assert len(raw) == 3
    assert raw[2]["superseded_id"] == ins1["id"]

    # Active insights must only show ins2
    active = get_active_insights(memory_file=ledger)
    assert len(active) == 1
    assert active[0]["id"] == ins2["id"]


def test_filtering_by_tag_company_query(tmp_path: Path):
    ledger = tmp_path / "insights.jsonl"
    record_insight("Perry Street values dry-monads", tags=["ruby", "dry-monads"], company="perry-street-software", memory_file=ledger)
    record_insight("Despegar uses SOFIA travel AI", tags=["python", "ai"], company="despegar", memory_file=ledger)
    record_insight("Rootstrap Rails microservices", tags=["ruby", "rails"], company="rootstrap", memory_file=ledger)

    # Filter by company
    res_comp = get_active_insights(memory_file=ledger, company="despegar")
    assert len(res_comp) == 1
    assert res_comp[0]["company"] == "despegar"

    # Filter by tag
    res_tag = get_active_insights(memory_file=ledger, tag="dry-monads")
    assert len(res_tag) == 1
    assert "dry-monads" in res_tag[0]["tags"]

    # Filter by query substring
    res_query = get_active_insights(memory_file=ledger, query="SOFIA")
    assert len(res_query) == 1
    assert res_query[0]["company"] == "despegar"


def test_invalid_arguments_raise_errors(tmp_path: Path):
    ledger = tmp_path / "insights.jsonl"
    with pytest.raises(ValueError):
        record_insight("   ", memory_file=ledger)

    with pytest.raises(FileNotFoundError):
        tombstone_insight("ins_nonexistent", memory_file=ledger)

    record_insight("Valid insight", memory_file=ledger)
    with pytest.raises(KeyError):
        tombstone_insight("ins_not_found_123", memory_file=ledger)
