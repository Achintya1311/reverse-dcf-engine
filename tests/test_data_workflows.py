"""D47: every fixture refresh runs the tests on what it just pushed.

A push made with the workflow's GITHUB_TOKEN does not start ci.yml, so without
this a refresh that outdates REPORT.md or the README (D46) shows no red run.
"""

from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
REFRESHES = ["fetch-market-price.yml", "fetch-peer-comparables.yml", "fetch-wacc-inputs.yml"]


@pytest.mark.parametrize("name", REFRESHES)
def test_refresh_runs_bare_pytest_after_its_push(name: str) -> None:
    text = (WORKFLOWS / name).read_text()
    lines = [line.strip() for line in text.splitlines()]
    assert "git push" in lines, name
    assert "pytest -q" in lines, f"{name} never runs the tests"
    assert lines.index("pytest -q") > lines.index("git push"), f"{name} tests before it pushes"
    assert "python -m pytest" not in text  # P8: bare pytest, so a broken install fails
    assert 'pip install -e ".[dev]"' in lines
