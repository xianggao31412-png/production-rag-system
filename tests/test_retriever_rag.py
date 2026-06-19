from app.config import Settings
from app.core.embeddings.hash_embedder import HashEmbedder
from app.core.keyword.bm25_index import BM25Index
from app.core.vectorstore.memory_store import MemoryVectorStore
from app.core.rerank.heuristic import HeuristicReranker
from app.core.retriever import Retriever
from app.core.rag import RagComposer
from app.models.domain import Chunk, ScoredChunk


def _build(tmp_path):
    s = Settings(data_dir=str(tmp_path), llm_force_stub=True, require_auth=False)
    emb = HashEmbedder(dim=128)
    vs = MemoryVectorStore(persist_path=str(tmp_path / "v.pkl"))
    bm = BM25Index()
    texts = {
        "ch1": "Employees receive 20 days of paid annual leave each year.",
        "ch2": "To reset your password open settings and click reset password.",
        "ch3": "The office is open from nine to five on weekdays.",
    }
    chunks = {}
    for i, (cid, txt) in enumerate(texts.items()):
        chunks[cid] = Chunk(id=cid, document_id="d1", namespace="ns", ordinal=i,
                            text=txt, filename="f.txt", char_start=0, char_end=len(txt))
    vs.add("ns", [(cid, emb.embed_query(t)) for cid, t in texts.items()])
    bm.add("ns", [(cid, t) for cid, t in texts.items()])

    def lookup(namespace, ids):
        return {cid: chunks[cid] for cid in ids if cid in chunks}

    r = Retriever(s, emb, vs, bm, lookup, HeuristicReranker())
    return s, r


def test_retriever_ranks_relevant_first(tmp_path):
    s, r = _build(tmp_path)
    scored, timings = r.retrieve("ns", "how many vacation days of annual leave", use_hybrid=True, use_rerank=True)
    assert scored
    assert scored[0].chunk.id == "ch1"
    assert "embed_ms" in timings and "vector_search_ms" in timings


def test_hybrid_populates_keyword_score(tmp_path):
    s, r = _build(tmp_path)
    scored, _ = r.retrieve("ns", "reset password settings", use_hybrid=True, use_rerank=False)
    top = scored[0]
    assert top.chunk.id == "ch2"
    assert top.keyword_score is not None


def test_rag_stub_is_grounded_and_cited(tmp_path):
    s, r = _build(tmp_path)
    scored, timings = r.retrieve("ns", "how many vacation days", use_hybrid=True, use_rerank=True)
    rag = RagComposer(s, llm_client=None)
    res = rag.compose("how many vacation days", scored, answer_style="concise", retrieval_timings=timings)
    assert res.grounded is True
    assert len(res.citations) >= 1
    assert res.citations[0].marker.startswith("[")
    assert res.model == "extractive-stub"


def test_rag_handles_no_chunks(tmp_path):
    s, r = _build(tmp_path)
    rag = RagComposer(s, llm_client=None)
    res = rag.compose("anything", [], answer_style="detailed")
    assert res.grounded is False
    assert res.citations == []
