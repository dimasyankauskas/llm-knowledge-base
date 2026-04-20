"""LLM Knowledge Base v2 — Phase 3: Smart Recheck Scheduling.

Backoff logic, stale detection, and confidence-layer integration for
intelligent re-check timing of wiki pages.

Architecture
────────────
The scheduler tracks per-page recheck state in a JSON sidecar
(`_recheck_schedules.json`) alongside the wiki.  When a page passes a
staleness check (its sources haven't changed), its interval is multiplied
by a backoff factor, up to a maximum.  When sources HAVE changed (stale),
the interval is reset to the per-confidence minimum so the page gets
prompt attention.

Confidence intervals (in hours)
────────────────────────────────
HIGH   → recheck every  6 h  (high-value claims need tight monitoring)
MEDIUM → recheck every 24 h  (single-source claims)
LOW    → recheck every 72 h  (inference / contested)

Backoff
───────
On a clean (non-stale) recheck: interval *= backoff_factor (default 1.5)
On a stale recheck:              interval  = confidence_minimum (reset)
Maximum interval: 7 days (168 h)

Integration
──────────
- `should_recheck_page(page_name)` → bool  — call before running a full
  staleness check to avoid unnecessary work.
- `record_recheck_result(page_name, is_stale)` — call after checking to
  update the schedule.
- `get_recheck_schedule()` → dict — returns the full schedule for inspection.
- `generate_refinement_tasks()` in `refine.py` calls these to priority-rank
  stale pages, and respects backoff intervals so pages that were recently
  checked clean aren't re-checked as urgently.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from provenance import get_stale_pages
from schema import load_schema
from utils import WIKI_DIR, SOURCES_DIR


# ── Confidence-tier intervals (hours) ──────────────────────────────────────────

DEFAULT_MIN_INTERVALS = {
    "HIGH":   6,    # HIGH confidence: tight monitoring
    "MEDIUM": 24,   # MEDIUM confidence: daily
    "LOW":    72,   # LOW confidence: checked every 3 days
}

DEFAULT_MAX_INTERVALS = {
    "HIGH":   24 * 3,   # 3 days max even for HIGH
    "MEDIUM": 24 * 7,   # 1 week max for MEDIUM
    "LOW":    24 * 7,   # 1 week max for LOW
}

DEFAULT_BACKOFF_FACTOR = 1.5

DEFAULT_MAX_INTERVAL_HOURS = 24 * 7   # 7 days hard cap


# ── Schedule storage ──────────────────────────────────────────────────────────

def _schedule_path() -> Path:
    return WIKI_DIR / "_recheck_schedules.json"


def load_schedule() -> dict[str, dict[str, Any]]:
    """Load the recheck schedule from disk. Returns empty dict if absent."""
    path = _schedule_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_schedule(schedule: dict[str, dict[str, Any]]) -> None:
    """Write the recheck schedule to disk atomically."""
    path = _schedule_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(schedule, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ── CI mode detection ───────────────────────────────────────────────────────────

def is_ci_mode() -> bool:
    """Return True if running in a CI environment."""
    return os.getenv("CI") == "true" or os.getenv("WIKI_CI_MODE") == "true"


# ── Per-page schedule management ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_page_entry(
    schedule: dict[str, dict[str, Any]],
    page_name: str,
    confidence: str,
) -> dict[str, Any]:
    """Return existing entry or create a new one with confidence-driven defaults."""
    if page_name in schedule:
        return schedule[page_name]

    min_interval = DEFAULT_MIN_INTERVALS.get(confidence.upper(), 24)
    schedule[page_name] = {
        "confidence":        confidence.upper(),
        "current_interval_h": min_interval,
        "min_interval_h":    min_interval,
        "max_interval_h":    DEFAULT_MAX_INTERVALS.get(confidence.upper(), 24 * 7),
        "backoff_factor":    DEFAULT_BACKOFF_FACTOR,
        "last_checked_at":   None,
        "next_check_after":  None,   # ISO timestamp; None = check now
        "total_checks":      0,
        "stale_count":       0,
        "clean_count":       0,
        "created_at":        _now_iso(),
    }
    return schedule[page_name]


def _compute_next_check(entry: dict[str, Any]) -> str:
    """Given a schedule entry, compute the next_check_after ISO timestamp."""
    interval_h = min(entry["current_interval_h"], DEFAULT_MAX_INTERVAL_HOURS)
    last_checked = entry.get("last_checked_at")
    if last_checked:
        last_dt = datetime.fromisoformat(last_checked)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        next_dt = last_dt + timedelta(hours=interval_h)
    else:
        next_dt = datetime.now(timezone.utc)
    return next_dt.isoformat()


def should_recheck_page(
    page_name: str,
    confidence: str = "MEDIUM",
    schedule: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Return True if a page is due for a staleness recheck.

    Call this before running an expensive staleness check to avoid
    re-checking pages that were recently verified clean.

    Args:
        page_name:   Page stem (filename without extension).
        confidence:  Page confidence level (HIGH / MEDIUM / LOW).
        schedule:    Optional pre-loaded schedule dict to avoid re-reading.

    Returns:
        True if the page should be re-checked now, False if it's still within
        its backoff window.
    """
    if schedule is None:
        schedule = load_schedule()

    entry = schedule.get(page_name)
    if entry is None:
        # Never checked → should check now
        return True

    next_check = entry.get("next_check_after")
    if next_check is None:
        return True

    now = datetime.now(timezone.utc)
    due_dt = datetime.fromisoformat(next_check)
    if due_dt.tzinfo is None:
        due_dt = due_dt.replace(tzinfo=timezone.utc)

    return now >= due_dt


