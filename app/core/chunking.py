"""
Chunking.

Splits a document into overlapping windows sized for an embedding model. The
splitter slides a window of at most `chunk_size` characters across the text and,
when possible, snaps each window's end to a natural boundary (paragraph break,
then sentence end, then whitespace) that falls inside the window. Consecutive
windows overlap by `chunk_overlap` characters so a fact straddling a boundary is
fully present in at least one chunk.

Guarantee: every emitted chunk has ``len(text) <= chunk_size``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_WHITESPACE = re.compile(r"[ \t]+")


@dataclass
class TextChunk:
    text: str
    char_start: int
    char_end: int


def _normalise(text: str) -> str:
    """Collapse spaces/tabs per line but keep line and paragraph breaks."""
    lines = [_WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
    # Collapse 3+ consecutive blank lines down to a single paragraph break.
    out: List[str] = []
    blank_run = 0
    for line in lines:
        if line:
            out.append(line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run == 1:
                out.append("")
    return "\n".join(out).strip()


def _find_boundary(text: str, lo: int, hi: int) -> Optional[int]:
    """Return the best break position in (lo, hi], or None.

    Preference order: paragraph break > sentence end > newline > space.
    The returned index is the position *after* the boundary character(s).
    """
    window = text[lo:hi]
    # Paragraph break.
    p = window.rfind("\n\n")
    if p != -1 and p > 0:
        return lo + p + 2
    # Sentence end followed by whitespace.
    for sep in (". ", ".\n", "! ", "? ", "。", "！", "？"):
        s = window.rfind(sep)
        if s != -1 and s > 0:
            return lo + s + len(sep)
    # Newline.
    n = window.rfind("\n")
    if n != -1 and n > 0:
        return lo + n + 1
    # Whitespace.
    w = window.rfind(" ")
    if w != -1 and w > 0:
        return lo + w + 1
    return None


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    min_chunk_chars: int = 40,
) -> List[TextChunk]:
    """Chunk ``text`` into overlapping spans no longer than ``chunk_size``."""
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    norm = _normalise(text)
    n = len(norm)
    if n == 0:
        return []
    if n <= chunk_size:
        return [TextChunk(text=norm, char_start=0, char_end=n)]

    chunks: List[TextChunk] = []
    pos = 0
    # Only look for a boundary in the trailing part of the window so chunks
    # don't collapse to tiny fragments.
    soft_floor = max(1, int(chunk_size * 0.6))

    while pos < n:
        hard_end = min(pos + chunk_size, n)
        if hard_end >= n:
            end = n
        else:
            boundary = _find_boundary(norm, pos + soft_floor, hard_end)
            end = boundary if boundary is not None else hard_end

        piece = norm[pos:end].strip()
        if piece and (len(piece) >= min_chunk_chars or not chunks):
            start = norm.find(piece[:32], pos) if piece else pos
            start = start if start != -1 else pos
            chunks.append(TextChunk(text=piece, char_start=start, char_end=start + len(piece)))

        if end >= n:
            break
        # Step forward, retaining `chunk_overlap` chars; always make progress.
        next_pos = end - chunk_overlap
        pos = next_pos if next_pos > pos else end

    return chunks
