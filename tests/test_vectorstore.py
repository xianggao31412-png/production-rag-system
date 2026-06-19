import os
from app.core.vectorstore.memory_store import MemoryVectorStore


def _vec(seed, dim=8):
    import math
    v = [math.sin(seed + i) for i in range(dim)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def test_add_query_count(tmp_path):
    s = MemoryVectorStore(persist_path=str(tmp_path / "v.pkl"))
    s.add("ns", [("c1", _vec(1)), ("c2", _vec(2)), ("c3", _vec(3))])
    assert s.count("ns") == 3
    hits = s.query("ns", _vec(1), top_k=2)
    assert hits[0][0] == "c1"           # closest to itself
    assert len(hits) == 2


def test_delete(tmp_path):
    s = MemoryVectorStore(persist_path=str(tmp_path / "v.pkl"))
    s.add("ns", [("c1", _vec(1)), ("c2", _vec(2))])
    removed = s.delete_chunks("ns", ["c1"])
    assert removed == 1
    assert s.count("ns") == 1


def test_persist_roundtrip(tmp_path):
    p = str(tmp_path / "v.pkl")
    s = MemoryVectorStore(persist_path=p)
    s.add("ns", [("c1", _vec(1)), ("c2", _vec(2))])
    s.persist()
    assert os.path.exists(p)
    s2 = MemoryVectorStore(persist_path=p)
    assert s2.count("ns") == 2
    assert s2.query("ns", _vec(1), top_k=1)[0][0] == "c1"


def test_namespace_isolation(tmp_path):
    s = MemoryVectorStore(persist_path=str(tmp_path / "v.pkl"))
    s.add("a", [("c1", _vec(1))])
    s.add("b", [("c2", _vec(2))])
    assert s.count("a") == 1 and s.count("b") == 1
    assert set(s.namespaces()) == {"a", "b"}
