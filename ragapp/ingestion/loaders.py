"""
Dokument-Loader
===============

Extrahiert reinen Text (inkl. Struktur-Metadaten) aus verschiedenen Formaten:

    .pdf          -> PyMuPDF (fitz), Fallback pypdf; Text pro Seite
    .md / .txt    -> direkt (Markdown behält Überschriften-Struktur)
    .docx         -> python-docx
    .pptx         -> python-pptx (Text pro Folie)

Rückgabe: ``LoadedDoc`` mit
    * text   : vollständiger, normalisierter Text
    * blocks : Liste von Textblöcken mit Metadaten (Seite/Folie), damit der
               Chunker Quellenangaben wie "Seite 4" anhängen kann.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ragapp.config import settings

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown", ".docx", ".pptx"}


@dataclass
class Block:
    text: str
    page: int | None = None      # Seiten-/Foliennummer, falls vorhanden
    kind: str = "text"
    ocr: bool = False            # True, wenn der Text per OCR gewonnen wurde
    ocr_engine: str = ""         # "vision" | "easyocr" (nur gesetzt, wenn ocr=True)


@dataclass
class LoadedDoc:
    text: str
    blocks: list[Block]
    filetype: str
    is_markdown: bool = False
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Normalisierung
# --------------------------------------------------------------------------- #
def normalize_text(text: str) -> str:
    """Vereinheitlicht Whitespace/Unicode, wichtig für stabile Hashes & Dedup."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # häufige PDF-Artefakte: harte Trennstriche am Zeilenende zusammenfügen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # überzählige Leerzeichen
    text = re.sub(r"[ \t]+", " ", text)
    # mehr als 2 Leerzeilen -> 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Format-spezifische Loader
# --------------------------------------------------------------------------- #
_EASYOCR_READER = None
_EASYOCR_TRIED = False


def _get_easyocr():
    """Gibt einen (gecachten) easyocr-Reader (dt.+engl.) zurueck oder None. Bevorzugt
    die GPU (ROCm/CUDA), faellt auf CPU zurueck. Modelle werden beim ersten Mal geladen."""
    global _EASYOCR_READER, _EASYOCR_TRIED
    if _EASYOCR_TRIED:
        return _EASYOCR_READER
    _EASYOCR_TRIED = True
    try:
        import easyocr
        try:
            _EASYOCR_READER = easyocr.Reader(["de", "en"], gpu=True)
        except Exception:  # noqa: BLE001 - GPU evtl. nicht nutzbar -> CPU
            _EASYOCR_READER = easyocr.Reader(["de", "en"], gpu=False)
    except Exception:  # noqa: BLE001 - easyocr nicht installiert
        _EASYOCR_READER = None
    return _EASYOCR_READER


def _easyocr_page(page) -> str:
    """Klassisches OCR einer text-losen Seite: easyocr (GPU, dt.+engl.),
    Fallback pytesseract. '' wenn kein OCR verfuegbar ist."""
    try:
        png = page.get_pixmap(dpi=200).tobytes("png")
    except Exception:  # noqa: BLE001
        return ""
    reader = _get_easyocr()
    if reader is not None:
        try:
            import io
            import numpy as np
            from PIL import Image
            arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            lines = reader.readtext(arr, detail=0, paragraph=True)
            return "\n".join(str(x) for x in lines)
        except Exception:  # noqa: BLE001
            pass
    try:  # Fallback: pytesseract (falls Tesseract installiert ist)
        import io
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(png))
        try:
            return pytesseract.image_to_string(img, lang="deu") or ""
        except Exception:  # noqa: BLE001
            return pytesseract.image_to_string(img) or ""
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# Vision-OCR (Ollama-Multimodal): liest auch Handschrift als zusammenhaengende
# Woerter, wo easyocr nur Zeichenbrei liefert. Nicht garantiert wortgetreu ->
# Decoding wird gegen Wiederholungs-Loops abgesichert, degenerierte Ausgaben
# werden verworfen (Fallback easyocr).
# --------------------------------------------------------------------------- #
_VISION_CAP_CACHE: dict[str, bool] = {}     # model -> vision-faehig?
_VISION_MODEL_RESOLVED = None               # gecachtes Auto-Detektionsergebnis ("" = keins)

