from __future__ import annotations

import difflib


def generate_diff(original: str, fixed: str, filename: str = "code") -> str:
    """Return a unified diff string between original and fixed code."""
    original_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        fixed_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )
    return "".join(diff)


def generate_html_diff(original: str, fixed: str) -> str:
    """Return an HTML table diff for side-by-side display."""
    differ = difflib.HtmlDiff(wrapcolumn=80)
    return differ.make_table(
        original.splitlines(),
        fixed.splitlines(),
        fromdesc="Original",
        todesc="Fixed",
        context=True,
        numlines=3,
    )
