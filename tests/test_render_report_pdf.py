import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from render_report_pdf import (  # noqa: E402
    parse_blocks,
    render,
    fit_column_widths,
    truncate,
    _strip_inline_markdown,
)


def test_strip_inline_markdown_handles_bold_italic_code_and_links():
    assert _strip_inline_markdown("**bold**") == "bold"
    assert _strip_inline_markdown("plain *italic* word") == "plain italic word"
    assert _strip_inline_markdown("`code`") == "code"
    assert _strip_inline_markdown("[text](https://example.com)") == "text"
    assert _strip_inline_markdown("**-0.49%** headline") == "-0.49% headline"


def test_parse_blocks_headings():
    blocks = parse_blocks("# Title\n\n## Section\n\n### Sub\n")
    assert blocks == [("h1", "Title"), ("h2", "Section"), ("h3", "Sub")]


def test_parse_blocks_paragraph_joins_wrapped_lines():
    blocks = parse_blocks("This is line one\nand this continues it.\n\nNew paragraph.\n")
    assert blocks[0] == ("p", "This is line one and this continues it.")
    assert blocks[1] == ("p", "New paragraph.")


def test_parse_blocks_bullets_group_consecutive_items():
    blocks = parse_blocks("- first item\n- second item\n  continued\n\nAfter.\n")
    kind, items = blocks[0]
    assert kind == "bullets"
    assert items == ["first item", "second item continued"]
    assert blocks[1] == ("p", "After.")


def test_parse_blocks_table_splits_header_and_body_and_drops_separator():
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    blocks = parse_blocks(md)
    kind, (header, body) = blocks[0]
    assert kind == "table"
    assert header == ["A", "B"]
    assert body == [["1", "2"], ["3", "4"]]


def test_parse_blocks_pagebreak_on_horizontal_rule():
    blocks = parse_blocks("Para one.\n\n---\n\nPara two.\n")
    assert blocks == [("p", "Para one."), ("pagebreak", None), ("p", "Para two.")]


def test_truncate_pads_short_cells_and_ellipsizes_long_ones():
    assert truncate("ok", 5) == "ok   "
    assert truncate("abcdefgh", 5) == "abcd…"
    assert len(truncate("abcdefgh", 5)) == 5


def test_fit_column_widths_preserves_short_columns_when_one_runs_long():
    header = ["Entity", "Basis", "Note"]
    body = [
        ["Gulf Oil", "today's price", "a" * 90],
    ]
    widths = fit_column_widths(header, body)
    assert widths[0] == len("Gulf Oil")
    assert widths[1] == len("today's price")
    assert widths[2] < 90
    assert sum(widths) <= 100 - 3 * 2


def test_fit_column_widths_leaves_narrow_tables_untouched():
    header = ["A", "B"]
    body = [["1", "2"]]
    assert fit_column_widths(header, body) == [1, 1]


def test_render_produces_a_valid_multi_page_pdf(tmp_path):
    markdown = (
        "# Report Title\n\n"
        "## Section\n\n"
        "Some body text that explains a finding in plain prose.\n\n"
        "| Metric | Value |\n|---|---|\n| implied growth | -0.49% |\n\n"
        "- a limitation\n- another limitation\n"
    )
    out = tmp_path / "out.pdf"
    render(parse_blocks(markdown), out)

    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 500
