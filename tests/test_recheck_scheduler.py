"""Tests for recheck_scheduler — Phase 3 backoff scheduling."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.recheck_scheduler import (
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_MAX_INTERVAL_HOURS,
    DEFAULT_MAX_INTERVALS,
    DEFAULT_MIN_INTERVALS,
    _ensure_page_entry,
    _now_iso,
    get_confidence_interval,
    get_pages_due_for_recheck,
    load_schedule,
    print_schedule_summary,
    record_recheck_result,
    save_schedule,
    should_recheck_page,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def schedule_file(tmp_path):
    """A temporary _recheck_schedules.json to avoid touching the real wiki."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    yield wiki_dir / "_recheck_schedules.json"
    # Clean up after each test


@pytest.fixture
def sched(schedule_file, monkeypatch):
    """Replace the schedule path so tests write to tmp_path."""
    def _fake_path():
        return schedule_file

    monkeypatch.setattr("scripts.recheck_scheduler._schedule_path", _fake_path)
    # Clear any cached schedule
    yield
    # No extra cleanup needed — each test gets a fresh tmp_path


# ── DEFAULT constants ─────────────────────────────────────────────────────────

class TestDefaults:
    def test_min_intervals_by_confidence(self):
        assert DEFAULT_MIN_INTERVALS["HIGH"] == 6
        assert DEFAULT_MIN_INTERVALS["MEDIUM"] == 24
        assert DEFAULT_MIN_INTERVALS["LOW"] == 72

    def test_max_intervals_by_confidence(self):
        assert DEFAULT_MAX_INTERVALS["HIGH"] == 24 * 3
        assert DEFAULT_MAX_INTERVALS["MEDIUM"] == 24 * 7
        assert DEFAULT_MAX_INTERVALS["LOW"] == 24 * 7

    def test_backoff_factor(self):
        assert DEFAULT_BACKOFF_FACTOR == 1.5

    def test_get_confidence_interval(self):
        assert get_confidence_interval("HIGH", "min") == 6
        assert get_confidence_interval("MEDIUM", "min") == 24
        assert get_confidence_interval("LOW", "min") == 72
        assert get_confidence_interval("HIGH", "max") == 24 * 3
        assert get_confidence_interval("bogus", "min") == 24  # fallback


# ── should_recheck_page ──────────────────────────────────────────────────────

class TestShouldRecheckPage:
    def test_new_page_is_due(self, sched):
        # A page with no schedule entry is always due
        assert should_recheck_page("BrandNewPage", confidence="HIGH") is True

    def test_never_checked_is_due(self, sched):
        # Entry exists but has no next_check_after → due
        sched_dict = {"SomePage": {"confidence": "HIGH", "next_check_after": None}}
        save_schedule(sched_dict)
        assert should_recheck_page("SomePage", confidence="HIGH") is True

    def test_within_backoff_not_due(self, sched):
        # Future next_check_after → not due
        future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        sched_dict = {
            "CoolPage": {
                "confidence": "HIGH",
                "next_check_after": future,
                "current_interval_h": 6,
                "min_interval_h": 6,
                "max_interval_h": 72,
                "backoff_factor": 1.5,
                "last_checked_at": _now_iso(),
                "total_checks": 1,
                "stale_count": 0,
                "clean_count": 1,
                "created_at": _now_iso(),
            }
        }
        save_schedule(sched_dict)
        assert should_recheck_page("CoolPage", confidence="HIGH") is False


# ── record_recheck_result ─────────────────────────────────────────────────────

class TestRecordRecheckResult:
    def test_stale_resets_interval_to_minimum(self, sched):
        # First record a clean result (interval set to minimum, no backoff on first check)
        entry = record_recheck_result("StaleTestPage", is_stale=False, confidence="HIGH")
        assert entry["current_interval_h"] == 6.0  # HIGH min, no backoff yet

        # Now mark it stale — interval should reset to min (6h)
        entry2 = record_recheck_result("StaleTestPage", is_stale=True, confidence="HIGH")
        assert entry2["current_interval_h"] == 6.0
        assert entry2["stale_count"] == 1
        assert entry2["clean_count"] == 1

    def test_clean_applies_backoff(self, sched):
        # First clean: interval set to minimum (no backoff on first check)
        entry = record_recheck_result("CleanPage", is_stale=False, confidence="MEDIUM")
        assert entry["clean_count"] == 1
        assert entry["current_interval_h"] == 24  # MEDIUM min, no backoff yet

        # Second clean: backoff applies (24 * 1.5 = 36)
        entry2 = record_recheck_result("CleanPage", is_stale=False, confidence="MEDIUM")
        assert entry2["current_interval_h"] == 36.0

        # Third clean: backoff again (36 * 1.5 = 54)
        entry3 = record_recheck_result("CleanPage", is_stale=False, confidence="MEDIUM")
        assert entry3["current_interval_h"] == 54.0

    def test_clean_capped_at_max_interval(self, sched):
        # Create page with very large interval
        sched_dict = {
            "BigIntervalPage": {
                "confidence": "LOW",
                "current_interval_h": 24 * 7 - 1,  # just under max
                "min_interval_h": 72,
                "max_interval_h": 24 * 7,
                "backoff_factor": 1.5,
                "last_checked_at": _now_iso(),
                "next_check_after": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "total_checks": 5,
                "stale_count": 0,
                "clean_count": 5,
                "created_at": _now_iso(),
            }
        }
        save_schedule(sched_dict)

        entry = record_recheck_result("BigIntervalPage", is_stale=False, confidence="LOW")
        # Capped at max_interval_h (168h)
        assert entry["current_interval_h"] == 24 * 7

    def test_new_page_gets_confidence_minimum(self, sched):
        # Page not in schedule yet
        entry = record_recheck_result("BrandNewPage", is_stale=False, confidence="LOW")
        assert entry["current_interval_h"] == 72  # LOW minimum
        assert entry["confidence"] == "LOW"
        assert entry["min_interval_h"] == 72


# ── get_pages_due_for_recheck ──────────────────────────────────────────────────

class TestGetPagesDueForRecheck:
    def test_overdue_pages_returned(self, sched):
        past = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        sched_dict = {
            "OverduePage": {
                "confidence": "HIGH",
                "current_interval_h": 6,
                "min_interval_h": 6,
                "max_interval_h": 72,
                "backoff_factor": 1.5,
                "last_checked_at": past,
                "next_check_after": past,
                "total_checks": 1,
                "stale_count": 0,
                "clean_count": 1,
                "created_at": _now_iso(),
            }
        }
        save_schedule(sched_dict)

        due = get_pages_due_for_recheck()
        assert any(p["page_name"] == "OverduePage" for p in due)

    def test_within_window_not_returned(self, sched):
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        sched_dict = {
            "FuturePage": {
                "confidence": "HIGH",
                "current_interval_h": 6,
                "min_interval_h": 6,
                "max_interval_h": 72,
                "backoff_factor": 1.5,
                "last_checked_at": _now_iso(),
                "next_check_after": future,
                "total_checks": 1,
                "stale_count": 0,
                "clean_count": 1,
                "created_at": _now_iso(),
            }
        }
        save_schedule(sched_dict)

        due = get_pages_due_for_recheck()
        assert not any(p["page_name"] == "FuturePage" for p in due)

    def test_confidence_filter(self, sched):
        past = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        sched_dict = {
            "HighPage": {
                "confidence": "HIGH",
                "current_interval_h": 6,
                "min_interval_h": 6,
                "max_interval_h": 72,
                "backoff_factor": 1.5,
                "last_checked_at": past,
                "next_check_after": past,
                "total_checks": 1,
                "stale_count": 0,
                "clean_count": 1,
                "created_at": _now_iso(),
            },
            "LowPage": {
                "confidence": "LOW",
                "current_interval_h": 72,
                "min_interval_h": 72,
                "max_interval_h": 168,
                "backoff_factor": 1.5,
                "last_checked_at": past,
                "next_check_after": past,
                "total_checks": 1,
                "stale_count": 0,
                "clean_count": 1,
                "created_at": _now_iso(),
            },
        }
        save_schedule(sched_dict)

        due_high = get_pages_due_for_recheck(confidence_filter="HIGH")
        assert any(p["page_name"] == "HighPage" for p in due_high)
        assert not any(p["page_name"] == "LowPage" for p in due_high)


# ── _ensure_page_entry ────────────────────────────────────────────────────────

class TestEnsurePageEntry:
    def test_new_page_gets_correct_defaults(self, sched):
        sched_dict = {}
        entry = _ensure_page_entry(sched_dict, "NewPage", "HIGH")
        assert entry["confidence"] == "HIGH"
        assert entry["current_interval_h"] == 6  # HIGH minimum
        assert entry["min_interval_h"] == 6
        assert entry["max_interval_h"] == 72
        assert entry["backoff_factor"] == 1.5
        assert entry["total_checks"] == 0

    def test_existing_entry_preserved(self, sched):
        sched_dict = {
            "OldPage": {
                "confidence": "MEDIUM",
                "current_interval_h": 54.0,
                "min_interval_h": 24,
                "max_interval_h": 168,
                "backoff_factor": 1.5,
                "last_checked_at": _now_iso(),
                "next_check_after": _now_iso(),
                "total_checks": 3,
                "stale_count": 1,
                "clean_count": 2,
                "created_at": _now_iso(),
            }
        }
        entry = _ensure_page_entry(sched_dict, "OldPage", "MEDIUM")
        assert entry["current_interval_h"] == 54.0
        assert entry["total_checks"] == 3


# ── print_schedule_summary ────────────────────────────────────────────────────

class TestPrintScheduleSummary:
    def test_empty_schedule(self, sched, capsys):
        print_schedule_summary()
        out = capsys.readouterr().out
        assert "No recheck schedule recorded yet" in out

    def test_populated_schedule(self, sched, capsys):
        sched_dict = {
            "TestPage": {
                "confidence": "HIGH",
                "current_interval_h": 6.0,
                "min_interval_h": 6,
                "max_interval_h": 72,
                "backoff_factor": 1.5,
                "last_checked_at": _now_iso(),
                "next_check_after": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
                "total_checks": 1,
                "stale_count": 0,
                "clean_count": 1,
                "created_at": _now_iso(),
            }
        }
        save_schedule(sched_dict)
        print_schedule_summary()
        out = capsys.readouterr().out
        assert "TestPage" in out
        assert "HIGH" in out
