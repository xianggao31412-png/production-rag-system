from app.core.fusion import fuse
from app.core.rerank.heuristic import HeuristicReranker


def test_rrf_rewards_agreement():
    vector = [("a", 0.9), ("b", 0.8), ("c", 0.1)]
    keyword = [("b", 5.0), ("a", 4.0), ("d", 1.0)]
    hits = fuse(vector, keyword, method="rrf", rrf_k=60)
    ids = [h.chunk_id for h in hits]
    # a and b appear high in both -> should top the fused list
    assert set(ids[:2]) == {"a", "b"}


def test_weighted_fusion_runs():
    vector = [("a", 0.9), ("b", 0.2)]
    keyword = [("a", 1.0), ("b", 0.5)]
    hits = fuse(vector, keyword, method="weighted", vector_weight=0.5, keyword_weight=0.5)
    assert hits[0].chunk_id == "a"


def test_heuristic_reranker_orders_by_relevance():
    rr = HeuristicReranker()
    docs = [
        ("c1", "Annual leave policy: employees get 20 vacation days per year."),
        ("c2", "The cafeteria serves lunch from noon."),
    ]
    ranked = rr.rerank("How many vacation days of annual leave?", docs)
    assert ranked[0][0] == "c1"
    assert ranked[0][1] >= ranked[1][1]
