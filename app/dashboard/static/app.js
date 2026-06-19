/* Operations console controller.
   Talks to the same API the rest of the world uses: /v1/admin/* for telemetry,
   /v1/query to drive the pipeline. The pipeline spine is wired to the real
   `timings_ms` a query returns, so it visualises the actual run, not a mockup. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const KEY_STORE = "eka.apikey";

  // ---- API key handling -------------------------------------------------
  const keyInput = $("apikey");
  try {
    keyInput.value = localStorage.getItem(KEY_STORE) || "dev-local-key";
  } catch { keyInput.value = "dev-local-key"; }
  keyInput.addEventListener("change", () => {
    try { localStorage.setItem(KEY_STORE, keyInput.value); } catch {}
    refreshAll();
  });

  function headers(extra) {
    const h = Object.assign({}, extra || {});
    const k = keyInput.value.trim();
    if (k) h["X-API-Key"] = k;
    return h;
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: headers(opts && opts.json ? { "Content-Type": "application/json" } : {}) }, opts || {}));
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json();
  }

  // ---- liveness ---------------------------------------------------------
  function setLive(state, label) {
    const el = $("live");
    el.classList.remove("ok", "err");
    if (state) el.classList.add(state);
    $("liveLabel").textContent = label;
  }

  const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());
  const pct = (n) => (n == null ? "—" : (n * 100).toFixed(1));

  // ---- telemetry refresh ------------------------------------------------
  async function refreshStats() {
    const s = await api("/v1/admin/stats");
    $("mDocs").textContent = fmt(s.total_documents);
    $("mChunks").textContent = fmt(s.total_chunks);
    $("mQueries").textContent = fmt(s.total_queries);
    $("cfgMeta").textContent = `${s.embedding_provider} · ${s.vector_backend} · rerank:${s.rerank_provider}`;
    $("probeModel").textContent = s.llm_active ? s.llm_model : "extractive-stub";
    $("footLeft").textContent = `embeddings:${s.embedding_provider}  vectors:${s.vector_backend}  llm:${s.llm_active ? s.llm_model : "stub"}`;

    // namespace dropdown (preserve current selection)
    const sel = $("ns");
    const cur = sel.value;
    const opts = ['<option value="">all</option>']
      .concat(s.namespaces.map((n) => `<option value="${esc(n.namespace)}">${esc(n.namespace)}</option>`));
    sel.innerHTML = opts.join("");
    sel.value = cur;

    // namespaces table
    const body = $("nsBody");
    if (!s.namespaces.length) {
      body.innerHTML = '<tr><td colspan="3" class="empty">no documents ingested yet</td></tr>';
    } else {
      body.innerHTML = s.namespaces.map((n) =>
        `<tr><td><span class="ns-pill">${esc(n.namespace)}</span></td>` +
        `<td class="num">${fmt(n.documents)}</td><td class="num">${fmt(n.chunks)}</td></tr>`
      ).join("");
    }
    return s;
  }

  async function refreshMetrics() {
    const m = await api("/v1/admin/metrics");
    $("mSuccess").textContent = m.total_queries ? pct(m.success_rate) : "—";
    $("mGrounded").textContent = m.total_queries ? pct(m.grounded_rate) : "—";
    $("mP95").textContent = m.total_queries ? Math.round(m.p95_latency_ms) : "—";
  }

  async function refreshQueries() {
    const ns = $("ns").value;
    const data = await api("/v1/admin/queries?limit=12");
    let items = data.items || [];
    if (ns) items = items.filter((i) => i.namespace === ns);
    const body = $("qBody");
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty">no queries yet — ask something above</td></tr>';
      return;
    }
    body.innerHTML = items.map((i) => {
      const t = new Date(i.ts * 1000).toLocaleTimeString();
      const g = i.grounded ? '<span class="flag ok">grounded</span>' : '<span class="flag no">ungrounded</span>';
      return `<tr><td>${t}</td><td><span class="ns-pill">${esc(i.namespace)}</span></td>` +
             `<td>${esc(truncate(i.question, 70))}</td><td>${g}</td>` +
             `<td class="num">${i.num_citations}</td><td class="num">${Math.round(i.latency_ms)} ms</td></tr>`;
    }).join("");
  }

  async function refreshAll() {
    try {
      await refreshStats();
      await refreshMetrics();
      await refreshQueries();
      setLive("ok", "live");
    } catch (e) {
      setLive("err", e.message.startsWith("401") ? "auth: check API key" : "offline");
    }
  }

  // ---- pipeline spine ---------------------------------------------------
  const PIPELINE_ORDER = ["embed_ms", "vector_search_ms", "keyword_search_ms", "fusion_ms", "rerank_ms", "generation_ms"];

  function resetSpine() {
    document.querySelectorAll(".stage").forEach((st) => {
      st.classList.remove("lit", "skipped");
      st.querySelector("[data-ms]").textContent = "—";
    });
    $("totalMs").textContent = "—";
  }

  function animateSpine(timings) {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let step = 0;
    PIPELINE_ORDER.forEach((key) => {
      const st = document.querySelector(`.stage[data-key="${key}"]`);
      if (!st) return;
      const val = timings[key];
      if (val == null) {            // stage didn't run in this configuration
        st.classList.add("skipped");
        st.querySelector("[data-ms]").textContent = "off";
        return;
      }
      const delay = reduced ? 0 : step * 180;
      step += 1;
      setTimeout(() => {
        st.classList.add("lit");
        st.querySelector("[data-ms]").textContent = `${val.toFixed(1)} ms`;
      }, delay);
    });
    $("totalMs").textContent = timings.total_ms != null ? `${timings.total_ms.toFixed(1)} ms` : "—";
    $("spineHint").textContent = "traced from the last query";
  }

  // ---- run a query ------------------------------------------------------
  const SIG_COLOR = {
    vector_score: "var(--vector)", keyword_score: "var(--lexical)",
    fused_score: "var(--fusion)", rerank_score: "var(--rerank)",
  };

  async function runQuery() {
    const question = $("q").value.trim();
    if (!question) { $("q").focus(); return; }
    const btn = $("runBtn");
    btn.disabled = true; btn.textContent = "Running…";
    resetSpine();
    $("spineHint").textContent = "tracing…";

    const ns = $("ns").value || "default";
    const payload = {
      question,
      namespace: ns,
      answer_style: $("style").value,
      hybrid: $("tHybrid").checked,
      rerank: $("tRerank").checked,
      include_chunks: true,
    };

    try {
      const r = await api("/v1/query", { method: "POST", body: JSON.stringify(payload), json: true });
      renderAnswer(r);
      animateSpine(r.timings_ms || {});
      refreshMetrics(); refreshQueries();
    } catch (e) {
      renderError(e.message);
    } finally {
      btn.disabled = false; btn.textContent = "Run query";
    }
  }

  function renderAnswer(r) {
    const box = $("answer"); box.classList.add("show");
    const tag = $("groundedTag");
    if (r.grounded) { tag.className = "grounded-tag ok"; tag.textContent = "● grounded · " + r.model; }
    else { tag.className = "grounded-tag no"; tag.textContent = "○ ungrounded · " + r.model; }

    $("answerText").innerHTML = esc(r.answer).replace(/\[(\d{1,3})\]/g, '<sup>[$1]</sup>');

    const warn = $("warnLine");
    warn.textContent = (r.warnings && r.warnings.length) ? "⚠ " + r.warnings.join(" · ") : "";

    const cites = $("cites");
    cites.innerHTML = (r.citations || []).map((c) =>
      `<div class="cite"><div class="head">${esc(c.marker)} ${esc(c.filename)} · chunk #${c.ordinal} · score ${Number(c.score).toFixed(3)}</div>` +
      `<div class="snip">${esc(c.snippet)}</div></div>`
    ).join("");

    renderScoreBars(r.chunks || []);
  }

  function renderScoreBars(chunks) {
    const wrap = $("scorebars");
    if (!chunks.length) { wrap.innerHTML = ""; return; }
    // normalise each signal across the returned chunks for a fair bar length
    const signals = ["vector_score", "keyword_score", "fused_score", "rerank_score"];
    const maxima = {};
    signals.forEach((s) => { maxima[s] = Math.max(0.0001, ...chunks.map((c) => Math.abs(c[s] || 0))); });

    wrap.innerHTML = '<div class="sb-head" style="color:var(--ink-faint);font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px">retrieval signals · top chunk</div>';
    const top = chunks[0];
    wrap.innerHTML += signals.filter((s) => top[s] != null).map((s) => {
      const v = top[s] || 0;
      const w = Math.min(100, (Math.abs(v) / maxima[s]) * 100);
      return `<div class="sb"><div class="sb-head"><span>${s.replace("_score", "")}</span><span>${v.toFixed(4)}</span></div>` +
             `<div class="track"><div class="fill" style="width:${w}%;background:${SIG_COLOR[s] || "var(--ink-dim)"}"></div></div></div>`;
    }).join("");
  }

  function renderError(msg) {
    const box = $("answer"); box.classList.add("show");
    $("groundedTag").className = "grounded-tag no";
    $("groundedTag").textContent = "✕ request failed";
    $("answerText").textContent = msg;
    $("warnLine").textContent = ""; $("cites").innerHTML = ""; $("scorebars").innerHTML = "";
    $("spineHint").textContent = "query failed";
  }

  // ---- utils ------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function truncate(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  // ---- wire up ----------------------------------------------------------
  $("runBtn").addEventListener("click", runQuery);
  $("q").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") runQuery();
  });
  $("ns").addEventListener("change", refreshQueries);

  refreshAll();
  setInterval(refreshAll, 6000);
})();
