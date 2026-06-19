# Usage Guide / 操作手册

This is the hands-on manual for operating the platform: starting it, loading
documents, asking questions, reading the dashboard, and switching from the
offline demo to a real local-LLM setup.

> 本文是平台的实操手册：启动、导入文档、提问、看懂仪表盘，以及从离线演示切换到本地大模型。

---

## 1. Start the server / 启动服务

**Offline demo (recommended first run):**

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- macOS/Linux: `./run.sh` does the venv + install + start in one step.
- Windows: double-click **`run.bat`**.

You should see structured startup logs ending in `startup_complete`. Visit
**http://localhost:8000/** — it redirects to the dashboard.

> 离线演示：装依赖后 `uvicorn app.main:app --port 8000`；Windows 直接双击 `run.bat`。
> 启动日志出现 `startup_complete` 即成功，浏览器打开根路径会自动跳转到仪表盘。

---

## 2. Authentication / 鉴权

With the default `REQUIRE_AUTH=true`, every `/v1/**` call needs a key from
`API_KEYS` (default `dev-local-key`) in the `X-API-Key` header. In the dashboard,
paste the key into the **API key** box in the top bar — it's remembered in your
browser. Health and the dashboard itself don't need a key.

> 默认开启鉴权。所有 `/v1` 接口需在 `X-API-Key` 头里带上 `API_KEYS` 中的某个 key（默认
> `dev-local-key`）。仪表盘顶部填入 key 即可，浏览器会记住。

---

## 3. Load documents / 导入文档

**From the dashboard:** use the upload control, pick a namespace, choose a TXT /
MD / CSV / PDF file.

**From the command line:**

```bash
curl -X POST "http://localhost:8000/v1/documents?namespace=demo" \
  -H "X-API-Key: dev-local-key" -F "file=@examples/product_faq.md"
```

**Seed the bundled examples in one go:**

```bash
python scripts/seed_examples.py --api-key dev-local-key   # server must be running
```

Notes:
- **Namespaces** keep document sets isolated (e.g. `hr`, `support`, `legal`).
  Queries, listings, and analytics are all per-namespace.
- **Dedup**: uploading the exact same bytes into the same namespace returns the
  existing document with `deduplicated: true` and does no extra work.
- Supported types: **TXT, Markdown, CSV/TSV, PDF**. CSV rows are rendered as
  `column: value; ...` so they retrieve well.

> 命名空间用于隔离不同文档集合（如 `hr`/`support`/`legal`），查询与统计都按命名空间区分。
> 相同字节的文件重复上传会被去重。支持 TXT/Markdown/CSV/PDF。

---

## 4. Ask questions / 提问

**From the dashboard:** type into *Ask the knowledge base*, choose a style
(detailed / concise / bullet), toggle **hybrid** and **rerank**, and hit **Run
query**. Watch the pipeline spine light up with real per-stage latencies, and
read the answer with its citations and per-signal score bars.

**From the command line:**

```bash
curl -X POST "http://localhost:8000/v1/query" \
  -H "X-API-Key: dev-local-key" -H "Content-Type: application/json" \
  -d '{"question":"How do I reset my password?","namespace":"demo","answer_style":"concise","include_chunks":true}'
```

Every answer reports `grounded` (did it cite at least one source?) and `model`
(`extractive-stub` in the demo, or your LLM's name in production).

> 仪表盘里输入问题、选风格、切换 hybrid/rerank、点击 Run query，即可看到流水线按真实延迟点亮、
> 答案、引用和各信号得分条。命令行用上面的 `curl`。每条回答都带 `grounded` 与 `model` 字段。

---

## 5. Read the dashboard / 看懂仪表盘

The console is a retrieval **instrument panel**. Top to bottom:

- **Pipeline spine** — the signature element. Each node is a real pipeline stage
  (Embed → Vector → BM25 → Fuse → Rerank → Generate). When you run a query it
  lights up stage-by-stage using the measured `timings_ms`. A node shown as
  *off* means that stage didn't run in the current configuration (e.g. BM25 and
  Fuse are off when hybrid is disabled). Colour encodes signal: cyan = vector,
  amber = lexical/BM25, violet = fusion, coral = rerank, green = generation.
- **Metric strip** — documents, chunks, queries, success %, grounded %, and p95
  latency over a recent window.
