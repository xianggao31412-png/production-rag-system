# Deployment

## Local (no containers)

```bash
python -m pip install -r requirements.txt
cp .env.example .env            # edit for production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **Workers and in-process state.** The default vector store and the token-bucket
> rate limiter live in process memory. Run a **single worker** unless you switch
> to a shared vector backend (ChromaDB) and an external rate-limit store. For
> read-heavy scaling, put several single-worker instances behind a load balancer,
> all pointing at a shared ChromaDB and a shared `DATA_DIR` for the catalogue, or
> promote the catalogue to a networked database.

## Docker

```bash
docker build -t enterprise-knowledge-assistant:latest .
docker run -p 8000:8000 \
  -e REQUIRE_AUTH=true -e API_KEYS=replace-me \
  -e LLM_FORCE_STUB=true \
  -v eka_data:/app/data \
  enterprise-knowledge-assistant:latest
```

The image runs the offline demo profile by default and includes a
container-level `HEALTHCHECK` that hits `/health`. Mount a volume at `/app/data`
to persist the catalogue and vectors across restarts.

## Docker Compose

```bash
docker compose up --build
```

`docker-compose.yml` exposes port 8000, persists a named volume `eka_data`, and
includes a commented block to point the container at a **host-run Ollama** via
`host.docker.internal` (the `extra_hosts` mapping makes this work on Linux too):

```yaml
# LLM_FORCE_STUB: "false"
# LLM_BASE_URL: "http://host.docker.internal:11434/v1"
# LLM_MODEL: "qwen3-coder:30b"
# EMBEDDING_PROVIDER: "openai_compatible"
# EMBEDDING_BASE_URL: "http://host.docker.internal:11434/v1"
# EMBEDDING_MODEL: "nomic-embed-text"
# EMBEDDING_DIM: "768"
```

## Connecting to model runtimes

**Ollama** (default assumption): exposes an OpenAI-compatible API at
`http://127.0.0.1:11434/v1`. Pull `qwen3-coder:30b` and `nomic-embed-text` first.

**llama.cpp server**: also OpenAI-compatible — point `LLM_BASE_URL` /
`EMBEDDING_BASE_URL` at `http://127.0.0.1:8080/v1`.

**Hosted OpenAI-compatible APIs**: set the base URL, model, and `*_API_KEY`.

## Production hardening checklist

- [ ] `ENVIRONMENT=production`, `DEBUG=false`
- [ ] `REQUIRE_AUTH=true` and **strong, unique** `API_KEYS` (rotate periodically)
- [ ] Restrict `CORS_ORIGINS` to known front-end origins (not `*`)
- [ ] `LOG_JSON=true` and ship stdout to your aggregator; alert on error rate and
      on `success_rate` / `grounded_rate` from `/v1/admin/metrics`
- [ ] Terminate TLS at a reverse proxy (nginx, Caddy, a cloud LB); forward
      `X-Request-ID` for end-to-end tracing
- [ ] Tune `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_BURST` to expected traffic; for
      multiple replicas, move rate limiting to a shared store or the proxy
- [ ] Choose `VECTOR_BACKEND=chroma` for larger corpora; back up `DATA_DIR`
      (catalogue + analytics + vectors) and the Chroma path
- [ ] Pin embedding model + dimension; re-ingest if either changes
- [ ] Probe `/ready` from your orchestrator; route traffic only when ready
- [ ] Set realistic `LLM_TIMEOUT`; the extractive stub will cover transient LLM
      outages, but monitor how often it engages (a spike means the LLM is down)
- [ ] Resource sizing for `qwen3-coder:30b`: a GPU with adequate VRAM or a
      capable CPU host; size the host for your concurrency target

## Backup & restore

Everything stateful lives under `DATA_DIR`:

```
data/
├── metadata.db        # documents + chunks (catalogue)
├── analytics.db       # query logs
├── vectors.pkl        # memory vector store (if VECTOR_BACKEND=memory)
└── chroma/            # ChromaDB (if VECTOR_BACKEND=chroma)
```

Back up the whole directory. To restore, stop the service, replace `DATA_DIR`,
and start again — BM25 is rebuilt automatically from the catalogue on startup.
