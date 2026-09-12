"""Tests für ragapp.ingestion.loaders.ocr_image_bytes() (Foto-Mitschrift,
siehe Notizen.py) - deckt nur die Grenzfaelle/Guards ab, die ohne echtes
Vision-Modell/GPU prüfbar sind. Die eigentliche Bilderkennungsqualität wird
per Live-Test mit einer echten Ollama-Instanz verifiziert (Session-Konvention:
Modell-Ausgabequalität lässt sich nicht durch Unit-Tests ersetzen)."""
from __future__ import annotations

from ragapp.ingestion import loaders


def test_ocr_image_bytes_ohne_vision_modell_liefert_leeres_tupel(monkeypatch):
    monkeypatch.setattr(loaders, "_resolve_vision_model", lambda: "")
    text, engine = loaders.ocr_image_bytes(b"irrelevant")
    assert (text, engine) == ("", "")


def test_ocr_image_bytes_bei_zu_wenig_vram_liefert_leeres_tupel(monkeypatch):
    monkeypatch.setattr(loaders, "_resolve_vision_model", lambda: "gemma3:4b")
    monkeypatch.setattr(loaders, "_vision_ocr_prepare", lambda model: False)
    text, engine = loaders.ocr_image_bytes(b"irrelevant")
    assert (text, engine) == ("", "")


def test_ocr_image_bytes_bei_kaputten_bild_bytes_liefert_leeres_tupel(monkeypatch):
    monkeypatch.setattr(loaders, "_resolve_vision_model", lambda: "gemma3:4b")
    monkeypatch.setattr(loaders, "_vision_ocr_prepare", lambda model: True)
    text, engine = loaders.ocr_image_bytes(b"das ist kein Bild")
    assert (text, engine) == ("", "")


def test_ocr_image_bytes_leitet_gutes_ergebnis_durch(monkeypatch):
    import io
    from PIL import Image

    monkeypatch.setattr(loaders, "_resolve_vision_model", lambda: "gemma3:4b")
    monkeypatch.setattr(loaders, "_vision_ocr_prepare", lambda model: True)
    monkeypatch.setattr(loaders, "_vision_ocr_bytes", lambda png, model: "Erkannter Text")

    img = Image.new("RGB", (50, 50), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    text, engine = loaders.ocr_image_bytes(buf.getvalue())
    assert text == "Erkannter Text"
    assert engine == "vision"