def record_recheck_result(
    page_name: str,
    is_stale: bool,
    confidence: str = "MEDIUM",
) -> dict[str, Any]:
    """Record the outcome of a staleness recheck and update the schedule.

    Args:
        page_name:  Page stem.
        is_stale:   True if any source changed since last check.
        confidence: Page confidence level (used for new pages).

    Returns:
        The updated schedule entry for the page.
    """
    schedule = load_schedule()
    entry = _ensure_page_entry(schedule, page_name, confidence)

    now = _now_iso()
    entry["last_checked_at"] = now
    entry["total_checks"] += 1

    if is_stale:
        entry["stale_count"] += 1
        # Reset interval to minimum: stale pages need prompt re-attention
        entry["current_interval_h"] = entry["min_interval_h"]
        entry["next_check_after"] = _compute_next_check(entry)
    else:
        entry["clean_count"] += 1
        # Apply backoff only if this is not the first clean check.
        # On the first check we just set the interval to the confidence minimum;
        # backoff starts on subsequent clean checks.
        if entry["total_checks"] > 1:
            new_interval = min(
                entry["current_interval_h"] * entry["backoff_factor"],
                entry["max_interval_h"],
                DEFAULT_MAX_INTERVAL_HOURS,
            )
            entry["current_interval_h"] = new_interval
        entry["next_check_after"] = _compute_next_check(entry)

    schedule[page_name] = entry
    save_schedule(schedule)
    return entry


def get_recheck_schedule() -> dict[str, dict[str, Any]]:
    """Return the full recheck schedule for all tracked pages."""
    return load_schedule()


