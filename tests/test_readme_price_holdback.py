"""P167: since 5 Nov 2026 the market-price workflow holds back a new price
that would outdate the hand-written docs (the docs_pin tests pin the price),
so the README must not say the fixture refreshes weekly or that the prose
may lag the fixture."""

from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def test_readme_does_not_claim_a_weekly_price_refresh():
    assert "is refreshed weekly by" not in README


def test_readme_says_a_new_price_is_held_back_until_the_docs_are_regenerated():
    assert "held back" in README
    assert "docs_pin" in README
