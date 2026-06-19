# Enterprise Knowledge Assistant

A **minimum-production-grade hybrid-retrieval RAG platform** with reranking,
grounded citations, namespace isolation, API-key auth, rate limiting, structured
logging, health/readiness probes, and a built-in **live operations dashboard**.

It runs **fully offline out of the box** (no model downloads, no GPU, no network)
using a deterministic hashing embedder, an in-memory vector store, and an
extractive answer composer — then upgrades to **local Ollama** (`qwen3-coder:30b`
+ `nomic-embed-text`), **ChromaDB**, and a **cross-encoder reranker** by flipping a
few environment variables. Nothing about the API or the dashboard changes.

> **中文简介**：这是一个「最低生产级」的企业知识助手平台，核心是**混合检索（BM25 关键词 +
> 向量语义）+ 重排序 + 带引用的生成**。默认零依赖、可离线运行；改几个环境变量即可切换到本地
> Ollama（`qwen3-coder:30b` / `nomic-embed-text`）、ChromaDB 与交叉编码器重排序。附带一个
> 实时可观测的运维仪表盘。

---

## Why this is not a toy

Most "RAG demos" are a single vector search wired to an LLM. This is the three
upgrades that turn that into a platform:

1. **Hybrid search** — BM25 lexical retrieval fused with dense vector retrieval
   via Reciprocal Rank Fusion. Catches exact terms, IDs, and acronyms that
   embeddings wash out, *and* the semantic matches keywords miss.
2. **Reranking** — a second-stage relevance pass over the fused candidates
   (heuristic by default, cross-encoder optional) so the chunks handed to the
   LLM are the *most* relevant, not just the most retrievable.
3. **Operations dashboard** — a real instrument panel that traces the live
   retrieval pipeline stage-by-stage with measured per-stage latencies, plus
   catalogue, metrics, and a recent-query feed.

On top of that it has the things a real service needs: dedup on ingest,
durable catalogue (SQLite) decoupled from the vector index, per-request tracing,
token-bucket rate limiting, consistent JSON error envelopes, a ~40-test suite,
and Docker packaging.

## Feature summary

| Area | What you get |
|------|--------------|
| Retrieval | Hybrid BM25 + vector, RRF or weighted fusion, configurable top-k at each stage |
| Reranking | Heuristic (no download) or cross-encoder (`sentence-transformers`) |
| Generation | OpenAI-compatible chat (Ollama/llama.cpp) with an **extractive stub fallback** so answers are *always* grounded and cited |
| Citations | Every answer carries `[n]` markers mapped to source chunks; `grounded` flag |
| Isolation | Namespaces partition documents, retrieval, and analytics |
| Security | API-key auth (`X-API-Key`), per-client token-bucket rate limiting |
| Observability | Structured JSON logs + request IDs, `/health`, `/ready`, `/v1/admin/metrics`, live dashboard |
| Storage | SQLite catalogue + analytics; numpy vector store (pickle-persisted) or ChromaDB |
| Ingestion | TXT, Markdown, CSV/TSV, PDF; sha256 dedup; boundary-aware chunking |
| Ops | Dockerfile + compose, Makefile, `run.sh` / `run.bat`, smoke + seed scripts |

## Quickstart

### Option A — offline demo (zero dependencies beyond pip)

```bash
# 1. install
python -m pip install -r requirements.txt

# 2. (optional) copy the demo env; defaults already run offline
cp .env.example .env

# 3. run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000/dashboard**, paste the API key `dev-local-key`
in the top bar, and ingest a file or run a query. Or seed the bundled examples:

```bash
python scripts/seed_examples.py --api-key dev-local-key
```

On Windows you can just double-click **`run.bat`** (creates the venv, installs,
copies the demo env, and starts the server).

> **中文 · 快速开始**：`pip install -r requirements.txt` → `uvicorn app.main:app --port 8000`
> → 打开 `http://localhost:8000/dashboard`，在顶部输入 API key `dev-local-key` 即可上传文档、
> 提问。Windows 用户直接双击 `run.bat`。

### Option B — production profile with local Ollama

```bash
ollama pull qwen3-coder:30b
ollama pull nomic-embed-text
```

In `.env`, comment out the demo block and enable the production block (see
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)). The key switches:

```ini
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
LLM_FORCE_STUB=false
LLM_MODEL=qwen3-coder:30b
# optional heavier backends:
# VECTOR_BACKEND=chroma          (pip install chromadb)
# RERANK_PROVIDER=cross_encoder  (pip install sentence-transformers)
```

Restart the server. The dashboard now shows the live model name and real
generation latencies.

## Try it from the command line

