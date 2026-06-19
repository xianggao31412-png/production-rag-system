"""
Application configuration.

All settings are read from environment variables (or a local `.env` file).
Field names are matched case-insensitively, so the field `embedding_provider`
is populated from the env var `EMBEDDING_PROVIDER`.

Design note
-----------
List-style settings (API keys, CORS origins) are stored as raw comma-separated
strings and exposed through computed properties. This avoids the JSON-parsing
behaviour that `pydantic-settings` applies to `list` fields read from the
environment, which would otherwise force callers to write JSON arrays in `.env`.
"""
from __future__ import annotations

import functools
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    # ---- Service identity -------------------------------------------------
    app_name: str = "Enterprise Knowledge Assistant"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True

    host: str = "0.0.0.0"
    port: int = 8000

    # ---- Storage ----------------------------------------------------------
    data_dir: str = "./data"

    # ---- Security ---------------------------------------------------------
    require_auth: bool = True
    # Comma-separated list of accepted API keys. Default key is for local dev.
    api_keys_raw: str = Field(default="dev-local-key", alias="API_KEYS")
    api_key_header: str = "X-API-Key"

    # ---- CORS -------------------------------------------------------------
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    # ---- Rate limiting ----------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 20

    # ---- Chunking ---------------------------------------------------------
    chunk_size: int = 800          # characters per chunk (target)
    chunk_overlap: int = 120       # characters of overlap between chunks
    min_chunk_chars: int = 40      # chunks shorter than this are dropped

    # ---- Embeddings -------------------------------------------------------
    # "hash"             -> deterministic local hashing embedder, zero downloads
    # "openai_compatible"-> any OpenAI-compatible /v1/embeddings endpoint (Ollama, etc.)
    embedding_provider: Literal["hash", "openai_compatible"] = "hash"
    embedding_dim: int = 384       # used by the hash embedder
    embedding_base_url: str = "http://127.0.0.1:11434/v1"
    embedding_api_key: str = "local"
    embedding_model: str = "nomic-embed-text"
    embedding_timeout: float = 60.0
    embedding_batch_size: int = 32

    # ---- Vector store -----------------------------------------------------
    # "memory" -> numpy cosine store persisted to disk, zero heavy deps
    # "chroma" -> ChromaDB persistent client (requires `pip install chromadb`)
    vector_backend: Literal["memory", "chroma"] = "memory"
    chroma_path: str = "./data/chroma"

    # ---- Keyword (BM25) ---------------------------------------------------
    bm25_enabled: bool = True

    # ---- Hybrid retrieval -------------------------------------------------
    hybrid_enabled: bool = True
    # "rrf"      -> Reciprocal Rank Fusion (rank-based, robust, recommended)
    # "weighted" -> min-max normalised weighted score blend
    fusion_method: Literal["rrf", "weighted"] = "rrf"
    rrf_k: int = 60
    vector_weight: float = 0.5
    keyword_weight: float = 0.5

    # Number of candidates pulled from each retriever before fusion/rerank.
    vector_top_k: int = 20
    keyword_top_k: int = 20
    # Candidates handed to the reranker after fusion.
    rerank_candidates: int = 12
    # Final number of chunks returned to the LLM / caller.
    final_top_k: int = 5

    # ---- Reranking --------------------------------------------------------
    # "none"          -> use fused order directly
    # "heuristic"     -> lexical-overlap reranker, zero downloads
    # "cross_encoder" -> sentence-transformers CrossEncoder (requires extra install)
    rerank_provider: Literal["none", "heuristic", "cross_encoder"] = "heuristic"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ---- LLM --------------------------------------------------------------
    # When enabled, calls an OpenAI-compatible /v1/chat/completions endpoint.
    # When disabled (or the call fails) an extractive stub answer is returned
    # so the pipeline always produces a grounded, citation-bearing response.
    llm_enabled: bool = True
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "local"
    llm_model: str = "qwen3-coder:30b"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 800
    llm_timeout: float = 120.0
    # If True, never call the network LLM; always use the extractive stub.
    # Useful for demos, CI, and air-gapped environments.
    llm_force_stub: bool = False

    # ---- Prompting --------------------------------------------------------
    max_context_chars: int = 6000

    # ---- Logging ----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    # ---- Computed list properties ----------------------------------------
    @property
    def api_keys(self) -> List[str]:
        return [k.strip() for k in self.api_keys_raw.split(",") if k.strip()]

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


@functools.lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
