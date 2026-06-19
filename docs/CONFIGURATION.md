# Configuration Reference

All configuration is environment-driven (via real env vars or a `.env` file in
the project root). Names are case-insensitive. Every value has a sensible default
— the defaults form the **offline demo profile**. Copy `.env.example` to `.env`
to start customising.

> 所有配置均通过环境变量或项目根目录下的 `.env` 文件设置；变量名大小写不敏感。下表给出每个
> 变量的含义、默认值与示例。默认值即「离线演示档」。

## How profiles work

There are two reference profiles. You switch by editing a handful of variables:

- **Demo (default):** `EMBEDDING_PROVIDER=hash`, `VECTOR_BACKEND=memory`,
  `RERANK_PROVIDER=heuristic`, `LLM_FORCE_STUB=true`. No downloads, no network.
- **Production:** `EMBEDDING_PROVIDER=openai_compatible` (+ Ollama URL/model),
  `LLM_FORCE_STUB=false`, optionally `VECTOR_BACKEND=chroma` and
  `RERANK_PROVIDER=cross_encoder`.

## Service identity

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `Enterprise Knowledge Assistant` | Display name in `/health` and the dashboard |
| `APP_VERSION` | `1.0.0` | Reported version string |
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` |
| `DEBUG` | `true` | Enables debug behaviours |
| `HOST` | `0.0.0.0` | Bind host for uvicorn |
| `PORT` | `8000` | Bind port |

## Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `./data` | Directory for the SQLite databases and the vector-store pickle. Mount a volume here in Docker to persist. |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUIRE_AUTH` | `true` | When true, all `/v1/**` routes require a valid API key. `/health`, `/ready`, and the dashboard stay open. |
| `API_KEYS` | `dev-local-key` | Comma-separated list of accepted keys. **Change this in production.** |
| `API_KEY_HEADER` | `X-API-Key` | Header clients must send the key in |

## CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins, or `*` for any |

## Rate limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Toggle the token-bucket limiter |
| `RATE_LIMIT_PER_MINUTE` | `60` | Sustained refill rate (tokens/minute) per client |
| `RATE_LIMIT_BURST` | `20` | Bucket capacity — the maximum short burst before throttling |

Clients are keyed by API key when present, otherwise by client IP. `/health`,
`/ready`, `/dashboard`, and the API docs are exempt.

## Chunking

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | `800` | Target characters per chunk |
| `CHUNK_OVERLAP` | `120` | Characters of overlap carried between adjacent chunks |
| `MIN_CHUNK_CHARS` | `40` | Chunks shorter than this are dropped (except a document's only chunk) |

## Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_PROVIDER` | `hash` | `hash` (deterministic local, no download) or `openai_compatible` (any `/v1/embeddings` endpoint, e.g. Ollama) |
| `EMBEDDING_DIM` | `384` | Vector dimension for the hash embedder. For `nomic-embed-text` set `768`. |
| `EMBEDDING_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible embeddings base URL |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `EMBEDDING_API_KEY` | `local` | API key for the embeddings endpoint (Ollama ignores it) |
| `EMBEDDING_TIMEOUT` | `60.0` | Request timeout (seconds) |
| `EMBEDDING_BATCH_SIZE` | `32` | Documents embedded per request |

> **Dimension must match the store.** If you change the embedder or its
> dimension after ingesting data, re-ingest (or use a fresh `DATA_DIR`), since
> existing vectors were written at the old dimension.

## Vector store

| Variable | Default | Description |
|----------|---------|-------------|
| `VECTOR_BACKEND` | `memory` | `memory` (numpy cosine, pickle-persisted) or `chroma` (requires `pip install chromadb`) |
| `CHROMA_PATH` | `./data/chroma` | Persistent path for the ChromaDB client |

## Keyword (BM25) and hybrid fusion

| Variable | Default | Description |
|----------|---------|-------------|
| `BM25_ENABLED` | `true` | Maintain the lexical index |
| `HYBRID_ENABLED` | `true` | Fuse vector + keyword results. When false, retrieval is vector-only. |
| `FUSION_METHOD` | `rrf` | `rrf` (Reciprocal Rank Fusion, rank-based, robust) or `weighted` (min-max normalised blend) |
| `RRF_K` | `60` | RRF constant; larger flattens the contribution of rank position |
| `VECTOR_WEIGHT` | `0.5` | Weight for vector scores when `FUSION_METHOD=weighted` |
| `KEYWORD_WEIGHT` | `0.5` | Weight for keyword scores when `FUSION_METHOD=weighted` |
| `VECTOR_TOP_K` | `20` | Candidates pulled from the vector store before fusion |
| `KEYWORD_TOP_K` | `20` | Candidates pulled from BM25 before fusion |
| `RERANK_CANDIDATES` | `12` | Fused candidates handed to the reranker |
| `FINAL_TOP_K` | `5` | Chunks returned to the LLM / caller |

## Reranking

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_PROVIDER` | `heuristic` | `none` (use fused order), `heuristic` (lexical overlap, no download), or `cross_encoder` (requires `sentence-transformers`) |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model name |

## LLM (answer generation)

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ENABLED` | `true` | Allow calling the network LLM |
| `LLM_FORCE_STUB` | `false` | When true, never call the LLM — always use the extractive stub. Set **true** for the demo/CI/air-gapped. |
| `LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible chat base URL |
| `LLM_MODEL` | `qwen3-coder:30b` | Chat model name |
| `LLM_API_KEY` | `local` | API key for the chat endpoint |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `LLM_MAX_TOKENS` | `800` | Max tokens in the generated answer |
| `LLM_TIMEOUT` | `120.0` | Request timeout (seconds) |
| `MAX_CONTEXT_CHARS` | `6000` | Cap on assembled context handed to the LLM |

> **The extractive stub is always the safety net.** If the LLM is disabled,
> forced off, or the call raises, the composer returns an extractive,
> citation-bearing answer instead of failing. `model` in the response tells you
> which path was used (`extractive-stub` vs the model name).

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LOG_JSON` | `true` | `true` emits one JSON object per line (recommended for aggregation); `false` is human-friendly for local dev |

## Minimal production `.env`

```ini
ENVIRONMENT=production
REQUIRE_AUTH=true
API_KEYS=replace-with-a-strong-key,another-service-key
LOG_JSON=true

EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768

LLM_FORCE_STUB=false
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen3-coder:30b

# heavier, optional:
# VECTOR_BACKEND=chroma
# RERANK_PROVIDER=cross_encoder
```
