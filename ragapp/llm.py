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
from typing import Any, Iterator

import ollama

from ragapp.config import settings

try:  # zentrales Logging (von logging_setup bereitgestellt)
    from ragapp.logging_setup import get_logger
    _log = get_logger(__name__)
except Exception:  # Modul evtl. noch nicht vorhanden -> Standard-Logging als Fallback
    import logging
    _log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Fehlerdiagnose (Ollama-aus / Modell-fehlt / VRAM-OOM) -> klare deutsche Meldung
# --------------------------------------------------------------------------- #
# Marker, an denen ein Verbindungsproblem zum Ollama-Server erkennbar ist
# (httpx/requests/urllib3 formulieren das je nach Plattform unterschiedlich).
_CONNECTION_MARKERS = (
    "connection refused", "actively refused", "errno 111",
    "all connection attempts", "failed to establish", "max retries",
    "connectionerror", "connecterror", "newconnectionerror",
    "connection reset", "remotedisconnected", "no connection could be made",
    "cannot connect", "connection aborted",
)


def _is_connection_error(exc: Exception) -> bool:
    """True, wenn die Exception nach einem nicht erreichbaren Ollama-Server aussieht."""
    low = str(exc).lower()
    return any(m in low for m in _CONNECTION_MARKERS)


def diagnose_error(exc: Exception) -> str:
    """Uebersetzt haeufige Ollama-/LLM-Fehler in eine verstaendliche deutsche Meldung.

    Deckt die drei praktisch relevanten Faelle ab:
        * Ollama-Dienst nicht erreichbar (Connection refused)
        * angefragtes Modell nicht installiert (404 / "model not found")
        * zu wenig Speicher / Backend-Absturz (VRAM/OOM/500)
    Unbekannte Fehler werden mit ihrer Originalmeldung durchgereicht.
    """
    msg = (str(exc) or exc.__class__.__name__).strip()
    low = msg.lower()
    status = getattr(exc, "status_code", None)

    # 1) Modell nicht installiert (404 bzw. "model ... not found, try pulling")
    if status == 404 or ("not found" in low and "model" in low) \
            or "try pulling" in low or "pull it first" in low:
        m = re.search(r'model\s+"?([\w./:-]+)"?\s+not found', msg, re.IGNORECASE)
        modell = m.group(1) if m else "<modell>"
        return (f"Modell nicht installiert: '{modell}' ist in Ollama nicht vorhanden. "
                f"Bitte zuerst laden: `ollama pull {modell}`.")

    # 2) Ollama-Server nicht erreichbar
    if _is_connection_error(exc):
        return (f"Ollama ist nicht erreichbar ({settings.OLLAMA_BASE_URL}). "
                "Laeuft der Ollama-Dienst? Starte ihn (z. B. `ollama serve`) "
                "und versuche es erneut.")

    # 3) Zeitueberschreitung
    if any(k in low for k in ("timed out", "timeout", "read timeout", "readtimeout")):
        return (f"Zeitueberschreitung nach {settings.LLM_TIMEOUT}s. Die Inferenz dauert "
                "auf CPU lange - kuerzere Anfrage/kleineres Modell waehlen oder "
                "LLM_TIMEOUT erhoehen.")

    # 4) Zu wenig Speicher / Modell-Runner abgestuerzt (VRAM/OOM/500)
    if status == 500 or any(k in low for k in (
            "out of memory", "oom", "insufficient memory", "not enough memory",
            "vram", "cuda error", "cuda out of memory", "model runner",
            "unexpectedly stopped", "failed to allocate", "cannot allocate")):
        return ("Zu wenig Speicher oder der Modell-Runner ist abgestuerzt (VRAM/RAM). "
                "Kleineres Modell bzw. kuerzeren Kontext waehlen oder andere "
                "GPU-Anwendungen schliessen und Ollama neu starten.")

    # Fallback: Originalmeldung durchreichen, damit nichts verschluckt wird
    return f"LLM-Fehler: {msg}"


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
                # Verbindungsfehler heilen sich nicht in 1-2 s -> nicht sinnlos wiederholen
                if _is_connection_error(exc):
                    _log.warning("Ollama nicht erreichbar (%s): %s", self.model, exc)
                    break
                if attempt < retries:            # nach dem letzten Versuch nicht mehr warten
                    _log.debug("LLM-Versuch %d/%d fehlgeschlagen (%s): %s",
                               attempt + 1, retries + 1, self.model, exc)
                    time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(diagnose_error(last_err)) from last_err

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

    def generate_stream(
        self,
        prompt: str | list[dict] | None = None,
        *,
        messages: list[dict] | None = None,
        system: str | None = None,
        temperature: float | None = None,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        think: bool | str = False,
    ) -> Iterator[str]:
        """Streamt die Antwort Token fuer Token (Generator ueber ``message.content``-Deltas).

        Nutzt Ollamas ``/api/chat`` mit ``stream=True``; jede Antwort-Zeile ist ein
        JSON-Chunk, aus dem der Content-Delta geyieldet wird. Die bestehenden
        Signaturen von ``chat()``/``generate()``/``generate_json()`` bleiben
        unveraendert - das Wiring in Graph/Home passiert in einer spaeteren Phase.

        Eingaben: entweder ``prompt`` (+ optional ``system``) oder eine fertige
        ``messages``-Liste (auch als erstes Positionsargument erlaubt).

        Fehler (Verbindung/Timeout/OOM) werden ueber :func:`diagnose_error` in eine
        klare deutsche Meldung uebersetzt und als ``RuntimeError`` geworfen. Wird
        der Reasoning-Schalter vom Backend nicht akzeptiert, wird - solange noch
        nichts ausgegeben wurde - ohne ihn erneut gestartet.
        """
        # Eingaben normalisieren: prompt (str) ODER fertige messages-Liste
        if isinstance(prompt, list) and messages is None:
            messages = prompt
            prompt = None
        if messages is None:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt or ""})

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
            "stream": True,
        }

        def _iter_once(kw: dict) -> Iterator[str]:
            for chunk in self._client.chat(**kw):
                msg = chunk.get("message", {}) or {}
                delta = msg.get("content", "") or ""
                if delta:
                    yield delta

        try:
            yielded = False
            try:
                for delta in _iter_once(kwargs):
                    yielded = True
                    yield delta
            except Exception as exc:
                # Reasoning-Schalter nicht unterstuetzt UND noch nichts ausgegeben -> ohne ihn
                if (not yielded and kwargs.get("think") not in (False, None)
                        and "think" in str(exc).lower()):
                    kwargs["think"] = False
                    for delta in _iter_once(kwargs):
                        yield delta
                else:
                    raise
        except Exception as exc:  # pragma: no cover - Netz-/Backend-Fehler
            _log.warning("Streaming-Aufruf fehlgeschlagen (%s): %s", self.model, exc)
            raise RuntimeError(diagnose_error(exc)) from exc


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