```bash
KEY=dev-local-key

# ingest
curl -s -X POST "http://localhost:8000/v1/documents?namespace=demo" \
  -H "X-API-Key: $KEY" -F "file=@examples/company_policy.txt"

# ask
curl -s -X POST "http://localhost:8000/v1/query" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"How many vacation days do employees get?","namespace":"demo"}'
```

See [`docs/API.md`](docs/API.md) for the full endpoint reference.

## Project structure

```
enterprise-knowledge-assistant/
├── app/
│   ├── config.py            # env-driven settings (pydantic-settings)
│   ├── logging_config.py    # JSON logs + request-id context
│   ├── errors.py            # typed errors + JSON envelope handlers
│   ├── models/              # domain dataclasses + Pydantic wire schemas
│   ├── core/
│   │   ├── extraction.py    # TXT/MD/CSV/PDF text extraction
│   │   ├── chunking.py      # boundary-aware sliding-window chunker
│   │   ├── embeddings/      # hash (default) | openai_compatible
│   │   ├── vectorstore/     # memory (default) | chroma
│   │   ├── keyword/         # BM25 index
│   │   ├── fusion.py        # RRF + weighted fusion
│   │   ├── rerank/          # heuristic (default) | cross_encoder
│   │   ├── retriever.py     # the hybrid retrieval pipeline
│   │   ├── llm.py           # OpenAI-compatible client + extractive stub
│   │   └── rag.py           # context assembly + citation extraction
│   ├── storage/             # SQLite catalogue + analytics
│   ├── services/            # ingest / query / admin orchestration
│   ├── middleware/          # request-id + rate-limit
│   ├── api/                 # FastAPI routers + auth deps
│   ├── dashboard/           # single-page ops console (HTML/CSS/JS)
│   ├── container.py         # dependency wiring
│   └── main.py              # app factory + lifespan
├── tests/                   # ~40 unit + integration tests
├── examples/                # demo corpus (policy, FAQ, employees)
├── scripts/                 # smoke_test.py, seed_examples.py
├── docs/                    # USAGE, ARCHITECTURE, API, CONFIGURATION, DEPLOYMENT, DEVELOPMENT_LOOP
├── Dockerfile, docker-compose.yml, Makefile, run.sh, run.bat
└── requirements.txt, requirements-optional.txt, .env.example
```

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/USAGE.md](docs/USAGE.md) | Operating the platform: ingest, query, dashboard, switching backends (中文操作手册 included) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layering, the retrieval pipeline, design decisions and trade-offs |
| [docs/API.md](docs/API.md) | Every endpoint with request/response examples |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable, with demo vs production profiles |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, compose, and a production hardening checklist |
| [docs/DEVELOPMENT_LOOP.md](docs/DEVELOPMENT_LOOP.md) | The iterative build log, verification tables, and the three real bugs found and fixed |

## Testing

```bash
python -m pytest        # ~40 unit + integration tests
python scripts/smoke_test.py   # end-to-end boot + ingest + query
```

## Tech stack

FastAPI · Pydantic v2 · SQLite · NumPy · rank-bm25 · pypdf · httpx · vanilla
HTML/CSS/JS dashboard. Optional: ChromaDB, sentence-transformers. Designed for a
local Ollama runtime (`qwen3-coder:30b`, `nomic-embed-text`).

## For reviewers / interview blurb

> I built a hybrid-retrieval RAG platform that fuses BM25 and dense vector search
> with reciprocal rank fusion, adds a reranking stage, and always returns grounded,
> cited answers — with an extractive fallback so it degrades gracefully when no LLM
> is reachable. It has namespace isolation, API-key auth, token-bucket rate limiting,
> structured request-traced logging, health/readiness probes, and a live dashboard
> that visualises the retrieval pipeline with real per-stage latencies. It runs
> offline by default and switches to local Ollama, ChromaDB, and a cross-encoder
> reranker via environment variables. I built it in verified iterations and the
> integration tests surfaced three real bugs — a logging reserved-key crash, a BM25
> small-corpus negative-IDF filter that silently disabled lexical search, and a
> property-vs-method readiness check — which I documented and fixed.

> **中文 · 面试讲法**：我做了一个混合检索 RAG 平台——用 RRF 融合 BM25 与向量检索，加重排序，
> 始终返回带引用的、可溯源的答案，并在没有可用 LLM 时优雅降级为抽取式回答。具备命名空间隔离、
> API key 鉴权、令牌桶限流、带请求追踪的结构化日志、健康/就绪探针，以及一个用真实分阶段延迟
> 可视化检索流水线的实时仪表盘。默认离线运行，改环境变量即可切换到本地 Ollama / ChromaDB /
> 交叉编码器。开发采用「验证式迭代」，集成测试中发现并修复了三个真实 bug。

## License

Provided as-is for portfolio and evaluation purposes.
