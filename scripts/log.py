"""
Antigravity Wiki v2 — Chronological Log

Append-only journal tracking every pipeline operation.
Implements the Karpathy LLM-Wiki `log.md` pattern.

Format:
    ## [2026-04-15] ingest | Article: "source_name"
    - Source: sources/article/file.pdf
    - Pages created: Page1, Page2
    - Lint: 0 errors, 2 warnings
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from utils import LOG_PATH, WIKI_DIR


_LOG_HEADER = """\
# Wiki Log

Chronological record of all wiki pipeline operations.
Parseable with `grep`. Newest entries at the bottom.

"""


def append_log(
    event_type: str,
    summary: str,
    details: dict | None = None,
    log_path: Path | None = None,
) -> None:
    """Append a timestamped entry to wiki/_log.md.

    Args:
        event_type: "ingest" | "lint" | "query" | "rebuild" | "consolidate" | "validate"
        summary: One-line description (e.g. source filename, question text)
        details: Optional dict of bullet-point details to include
        log_path: Override log file path (for testing)
    """
    if log_path is None:
        log_path = LOG_PATH

    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file with header if it doesn't exist
    if not log_path.exists():
        log_path.write_text(_LOG_HEADER, encoding="utf-8")

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    entry_lines: list[str] = []
    entry_lines.append(f"\n## [{date_str} {time_str}] {event_type} | {summary}\n")

    if details:
        for key, value in details.items():
            entry_lines.append(f"- **{key}**: {value}")
        entry_lines.append("")  # trailing newline

    entry = "\n".join(entry_lines) + "\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)
