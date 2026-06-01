import subprocess
import sys
import pytest


def run_scout(*args):
    result = subprocess.run(
        [sys.executable, "scout.py", *args],
        capture_output=True,
        text=True,
        cwd="/Users/francois/dev/forestgarden",
    )
    return result


def test_cli_help():
    result = run_scout("--help")
    assert result.returncode == 0
    assert "fetch" in result.stdout
    assert "filter" in result.stdout
    assert "map" in result.stdout
    assert "run" in result.stdout
    assert "stats" in result.stdout


def test_cli_stats_no_db():
    """Stats should fail gracefully when no database exists."""
    result = run_scout("stats", "--db", "/tmp/nonexistent_scout_test.db")
    assert result.returncode != 0 or "no database" in result.stderr.lower() or "no database" in result.stdout.lower()
