"""Unit tests for tools/doctor.py (environment and toolchain diagnostic)."""

from pathlib import Path
from unittest.mock import patch
import pytest
from tools.doctor import (
    run_doctor,
    check_python,
    check_uv,
    check_latex_compilers,
    check_poppler,
    check_js_runtime,
    check_browser_automation,
    check_workspace_files,
    format_doctor_report,
)


def test_check_python_passes():
    res = check_python()
    assert res["status"] == "OK"
    assert res["critical"] is True
    assert "Python" in res["detail"]


def test_doctor_full_run_healthy_on_workspace():
    res = run_doctor()
    assert "checks" in res
    assert "summary" in res
    assert "healthy" in res
    assert res["summary"]["OK"] >= 10
    # Current environment should be healthy
    assert res["healthy"] is True


def test_doctor_detects_missing_critical_tool():
    with patch("tools.doctor.check_command") as mock_cmd:
        # Simulate lualatex missing
        mock_cmd.return_value = (False, "Not found on PATH")
        res = check_latex_compilers()
        lua = [c for c in res if "LuaLaTeX" in c["name"]][0]
        assert lua["status"] == "FAIL"
        assert lua["critical"] is True


def test_doctor_js_runtime_detection():
    res = check_js_runtime()
    # At least bun or node must be found in this environment
    assert res["status"] == "OK"
    assert "bun" in res["detail"] or "node" in res["detail"]


def test_format_doctor_report():
    mock_res = {
        "checks": [
            {"name": "Python", "status": "OK", "detail": "3.12"},
            {"name": "Typst", "status": "WARN", "detail": "Optional"},
        ],
        "summary": {"OK": 1, "WARN": 1, "FAIL": 0},
        "healthy": True,
    }
    report = format_doctor_report(mock_res)
    assert "[OK]" in report
    assert "[WARN]" in report
    assert "HEALTH VERDICT: [OK]" in report
