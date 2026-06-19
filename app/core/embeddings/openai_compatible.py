"""
OpenAI-compatible embedder.

Calls any service exposing the OpenAI `/v1/embeddings` schema — OpenAI itself,
Ollama, llama-server, LM Studio, vLLM, TEI, etc. The dimension is discovered
lazily from the first successful response, so you don't have to hard-code it per
model.
"""
from __future__ import annotations

from typing import List, Optional

import httpx

from app.core.embeddings.base import Embedder
from app.errors import UpstreamError
from app.logging_config import get_logger

logger = get_logger("eka.embeddings.openai")


class OpenAICompatibleEmbedder(Embedder):
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        batch_size: int = 32,
        fallback_dim: int = 768,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._batch_size = max(1, batch_size)
        self._dim: Optional[int] = None
        self._fallback_dim = fallback_dim

    @property
    def dimension(self) -> int:
        # Known only after the first call; report a sensible default until then.
        return self._dim or self._fallback_dim

    def _post(self, inputs: List[str]) -> List[List[float]]:
        url = f"{self._base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {"model": self._model, "input": inputs}
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("embedding_request_failed", extra={"url": url, "error": str(exc)})
            raise UpstreamError(
                f"Embedding service call failed: {exc}. "
                f"Check EMBEDDING_BASE_URL ({self._base_url}) and that the model is pulled."
            ) from exc

        data = resp.json().get("data", [])
        vectors = [item["embedding"] for item in data]
        if vectors:
            self._dim = len(vectors[0])
        return vectors

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), self._batch_size):
            out.extend(self._post(texts[i : i + self._batch_size]))
        return out

    def embed_query(self, text: str) -> List[float]:
        return self._post([text])[0]
