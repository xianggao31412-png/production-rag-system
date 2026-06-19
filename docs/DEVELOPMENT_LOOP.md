# Development Loop Log

This project was built with **loop development**: small, ordered iterations, each
ending in a concrete verification before the next began. Bottom layers were
built and proven first, so every later iteration stood on already-verified code.
This log records the iterations, what was verified, and the three real bugs that
verification surfaced.

> 本项目采用「循环式开发」：自底向上、小步快跑，每个迭代以一次具体验证收尾，验证通过才进入下一步。
> 下面记录了各迭代、验证结果，以及验证过程中暴露并修复的三个真实 bug。

## The loop

```
PLAN ──► BUILD ──► VERIFY ──► (fix) ──► RECORD ──► NEXT
  ▲                                                 │
  └─────────────────────────────────────────────────┘
```

## Iteration ledger

| # | Iteration | Key modules | Verification | Result |
|---|-----------|-------------|--------------|--------|
| 1 | Foundation | `config`, `logging_config`, `errors`, `models/` | import + instantiate settings; emit a log line; raise/handle each error | pass |
| 2 | Ingestion primitives | `extraction`, `chunking`, `hashing` | extract TXT/MD/CSV/PDF; chunk sizes ≤ budget with overlap; stable sha256 | pass |
| 3 | Retrieval engine | `embeddings/`, `vectorstore/`, `keyword/`, `fusion`, `rerank/`, `retriever` | hash embedder determinism + unit norm; cosine top-k; BM25 match; RRF ordering; heuristic rerank; end-to-end retrieve | pass (after **Bug #2**) |
| 4 | Storage + RAG | `metadata_store`, `analytics_store`, `llm`, `rag`, `services/`, `container` | add/dedup/get/delete; analytics metrics + percentile; stub composition grounded + cited; full ingest→query in-process | pass (after **Bug #1**) |
| 5 | Middleware | `request_id`, `rate_limit` | request-id propagation + echo header; token bucket emits 429 on burst; health exempt | pass |
| 6 | API + auth | `api/deps`, `routes_*` | 201 upload; list; query; admin; delete; 404; 422 envelope; 401 without key | pass |
| 7 | Dashboard | `dashboard/static/*`, `dashboard/router` | page + assets serve 200; spine keys match `timings_ms`; query drives the spine | pass |
| 8 | App factory | `main` | lifespan build/shutdown; handler registration; middleware order; root redirect | pass (after **Bug #3**) |
| 9 | Tests | `tests/` (~40) | full `pytest` suite green | pass |
| 10 | Deploy + docs + examples | Dockerfile, compose, Makefile, scripts, `docs/` | `smoke_test.py` green; `compileall` clean | pass |

## Integration verification (in-process `TestClient`, `LLM_FORCE_STUB=true`)

| Check | Outcome |
|-------|---------|
| `GET /health` | 200 |
| `GET /ready` | `ready: true`, all components ok (after Bug #3) |
| Auth enforced (no key) | 401 |
| Ingest 3 documents | 201 each, correct chunk counts |
| Dedup on identical re-upload | `deduplicated: true`, no re-index |
| `GET /v1/documents` total | correct |
| Queries (hybrid + rerank) | grounded, correct citations, full `timings_ms` |
| Admin stats / metrics / queries | correct counts and rates |
| Dashboard + assets | 200 / 200 / 200 |
| Root redirect | 307 → `/dashboard` |
| `X-Request-ID` header | present |
| Delete document | removes doc + chunks across all stores |
| Rate limiting (burst = 5) | `[200×5, 429×4]`; `/health` exempt |
| Persistence across restart | documents survive; query grounded; BM25 rebuilt |
| Hybrid scoring | relevant chunks get `keyword_score`; unrelated get `None` |
| Full `pytest` | 40 passed |
| `smoke_test.py` | all checks green |

## Bugs found and fixed during verification

### Bug #1 — logging crash on a reserved `LogRecord` key
**Symptom.** Every document upload raised
`KeyError: "Attempt to overwrite 'filename' in LogRecord"` and returned 500.

**Root cause.** Ingestion logged with `extra={"filename": ...}`. Python's logging
reserves `filename` (and `module`, `name`, `args`, …) as built-in `LogRecord`
attributes; passing any of them in `extra` raises at record-creation time, before
any formatter runs.

**Fix.** Two layers: (1) renamed the offending keys `filename → file` at the three
call sites; (2) hardened `get_logger` to return a `LoggerAdapter` that transparently
re-homes any reserved key in `extra` under an `x_` prefix — so this class of bug
can never crash a request again, regardless of future call sites.

**Re-verified.** Uploads succeed; logs carry `file=...`.

### Bug #2 — BM25 silently disabled on small corpora (negative IDF)
**Symptom.** Hybrid retrieval returned no lexical matches on small knowledge
bases; `keyword_score` was always `None` and hybrid degraded to vector-only —
even for an obvious term match.

**Root cause.** The BM25 query filtered results with `if score > 0.0`. BM25Okapi's
IDF turns **negative** for a term that appears in most/all documents, which is the
common case on a small corpus (and always the case with a single document). So
every genuine match was discarded by the positive-score filter.

**Fix.** Filter by **lexical overlap** (does the chunk share at least one query
token?) instead of score sign, and keep the scores as-is. Reciprocal Rank Fusion
ranks by order, so a negative absolute score is harmless — real term overlap is
the signal that matters.

**Re-verified.** Single-document corpus returns the match; multi-document ranks
correctly; chunks with no overlap are excluded; the vector-only path is unaffected.

### Bug #3 — readiness reported embedder unhealthy (`property` called like a method)
**Symptom.** `/ready` returned 503 with
`embedder: ok=false ("'int' object is not callable")`.

**Root cause.** The readiness check called `embedder.dimension()`, but `dimension`
is a `@property` returning an `int`; invoking the int raised `TypeError`.

**Fix.** Access it as a property: `embedder.dimension`.

**Re-verified.** `/ready` returns `true` with `embedder: hash dim=384`.

## What the loop bought us

All three bugs were caught by **running** the system (integration + readiness
checks), not by reading it — and two of them (the reserved-key crash and the
negative-IDF filter) are exactly the kind that pass a syntax check and a casual
demo but fail in production or on a real corpus. Building bottom-up meant each was
found the moment the layer that exercised it came online, and fixed against an
otherwise-verified stack.
