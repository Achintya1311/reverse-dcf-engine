"""S28: the repo's named-stock pages carry PLAN.md rule 1's disclaimer, not only README.md."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_report_pdf import parse_blocks  # noqa: E402

RULE_1 = "Educational research on historical data. Not investment advice. Not a SEBI-registered research analyst."


@pytest.mark.parametrize("page", ["REPORT.md", "research/shortlist.md"])
def test_page_carries_rule_1(page):
    assert RULE_1 in (ROOT / page).read_text()


def test_report_pdf_puts_the_disclaimer_before_the_first_section():
    blocks = parse_blocks((ROOT / "REPORT.md").read_text())
    first_h2 = next(i for i, (kind, _) in enumerate(blocks) if kind == "h2")
    assert any(kind == "p" and RULE_1 in str(text) for kind, text in blocks[:first_h2])
