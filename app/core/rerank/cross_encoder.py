"""
Cross-encoder reranker (optional).

Used when `RERANK_PROVIDER=cross_encoder`. Loads a sentence-transformers
CrossEncoder (default: ms-marco-MiniLM-L-6-v2) and scores each (query, passage)
pair jointly. This is the most accurate option and the standard production
choice, at the cost of a model download and heavier CPU/GPU use.

If the model can't be loaded, this raises at construction time so the factory
can surface a clear message rather than failing per-request.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from app.errors import UpstreamError
from app.logging_config import get_logger

logger = get_logger("eka.rerank.cross_encoder")


class CrossEncoderReranker:
    name = "cross_encoder"

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - optional dep
            raise UpstreamError(
                "RERANK_PROVIDER=cross_encoder requires sentence-transformers. "
                "Install with `pip install sentence-transformers`, or set "
                "RERANK_PROVIDER=heuristic."
            ) from exc
        try:
            self._model = CrossEncoder(model_name)
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"Failed to load cross-encoder '{model_name}': {exc}") from exc
        logger.info("cross_encoder_loaded", extra={"model": model_name})

    def rerank(
        self, query: str, candidates: Sequence[Tuple[str, str]]
    ) -> List[Tuple[str, float]]:
        if not candidates:
            return []
        pairs = [[query, text] for _, text in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(
            ((cid, float(s)) for (cid, _), s in zip(candidates, scores)),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked
