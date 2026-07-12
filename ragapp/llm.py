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
import re
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
        num_predict: int | None = None,     # pro Aufruf ueberschreibbares Token-Budget
        json_mode: bool = False,
        think: bool | str = False,          # gpt-oss & Co.: "low"/"medium"/"high" moeglich
        retries: int = 2,
        _thinking_fallback: bool = False,   # nur JSON-Pfad: leeren content aus dem Denk-Kanal retten
    ) -> str:
        options = {
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
            "num_ctx": num_ctx or settings.LLM_NUM_CTX,
            "num_predict": num_predict or settings.LLM_NUM_PREDICT,
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
                msg = resp.get("message", {}) or {}
                content = msg.get("content", "") or ""
                # Reasoning-Modelle: bei knappem num_predict kann der Antwort-Channel
                # leer bleiben (done_reason='length'). Den Denk-Kanal NUR im JSON-Pfad
                # als Fallback nehmen (dort wird das JSON heraus-geparst) - fuer Freitext
                # (Antwort/Zusammenfassung) NICHT, sonst leakt die Gedankenkette.
                if _thinking_fallback and not content.strip():
                    content = msg.get("thinking", "") or ""
                return content
            except Exception as exc:  # pragma: no cover
                last_err = exc
                # Backend/Modell akzeptiert den Reasoning-Schalter nicht -> ohne ihn erneut
                if kwargs.get("think") not in (False, None) and "think" in str(exc).lower():
                    kwargs["think"] = False
                    continue
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
        funktioniert auf CPU wie GPU.

        Zusaetzlich Reasoning knapp halten (``think="low"``), damit bei
        Reasoning-Modellen (gpt-oss) das num_predict-Budget nicht komplett von
        der Gedankenkette verbraucht wird und der Antwort-Channel leer/trunkiert
        bleibt (done_reason='length')."""
        kwargs.setdefault("think", "low")
        kwargs.setdefault("_thinking_fallback", True)   # JSON darf aus dem Denk-Kanal kommen
        raw = self.generate(prompt, system=system, **kwargs)
        return _safe_json(raw)


def _safe_json(raw: str) -> Any:
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    # Codefences irgendwo im Text entfernen (```json ... ```)
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Erstes BALANCIERTES {..} bzw. [..]-Objekt scannen (Strings/Escapes beachten),
    # damit Reasoning-Text mit einzelnen '{'/'}' die Extraktion nicht sprengt.
    for opener, closer in (("{", "}"), ("[", "]")):
        depth = 0
        start = -1
        instr = False
        esc = False
        for i, ch in enumerate(raw):
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
                continue
            if ch == '"':
                instr = True
            elif ch == opener:
                if depth == 0:
                    start = i
                depth += 1
            elif ch == closer and depth:
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        return json.loads(raw[start:i + 1])
                    except Exception:
                        start = -1
        # Greedy-Fallback wie bisher
        s, e = raw.find(opener), raw.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(raw[s:e + 1])
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
