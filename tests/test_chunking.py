from app.core.chunking import chunk_text


def test_small_text_stays_whole():
    chunks = chunk_text("A short note.", chunk_size=800, chunk_overlap=120, min_chunk_chars=4)
    assert len(chunks) == 1
    assert chunks[0].text == "A short note."
    assert chunks[0].char_start == 0


def test_chunks_never_exceed_size():
    text = ("Sentence number {}. ".format) and " ".join(f"Sentence {i} with some filler words." for i in range(200))
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=40, min_chunk_chars=20)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)


def test_overlap_is_present():
    text = " ".join(f"token{i}" for i in range(300))
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=50, min_chunk_chars=20)
    # consecutive chunks should share some tail/head text given overlap
    assert len(chunks) >= 2
    a, b = chunks[0].text, chunks[1].text
    assert any(tok in b for tok in a.split()[-3:])


def test_tiny_trailing_fragment_not_emitted_alone():
    chunks = chunk_text("word " * 100, chunk_size=120, chunk_overlap=20, min_chunk_chars=30)
    assert all(len(c.text) >= 30 or c is chunks[-1] for c in chunks)