# Bevorzugte kleine, laptop-taugliche Vision-Modelle (Reihenfolge = Praeferenz).
_VISION_PREFERRED = ("gemma3:4b", "gemma4:e4b", "gemma3", "gemma4",
                     "minicpm-v", "llava", "qwen2.5vl", "moondream")

_VISION_OCR_PROMPT = (
    "Transkribiere die deutsche Handschrift auf diesem Bild WORTGETREU, "
    "Zeile fuer Zeile, in originaler Reihenfolge. Uebernimm Spiegelstriche (-) "
    "und Pfeile (->). Fasse nichts zusammen, kuerze nichts und erfinde keine "
    "Aufzaehlungen oder Ueberschriften. Ein einzelnes unlesbares Wort ersetzt "
    "du durch [unleserlich]; bei erkennbaren Woertern rate die wahrscheinlichste "
    "Lesart. Wiederhole keine Zeile. Gib NUR den transkribierten Text aus - "
    "ohne Vorspann, ohne Erklaerung, ohne Anfuehrungszeichen."
)

_VISION_PREAMBLE_RE = re.compile(
    r"^\s*(hier ist|hier folgt|die transkription|transkription|"
    r"transkribierter text|text)\b[^\n:]*:\s*",
    re.IGNORECASE,
)


def _model_has_vision(model: str) -> bool:
    """True, wenn das Ollama-Modell die 'vision'-Capability meldet (gecacht)."""
    if not model:
        return False
    if model in _VISION_CAP_CACHE:
        return _VISION_CAP_CACHE[model]
    ok = False
    try:
        import ollama
        info = ollama.Client(host=settings.OLLAMA_BASE_URL, timeout=15).show(model)
        caps = getattr(info, "capabilities", None)
        if caps is None and hasattr(info, "get"):
            caps = info.get("capabilities")
        ok = "vision" in [str(c).lower() for c in (caps or [])]
    except Exception:  # noqa: BLE001
        ok = False
    _VISION_CAP_CACHE[model] = ok
    return ok


def _resolve_vision_model() -> str:
    """Ermittelt das zu nutzende Vision-Modell. Explizit gesetztes
    OCR_VISION_MODEL gewinnt; sonst Auto-Detektion eines kleinen installierten
    Vision-Modells (bevorzugt gemma3:4b/gemma4:e4b, sonst das kleinste)."""
    global _VISION_MODEL_RESOLVED
    explicit = (settings.OCR_VISION_MODEL or "").strip()
    if explicit:
        return explicit if _model_has_vision(explicit) else ""
    if _VISION_MODEL_RESOLVED is not None:
        return _VISION_MODEL_RESOLVED
    resolved = ""
    try:
        import ollama
        listing = ollama.Client(host=settings.OLLAMA_BASE_URL, timeout=15).list()
        models = getattr(listing, "models", None)
        if models is None and hasattr(listing, "get"):
            models = listing.get("models", [])
        avail: list[tuple[str, int]] = []
        for m in (models or []):
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if name is None and hasattr(m, "get"):
                name = m.get("model") or m.get("name")
            size = getattr(m, "size", None)
            if size is None and hasattr(m, "get"):
                size = m.get("size")
            if name:
                avail.append((str(name), int(size or 0)))

        def _pref_rank(name: str) -> int:
            low = name.lower()
            for i, p in enumerate(_VISION_PREFERRED):
                if low.startswith(p) or p in low:
                    return i
            return len(_VISION_PREFERRED)

        # Praeferenz zuerst, dann kleinste Datei -> laptop-schonend
        avail.sort(key=lambda t: (_pref_rank(t[0]), t[1]))
        for name, _ in avail:
            if _model_has_vision(name):
                resolved = name
                break
    except Exception:  # noqa: BLE001
        resolved = ""
    _VISION_MODEL_RESOLVED = resolved
    return resolved