- **Namespaces** — document and chunk counts per namespace, plus the active
  embedding/vector/rerank configuration.
- **Recent queries** — a live feed: time, namespace, question, grounded flag,
  citation count, latency.

The dashboard polls the admin endpoints every few seconds; the live dot in the
top bar shows connection/auth status.

> 仪表盘是一块「检索仪表面板」。最上面的**流水线脊柱**是标志性元件：每个节点是真实阶段，提问时
> 按实测延迟逐级点亮；某节点显示 *off* 表示该阶段在当前配置下未执行（如关闭 hybrid 时 BM25/Fuse
> 不亮）。颜色表示信号：青=向量、琥珀=BM25、紫=融合、珊瑚=重排、绿=生成。下面依次是指标条、
> 命名空间表、实时查询流。

---

## 6. Switch to local Ollama / 切换到本地 Ollama

```bash
ollama pull qwen3-coder:30b
ollama pull nomic-embed-text
```

Edit `.env` (comment the demo lines, enable production):

```ini
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
LLM_FORCE_STUB=false
LLM_MODEL=qwen3-coder:30b
```

Then **start from a clean `DATA_DIR`** (or re-ingest), because the vector
dimension changed from 384 (hash) to 768 (nomic). Restart the server; the
dashboard will show `qwen3-coder:30b` and real generation latencies.

Optional heavier backends:
- `VECTOR_BACKEND=chroma` after `pip install -r requirements-optional.txt`
- `RERANK_PROVIDER=cross_encoder` (downloads a small cross-encoder on first use)

> 拉取模型后改 `.env` 启用生产档；因为向量维度从 384 变成 768，需用全新的 `DATA_DIR` 或重新导入。
> 重启后仪表盘会显示真实模型名与生成延迟。可选地启用 ChromaDB / 交叉编码器。

---

## 7. Tune retrieval / 调优检索

Common knobs (see [CONFIGURATION.md](CONFIGURATION.md) for all):

- `FINAL_TOP_K` — how many chunks reach the LLM (precision vs recall).
- `FUSION_METHOD=rrf|weighted` and `RRF_K` — how vector and keyword results blend.
- `VECTOR_WEIGHT` / `KEYWORD_WEIGHT` — only used by `weighted` fusion.
- `RERANK_PROVIDER` — `heuristic` (fast, no download) vs `cross_encoder` (best quality).
- `CHUNK_SIZE` / `CHUNK_OVERLAP` — re-ingest after changing.

You can also override `hybrid`, `rerank`, and `top_k` **per query** in the
request body without changing config.

> 常用调优项：`FINAL_TOP_K`（精度/召回）、`FUSION_METHOD`+`RRF_K`、`VECTOR/KEYWORD_WEIGHT`、
> `RERANK_PROVIDER`、`CHUNK_SIZE/OVERLAP`（改后需重新导入）。也可在单次请求里临时覆盖
> `hybrid`/`rerank`/`top_k`。

---

## 8. Operate & troubleshoot / 运维与排错

- **Logs**: structured JSON when `LOG_JSON=true`. Grep one request across the
  pipeline by its `request_id`. Set `LOG_JSON=false` for readable local logs.
- **`/ready` returns 503**: read the `components` array — it names the failing
  piece (e.g. embeddings endpoint unreachable). The LLM being down does *not*
  fail readiness because the stub covers it.
- **Answers are ungrounded**: the namespace may be empty or the question shares
  no terms/semantics with any chunk. Check the namespace's chunk count in the
  dashboard.
- **Hybrid seems to make no difference on a tiny corpus**: that's expected when
  every document contains the query term — BM25's contribution is rank-based and
  small until the corpus grows.
- **`429 Too Many Requests`**: you exceeded the token bucket; back off or raise
  `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_BURST`.
- **Persistence**: documents and vectors survive restarts via SQLite + the
  vector pickle. The BM25 index is rebuilt from the catalogue at startup.

> 日志为 JSON（可按 `request_id` 串联一次请求）。`/ready` 返回 503 时看 `components` 定位故障；
> LLM 掉线不影响就绪（有抽取式兜底）。回答「未溯源」多半是命名空间为空或问题与文档无重叠。
> `429` 是触发限流。重启后数据通过 SQLite + 向量 pickle 持久化，BM25 索引在启动时重建。
