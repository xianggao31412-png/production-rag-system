from app.core.keyword.bm25_index import BM25Index, tokenize


def test_tokenize_filters_stopwords():
    toks = tokenize("How do I reset the password?")
    assert "reset" in toks and "password" in toks
    assert "the" not in toks and "do" not in toks


def test_single_document_corpus_returns_match():
    # Regression: BM25 idf goes negative on a tiny corpus; matches must survive.
    idx = BM25Index()
    idx.add("ns", [("c1", "The launch is scheduled for the third quarter budget")])
    hits = idx.query("ns", "launch budget", top_k=5)
    assert hits and hits[0][0] == "c1"


def test_overlap_filter_excludes_unrelated():
    idx = BM25Index()
    idx.add("ns", [
        ("c1", "quarterly budget review and launch expenses"),
        ("c2", "cats are small carnivorous mammals"),
    ])
    hits = dict(idx.query("ns", "budget launch", top_k=5))
    assert "c1" in hits and "c2" not in hits


def test_delete_and_count():
    idx = BM25Index()
    idx.add("ns", [("c1", "alpha beta"), ("c2", "gamma delta")])
    assert idx.count("ns") == 2
    assert idx.delete_chunks("ns", ["c1"]) == 1
    assert idx.count("ns") == 1
