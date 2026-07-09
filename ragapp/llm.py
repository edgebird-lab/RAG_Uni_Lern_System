"""
LLM-Client (Gemma 4 E4B über Ollama)
====================================

Ein dünner, gemeinsam genutzter Wrapper um Ollamas Chat-API. Wird von der
Fragen-Generierung, der Relevanz-Bewertung, dem Faithfulness-Check und der
finalen Antwortgenerierung verwendet.

Design-Entscheidungen für **wenig Halluzination**:
    * niedrige Temperatur (Standard 0.1)
    * "thinking" standardmäßig aus (schneller auf CPU, deterministischer)
    * optionaler JSON-Modus (format="json") für strukturierte Hilfsaufgaben
"""
from __future__ import annotations

import json
import time
from typing import Any

import ollama

from ragapp.config import settings


class LLM:
    def __init__(self, model: str | None = None):
        self.model = model or settings.LLM_MODEL
        # timeout wird an httpx durchgereicht -> hängende Anfragen brechen ab
        self._client = ollama.Client(
            host=settings.OLLAMA_BASE_URL, timeout=settings.LLM_TIMEOUT
        )

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        num_ctx: int | None = None,
        json_mode: bool = False,
        think: bool = False,
        retries: int = 2,
    ) -> str:
        options = {
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
            "num_ctx": num_ctx or settings.LLM_NUM_CTX,
            "num_predict": settings.LLM_NUM_PREDICT,
        }
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "options": options,
            "think": think,
        }
        if json_mode:
            kwargs["format"] = "json"

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._client.chat(**kwargs)
                return (resp.get("message", {}) or {}).get("content", "") or ""
            except Exception as exc:  # pragma: no cover
                last_err = exc
                if attempt < retries:            # nach dem letzten Versuch nicht mehr warten
                    time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"LLM-Aufruf fehlgeschlagen ({self.model}): {last_err}")

    def generate(
        self, prompt: str, system: str | None = None, **kwargs: Any
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)

    def generate_json(self, prompt: str, system: str | None = None, **kwargs: Any) -> Any:
        """Fordert JSON per Prompt an und parst robust.

        WICHTIG: KEIN Ollama-``format="json"`` (Grammar-constrained decoding),
        das crasht das IPEX-LLM/SYCL-Backend der Intel-iGPU ("model runner
        unexpectedly stopped"). Freie Generierung + robustes Parsen (_safe_json)
        funktioniert auf CPU wie GPU."""
        raw = self.generate(prompt, system=system, **kwargs)
        return _safe_json(raw)


def _safe_json(raw: str) -> Any:
    raw = raw.strip()
    # ggf. Codefences entfernen
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
    try:
        return json.loads(raw)
    except Exception:
        # ersten {...} oder [...] Block herausfischen
        for opener, closer in (("{", "}"), ("[", "]")):
            start = raw.find(opener)
            end = raw.rfind(closer)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except Exception:
                    continue
        return None


_default_llm: LLM | None = None


def get_llm(model: str | None = None) -> LLM:
    global _default_llm
    if model:
        return LLM(model)
    if _default_llm is None:
        _default_llm = LLM()
    return _default_llm
