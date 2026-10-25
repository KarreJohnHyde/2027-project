"""Safety and RFC-conformance checks for clinical CSV text rendering."""

import pytest

from app.services import document_parser


def test_csv_parser_handles_quoted_commas_newlines_quotes_and_uneven_rows():
    content = (
        'name,note,value\r\n'
        '"alpha, beta","line one\r\nline two",42\r\n'
        'short,only\r\n'
        'extra,"said ""ok""",7,overflow\r\n'
    ).encode("utf-8")

    rendered = document_parser.extract_text_from_csv(content)

    assert rendered.splitlines() == [
        "CLINICAL TABULAR REPORT (3 rows):",
        "name: alpha, beta | note: line one line two | value: 42",
        "name: short | note: only",
        'name: extra | note: said "ok" | value: 7 | Col3: overflow',
    ]


def test_csv_parser_strips_utf8_bom_and_caps_rendered_rows(monkeypatch):
    monkeypatch.setattr(document_parser, "MAX_CSV_ROWS", 2)
    content = "\ufeffanalyte,value\nA,1\nB,2\nC,3\n".encode("utf-8")

    rendered = document_parser.extract_text_from_csv(content)

    assert rendered.splitlines() == [
        "CLINICAL TABULAR REPORT (3 rows):",
        "analyte: A | value: 1",
        "analyte: B | value: 2",
        "[Truncated after 2 rows]",
    ]


@pytest.mark.parametrize(
    "content",
    [
        b'name,note\nvalue,"unterminated\n',
        b"name,value\nunsafe,\x00\n",
    ],
)
def test_csv_parser_rejects_malformed_or_nul_input(content):
    with pytest.raises(ValueError, match="CSV"):
        document_parser.extract_text_from_csv(content)
