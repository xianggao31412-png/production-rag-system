"""
Language-model client.

Two responsibilities live here:

1. ``LLMClient`` — a thin wrapper over any OpenAI-compatible
   ``/v1/chat/completions`` endpoint (Ollama, llama.cpp's ``llama-server``,
   vLLM, OpenAI itself, ...). It is intentionally minimal: one blocking call,
   explicit timeout, and a narrow return type.

2. An **extractive stub** (``extractive_answer``) used whenever a real model is
   unavailable, disabled, or has failed. Instead of erroring out, the pipeline
   degrades gracefully: it stitches the most relevant retrieved sentences into a
   short, fully-grounded answer with inline citation markers. This guarantees
   ``/query`` always returns something useful and verifiable, which is what
   makes the system demoable on an air-gapped laptop with zero model weights.
"""
from __future__ import annotations

from typing import List, Optional

import httpx

from app.config import Settings
from app.errors import UpstreamError
from app.logging_config import get_logger
from app.models.domain import ScoredChunk

logger = get_logger("eka.llm")


class LLMClient:
    """Blocking client for an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 800,
        timeout: float = 120.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamError(f"LLM request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(f"Malformed LLM response: {exc}") from exc

    def ping(self) -> bool:
        """Best-effort reachability probe. Never raises."""
        try:
            with httpx.Client(timeout=5.0) as client:
                # /models is the conventional cheap, side-effect-free endpoint.
                resp = client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code < 500
        except httpx.HTTPError:
            return False


def build_llm_client(settings: Settings) -> Optional[LLMClient]:
    """Construct an LLM client, or None when running in pure-stub mode."""
    if settings.llm_force_stub or not settings.llm_enabled:
        return None
    return LLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
    )


# --------------------------------------------------------------------------- #
# Extractive fallback
# --------------------------------------------------------------------------- #
_STUB_MODEL_NAME = "extractive-stub"


def _split_sentences(text: str) -> List[str]:
    out: List[str] = []
    buf = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?\n" and len("".join(buf).strip()) > 0:
            out.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def extractive_answer(question: str, chunks: List[ScoredChunk], max_sentences: int = 4) -> str:
    """Build a grounded answer by selecting the most on-topic sentences.

    The selection is a simple lexical-overlap score against the question. Each
    selected sentence keeps the citation marker of the chunk it came from, so
    the answer remains traceable to its source even without a real model.
    """
    if not chunks:
        return "I couldn't find anything relevant in the knowledge base to answer that."

    q_terms = {t for t in _tokenize(question) if len(t) > 2}
    scored_sentences = []
    for idx, sc in enumerate(chunks, start=1):
        for sent in _split_sentences(sc.chunk.text):
            s_terms = set(_tokenize(sent))
            if not s_terms:
                continue
            overlap = len(q_terms & s_terms)
            if overlap == 0 and idx > 1:
                continue
            # Prefer high overlap, then earlier (more relevant) chunks.
            score = overlap + (1.0 / idx)
            scored_sentences.append((score, idx, sent))

    if not scored_sentences:
        # No lexical overlap anywhere; fall back to the top chunk's opening.
        top = chunks[0]
        snippet = top.chunk.text.strip().replace("\n", " ")
        return f"{snippet[:400].rstrip()} [1]"

    scored_sentences.sort(key=lambda x: (-x[0], x[1]))
    chosen = scored_sentences[:max_sentences]
    # Keep the natural reading order of the chosen sentences.
    chosen.sort(key=lambda x: x[1])

    parts = []
    for _, idx, sent in chosen:
        sent = sent.strip().replace("\n", " ")
        if not sent.endswith((".", "!", "?")):
            sent += "."
        parts.append(f"{sent} [{idx}]")
    return " ".join(parts)


def _tokenize(text: str) -> List[str]:
    return [
        "".join(c for c in tok if c.isalnum())
        for tok in text.lower().split()
        if any(c.isalnum() for c in tok)
    ]