def has_vision_ocr_model(pull_if_missing: bool = False,
                         pull_model: str = "gemma3:4b") -> str:
    """Public (fuer den Installer): gibt ein installiertes, vision-faehiges Modell
    fuer die Handschrift-/Scan-OCR zurueck (Config ``OCR_VISION_MODEL`` oder
    Auto-Detektion). Ist keins da und ``pull_if_missing=True``, wird ein kleines,
    laptop-taugliches Vision-Modell (Standard: gemma3:4b, ~3.3 GB) gezogen. Gibt
    '' zurueck, wenn keins verfuegbar/ziehbar ist (dann faellt die OCR auf easyocr
    zurueck). Blockiert waehrend des Pulls."""
    global _VISION_MODEL_RESOLVED
    m = _resolve_vision_model()
    if m or not pull_if_missing:
        return m
    try:
        import ollama
        ollama.Client(host=settings.OLLAMA_BASE_URL, timeout=3600).pull(pull_model)
        _VISION_CAP_CACHE.pop(pull_model, None)
        _VISION_MODEL_RESOLVED = None          # Cache invalidieren -> neu detektieren
        return _resolve_vision_model() or pull_model
    except Exception:  # noqa: BLE001
        return ""


def _render_page_png(page, max_side: int, dpi: int) -> bytes | None:
    """Rendert die Seite und verkleinert sie auf 'max_side' (lange Kante) ->
    weniger VRAM, weniger Wiederholungs-Loops beim Vision-Modell."""
    try:
        import io
        from PIL import Image
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        w, h = img.size
        scale = max_side / max(w, h)
        if scale < 1:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                             Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _clean_vision_text(raw: str) -> str:
    """Entfernt Code-Fences, Vorspann ('Hier ist die Transkription:') und
    umschliessende Anfuehrungszeichen."""
    t = (raw or "").strip()
    if not t:
        return ""
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    t = _VISION_PREAMBLE_RE.sub("", t, count=1)
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        t = t[1:-1].strip()
    return t


