def test_seed_showcase_and_query(client):
    # Seed the showcase + examples into the demo namespace.
    r = client.post("/v1/demo/seed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["namespace"] == "demo"
    assert body["documents"] >= 4              # showcase + 3 examples
    assert body["chunks"] >= 5
    assert len(body["suggested_questions"]) >= 5
    assert any(d["filename"] == "AI_SOFTWARE_SHOWCASE_FILE.md" for d in body["ingested"])

    # A suggested question should return a grounded, cited answer.
    q = client.post("/v1/query", json={
        "question": "How long does the Helios One battery last and what is its payload?",
        "namespace": "demo", "include_chunks": True,
    }).json()
    assert q["grounded"] is True
    assert any(c["filename"] == "AI_SOFTWARE_SHOWCASE_FILE.md" for c in q["citations"])


def test_seed_is_idempotent(client):
    first = client.post("/v1/demo/seed").json()
    second = client.post("/v1/demo/seed").json()
    # Same document count, and the second pass deduplicates everything.
    assert second["documents"] == first["documents"]
    assert all(d["deduplicated"] for d in second["ingested"])
