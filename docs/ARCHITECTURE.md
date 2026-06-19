# Architecture

## Design goals

1. **Run anywhere, instantly.** Defaults require no model downloads, no GPU, and
   no network — so the project boots and demos in seconds — while every heavy
   component is swappable for a production backend via one env var.
2. **Always return a grounded, cited answer.** Generation degrades gracefully to
   an extractive stub so the query path never hard-fails on a missing LLM.
3. **Be observable and operable.** Request tracing, health/readiness, metrics,
   and a dashboard that shows what the retrieval pipeline actually did.
4. **Clean layering, no import cycles.** Each layer depends only on those below
   it; backends sit behind small interfaces.

## Layered structure

```
            ┌─────────────────────────────────────────────┐
 entry      │ main.py  (app factory, lifespan, handlers)   │
            └───────────────┬─────────────────────────────┘
            ┌───────────────▼─────────────────────────────┐
 wiring     │ container.py  (singletons, BM25 rebuild)     │
            └───────────────┬─────────────────────────────┘
 interface  │ api/ (routers, auth)   middleware/   dashboard/
            └───────────────┬─────────────────────────────┘
 services   │ ingest_service · query_service · admin_service
            └───────────────┬─────────────────────────────┘
 core       │ retriever · rag · fusion · embeddings · vectorstore
            │ · keyword(BM25) · rerank · extraction · chunking · llm
            └───────────────┬─────────────────────────────┘
 storage    │ metadata_store (SQLite) · analytics_store (SQLite)
            └───────────────┬─────────────────────────────┘
 foundation │ config · logging_config · errors · models
            └─────────────────────────────────────────────┘
```

Import direction is strictly downward. The retriever is decoupled from storage
via a `chunk_lookup` callable (bound to `metadata_store.get_chunks`), so the core
retrieval engine never imports the storage layer directly.

## The retrieval pipeline

A single query flows through six stages; the per-stage latencies are what the
dashboard spine visualises.

```
question
   │
   ▼  embed_ms
[1] Embed query ─────────────► query vector
   │
   ├──► [2] Vector search (cosine top-k)        vector_search_ms
   │
   └──► [3] BM25 search (lexical top-k)         keyword_search_ms      (hybrid only)
                 │
                 ▼  fusion_ms
        [4] Fuse (Reciprocal Rank Fusion)  ──► ranked candidates
                 │
                 ▼  (hydrate chunk text via chunk_lookup)
        [5] Rerank candidates              ──► reordered            rerank_ms
                 │
                 ▼  (take FINAL_TOP_K)
        [6] Compose answer + citations     ──► grounded answer      generation_ms
```

**Why hybrid.** Dense vectors capture meaning but blur exact tokens (codes,
acronyms, names); BM25 nails exact terms but misses paraphrase. Fusing them gives
both. **Reciprocal Rank Fusion** is the default because it combines *ranks*, not
raw scores, so it's robust to the two retrievers using completely different score
scales — and it needs no per-corpus tuning.

**Why a reranker.** Fusion produces a good candidate set, but a focused
relevance pass over the top dozen candidates measurably improves what the LLM
sees. The heuristic reranker (lexical coverage + term-frequency saturation +
bigram bonus − length penalty) needs no model; a cross-encoder is available when
quality matters more than cold-start time.

**Why the extractive stub.** A platform should not return a 500 because an LLM is
unreachable. When generation is off or fails, the composer selects the
best-supported sentences from the retrieved chunks and labels them with `[n]`
citations — still grounded, still cited, just extractive. `model` in the
response records which path ran.

## Storage model

Two SQLite databases (WAL mode, thread-safe) plus the vector index:

- **metadata_store** — `documents` (with a `UNIQUE(namespace, content_hash)`
  constraint that implements dedup) and `chunks` (foreign-keyed, `ON DELETE
  CASCADE`). It's the durable source of truth and is the *last* thing written
  during ingestion, so a crash mid-ingest never leaves a half-committed catalogue.
- **analytics_store** — an append-only `query_logs` table powering the metrics
  and recent-query feed.
- **vector store** — `memory` (numpy, atomic pickle persistence) or `chroma`.

The **BM25 index is not persisted**: it's an in-memory structure rebuilt at
startup from `metadata_store.iter_all_chunks()`. This keeps the on-disk format
simple and guarantees the lexical index can never drift from the catalogue.

## Ingestion path

```
upload → extract_text → sha256 → [dedup hit? return existing]
       → chunk (boundary-aware) → embed (batched)
       → vector_store.add + bm25.add
       → metadata_store.add_document   ← durable commit, written last
       → vector_store.persist
```

Chunking snaps to paragraph → sentence → newline → space boundaries within the
size budget and carries `CHUNK_OVERLAP` characters between chunks to preserve
context across boundaries.

## Cross-cutting concerns

- **Config** — one `pydantic-settings` object, env-driven, with computed list
  properties for `API_KEYS` / `CORS_ORIGINS` (stored as raw comma strings).
- **Logging** — JSON formatter; a `request_id` ContextVar set by middleware is
  attached to every line. `get_logger` returns an adapter that re-homes any
  reserved `LogRecord` field passed in `extra` (so `extra={"name": ...}` can't
  crash a request).
- **Errors** — typed `AppError` subclasses map to status codes; handlers render
  one JSON envelope `{error, detail, request_id}` for domain, validation, and
  unexpected errors alike.
- **Middleware order** (outer → inner): CORS → RequestID → RateLimit. The rate
  limiter returns its `429` envelope directly (middleware exceptions bypass the
  exception handlers, so it must not raise).
- **Lifespan** — the container is built on startup (wiring singletons and
  rebuilding BM25) and flushed on shutdown (persist vectors, close DBs).

## Extension points

| Want to… | Do this |
|----------|---------|
| Add an embeddings provider | implement `Embedder`, register in `embeddings/__init__.py` |
| Add a vector backend | implement `VectorStore`, register in `vectorstore/__init__.py` |
| Add a reranker | implement `Reranker`, register in `rerank/__init__.py` |
| Add a file type | extend `core/extraction.py` |
| Change fusion | add a function in `core/fusion.py` and a `FUSION_METHOD` value |

Each interface is a small ABC, so a new backend is a single file plus a one-line
registration — the services, API, and dashboard are unaffected.