def _looks_degenerate(text: str) -> bool:
    """True, wenn die Vision-Ausgabe entartet ist -> als gescheitert werten
    (Fallback easyocr / Seite als nicht sicher lesbar behandeln). Faengt drei
    Muster ab, die kleine Modelle bei schwerer Handschrift produzieren:
      (a) exakte Zeilen-Wiederholung (eine Zeile dominiert),
      (b) zu viele '[unleserlich]'-Zeilen (Seite faktisch nicht gelesen),
      (c) Template-Loop (gleiches Zeilen-Skelett mit nur wechselnden Zahlen,
          z. B. 'Matrix 1: … / Zeile 2: Matrix 1: …')."""
    from collections import Counter
    lines = [ln.strip().lower() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 5:
        return False
    n = len(lines)
    # (a) exakte Wiederholung
    if Counter(lines).most_common(1)[0][1] / n > 0.6:
        return True
    # (b) [unleserlich]-Flut -> Seite nicht wirklich transkribiert
    if sum(1 for ln in lines if "[unleserlich]" in ln) / n > 0.45:
        return True
    # (c) Zeilen-Skelett (Ziffern/Sonderzeichen entfernt) dominiert -> Template-Loop
    def _skel(ln: str) -> str:
        return re.sub(r"\d+", "#", re.sub(r"[^0-9a-zäöüß#]+", " ", ln)).strip()
    skels = Counter(s for s in (_skel(ln) for ln in lines) if s)
    if skels and skels.most_common(1)[0][1] / n > 0.5:
        return True
    return False


def _collapse_repeats(text: str, max_repeat: int = 2) -> str:
    """Reduziert direkt aufeinanderfolgende identische Zeilen auf hoechstens
    'max_repeat' (fangt kleinere Loops ab, die den Degenerations-Test knapp
    verfehlen)."""
    out: list[str] = []
    run, last = 0, None
    for line in text.split("\n"):
        key = line.strip().lower()
        if key and key == last:
            run += 1
            if run > max_repeat:
                continue
        else:
            run, last = 1, key
        out.append(line)
    return "\n".join(out).strip()


def _vision_ocr_page(page, model: str) -> str:
    """Rendert die Seite -> verkleinertes PNG -> Ollama-Vision -> bereinigter
    Text. Gibt '' bei Fehler oder degenerierter Ausgabe zurueck (Aufrufer faellt
    dann auf easyocr zurueck)."""
    png = _render_page_png(page, settings.OCR_VISION_MAX_SIDE, settings.OCR_RENDER_DPI)
    if not png:
        return ""
    try:
        import base64
        import ollama
        client = ollama.Client(host=settings.OLLAMA_BASE_URL,
                               timeout=settings.OCR_VISION_TIMEOUT)
        b64 = base64.b64encode(png).decode("ascii")
        resp = client.chat(
            model=model,
            messages=[{"role": "user", "content": _VISION_OCR_PROMPT,
                       "images": [b64]}],
            options={
                "temperature": 0.2, "top_p": 0.9, "top_k": 40,
                "repeat_penalty": 1.3, "repeat_last_n": 64,   # gegen Endlos-Loops
                "num_ctx": 4096,
                "num_predict": settings.OCR_VISION_NUM_PREDICT,
            },
        )
        raw = (resp.get("message", {}) or {}).get("content", "") or ""
    except Exception:  # noqa: BLE001
        return ""
    cleaned = _clean_vision_text(raw)
    if not cleaned or _looks_degenerate(cleaned):
        return ""
    return _collapse_repeats(cleaned)


def _ocr_page(page) -> tuple[str, str]:
    """OCR einer text-losen PDF-Seite. Waehlt die Engine gemaess
    settings.OCR_ENGINE ('vision' | 'easyocr' | 'auto'). 'auto' = Vision, falls
    ein vision-faehiges Ollama-Modell installiert ist, sonst easyocr; bei
    Vision-Fehler/Loop Fallback auf easyocr.
    Rueckgabe: (text, engine) - engine in {'vision', 'easyocr', ''}."""
    engine = (settings.OCR_ENGINE or "auto").strip().lower()
    if engine in ("vision", "auto"):
        model = _resolve_vision_model()
        if model:
            txt = _vision_ocr_page(page, model)
            if txt.strip():
                return txt, "vision"
            # kein/degeneriertes Ergebnis -> easyocr, damit ueberhaupt Text entsteht
    txt = _easyocr_page(page)
    return (txt, "easyocr" if txt.strip() else "")


def _load_pdf(path: Path, progress=None) -> LoadedDoc:
    blocks: list[Block] = []
    text_parts: list[str] = []
    ocr_pages: list[int] = []
    ocr_engines: set[str] = set()
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            n_pages = doc.page_count
            for i, page in enumerate(doc, start=1):
                raw = page.get_text("text") or ""
                norm = normalize_text(raw)
                ocr_engine = ""
                if not norm:
                    # Keine Textebene -> vermutlich Scan/Bild -> OCR versuchen.
                    if progress:
                        try:
                            progress(f"OCR Seite {i}/{n_pages} …", i, n_pages)
                        except Exception:  # noqa: BLE001
                            pass
                    ocr_text, ocr_engine = _ocr_page(page)
                    norm = normalize_text(ocr_text)
                if norm:
                    blk = Block(text=norm, page=i, kind="page")
                    if ocr_engine:
                        blk.ocr = True
                        blk.ocr_engine = ocr_engine
                        ocr_pages.append(i)
                        ocr_engines.add(ocr_engine)
                    blocks.append(blk)
                    text_parts.append(norm)
    except Exception as exc:  # Fallback auf pypdf
        # evtl. schon teilbefüllte fitz-Ergebnisse verwerfen -> keine Seiten-Duplikate
        blocks, text_parts = [], []
        ocr_pages, ocr_engines = [], set()
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            for i, page in enumerate(reader.pages, start=1):
                norm = normalize_text(page.extract_text() or "")
                if norm:
                    blocks.append(Block(text=norm, page=i, kind="page"))
                    text_parts.append(norm)
        except Exception as exc2:
            raise RuntimeError(f"PDF konnte nicht gelesen werden: {exc} / {exc2}")
    return LoadedDoc(
        text="\n\n".join(text_parts),
        blocks=blocks,
        filetype="pdf",
        is_markdown=False,
        meta={
            "pages": len(blocks),
            "ocr": bool(ocr_pages),
            "ocr_pages": ocr_pages,
            "ocr_engine": ",".join(sorted(ocr_engines)),
        },
    )


def _load_markdown(path: Path) -> LoadedDoc:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # optionales YAML-Frontmatter entfernen (Metadaten)
    fm_meta: dict = {}
    try:
        import frontmatter

        post = frontmatter.loads(raw)
        fm_meta = dict(post.metadata)
        raw = post.content
    except Exception:
        pass
    norm = normalize_text(raw)
    return LoadedDoc(
        text=norm,
        blocks=[Block(text=norm, page=None, kind="markdown")],
        filetype="md",
        is_markdown=True,
        meta=fm_meta,
    )


def _load_txt(path: Path) -> LoadedDoc:
    norm = normalize_text(path.read_text(encoding="utf-8", errors="replace"))
    return LoadedDoc(
        text=norm, blocks=[Block(text=norm, kind="text")], filetype="txt"
    )


def _table_to_md(rows: list) -> str:
    """Wandelt eine Tabelle (Liste von Zeilen mit Zellen) in eine Markdown-Tabelle -
    so bleiben Zeilen/Spalten-Beziehungen (Pro/Contra, Klassifikationen, Kennzahlen)
    erhalten, statt zu Zeichenbrei zu kollabieren."""
    clean = [[str(c).replace("\n", " ").replace("|", "/").strip() for c in r]
             for r in rows if any(str(c).strip() for c in r)]
    if not clean:
        return ""
    ncol = max(len(r) for r in clean)
    clean = [r + [""] * (ncol - len(r)) for r in clean]
    out = ["| " + " | ".join(clean[0]) + " |",
           "| " + " | ".join(["---"] * ncol) + " |"]
    for r in clean[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _load_docx(path: Path) -> LoadedDoc:
    from docx import Document

    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    # Tabellen als Markdown erfassen (Struktur bleibt erhalten)
    for table in doc.tables:
        md = _table_to_md([[c.text for c in row.cells] for row in table.rows])
        if md:
            paras.append(md)
    norm = normalize_text("\n".join(paras))
    return LoadedDoc(
        text=norm, blocks=[Block(text=norm, kind="text")], filetype="docx"
    )


def _iter_pptx_shapes(shapes):
    """Iteriert Folien-Shapes rekursiv - auch in Gruppen/SmartArt (die sonst
    komplett verloren gingen)."""
    for shape in shapes:
        yield shape
        if hasattr(shape, "shapes"):          # GroupShape
            try:
                yield from _iter_pptx_shapes(shape.shapes)
            except Exception:  # noqa: BLE001
                pass


def _load_pptx(path: Path) -> LoadedDoc:
    from pptx import Presentation

    prs = Presentation(str(path))
    blocks: list[Block] = []
    parts: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in _iter_pptx_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs)
                    if line.strip():
                        texts.append(line)
            if getattr(shape, "has_table", False) and shape.has_table:
                md = _table_to_md([[c.text for c in row.cells] for row in shape.table.rows])
                if md:
                    texts.append(md)
        # Sprechernotizen: oft die AUSFORMULIERTE Erklaerung, die die knappe Folie
        # nur andeutet - bisher komplett verworfen.
        try:
            if slide.has_notes_slide:
                notes = (slide.notes_slide.notes_text_frame.text or "").strip()
                if notes:
                    texts.append("Notizen: " + notes)
        except Exception:  # noqa: BLE001
            pass
        norm = normalize_text("\n".join(texts))
        if norm:
            blocks.append(Block(text=norm, page=i, kind="slide"))
            parts.append(norm)
    return LoadedDoc(
        text="\n\n".join(parts), blocks=blocks, filetype="pptx",
        meta={"slides": len(blocks)},
    )


_LOADERS = {
    ".pdf": _load_pdf,
    ".md": _load_markdown,
    ".markdown": _load_markdown,
    ".txt": _load_txt,
    ".docx": _load_docx,
    ".pptx": _load_pptx,
}


def load_document(path: str | Path, progress=None) -> LoadedDoc:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in _LOADERS:
        raise ValueError(f"Nicht unterstütztes Format: {ext} ({path.name})")
    # Nur der PDF-Loader kann Seiten rendern -> OCR-Fortschritt melden.
    if ext == ".pdf":
        return _LOADERS[ext](path, progress=progress)
    return _LOADERS[ext](path)
