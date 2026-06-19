"""
Text extraction.

Turns uploaded bytes into plain text the rest of the pipeline can chunk and
embed. Supported formats: plain text, Markdown, CSV, and PDF. The format is
chosen from the filename extension first (most reliable) and the declared MIME
type second.
"""
from __future__ import annotations

import csv
import io
from typing import Tuple

from app.errors import EmptyDocumentError, UnsupportedFileTypeError
from app.logging_config import get_logger

logger = get_logger("eka.extraction")

TEXT_EXTS = {".txt", ".text", ".log"}
MARKDOWN_EXTS = {".md", ".markdown"}
CSV_EXTS = {".csv", ".tsv"}
PDF_EXTS = {".pdf"}

SUPPORTED_EXTS = TEXT_EXTS | MARKDOWN_EXTS | CSV_EXTS | PDF_EXTS


def _ext(filename: str) -> str:
    name = filename.lower().strip()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def _decode(raw: bytes) -> str:
    """Decode bytes as UTF-8, falling back to latin-1 so we never crash."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_csv(raw: bytes, delimiter: str) -> str:
    """Render tabular data as 'column: value' lines, one block per row.

    This layout keeps each row's fields lexically close together, which helps
    both keyword and vector retrieval treat a row as a coherent unit.
    """
    text = _decode(raw)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ""

    header = rows[0]
    has_header = all(cell.strip() for cell in header) and len(set(header)) == len(header)

    lines = []
    if has_header:
        for row in rows[1:]:
            pairs = [
                f"{header[i].strip()}: {cell.strip()}"
                for i, cell in enumerate(row)
                if i < len(header) and cell.strip()
            ]
            if pairs:
                lines.append("; ".join(pairs))
    else:
        for row in rows:
            cells = [c.strip() for c in row if c.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency always present
        raise UnsupportedFileTypeError(
            "PDF support requires the 'pypdf' package."
        ) from exc

    reader = PdfReader(io.BytesIO(raw))
    parts = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - a single bad page shouldn't abort ingestion
            page_text = ""
        if page_text.strip():
            parts.append(page_text.strip())
    return "\n\n".join(parts)


def extract_text(raw: bytes, filename: str, content_type: str = "") -> Tuple[str, str]:
    """Extract plain text from uploaded bytes.

    Returns (text, resolved_kind) where resolved_kind is one of
    "text" | "markdown" | "csv" | "pdf".

    Raises:
        UnsupportedFileTypeError: the extension/MIME type is not handled.
        EmptyDocumentError: extraction produced no usable text.
    """
    ext = _ext(filename)
    ctype = (content_type or "").lower()

    if ext in PDF_EXTS or "pdf" in ctype:
        kind, text = "pdf", _extract_pdf(raw)
    elif ext in CSV_EXTS or "csv" in ctype:
        delimiter = "\t" if ext == ".tsv" else ","
        kind, text = "csv", _extract_csv(raw, delimiter)
    elif ext in MARKDOWN_EXTS or "markdown" in ctype:
        kind, text = "markdown", _decode(raw)
    elif ext in TEXT_EXTS or ctype.startswith("text/"):
        kind, text = "text", _decode(raw)
    else:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext or content_type or 'unknown'}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTS))}."
        )

    text = text.strip()
    if not text:
        raise EmptyDocumentError("No extractable text was found in the document.")

    logger.info(
        "extracted_text",
        extra={"kind": kind, "file": filename, "chars": len(text)},
    )
    return text, kind
