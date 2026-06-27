#!/usr/bin/env python
"""
Showcase demo (command line).

Boots the platform in-process (offline, no server, no network), ingests the
showcase file plus the example corpus, and walks through every core feature with
narration: grounded cited answers, multi-format retrieval, hybrid vs vector-only,
reranking, graceful out-of-scope handling, and live metrics.

    python run_demo.py

Runs entirely in a throwaway temp directory, so it never touches your real data.
To explore interactively instead, launch the app (START_SOFTWARE.bat) and click
"Run showcase demo" in the dashboard.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

LINE = "=" * 74
THIN = "-" * 74


def hr(title: str) -> None:
    print("\n" + LINE)
    print(f"  {title}")
    print(LINE)


def wrap(text: str, indent: str = "    ") -> str:
    out = []
    for para in str(text).split("\n"):
        out.append(textwrap.fill(para, width=70, initial_indent=indent,
                                 subsequent_indent=indent) if para.strip() else "")
    return "\n".join(out)


def show_answer(client, question: str, *, namespace: str = "demo",
                hybrid: bool = True, rerank: bool = True,
                include_chunks: bool = True) -> dict:
    body = client.post("/v1/query", json={
        "question": question, "namespace": namespace,
        "hybrid": hybrid, "rerank": rerank, "include_chunks": include_chunks,
    }).json()
    print(f"\n  Q: {question}")
    print(wrap(body["answer"], indent="     "))
    cites = ", ".join(f'{c["marker"]} {c["filename"]}' for c in body.get("citations", []))
    tag = "grounded" if body.get("grounded") else "ungrounded"
    print(f"     -> {tag} | model: {body['model']} | sources: {cites or 'none'}")
    return body


def main() -> int:
    hr("Enterprise Knowledge Assistant - Showcase Demo")
    print(wrap(
        "This demo runs the whole platform offline and exercises every core "
        "feature using demo/showcase/AI_SOFTWARE_SHOWCASE_FILE.md and the bundled "
        "example corpus. No server, no network, no GPU required."))

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            data_dir=tmp, llm_force_stub=True, require_auth=False,
            rate_limit_enabled=False, log_level="ERROR", log_json=False,
        )
        app = create_app(settings)
        with TestClient(app) as client:

            # --- 1. Configuration snapshot -------------------------------
            hr("1) System configuration (offline demo profile)")
            s = client.get("/v1/admin/stats").json()
            print(wrap(
                f"embeddings : {s['embedding_provider']} (dim {s['embedding_dim']})\n"
                f"vectors    : {s['vector_backend']}\n"
                f"reranker   : {s['rerank_provider']}\n"
                f"generation : {'LLM ' + s['llm_model'] if s['llm_active'] else 'extractive stub (no LLM needed)'}"))
            ready = client.get("/ready").json()
            print(wrap("readiness  : " + ", ".join(
                f"{c['name']}={'ok' if c['ok'] else 'DOWN'}" for c in ready["components"])))

            # --- 2. Ingestion --------------------------------------------
            hr("2) Ingest the showcase file + example corpus")
            seed = client.post("/v1/demo/seed").json()
            for d in seed["ingested"]:
                flag = " (already indexed - deduplicated)" if d["deduplicated"] else ""
                print(f"    [ok] {d['filename']:24} {d['chunk_count']} chunk(s){flag}")
            print(wrap(f"\nNamespace '{seed['namespace']}' now holds "
                       f"{seed['documents']} documents / {seed['chunks']} passages."))

            # --- 3. Grounded, cited Q&A ----------------------------------
            hr("3) Grounded answers with citations")
            print(wrap("Every answer cites the exact source passage it used.", "  "))
            show_answer(client, "What can this knowledge assistant platform do?")
            show_answer(client, "How long does the Helios One battery last and what is its payload?")
            show_answer(client, "What is the price and warranty of the Helios One?")
            show_answer(client, "How is customer data protected?")

            # --- 4. Multi-format + multi-source retrieval ----------------
            hr("4) Multi-format retrieval (Markdown, TXT, CSV)")
            print(wrap("The same namespace mixes a Markdown spec, a text policy, "
                       "and a CSV roster - retrieval spans all of them.", "  "))
            show_answer(client, "How many vacation days do full-time employees get?")
            show_answer(client, "Where is Grace Hopper located?")

            # --- 5. Hybrid vs vector-only --------------------------------
            hr("5) Hybrid retrieval vs vector-only")
            print(wrap("Hybrid adds a BM25 keyword signal on top of semantic "
                       "search. Watch the keyword score appear when hybrid is on.", "  "))
            q = "Helios One warranty period"
            hyb = show_answer(client, q, hybrid=True, rerank=True)
            vec = show_answer(client, q, hybrid=False, rerank=True)
            def kw(body):
                chunks = body.get("chunks") or []
                return next((c.get("keyword_score") for c in chunks if c.get("keyword_score") is not None), None)
            print(wrap(f"\n  hybrid=on  -> top passage keyword_score = {kw(hyb)}", "  "))
            print(wrap(f"  hybrid=off -> top passage keyword_score = {kw(vec)} (lexical signal absent)", "  "))

            # --- 6. Reranking on/off -------------------------------------
            hr("6) Reranking")
            print(wrap("The reranker reorders fused candidates so the most "
                       "relevant passage leads. rerank_score is attached when on.", "  "))
            r_on = show_answer(client, "support hours", rerank=True)
            top = (r_on.get("chunks") or [{}])[0]
            print(wrap(f"\n  top passage: {top.get('filename','?')} | "
                       f"rerank_score={top.get('rerank_score')} | "
                       f"fused_score={top.get('fused_score')}", "  "))

            # --- 7. Traceability / no fabrication ------------------------
            hr("7) Every sentence is traceable - extractive, never fabricated")
            print(wrap("The offline engine assembles answers only from real "
                       "passages in your documents, each cited. Ask something "
                       "only partly covered and you can see the citations don't "
                       "fit - it returns the closest real text rather than "
                       "inventing facts. (With a configured LLM, the model is "
                       "additionally instructed to say when the answer isn't in "
                       "the sources.)", "  "))
            show_answer(client, "What is the capital of Australia?")

            # --- 8. Observability ----------------------------------------
            hr("8) Observability - live metrics & pipeline timings")
            m = client.get("/v1/admin/metrics").json()
            print(wrap(
                f"queries        : {m['total_queries']}\n"
                f"success rate   : {m['success_rate']*100:.0f}%\n"
                f"grounded rate  : {m['grounded_rate']*100:.0f}%\n"
                f"avg latency    : {m['avg_latency_ms']:.1f} ms\n"
                f"p95 latency    : {m['p95_latency_ms']:.1f} ms"))
            timed = client.post("/v1/query", json={
                "question": "Helios One battery life", "namespace": "demo"}).json()
            print(wrap("\nPer-stage timing for one query (ms):", "  "))
            order = ["embed_ms", "vector_search_ms", "keyword_search_ms",
                     "fusion_ms", "rerank_ms", "generation_ms", "total_ms"]
            for k in order:
                if k in timed["timings_ms"]:
                    bar = "#" * min(40, int(timed["timings_ms"][k]) + 1)
                    print(f"      {k:18} {timed['timings_ms'][k]:8.2f}  {bar}")

            # --- done ----------------------------------------------------
            hr("Demo complete - capabilities demonstrated")
            for item in [
                "Document ingestion (Markdown / TXT / CSV) with dedup",
                "Hybrid retrieval: BM25 keyword + dense vector",
                "Rank fusion + reranking",
                "Grounded answers with inline citations",
                "Namespace-scoped multi-source retrieval",
                "Extractive + cited answers - only real document text, never fabricated",
                "Live metrics and per-stage pipeline timings",
                "Fully offline operation with extractive fallback",
            ]:
                print(f"    [x] {item}")
            print(THIN)
            print(wrap(
                "To explore interactively: double-click START_SOFTWARE.bat "
                "(or run `uvicorn app.main:app --port 8000`), open "
                "http://127.0.0.1:8000/dashboard, and click 'Run showcase demo'.",
                "  "))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
