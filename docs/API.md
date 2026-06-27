# API Reference

Base URL (default): `http://localhost:8000`

All `/v1/**` endpoints require the `X-API-Key` header when `REQUIRE_AUTH=true`
(the default). `/health`, `/ready`, the interactive docs, and the dashboard are
always open.

Interactive OpenAPI docs are available at **`/docs`** (Swagger UI) and
**`/redoc`** while the server is running.

Every response includes an **`X-Request-ID`** header; the same id appears in the
JSON logs for that request, and in error envelopes.

---

## Conventions

**Authentication**

```
X-API-Key: dev-local-key
```

**Error envelope** — all errors share one shape:

```json
{
  "error": "not_found",
  "detail": "Document 'doc_x' not found.",
  "request_id": "9f2c1a4b7e8d0c11"
}
```

Status codes: `401` auth, `404` missing, `415` unsupported file type,
`422` validation/empty document, `429` rate limited, `502` upstream LLM/embedding
failure, `500` unexpected.

---

## Health

### `GET /health` — liveness
Cheap, dependency-free. Returns `200` whenever the process is up.

```json
{ "status": "ok", "app": "Enterprise Knowledge Assistant", "version": "1.0.0", "environment": "development" }
```

### `GET /ready` — readiness
Checks each component. Returns `200` with `ready: true`, or `503` with
`ready: false` if any required component is down. The network LLM is treated as
optional (the extractive stub covers it).

```json
{
  "ready": true,
  "components": [
    { "name": "vector_store", "ok": true, "detail": "memory" },
    { "name": "embedder", "ok": true, "detail": "hash dim=384" },
    { "name": "llm", "ok": true, "detail": "extractive-stub (no network LLM)" }
  ]
}
```

---

## Documents

### `POST /v1/documents` — upload & ingest
`multipart/form-data`. The file is extracted, deduplicated (sha256), chunked,
embedded, and indexed into both the vector store and BM25.

| Param | In | Default | Notes |
|-------|----|---------|-------|
| `file` | form (file) | — | TXT, MD, CSV/TSV, or PDF |
| `namespace` | query or form | `default` | Logical partition |
| `title` | form | — | Optional display title |

```bash
curl -X POST "http://localhost:8000/v1/documents?namespace=demo" \
  -H "X-API-Key: dev-local-key" \
  -F "file=@demo/examples/company_policy.txt"
```

`201 Created`:

```json
{
  "document_id": "doc_3f9a...",
  "namespace": "demo",
  "filename": "company_policy.txt",
  "chunk_count": 2,
  "char_count": 1184,
  "deduplicated": false
}
```

If an identical file (same bytes) already exists in the namespace, the existing
document is returned with `"deduplicated": true` and nothing is re-indexed.

### `GET /v1/documents` — list
| Param | In | Default |
|-------|----|---------|
| `namespace` | query | (all) |
| `limit` | query | `50` (1–500) |
| `offset` | query | `0` |

```json
{
  "namespace": "demo",
  "total": 3,
  "documents": [
    { "id": "doc_3f9a...", "namespace": "demo", "filename": "company_policy.txt",
      "content_type": "text/plain", "char_count": 1184, "chunk_count": 2,
      "size_bytes": 1184, "created_at": 1718750000.12, "title": null }
  ]
}
```

### `DELETE /v1/documents/{document_id}` — delete
Removes the document and all its chunks from the catalogue, vector store, and
BM25 index. `404` if unknown.

```json
{ "document_id": "doc_3f9a...", "deleted_chunks": 2, "deleted": true }
```

---

## Query

### `POST /v1/query`
Runs the hybrid retrieval pipeline and composes a grounded, cited answer.

Request body:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `question` | string | — | required |
| `namespace` | string | `default` | which partition to search |
| `top_k` | int | (config `FINAL_TOP_K`) | override number of chunks |
| `answer_style` | string | `detailed` | `concise` \| `detailed` \| `bullet` |
| `hybrid` | bool | (config) | override hybrid on/off for this query |
| `rerank` | bool | (config) | override reranking on/off for this query |
| `include_chunks` | bool | `false` | include retrieved chunks with per-signal scores |

```bash
curl -X POST "http://localhost:8000/v1/query" \
  -H "X-API-Key: dev-local-key" -H "Content-Type: application/json" \
  -d '{"question":"How many vacation days do employees get?","namespace":"demo","include_chunks":true}'
```

Response (abridged):

```json
{
  "question": "How many vacation days do employees get?",
  "namespace": "demo",
  "answer": "All full-time employees receive 20 days of paid annual leave each year. [1]",
  "grounded": true,
  "model": "qwen3-coder:30b",
  "citations": [
    { "marker": "[1]", "chunk_id": "ch_a1...", "document_id": "doc_3f...",
      "filename": "company_policy.txt", "ordinal": 0, "score": 0.83,
      "snippet": "All full-time employees receive 20 days of paid annual leave..." }
  ],
  "timings_ms": {
    "embed_ms": 0.4, "vector_search_ms": 0.6, "keyword_search_ms": 0.3,
    "fusion_ms": 0.1, "rerank_ms": 0.2, "generation_ms": 980.0, "total_ms": 982.1
  },
  "chunks": [
    { "chunk_id": "ch_a1...", "filename": "company_policy.txt", "ordinal": 0,
      "text": "...", "score": 0.83,
      "vector_score": 0.69, "keyword_score": 0.20, "fused_score": 0.033, "rerank_score": 0.83 }
  ]
}
```

- **`grounded`** is true when the answer cites at least one chunk.
- **`model`** is the model used, or `extractive-stub` when the stub answered.
- **`timings_ms`** keys present depend on configuration — e.g. `keyword_search_ms`
  and `fusion_ms` are absent when `hybrid=false`. The dashboard uses exactly
  these keys to light up the pipeline.

---

## Admin (used by the dashboard)

### `GET /v1/admin/stats` — catalogue + config snapshot
```json
{
  "total_documents": 3, "total_chunks": 5, "total_queries": 12,
  "embedding_provider": "hash", "embedding_dim": 384,
  "vector_backend": "memory", "rerank_provider": "heuristic",
  "llm_model": "qwen3-coder:30b", "llm_active": false,
  "namespaces": [ { "namespace": "demo", "documents": 3, "chunks": 5 } ]
}
```

### `GET /v1/admin/metrics` — operational metrics (recent window)
```json
{
  "window": "last 12 queries",
  "total_queries": 12, "success_rate": 1.0, "grounded_rate": 0.92,
  "avg_latency_ms": 14.3, "p95_latency_ms": 21.0,
  "queries_per_namespace": { "demo": 12 }
}
```

### `GET /v1/admin/queries` — recent query feed
| Param | Default |
|-------|---------|
| `limit` | `50` (1–500) |
| `offset` | `0` |

```json
{
  "total": 12,
  "items": [
    { "id": "q_8a...", "ts": 1718750100.4, "namespace": "demo",
      "question": "How many vacation days...", "grounded": true,
      "num_citations": 1, "latency_ms": 982.1, "model": "qwen3-coder:30b", "success": true }
  ]
}
```

---

## Dashboard

### `GET /dashboard`
Serves the single-page operations console. Static assets are under
`/dashboard/static/`. The console calls the `/v1/admin/*` and `/v1/query`
endpoints above, sending the API key you enter in its top bar.
