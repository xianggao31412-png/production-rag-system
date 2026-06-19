"""
Retrieval-augmented generation composer.

This module turns a ranked list of chunks into a final, cited answer. It owns:

* **Prompt construction** — numbered context blocks, a context-budget cap
  (``max_context_chars``), and an answer-style instruction
  (concise / detailed / bullet).
* **Generation** — calls the real LLM when available, and transparently falls
  back to the extractive stub on disable/failure, recording a warning so the
  degradation is visible in the response and the logs.
* **Citation extraction** — parses the ``[n]`` markers the model actually used
  and maps them back to the source chunks, so every citation returned to the
  caller corresponds to text the model was given.

The grounding contract: an answer is ``grounded`` if it cites at least one real
chunk. Ungrounded answers (no markers, or the explicit "not found" response)
are flagged so the dashboard can track them.
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple

from app.config import Settings
from app.core.llm import LLMClient, extractive_answer
from app.logging_config import get_logger
from app.models.domain import Citation, RagResult, ScoredChunk

logger = get_logger("eka.rag")

_CITATION_RE = re.compile(r"\[(\d{1,3})\]")

_SYSTEM_PROMPT = (
    "You are a precise enterprise knowledge assistant. Answer the user's "
    "question using ONLY the numbered context passages provided. Cite every "
    "claim with its source marker in square brackets, e.g. [1] or [2]. If the "
    "context does not contain the answer, say so plainly and do not invent "
    "facts. Never cite a source number that was not provided."
)

_STYLE_INSTRUCTIONS = {
    "concise": "Answer in 1-3 sentences. Be direct.",
    "detailed": "Answer thoroughly in well-structured prose, covering the relevant details from the context.",
    "bullet": "Answer as a short bulleted list. Start each bullet with '- '.",
}


class RagComposer:
    def __init__(self, settings: Settings, llm_client: Optional[LLMClient]):
        self._s = settings
        self._llm = llm_client

    def compose(
        self,
        question: str,
        chunks: List[ScoredChunk],
        answer_style: str = "detailed",
        retrieval_timings: Optional[Dict[str, float]] = None,
    ) -> RagResult:
        timings: Dict[str, float] = dict(retrieval_timings or {})
        warnings: List[str] = []

        if not chunks:
            return RagResult(
                answer="I couldn't find anything relevant in the knowledge base to answer that.",
                citations=[],
                used_chunks=[],
                model=self._model_label(used_stub=True),
                grounded=False,
                timings_ms=timings,
                warnings=["no_chunks_retrieved"],
            )

        context, included = self._build_context(chunks)
        if len(included) < len(chunks):
            warnings.append("context_truncated")

        style = _STYLE_INSTRUCTIONS.get(answer_style, _STYLE_INSTRUCTIONS["detailed"])
        user_prompt = (
            f"{style}\n\n"
            f"# Context\n{context}\n\n"
            f"# Question\n{question}\n\n"
            f"# Answer (with [n] citations)"
        )

        used_stub = self._llm is None
        t0 = time.perf_counter()
        if self._llm is not None:
            try:
                answer = self._llm.complete(_SYSTEM_PROMPT, user_prompt)
            except Exception as exc:  # noqa: BLE001 - degrade, don't fail
                logger.warning("llm_failed_fallback_to_stub", extra={"error": str(exc)})
                warnings.append(f"llm_unavailable:{type(exc).__name__}")
                answer = extractive_answer(question, included)
                used_stub = True
        else:
            answer = extractive_answer(question, included)
        timings["generation_ms"] = (time.perf_counter() - t0) * 1000

        citations = self._extract_citations(answer, included)
        grounded = len(citations) > 0

        if not grounded and used_stub:
            # The stub always cites; absence means genuinely nothing matched.
            warnings.append("ungrounded_answer")

        return RagResult(
            answer=answer,
            citations=citations,
            used_chunks=included,
            model=self._model_label(used_stub),
            grounded=grounded,
            timings_ms=timings,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _build_context(self, chunks: List[ScoredChunk]) -> Tuple[str, List[ScoredChunk]]:
        """Render numbered context blocks under the character budget."""
        budget = self._s.max_context_chars
        blocks: List[str] = []
        included: List[ScoredChunk] = []
        used = 0
        for i, sc in enumerate(chunks, start=1):
            text = sc.chunk.text.strip()
            header = f"[{i}] (source: {sc.chunk.filename})\n"
            block = header + text
            # Always include at least the first chunk, even if it alone is large.
            if used + len(block) > budget and included:
                break
            blocks.append(block)
            included.append(sc)
            used += len(block) + 2
        return "\n\n".join(blocks), included

    def _extract_citations(
        self, answer: str, chunks: List[ScoredChunk]
    ) -> List[Citation]:
        markers = [int(m) for m in _CITATION_RE.findall(answer)]
        seen = set()
        citations: List[Citation] = []
        for n in markers:
            if n in seen or n < 1 or n > len(chunks):
                continue
            seen.add(n)
            sc = chunks[n - 1]
            snippet = sc.chunk.text.strip().replace("\n", " ")
            citations.append(
                Citation(
                    marker=f"[{n}]",
                    chunk_id=sc.chunk.id,
                    document_id=sc.chunk.document_id,
                    filename=sc.chunk.filename,
                    ordinal=sc.chunk.ordinal,
                    snippet=snippet[:300],
                    score=round(float(sc.score), 6),
                )
            )
        return citations

    def _model_label(self, used_stub: bool) -> str:
        return "extractive-stub" if used_stub else (self._llm.model if self._llm else "extractive-stub")