def get_pages_due_for_recheck(
    confidence_filter: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return pages that are due for rechecking, sorted by urgency.

    Urgency = how overdue the next_check_after time is.
    Optionally filter by confidence level.

    Returns list of dicts with page metadata:
        {page_name, confidence, interval_h, overdue_by_h, is_stale_candidate}
    """
    from provenance import get_stale_pages

    schedule = load_schedule()
    now = datetime.now(timezone.utc)

    # Get currently stale pages from provenance (live check)
    try:
        stale_now = set(get_stale_pages(WIKI_DIR, SOURCES_DIR))
    except Exception:
        stale_now = set()

    due: list[dict[str, Any]] = []

    for page_name, entry in schedule.items():
        next_check_str = entry.get("next_check_after")
        if next_check_str is None:
            # Never had a check scheduled — treat as due
            overdue_h = 9999.0
        else:
            due_dt = datetime.fromisoformat(next_check_str)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            delta = now - due_dt
            overdue_h = delta.total_seconds() / 3600

        if overdue_h <= 0 and not (next_check_str is None):
            # Not yet due — skip unless we want upcoming ones
            continue

        conf = entry.get("confidence", "MEDIUM")
        if confidence_filter and conf.upper() != confidence_filter.upper():
            continue

        due.append({
            "page_name":       page_name,
            "confidence":      conf,
            "interval_h":      entry.get("current_interval_h", 24),
            "min_interval_h":  entry.get("min_interval_h", 6),
            "overdue_by_h":    max(0.0, overdue_h),
            "is_currently_stale": page_name in stale_now,
            "total_checks":    entry.get("total_checks", 0),
            "stale_count":     entry.get("stale_count", 0),
            "clean_count":     entry.get("clean_count", 0),
            "last_checked_at": entry.get("last_checked_at"),
            "next_check_after": next_check_str,
        })

    # Sort by overdue amount descending (most overdue first)
    due.sort(key=lambda x: x["overdue_by_h"], reverse=True)

    if limit:
        due = due[:limit]

    return due


# ── Confidence-tier backoff configuration access ─────────────────────────────

def get_confidence_interval(confidence: str, kind: str = "min") -> float:
    """Return the interval in hours for a confidence level.

    Args:
        confidence: HIGH | MEDIUM | LOW
        kind:       "min" | "max"

    Returns:
        Interval in hours as a float.
    """
    conf_upper = confidence.upper()
    if kind == "min":
        return float(DEFAULT_MIN_INTERVALS.get(conf_upper, 24))
    else:
        return float(DEFAULT_MAX_INTERVALS.get(conf_upper, 24 * 7))


# ── CLI helper ────────────────────────────────────────────────────────────────

def print_schedule_summary() -> None:
    """Print a human-readable summary of the recheck schedule."""
    schedule = load_schedule()
    if not schedule:
        print("No recheck schedule recorded yet.")
        print("Pages will be checked on first run and then scheduled per confidence.")
        return

    now = datetime.now(timezone.utc)
    print(f"\nRecheck Schedule — {len(schedule)} pages tracked\n")
    print(f"{'Page':<35} {'Conf':<8} {'Interval':>8} {'Next Check':<28} {'Status'}")
    print("-" * 100)

    for page_name, entry in sorted(schedule.items()):
        conf = entry.get("confidence", "?")
        interval = entry.get("current_interval_h", 0)
        next_check = entry.get("next_check_after")
        if next_check:
            due_dt = datetime.fromisoformat(next_check)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            delta = now - due_dt
            overdue_h = delta.total_seconds() / 3600
            if overdue_h > 0:
                status = f"OVERDUE by {overdue_h:.1f}h"
            else:
                status = f"OK (due in {-overdue_h:.1f}h)"
        else:
            status = "NEVER CHECKED"

        print(
            f"{page_name:<35} {conf:<8} {interval:>6.1f}h  "
            f"{(next_check or 'never'):<28} {status}"
        )


def main() -> None:
    """CLI: python scripts/recheck_scheduler.py"""
    import argparse

    parser = argparse.ArgumentParser(description="Smart recheck scheduler")
    parser.add_argument("--due", action="store_true", help="Show pages due for recheck")
    parser.add_argument("--summary", action="store_true", help="Show full schedule summary")
    parser.add_argument(
        "--recheck", metavar="PAGE", help="Record a recheck result for PAGE (interactive)"
    )
    parser.add_argument(
        "--stale", metavar="PAGE", help="Mark PAGE as stale (resets interval)"
    )
    parser.add_argument(
        "--clean", metavar="PAGE", help="Mark PAGE as clean (applies backoff)"
    )
    parser.add_argument(
        "--confidence", default="MEDIUM", choices=["HIGH", "MEDIUM", "LOW"],
        help="Confidence level for new pages"
    )
    parser.add_argument(
        "--reset", metavar="PAGE", help="Reset PAGE schedule to initial state"
    )
    args = parser.parse_args()

    if args.summary:
        print_schedule_summary()
        return

    if args.due:
        due = get_pages_due_for_recheck()
        if not due:
            print("No pages are currently due for rechecking.")
            return
        print(f"\nPages due for recheck ({len(due)}):\n")
        for item in due:
            stale_mark = " [STALE]" if item["is_currently_stale"] else ""
            print(
                f"  {item['page_name']} [{item['confidence']}] "
                f"overdue={item['overdue_by_h']:.1f}h "
                f"interval={item['interval_h']:.1f}h{stale_mark}"
            )
        return

    if args.stale:
        entry = record_recheck_result(args.stale, is_stale=True, confidence=args.confidence)
        print(f"Recorded STALE for {args.stale}: interval reset to {entry['current_interval_h']:.1f}h")
        return

    if args.clean:
        entry = record_recheck_result(args.clean, is_stale=False, confidence=args.confidence)
        print(
            f"Recorded CLEAN for {args.clean}: "
            f"interval now {entry['current_interval_h']:.1f}h, "
            f"next check after {entry['next_check_after']}"
        )
        return

    if args.recheck:
        # Interactive: check provenance then record
        from provenance import get_stale_pages
        try:
            stale = get_stale_pages(WIKI_DIR, SOURCES_DIR)
        except Exception as e:
            print(f"Could not check staleness: {e}")
            stale = []
        is_stale = args.recheck in stale
        entry = record_recheck_result(args.recheck, is_stale=is_stale, confidence=args.confidence)
        status = "STALE" if is_stale else "CLEAN"
        print(
            f"Recheck {args.recheck}: {status} — "
            f"interval={entry['current_interval_h']:.1f}h, "
            f"total_checks={entry['total_checks']}"
        )
        return

    if args.reset:
        schedule = load_schedule()
        if args.reset in schedule:
            del schedule[args.reset]
            save_schedule(schedule)
            print(f"Reset schedule for {args.reset}.")
        else:
            print(f"No schedule entry found for {args.reset}.")
        return

    # Default: show summary
    print_schedule_summary()


if __name__ == "__main__":
    main()
