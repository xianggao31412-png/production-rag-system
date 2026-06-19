from app.models.domain import Document, Chunk, new_id
from app.storage.metadata_store import MetadataStore
from app.storage.analytics_store import AnalyticsStore


def _doc_and_chunks(ns="default", h="hash1"):
    doc = Document(id=new_id("doc"), namespace=ns, filename="f.txt", content_type="text/plain",
                   content_hash=h, size_bytes=10, char_count=8, chunk_count=2)
    chunks = [
        Chunk(id=new_id("ch"), document_id=doc.id, namespace=ns, ordinal=0,
              text="first chunk text", filename="f.txt", char_start=0, char_end=16),
        Chunk(id=new_id("ch"), document_id=doc.id, namespace=ns, ordinal=1,
              text="second chunk text", filename="f.txt", char_start=16, char_end=33),
    ]
    return doc, chunks


def test_add_dedup_get_delete(tmp_path):
    md = MetadataStore(str(tmp_path / "m.db"))
    doc, chunks = _doc_and_chunks()
    md.add_document(doc, chunks)
    assert md.counts() == (1, 2)
    assert md.get_document_by_hash("default", "hash1") is not None
    got = md.get_chunks("default", [c.id for c in chunks])
    assert len(got) == 2 and got[chunks[0].id].text == "first chunk text"
    ns, ids = md.delete_document(doc.id)
    assert ns == "default" and len(ids) == 2
    assert md.counts() == (0, 0)
    md.close()


def test_iter_all_chunks_and_namespace_stats(tmp_path):
    md = MetadataStore(str(tmp_path / "m.db"))
    d1, c1 = _doc_and_chunks(ns="a", h="h_a")
    d2, c2 = _doc_and_chunks(ns="b", h="h_b")
    md.add_document(d1, c1); md.add_document(d2, c2)
    allc = md.iter_all_chunks()
    assert len(allc) == 4
    stats = dict((ns, (d, c)) for ns, d, c in md.namespace_stats())
    assert stats["a"] == (1, 2) and stats["b"] == (1, 2)
    md.close()


def test_analytics_metrics(tmp_path):
    an = AnalyticsStore(str(tmp_path / "a.db"))
    an.record_query("ns", "q1", True, 2, 10.0, "stub", True)
    an.record_query("ns", "q2", False, 0, 30.0, "stub", True)
    an.record_query("other", "q3", True, 1, 20.0, "stub", False)
    m = an.metrics()
    assert m["total_queries"] == 3
    assert 0.0 <= m["grounded_rate"] <= 1.0
    assert m["queries_per_namespace"]["ns"] == 2
    items, total = an.recent(limit=2)
    assert total == 3 and len(items) == 2
    an.close()
