"""LLM Knowledge Base v2 — Recheck Daemon

Runs `wiki recheck run` on a configurable interval.
Avoids system crontab complexity — just a Python sleep loop with SIGTERM handling.

Usage:
    .venv/bin/python scripts/recheck_daemon.py --interval 6 --command "recheck run"

The daemon writes its PID to wiki/_recheck_daemon.pid so you can manage it:
    kill $(cat wiki/_recheck_daemon.pid)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
CLI_SCRIPT = REPO_ROOT / "scripts" / "cli.py"
PID_FILE = WIKI_DIR / "_recheck_daemon.pid"


# ── Daemon logic ──────────────────────────────────────────────────────────────

def write_pid() -> None:
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def execute_wiki_command(command: str, ci_mode: bool = True) -> subprocess.CompletedProcess:
    """Run a wiki CLI command in the correct virtualenv.

    Args:
        command: The subcommand string, e.g. "recheck run --ci --json"
        ci_mode: If True, append --ci --json flags automatically

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    argv = command.split()
    if ci_mode and "--ci" not in argv and "--json" not in argv:
        argv.extend(["--ci", "--json"])

    result = subprocess.run(
        [str(VENV_PYTHON), str(CLI_SCRIPT)] + argv,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return result


def append_daemon_log(command: str, result: subprocess.CompletedProcess) -> None:
    """Append a daemon run entry to wiki/_log.md."""
    log_path = WIKI_DIR / "_log.md"
    timestamp = subprocess.run(
        ["date", "+%Y-%m-%d %H:%M:%S"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    entry = (
        f"\n| {timestamp} | recheck-daemon | "
        f"Ran '{command}' → exit={result.returncode} |"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def run_daemon(interval_hours: float, command: str, ci_mode: bool = True) -> None:
    """Main daemon loop with SIGTERM handling.

    Args:
        interval_hours: Hours between runs (supports fractional values)
        command: CLI subcommand to run
        ci_mode: If True, run in CI/silent mode
    """
    write_pid()

    # Handle SIGTERM gracefully
    def handle_sigterm(signum, frame):
        remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    interval_secs = interval_hours * 3600

    while True:
        result = execute_wiki_command(command, ci_mode=ci_mode)
        append_daemon_log(command, result)

        if result.returncode != 0:
            print(f"[recheck-daemon] WARNING: command failed with exit {result.returncode}", flush=True)
            print(f"  stderr: {result.stderr[:200]}", flush=True)

        time.sleep(interval_secs)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="LLM Knowledge Base — Recheck Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Run recheck every 6 hours (default HIGH confidence interval)
  python scripts/recheck_daemon.py --interval 6

  # Run every 1 minute (for testing)
  python scripts/recheck_daemon.py --interval 0.0167

  # Run a different command on a different schedule
  python scripts/recheck_daemon.py --interval 24 --command "refine"
""",
    )
    parser.add_argument(
        "--interval", type=float, default=6.0,
        help="Hours between runs (default: 6, matches HIGH confidence minimum)"
    )
    parser.add_argument(
        "--command", type=str, default="recheck run",
        help="Wiki CLI subcommand to run (default: 'recheck run')"
    )
    parser.add_argument(
        "--no-ci", action="store_true",
        help="Disable CI/silent mode (show human-readable output)"
    )

    args = parser.parse_args()

    print(
        f"[recheck-daemon] Starting — interval={args.interval}h, "
        f"command='{args.command}', CI={not args.no_ci}"
    )
    print(f"[recheck-daemon] PID file: {PID_FILE}")
    print(f"[recheck-daemon] Stop with: kill $(cat {PID_FILE})")

    try:
        run_daemon(
            interval_hours=args.interval,
            command=args.command,
            ci_mode=not args.no_ci,
        )
    except KeyboardInterrupt:
        remove_pid()
        print("\n[recheck-daemon] Stopped.")


if __name__ == "__main__":
    main()
