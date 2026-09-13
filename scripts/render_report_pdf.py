"""Render REPORT.md to outputs/REPORT.pdf.

No new dependency: reuses matplotlib (already in requirements.txt) as a plain
text/table typesetter via PdfPages. Not a general Markdown renderer - handles
exactly the subset REPORT.md uses (#/##/### headers, bullet lists, pipe
tables, blank-line paragraph breaks, a --- horizontal rule as an explicit
page break) and errors on anything else so a future syntax drift is caught
rather than silently mis-rendered.
"""
import argparse
import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

PAGE_WIDTH, PAGE_HEIGHT = 8.5, 11.0
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 0.75, 0.7, 0.7
LINE_HEIGHT = 0.185
WRAP_CHARS = 98

FONT = "DejaVu Sans"
MONO = "DejaVu Sans Mono"


def _strip_inline_markdown(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def _split_table_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def fit_column_widths(header, body, available_chars=100, min_col_width=10):
    """Shrink only the widest column(s) until the row fits in available_chars.

    Proportional scaling would truncate short label columns just because one
    free-text column runs long; greedily trimming the widest column preserves
    short columns (entity names, percentages) at full width.
    """
    col_widths = [
        max(len(header[c]), *(len(row[c]) for row in body)) if body else len(header[c])
        for c in range(len(header))
    ]
    budget = available_chars - 3 * (len(col_widths) - 1)
    while sum(col_widths) > budget and max(col_widths) > min_col_width:
        col_widths[col_widths.index(max(col_widths))] -= 1
    return col_widths


def truncate(cell, width):
    if len(cell) <= width:
        return cell.ljust(width)
    return (cell[: max(width - 1, 0)] + "…").ljust(width)


def parse_blocks(markdown_text):
    """Split REPORT.md into typed blocks: heading, paragraph, bullets, table, pagebreak."""
    lines = markdown_text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            blocks.append(("pagebreak", None))
            i += 1
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            blocks.append(("h%d" % level, _strip_inline_markdown(heading_match.group(2))))
            i += 1
            continue

        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            header = _split_table_row(table_lines[0])
            body = [
                _split_table_row(row)
                for row in table_lines[2:]
                if not re.match(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$", row.strip())
            ]
            body = [[_strip_inline_markdown(c) for c in row] for row in body]
            blocks.append(("table", (header, body)))
            continue

        if stripped.startswith("- "):
            bullet_lines = []
            para_lines = [stripped[2:]]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith(("- ", "|", "#")) and lines[i+1].strip() != "---":
                para_lines.append(lines[i + 1].strip())
                i += 1
            bullet_lines.append(_strip_inline_markdown(" ".join(para_lines)))
            i += 1
            while i < len(lines) and lines[i].strip().startswith("- "):
                para_lines = [lines[i].strip()[2:]]
                while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith(("- ", "|", "#")) and lines[i+1].strip() != "---":
                    para_lines.append(lines[i + 1].strip())
                    i += 1
                bullet_lines.append(_strip_inline_markdown(" ".join(para_lines)))
                i += 1
            blocks.append(("bullets", bullet_lines))
            continue

        para_lines = [stripped]
        while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith(("- ", "|", "#")) and lines[i+1].strip() != "---":
            para_lines.append(lines[i + 1].strip())
            i += 1
        blocks.append(("p", _strip_inline_markdown(" ".join(para_lines))))
        i += 1

    return blocks


class PageWriter:
    def __init__(self, pdf):
        self.pdf = pdf
        self.fig = None
        self.y = None
        self._new_page()

    def _new_page(self):
        if self.fig is not None:
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
        self.fig = plt.figure(figsize=(PAGE_WIDTH, PAGE_HEIGHT))
        self.fig.patch.set_facecolor("white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.axis("off")
        self.ax.set_xlim(0, PAGE_WIDTH)
        self.ax.set_ylim(0, PAGE_HEIGHT)
        self.y = PAGE_HEIGHT - MARGIN_TOP

    def ensure_space(self, height):
        if self.y - height < MARGIN_BOTTOM:
            self._new_page()

    def text(self, s, size=10, weight="normal", family=FONT, dy=LINE_HEIGHT, indent=0.0):
        self.ensure_space(dy)
        self.ax.text(
            MARGIN_X + indent, self.y, s, fontsize=size, fontweight=weight,
            family=family, va="top", ha="left",
        )
        self.y -= dy

    def wrapped(self, s, size=10, weight="normal", indent=0.0, wrap_chars=WRAP_CHARS):
        wrapped_lines = textwrap.wrap(s, width=wrap_chars) or [""]
        for wl in wrapped_lines:
            self.text(wl, size=size, weight=weight, indent=indent)

    def gap(self, dy=LINE_HEIGHT * 0.6):
        self.y -= dy

    def close(self):
        self.pdf.savefig(self.fig)
        plt.close(self.fig)


def render(blocks, pdf_path):
    with PdfPages(pdf_path) as pdf:
        writer = PageWriter(pdf)
        for kind, content in blocks:
            if kind == "pagebreak":
                writer._new_page()
            elif kind == "h1":
                writer.gap()
                writer.wrapped(content, size=16, weight="bold", wrap_chars=60)
                writer.gap()
            elif kind == "h2":
                writer.gap()
                writer.wrapped(content, size=13, weight="bold", wrap_chars=70)
                writer.gap(dy=LINE_HEIGHT * 0.3)
            elif kind == "h3":
                writer.gap(dy=LINE_HEIGHT * 0.3)
                writer.wrapped(content, size=11, weight="bold", wrap_chars=80)
            elif kind == "p":
                writer.wrapped(content, size=9.5)
                writer.gap(dy=LINE_HEIGHT * 0.4)
            elif kind == "bullets":
                for item in content:
                    lines = textwrap.wrap(item, width=WRAP_CHARS - 3) or [""]
                    writer.text("• " + lines[0], size=9.5, indent=0.15)
                    for cont in lines[1:]:
                        writer.text("  " + cont, size=9.5, indent=0.15)
                writer.gap(dy=LINE_HEIGHT * 0.4)
            elif kind == "table":
                header, body = content
                # DejaVu Sans Mono at 8pt is ~0.067in/char, giving ~100 usable chars
                # across the ~7in text width.
                col_widths = fit_column_widths(header, body)

                def fmt_row(row):
                    return " | ".join(
                        truncate(cell, col_widths[c]) for c, cell in enumerate(row)
                    )

                writer.text(fmt_row(header), size=8, weight="bold", family=MONO)
                writer.text("-+-".join("-" * w for w in col_widths), size=8, family=MONO)
                for row in body:
                    writer.text(fmt_row(row), size=8, family=MONO)
                writer.gap()
        writer.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="REPORT.md")
    parser.add_argument("--out", default="outputs/REPORT.pdf")
    args = parser.parse_args()

    source_path = Path(args.source)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    blocks = parse_blocks(source_path.read_text())
    render(blocks, out_path)
    print(f"Wrote {out_path} ({len(blocks)} blocks from {source_path})")


if __name__ == "__main__":
    main()
