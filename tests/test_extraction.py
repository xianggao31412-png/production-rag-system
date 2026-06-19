import pytest
from app.core.extraction import extract_text
from app.errors import UnsupportedFileTypeError, EmptyDocumentError


def test_txt():
    text, kind = extract_text(b"hello world", "a.txt", "text/plain")
    assert "hello world" in text and kind == "text"


def test_markdown():
    text, kind = extract_text(b"# Title\nbody", "a.md", "")
    assert "Title" in text and kind in ("md", "markdown", "txt")


def test_csv_rows_rendered():
    raw = b"name,role\nAda,Engineer\nGrace,Architect"
    text, kind = extract_text(raw, "t.csv", "text/csv")
    assert "Ada" in text and "Engineer" in text and kind == "csv"


def test_unsupported_type_raises():
    with pytest.raises(UnsupportedFileTypeError):
        extract_text(b"\x00\x01", "x.exe", "application/octet-stream")


def test_empty_raises():
    with pytest.raises((EmptyDocumentError, UnsupportedFileTypeError)):
        extract_text(b"", "a.txt", "text/plain")