# --------------------------------------------------------------------------- #
# VRAM-Pre-Flight: passt das Modell VOR der ersten Frage in den freien VRAM?
# --------------------------------------------------------------------------- #
# Sinn: Laeuft parallel eine zweite GPU-App und ist zu wenig VRAM frei, lagert
# Ollama das Modell zaeh auf die CPU aus (Antwort dauert Minuten). Statt still zu
# blockieren, zeigt der Chat dann eine klare Meldung ("nur X GB frei, Modell
# braucht ~Y GB - bitte andere GPU-App schliessen"). Alles best-effort: bei jedem
# Zweifel -> 'unknown' (der Chat laeuft normal weiter, es wird NICHT blockiert).
_GPU_INFO_CACHE: "dict | None" = None


def _gpu_info() -> dict:
    """GPU-Info EINMAL ermitteln und cachen (Hardware aendert sich nicht zur Laufzeit)."""
    global _GPU_INFO_CACHE
    if _GPU_INFO_CACHE is None:
        try:
            from ragapp import hardware
            _GPU_INFO_CACHE = hardware.detect_gpu() or {}
        except Exception:  # noqa: BLE001
            _GPU_INFO_CACHE = {}
    return _GPU_INFO_CACHE


def _ollama_get_json(path: str) -> "dict | None":
    import json
    import urllib.request
    base = str(settings.OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(base + path, timeout=4) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def _model_resident(model: str) -> bool:
    """Ist das Modell bereits in Ollama geladen? Dann passt es schon -> kein Risiko."""
    data = _ollama_get_json("/api/ps") or {}
    for m in data.get("models", []):
        if m.get("name") == model or m.get("model") == model:
            return True
    return False


def _model_size_gb(model: str) -> "float | None":
    """Groesse der Modell-Gewichte (GB) aus Ollama (~benoetigter VRAM). None unbekannt."""
    data = _ollama_get_json("/api/tags") or {}
    for m in data.get("models", []):
        if m.get("name") == model or m.get("model") == model:
            sz = m.get("size")
            if sz:
                return sz / (1024 ** 3)
    return None


def vram_preflight(model: "str | None" = None) -> dict:
    """Prueft, ob genug freier VRAM fuer das Modell da ist. Rueckgabe-dict:
        {status: 'ok'|'low'|'unknown', model, free_gb?, need_gb?, gpu_name?, resident?}
    'low' -> zu wenig frei (UI zeigt Warnung + bricht die Frage ab). Sonst nie blocken."""
    model = model or settings.LLM_MODEL
    try:
        gpu = _gpu_info()
        # Kein dedizierter GPU-Speicher (iGPU/CPU-only): laeuft ohnehin ueber RAM -> egal.
        if not gpu or gpu.get("is_igpu") or not gpu.get("vram_gb"):
            return {"status": "ok", "model": model}
        from ragapp import hardware
        free = hardware.vram_free_gb()
        if free is None:
            return {"status": "unknown", "model": model}
        # Modell schon geladen -> passt bereits, kein CPU-Auslagerungs-Risiko.
        if _model_resident(model):
            return {"status": "ok", "model": model, "free_gb": round(free, 1),
                    "resident": True}
        need = _model_size_gb(model)
        if not need:
            return {"status": "unknown", "model": model, "free_gb": round(free, 1)}
        # Bedarf ~ Gewichte + kleiner Puffer (Kontext/KV-Cache); 0.5 GB Toleranz.
        if free + 0.5 < need + 1.0:
            return {"status": "low", "free_gb": round(free, 1), "need_gb": round(need, 1),
                    "model": model, "gpu_name": gpu.get("name")}
        return {"status": "ok", "free_gb": round(free, 1), "need_gb": round(need, 1),
                "model": model}
    except Exception:  # noqa: BLE001
        return {"status": "unknown", "model": model}
