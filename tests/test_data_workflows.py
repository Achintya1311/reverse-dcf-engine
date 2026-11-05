"""D47: every fixture refresh runs the tests on what it fetched before it pushes.

A push made with the workflow's GITHUB_TOKEN does not start ci.yml, so the
refresh run is the only one that sees the new fixtures. Until 5 Nov 2026 the
refreshes pushed first and tested after, so a price move that outdated the
hand-written README/REPORT numbers (D46) left main red for days. Now the code
tests gate the run, and the docs_pin tests gate the commit: a fixture that
would outdate the docs is held back with a warning instead of pushed.
"""

from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
REFRESHES = ["fetch-market-price.yml", "fetch-peer-comparables.yml", "fetch-wacc-inputs.yml"]


@pytest.mark.parametrize("name", REFRESHES)
def test_refresh_tests_before_it_pushes(name: str) -> None:
    text = (WORKFLOWS / name).read_text()
    lines = [line.strip() for line in text.splitlines()]
    assert "git push" in lines, name
    code_tests = 'run: pytest -q -m "not docs_pin"'
    assert code_tests in lines, f"{name} never runs the code tests"
    assert "if pytest -q -m docs_pin; then" in lines, f"{name} never checks the docs"
    push = lines.index("git push")
    assert lines.index(code_tests) < push, f"{name} pushes before it tests"
    assert lines.index("if pytest -q -m docs_pin; then") < push, f"{name} pushes before the docs check"
    assert "if: steps.docs.outputs.match == 'true'" in lines, f"{name} commits even when the docs are stale"
    assert "python -m pytest" not in text  # P8: bare pytest, so a broken install fails
    assert 'run: pip install -e ".[dev]"' in lines
