from app.core.embeddings.hash_embedder import HashEmbedder


def test_dimension_and_determinism():
    e = HashEmbedder(dim=384)
    assert e.dimension == 384
    v1 = e.embed_query("enterprise knowledge assistant")
    v2 = e.embed_query("enterprise knowledge assistant")
    assert v1 == v2
    assert len(v1) == 384


def test_unit_norm():
    e = HashEmbedder(dim=128)
    v = e.embed_query("vectors are normalised")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_similar_text_more_similar():
    e = HashEmbedder(dim=256)
    def cos(a, b): return sum(x * y for x, y in zip(a, b))
    base = e.embed_query("annual leave vacation policy")
    near = e.embed_query("vacation leave policy annual")
    far = e.embed_query("kubernetes container orchestration")
    assert cos(base, near) > cos(base, far)
