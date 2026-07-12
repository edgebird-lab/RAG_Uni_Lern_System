"""
Cross-Encoder-Reranker (bge-reranker-v2-m3)
==========================================

Nach der Hybrid-Fusion bewertet ein Cross-Encoder jedes (Frage, Chunk)-Paar
gemeinsam und sortiert die Kandidaten neu. Das ist einer der stärksten Hebel für
die Trefferquote, weil der Cross-Encoder viel feiner unterscheidet als reine
Vektordistanz.

Robustheit: Lässt sich das Modell nicht laden (z. B. torch-Problem), fällt das
System automatisch auf die Fusions-Reihenfolge zurück und protokolliert eine
Warnung. Das System bleibt funktionsfähig.
"""
from __future__ import annotations

from typing import Optional

from ragapp.config import settings


class Reranker:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.RERANKER_MODEL
        self._model = None
        self._failed = False
        self._warmed = False

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._failed:
            return False
        try:
            import torch
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, max_length=settings.RERANKER_MAX_LENGTH)
            # WICHTIG: sentence-transformers 5.x wendet für num_labels==1-Modelle
            # (bge-reranker-v2-m3) standardmäßig eine Sigmoid-Aktivierung an ->
            # Scores in (0,1). Wir erzwingen rohe Logits (Identity), damit die
            # Relevanzschwelle RELEVANCE_MIN_SCORE (Logit-Skala) korrekt greift.
            try:
                self._model.activation_fn = torch.nn.Identity()
            except Exception:
                pass
            return True
        except Exception as exc:  # pragma: no cover
            print(f"[reranker] WARNUNG: konnte nicht geladen werden ({exc}). "
                  f"Fallback auf Fusions-Reihenfolge.")
            self._failed = True
            return False

    def warm(self) -> None:
        """Laedt die Cross-Encoder-Gewichte vorab und feuert genau EINEN Dummy-
        Forward-Pass ab, damit der teure Kaltstart (~14s fuer bge-reranker-v2-m3,
        ~568M) nicht erst beim ersten echten rerank()-Aufruf anfaellt.

        Idempotent (warmt hoechstens einmal) und exception-safe: Faellt das Laden
        oder der Forward-Pass aus, wird nur protokolliert; das System nutzt dann
        wie gewohnt die Fusions-Reihenfolge als Fallback."""
        if self._warmed:
            return
        try:
            if not self._ensure_loaded():
                return
            # Genau EIN Dummy-predict: materialisiert Gewichte im Speicher und
            # kompiliert/initialisiert den ersten Forward-Pass.
            try:
                import torch
                self._model.predict(
                    [["warmup", "warmup"]], show_progress_bar=False,
                    activation_fn=torch.nn.Identity(),
                )
            except TypeError:
                # aeltere/andere API ohne activation_fn-Parameter
                self._model.predict([["warmup", "warmup"]], show_progress_bar=False)
            self._warmed = True
        except Exception as exc:  # pragma: no cover
            print(f"[reranker] WARNUNG: Vorwaermen fehlgeschlagen ({exc}). "
                  f"Kaltstart erfolgt beim ersten rerank().")

    def rerank(self, query: str, candidates: list[dict], top_k: int | None = None,
               use_reranker: bool | None = None) -> list[dict]:
        """candidates: Liste mit 'document'. Fügt 'rerank_score' hinzu, sortiert absteigend.

        use_reranker überschreibt pro Aufruf die globale Einstellung USE_RERANKER.
        None = globale Einstellung verwenden; False = Reranker überspringen (z. B.
        "Schnelle Antworten" auf der Startseite -> spürbar schneller, weil der teure
        Cross-Encoder-Durchlauf entfällt)."""
        if not candidates:
            return []
        top_k = top_k or settings.FINAL_TOP_K
        enabled = settings.USE_RERANKER if use_reranker is None else use_reranker
        if not enabled or not self._ensure_loaded():
            # Fallback: bestehende Reihenfolge, Score aus Fusion übernehmen
            for c in candidates:
                c.setdefault("rerank_score", c.get("fusion_score", c.get("score", 0.0)))
            return candidates[:top_k]

        pairs = [[query, c["document"]] for c in candidates]
        try:
            import torch
            scores = self._model.predict(
                pairs, show_progress_bar=False, activation_fn=torch.nn.Identity()
            )
        except TypeError:
            # ältere/andere API ohne activation_fn-Parameter
            scores = self._model.predict(pairs, show_progress_bar=False)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates[:top_k]


_default_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = Reranker()
    return _default_reranker
