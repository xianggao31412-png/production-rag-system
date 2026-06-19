from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from tests.conftest import make_settings


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_components(client):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    names = {c["name"] for c in body["components"]}
    assert {"vector_store", "embedder", "llm"} <= names


def test_upload_then_list(client):
    r = client.post("/v1/documents?namespace=corp",
                    files={"file": ("a.txt", b"Annual leave is 20 days for full time staff.")})
    assert r.status_code == 201
    body = r.json()
    assert body["chunk_count"] >= 1 and body["deduplicated"] is False
    lst = client.get("/v1/documents?namespace=corp").json()
    assert lst["total"] == 1


def test_dedup_on_reupload(client):
    payload = {"file": ("a.txt", b"Identical content for dedup test.")}
    client.post("/v1/documents?namespace=ns", files=payload)
    again = client.post("/v1/documents?namespace=ns", files={"file": ("a.txt", b"Identical content for dedup test.")})
    assert again.json()["deduplicated"] is True


def test_query_grounded_with_citations(seeded_client):
    r = seeded_client.post("/v1/query", json={
        "question": "How many vacation days do employees get?",
        "namespace": "corp", "include_chunks": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is True
    assert len(body["citations"]) >= 1
    assert "embed_ms" in body["timings_ms"] and "total_ms" in body["timings_ms"]
    assert body["chunks"]  # included


def test_admin_endpoints(seeded_client):
    seeded_client.post("/v1/query", json={"question": "reset password", "namespace": "corp"})
    stats = seeded_client.get("/v1/admin/stats").json()
    assert stats["total_documents"] == 3 and stats["total_chunks"] >= 3
    metrics = seeded_client.get("/v1/admin/metrics").json()
    assert metrics["total_queries"] >= 1
    queries = seeded_client.get("/v1/admin/queries?limit=5").json()
    assert queries["total"] >= 1 and len(queries["items"]) >= 1


def test_delete_document(seeded_client):
    doc_id = seeded_client.get("/v1/documents?namespace=corp").json()["documents"][0]["id"]
    r = seeded_client.delete(f"/v1/documents/{doc_id}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert seeded_client.get("/v1/documents?namespace=corp").json()["total"] == 2


def test_delete_missing_is_404(client):
    assert client.delete("/v1/documents/doc_does_not_exist").status_code == 404


def test_validation_error_envelope(client):
    # missing required 'question'
    r = client.post("/v1/query", json={"namespace": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "request_id" in body


def test_auth_enforced(tmp_path):
    s = make_settings(tmp_path, require_auth=True, api_keys_raw="secret-key")
    app = create_app(s)
    with TestClient(app) as c:
        # no key -> 401
        assert c.post("/v1/documents", files={"file": ("a.txt", b"hello world")}).status_code == 401
        # wrong key -> 401
        assert c.get("/v1/admin/stats", headers={"X-API-Key": "nope"}).status_code == 401
        # correct key -> ok
        ok = c.post("/v1/documents?namespace=n", files={"file": ("a.txt", b"hello world")},
                    headers={"X-API-Key": "secret-key"})
        assert ok.status_code == 201
        # health stays open
        assert c.get("/health").status_code == 200
