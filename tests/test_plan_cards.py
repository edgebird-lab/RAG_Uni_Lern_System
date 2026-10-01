"""Lernplan x Karteikarten (``ragapp.plan_cards``) und die dafür erweiterte Pipeline
(``enrich_questions``/``harvest_cards``/``create_study_set`` mit ``chunk_ids``).

Alles offline: temporäre Datenbank, gefakter Vektorstore, kein LLM. Die Tests schreiben
nie in die echte ``data/config.json`` (``mark_needs_card_harvest`` speichert Settings).
"""
from __future__ import annotations

import contextlib
import time

import pytest

from ragapp import manifest, plan_cards, study


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "manifest_test.db")
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    from ragapp.config import settings
    monkeypatch.setattr(settings, "NEEDS_CARD_HARVEST", False, raising=False)
    monkeypatch.setattr(study, "mark_needs_card_harvest", lambda: None)
    return tmp_path


def _card(cid, doc, topic, *, answer="Antwort", source="question", subject="LA"):
    return {"card_id": cid, "source": source, "chroma_id": cid, "subject": subject,
            "topic": topic, "front": f"Frage {cid}?", "back": "Beleg", "answer": answer,
            "doc_id": doc}


def _seed(cards):
    manifest.upsert_review_items(cards)


def _set_progress(cid, reps, due):
    with manifest._connect() as conn:
        conn.execute("UPDATE review_items SET reps=?, due=? WHERE card_id=?", (reps, due, cid))


def _section(sid, *refs):
    return {"section_id": sid, "title": f"Thema {sid}",
            "source_refs": [{"doc_id": d, "filename": f"{d}.pdf", "section": s} for d, s in refs]}


# --------------------------------------------------------------------------- #
# Fundstellen
# --------------------------------------------------------------------------- #
def test_expand_titles_gewoehnlich_menge_und_bereich():
    assert plan_cards.expand_titles("Seite 3") == ["Seite 3"]
    assert plan_cards.expand_titles("Seite 3 / Seite 4") == ["Seite 3", "Seite 4"]
    ordered = [f"Seite {i}" for i in range(1, 10)]
    assert plan_cards.expand_titles("Seite 3 … Seite 6", ordered) == [
        "Seite 3", "Seite 4", "Seite 5", "Seite 6"]
    # Ohne Reihenfolge bleibt nur Anfang und Ende.
    assert plan_cards.expand_titles("Seite 3 … Seite 6") == ["Seite 3", "Seite 6"]
    assert plan_cards.expand_titles("") == []


def test_expand_titles_verschachtelte_zusammenfassung():
    # "A / B" wurde spaeter mit "C / D" zu einem Bereich zusammengelegt.
    ordered = ["a", "b", "x", "c", "d"]
    assert plan_cards.expand_titles("a / b … c / d", ordered) == ["a", "b", "x", "c", "d"]


def test_section_locations_loest_bereiche_ueber_die_dokumentreihenfolge_auf(monkeypatch):
    monkeypatch.setattr(plan_cards, "doc_titles", lambda did: [f"Seite {i}" for i in range(1, 8)])
    sec = _section("s1", ("d1", "Seite 2 … Seite 4"), ("d1", "Seite 6"), ("d2", "Seite 1"))
    assert plan_cards.section_locations(sec) == {
        "d1": ["Seite 2", "Seite 3", "Seite 4", "Seite 6"], "d2": ["Seite 1"]}


def test_section_locations_titel_mit_schraegstrich_bleibt_ganz_wenn_er_existiert(monkeypatch):
    monkeypatch.setattr(plan_cards, "doc_titles", lambda did: ["Kapitel 1 / Einleitung", "Kapitel 2"])
    sec = _section("s1", ("d1", "Kapitel 1 / Einleitung"))
    assert plan_cards.section_locations(sec) == {"d1": ["Kapitel 1 / Einleitung"]}


def test_section_locations_ueberspringt_refs_ohne_dokument():
    sec = {"section_id": "s", "source_refs": [{"doc_id": None, "section": "Seite 1"},
                                              {"doc_id": "d1", "section": ""}]}
    assert plan_cards.section_locations(sec) == {}


# --------------------------------------------------------------------------- #
# Karten eines Themas
# --------------------------------------------------------------------------- #
def test_section_cards_vermischt_dokumente_und_seiten_nicht(db):
    _seed([_card("a1", "A", "Seite 1"), _card("a7", "A", "Seite 7"),
           _card("b1", "B", "Seite 1"), _card("b7", "B", "Seite 7")])
    # Thema = A/Seite 1 + B/Seite 7 - NICHT das Kreuzprodukt (A/7, B/1).
    cards = plan_cards.section_cards(_section("s", ("A", "Seite 1"), ("B", "Seite 7")))
    assert sorted(c["card_id"] for c in cards) == ["a1", "b7"]


def test_section_cards_findet_auch_bestehende_karten_und_ignoriert_pausierte(db):
    _seed([_card("a1", "A", "Seite 1"), _card("a2", "A", "Seite 1")])
    with manifest._connect() as conn:
        conn.execute("UPDATE review_items SET suspended=1 WHERE card_id='a2'")
    assert [c["card_id"] for c in plan_cards.section_cards(_section("s", ("A", "Seite 1")))] == ["a1"]


def test_section_cards_karten_ohne_fundstelle_gehoeren_zu_abschnitt(db):
    _seed([_card("n1", "A", None)])
    assert [c["card_id"] for c in plan_cards.section_cards(_section("s", ("A", "Abschnitt")))] == ["n1"]


def test_plan_card_stats_zaehlt_je_thema_neu_gelernt_faellig_unbeantwortet(db):
    now = time.time()
    _seed([_card("c1", "A", "Seite 1"), _card("c2", "A", "Seite 1"),
           _card("c3", "A", "Seite 2", answer=""), _card("c4", "B", "Seite 1"),
           _card("c5", "A", "Seite 9")])
    _set_progress("c1", 3, now - 100)      # gelernt + faellig
    _set_progress("c2", 2, now + 86400)    # gelernt, nicht faellig
    plan = {"doc_ids": ["A", "B"]}
    s1 = _section("s1", ("A", "Seite 1"), ("A", "Seite 2"))
    s2 = _section("s2", ("B", "Seite 1"))
    s3 = _section("s3", ("A", "Seite 5"))                      # keine Karten
    stats = plan_cards.plan_card_stats(plan, [s1, s2, s3])
    assert stats["s1"] == {"cards": 3, "new": 1, "reviewed": 2, "due": 1, "known": 1,
                           "unanswered": 1, "flawed": 0, "flawed_ids": []}
    assert stats["s2"]["cards"] == 1 and stats["s2"]["new"] == 1
    assert stats["s3"]["cards"] == 0
    # c5 (Seite 9) gehoert zu keinem Thema.
    assert sum(v["cards"] for v in stats.values()) == 4


def test_study_card_ids_faellige_zuerst_dann_neue_dann_rest_mit_limit(db):
    now = time.time()
    _seed([_card("neu", "A", "Seite 1"), _card("spaet", "A", "Seite 1"),
           _card("faellig_alt", "A", "Seite 1"), _card("faellig_neu", "A", "Seite 1")])
    _set_progress("spaet", 2, now + 86400)
    _set_progress("faellig_alt", 2, now - 5000)
    _set_progress("faellig_neu", 2, now - 10)
    sec = _section("s", ("A", "Seite 1"))
    assert plan_cards.study_card_ids(sec, limit=10) == ["faellig_alt", "faellig_neu", "neu", "spaet"]
    assert plan_cards.study_card_ids(sec, limit=2) == ["faellig_alt", "faellig_neu"]


# --------------------------------------------------------------------------- #
# Karten erzeugen
# --------------------------------------------------------------------------- #
class _Chunk(dict):
    def __init__(self, cid, doc, loc):
        super().__init__(id=cid, document="Text " * 40, meta={"doc_id": doc, "location": loc})


class _FakeStore:
    def __init__(self, chunks_by_doc):
        self.chunks_by_doc = chunks_by_doc

    def get_doc_chunks(self, doc_id):
        return list(self.chunks_by_doc.get(doc_id, []))


@pytest.fixture()
def fake_store(monkeypatch):
    store = _FakeStore({
        "A": [_Chunk("A::c0", "A", "Seite 1"), _Chunk("A::c1", "A", "Seite 2"),
              _Chunk("A::c2", "A", "Seite 2"), _Chunk("A::c3", "A", "Seite 3")],
        "B": [_Chunk("B::c0", "B", "Seite 1")],
    })
    monkeypatch.setattr("ragapp.retrieval.vectorstore.get_vectorstore", lambda: store)
    return store


def test_section_chunks_liefert_nur_die_chunks_der_fundstellen(fake_store):
    sec = _section("s", ("A", "Seite 2"), ("B", "Seite 1"))
    assert [c["id"] for c in plan_cards.section_chunks(sec)] == ["A::c1", "A::c2", "B::c0"]


def test_create_section_cards_beschraenkt_pipeline_auf_die_chunks_des_themas(db, fake_store, monkeypatch):
    seen = {}

    def fake_set(doc_ids, **kw):
        seen["doc_ids"], seen["kw"] = doc_ids, kw
        return {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "error_msg": None}

    monkeypatch.setattr(study, "create_study_set", fake_set)
    _seed([_card("A::c1::eq0", "A", "Seite 2")])
    out = plan_cards.create_section_cards(_section("s", ("A", "Seite 2")))
    assert seen["doc_ids"] == ["A"]
    assert seen["kw"]["chunk_ids"] == ["A::c1", "A::c2"]
    # Kein Deckel als Standard (sonst bliebe der Rest groesserer Themen leer), 1 Frage je Chunk.
    assert seen["kw"]["max_chunks"] is None and seen["kw"]["n_per_chunk"] == 1
    assert out["status"] == "ok" and out["cards_total"] == 1
    plan_cards.create_section_cards(_section("s", ("A", "Seite 2")), max_chunks=7)
    assert seen["kw"]["max_chunks"] == 7


def test_create_section_cards_ohne_textabschnitte_meldet_ehrlich_leer(db, fake_store, monkeypatch):
    monkeypatch.setattr(study, "create_study_set", lambda *a, **k: pytest.fail("darf nicht laufen"))
    out = plan_cards.create_section_cards(_section("s", ("A", "Seite 99")))
    assert out["status"] == "empty" and "keine indexierten" in out["error_msg"]


@pytest.fixture()
def no_llm_task(monkeypatch):
    monkeypatch.setattr("ragapp.llm.llm_task", lambda model=None: contextlib.nullcontext())


def _scripted(monkeypatch, outputs):
    calls = []

    def fake(section, **kw):
        calls.append(section["section_id"])
        out = outputs[section["section_id"]]
        if kw.get("progress"):
            kw["progress"]("Frage 1/2")
        return out

    monkeypatch.setattr(plan_cards, "create_section_cards", fake)
    return calls


def test_fill_plan_cards_summiert_ueberspringt_leere_themen_und_meldet_fortschritt(no_llm_task, monkeypatch):
    calls = _scripted(monkeypatch, {
        "s1": {"status": "ok", "questions": 3, "cards_new": 3, "answers": 3, "cards_total": 3},
        "s2": {"status": "empty", "questions": 0, "cards_new": 0, "answers": 0, "cards_total": 0},
        "s3": {"status": "ok", "questions": 0, "cards_new": 0, "answers": 0, "cards_total": 5},
    })
    notes = []
    out = plan_cards.fill_plan_cards([_section("s1"), _section("s2"), _section("s3")],
                                     progress=notes.append)
    assert calls == ["s1", "s2", "s3"]
    assert (out["status"], out["topics"], out["topics_done"], out["topics_empty"]) == ("ok", 3, 2, 1)
    assert (out["questions"], out["cards_new"], out["answers"]) == (3, 3, 3)
    assert any("Thema 2/3" in n for n in notes) and any("Frage 1/2" in n for n in notes)


def test_fill_plan_cards_bricht_bei_fehlendem_modell_ab_und_nennt_fertige_themen(no_llm_task, monkeypatch):
    calls = _scripted(monkeypatch, {
        "s1": {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "cards_total": 2},
        "s2": {"status": "no_model", "error_msg": "Modell laeuft nicht", "cards_total": 0},
        "s3": {"status": "ok", "cards_total": 1},
    })
    out = plan_cards.fill_plan_cards([_section("s1"), _section("s2"), _section("s3")])
    assert calls == ["s1", "s2"]                          # s3 wurde nicht mehr angefasst
    assert out["status"] == "no_model" and out["topics_done"] == 1
    assert "1 Thema" in out["error_msg"] and "Modell laeuft nicht" in out["error_msg"]


def test_fill_plan_cards_zu_wenig_vram_beim_start(monkeypatch):
    from ragapp.llm import VramLowError

    @contextlib.contextmanager
    def boom(model=None):
        raise VramLowError("Zu wenig freier Grafikspeicher (VRAM).")
        yield  # pragma: no cover

    monkeypatch.setattr("ragapp.llm.llm_task", boom)
    out = plan_cards.fill_plan_cards([_section("s1")])
    assert out["status"] == "vram" and "VRAM" in out["error_msg"]


def test_fill_plan_cards_ohne_themen():
    assert plan_cards.fill_plan_cards([])["status"] == "empty"


# --------------------------------------------------------------------------- #
# Pipeline-Erweiterung: harvest_cards / enrich_questions mit chunk_ids
# --------------------------------------------------------------------------- #
class _FakeCol:
    def __init__(self, questions):
        self.questions = questions            # {qid: (frage, meta)}

    def get(self, where=None, include=None, **kw):
        flat = str(where)
        if "'type': 'question'" in flat:
            ids = list(self.questions)
            return {"ids": ids, "documents": [self.questions[i][0] for i in ids],
                    "metadatas": [self.questions[i][1] for i in ids]}
        return {"ids": [], "documents": [], "metadatas": []}


class _HarvestStore:
    def __init__(self, questions, parents):
        self._col = _FakeCol(questions)
        self.parents = parents

    def get_by_ids(self, ids):
        return {i: {"id": i, "document": self.parents[i], "meta": {}} for i in ids if i in self.parents}


def _qmeta(parent, doc="A", location="Seite 1"):
    return {"type": "question", "parent_id": parent, "doc_id": doc, "subject": "LA", "location": location}


def test_harvest_cards_mit_chunk_ids_erntet_nur_fragen_dieser_chunks(db, monkeypatch):
    store = _HarvestStore(
        {"c1::eq0": ("Was ist ein Vektor genau?", _qmeta("c1")),
         "c2::eq0": ("Was ist eine Matrix genau?", _qmeta("c2", location="Seite 2"))},
        {"c1": "Beleg eins " * 5, "c2": "Beleg zwei " * 5})
    monkeypatch.setattr(study, "get_vectorstore", lambda: store)
    out = study.harvest_cards(chunk_ids=["c1"])
    assert out["gefunden"] == 1 and out["neu"] == 1 and out["card_ids"] == ["c1::eq0"]
    assert [c["card_id"] for c in manifest.list_cards()] == ["c1::eq0"]
    # Ohne Filter bleibt alles beim Alten: beide Fragen, ``card_ids`` zusaetzlich.
    out_all = study.harvest_cards()
    assert out_all["gefunden"] == 2 and out_all["neu"] == 1
    assert sorted(out_all["card_ids"]) == ["c1::eq0", "c2::eq0"]


def test_enrich_questions_mit_chunk_ids_laedt_nur_diese_chunks(db, monkeypatch):
    from ragapp.ingestion import enrich

    class Store:
        added = []

        def get_all_chunks(self):
            pytest.fail("get_all_chunks darf mit chunk_ids nicht aufgerufen werden")

        def get_by_ids(self, ids):
            return {i: {"id": i, "document": "Ein Absatz " * 30,
                        "meta": {"doc_id": "A", "filename": "a.pdf", "subject": "LA"}}
                    for i in ids if i != "fehlt"}

        _col = type("C", (), {"get": staticmethod(
            lambda **kw: {"ids": [], "metadatas": []})})()

        def add(self, ids, embeddings, documents, metadatas):
            self.added.append((ids, documents, metadatas))

    store = Store()
    monkeypatch.setattr(enrich, "get_vectorstore", lambda: store)
    monkeypatch.setattr(enrich, "get_embedder",
                        lambda: type("E", (), {"embed_texts": staticmethod(lambda t: [[0.0]] * len(t))})())
    monkeypatch.setattr(enrich, "require_vram", lambda *a, **k: None)
    monkeypatch.setattr(enrich, "probe_model", lambda m: (True, "ok"))
    monkeypatch.setattr(enrich, "release_llm_unless_in_task", lambda: 0)
    monkeypatch.setattr(enrich, "generate_questions",
                        lambda text, n=None, stats=None: ["Was bedeutet dieser Absatz?"])
    out = enrich.enrich_questions(chunk_ids=["A::c1", "fehlt", "A::c2"], n_per_chunk=1)
    assert out["status"] == "ok" and out["questions"] == 2
    ids = [i for batch in store.added for i in batch[0]]
    assert sorted(ids) == ["A::c1::eq0", "A::c2::eq0"]
    assert all(m["parent_id"] in ("A::c1", "A::c2") for b in store.added for m in b[2])


# --------------------------------------------------------------------------- #
# Oberflaechen-Helfer
# --------------------------------------------------------------------------- #
def test_sections_needing_cards_leer_oder_unvollstaendig_nicht_fertige():
    secs = [_section("leer"), _section("voll"), _section("ohne_antwort"), _section("unbekannt")]
    stats = {"leer": {"cards": 0, "unanswered": 0}, "voll": {"cards": 4, "unanswered": 0},
             "ohne_antwort": {"cards": 3, "unanswered": 2}}
    assert [s["section_id"] for s in plan_cards.sections_needing_cards(stats, secs)] == [
        "leer", "ohne_antwort", "unbekannt"]


def test_estimate_missing_cards_und_minuten(db):
    manifest.upsert_document(doc_id="A", content_hash="h", source_path="/A.pdf", filename="A.pdf",
                             subject="LA", filetype="pdf", num_chunks=40, num_questions=0,
                             char_count=1, status="ok")
    plan = {"doc_ids": ["A", "gibt-es-nicht"]}
    assert plan_cards.estimate_missing_cards(plan, {"s1": {"cards": 10}, "s2": {"cards": 5}}) == 25
    assert plan_cards.estimate_missing_cards(plan, {"s1": {"cards": 500}}) == 0
    assert plan_cards.estimate_fill_minutes(0) == 1                      # nie "0 Min"
    assert plan_cards.estimate_fill_minutes(100) == round(100 * plan_cards.SEC_PER_CARD / 60)


def test_summarize_fill_stufen_und_texte():
    ok = plan_cards.summarize_fill({"status": "ok", "cards_new": 12, "questions": 12, "answers": 11,
                                    "topics_done": 3, "topics_empty": 1})
    assert ok[0] == "success" and "12 neue Karten" in ok[1] and "3 Themen" in ok[1]
    assert "übersprungen" in ok[1]
    err = plan_cards.summarize_fill({"status": "vram", "error_msg": "Zu wenig freier Grafikspeicher"})
    assert err == ("error", "Zu wenig freier Grafikspeicher")
    assert plan_cards.summarize_fill({"status": "no_model", "error_msg": None})[0] == "error"
    assert plan_cards.summarize_fill({"status": "empty"})[0] == "info"


# --------------------------------------------------------------------------- #
# Referenz: das Dokument, aus dem das Thema entstanden ist
# --------------------------------------------------------------------------- #
def test_page_number_und_compress_pages():
    assert plan_cards.page_number("Seite 7") == 7
    assert plan_cards.page_number("  Folie 12 ") == 12
    assert plan_cards.page_number("Einleitung") is None
    assert plan_cards.compress_pages([3, 1, 2, 7, 8, 12]) == "S. 1–3, 7–8, 12"
    assert plan_cards.compress_pages([5]) == "S. 5"
    assert plan_cards.compress_pages([]) == ""


def test_section_reference_nennt_dokument_und_seiten():
    sec = _section("s", ("A", "Seite 11"), ("A", "Seite 12"), ("A", "Seite 14"))
    for ref in sec["source_refs"]:
        ref["filename"] = "1 Vektorrechnung.pdf"
    assert plan_cards.section_reference(sec) == "1 Vektorrechnung.pdf · S. 11–12, 14"
    assert plan_cards.section_docs(sec) == [("A", "1 Vektorrechnung.pdf")]
    # zusammengefasste Fundstellen werden aufgeloest
    sec2 = _section("s2", ("A", "Seite 3 … Seite 6"))
    sec2["source_refs"][0]["filename"] = "A.pdf"
    assert plan_cards.section_reference(sec2) == "A.pdf · S. 3–6"


def test_section_reference_ohne_seitenzahlen_zeigt_ueberschriften_und_mehrere_dokumente():
    sec = _section("s", ("A", "1.1 Einleitung"), ("A", "1.2 Ziele"), ("A", "1.3 Plan"),
                   ("B", "Seite 2"))
    sec["source_refs"][0]["filename"] = sec["source_refs"][1]["filename"] = \
        sec["source_refs"][2]["filename"] = "a.md"
    sec["source_refs"][3]["filename"] = "b.pdf"
    ref = plan_cards.section_reference(sec)
    assert ref == "a.md · 1.1 Einleitung, 1.2 Ziele … | b.pdf · S. 2"
    assert len(plan_cards.section_docs(sec)) == 2


def test_section_start_gibt_dokument_und_kleinste_seite():
    sec = _section("s", ("A", "Seite 12"), ("A", "Seite 11"), ("B", "Seite 1"))
    assert plan_cards.section_start(sec) == ("A", 11)
    assert plan_cards.section_start(_section("s", ("A", "Einleitung"))) == ("A", None)
    assert plan_cards.section_start(_section("s")) == (None, None)


# --------------------------------------------------------------------------- #
# Uebungsaufgaben nur zu GENAU diesem Thema, nur aus seinem Text
# --------------------------------------------------------------------------- #
def _problem(topic, doc, subject="LA", text="Aufgabe"):
    return manifest.create_practice_problem(
        subject=subject, doc_id=doc, topic=topic, problem_text=text, steps=["s"])


def test_section_problems_nur_gleiches_thema_und_passendes_dokument(db):
    mine = _problem("Skalarprodukt", "A")
    _problem("Skalarprodukt", "B")                  # gleicher Titel, anderes Dokument
    _problem("Matrizen", "A")                       # gleiches Dokument, anderes Thema
    ohne_doc = _problem("Skalarprodukt", None)      # ohne Dokumentangabe: zaehlt
    sec = {"section_id": "s", "title": "Skalarprodukt",
           "source_refs": [{"doc_id": "A", "filename": "A.pdf", "section": "Seite 1"}]}
    got = {p["problem_id"] for p in plan_cards.section_problems(sec, "LA")}
    assert got == {mine, ohne_doc}
    assert plan_cards.section_problems({"section_id": "x", "title": ""}, "LA") == []


def test_plan_unit_stats_zaehlt_uebungen_je_thema(db):
    _seed([_card("c1", "A", "Seite 1")])
    _problem("Vektoren", "A")
    _problem("Vektoren", "A")
    _problem("Matrizen", "B")
    s1 = _section("s1", ("A", "Seite 1"))
    s1["title"] = "Vektoren"
    s2 = _section("s2", ("B", "Seite 4"))
    s2["title"] = "Skalar"
    stats = plan_cards.plan_unit_stats({"doc_ids": ["A", "B"], "subject": "LA"}, [s1, s2])
    assert stats["s1"]["cards"] == 1 and stats["s1"]["problems"] == 2
    assert len(stats["s1"]["problem_ids"]) == 2
    assert stats["s2"]["problems"] == 0 and stats["s2"]["cards"] == 0


def test_section_source_sections_nimmt_nur_die_abschnitte_des_themas(fake_store):
    sec = _section("s", ("A", "Seite 2"))
    sec["source_refs"][0]["filename"] = "A.pdf"
    out = plan_cards.section_source_sections(sec)
    assert [(label, title) for label, title, _b in out] == [("A.pdf", "Seite 2")]
    assert all(body.strip() for _l, _t, body in out)


def test_create_section_practice_uebergibt_nur_den_text_des_themas(fake_store, db, monkeypatch):
    from ragapp import practice_gen
    seen = {}

    def fake_generate(**kw):
        seen.update(kw)
        return "pid-1"

    monkeypatch.setattr(practice_gen, "generate_practice_problem", fake_generate)
    sec = _section("s", ("A", "Seite 2"))
    sec["title"] = "Skalarprodukt"
    sec["source_refs"][0]["filename"] = "A.pdf"
    assert plan_cards.create_section_practice(sec, subject="LA", model="m") == "pid-1"
    assert seen["subject"] == "LA" and seen["doc_ids"] == ["A"] and seen["topic"] == "Skalarprodukt"
    assert seen["model"] == "m"
    assert [t for _l, t, _b in seen["source_sections"]] == ["Seite 2"]   # NUR das Thema


def test_create_section_practice_zweite_aufgabe_beginnt_an_anderer_stelle(db, monkeypatch):
    from ragapp import practice_gen
    sources = [("A.pdf", "Seite 1", "eins"), ("A.pdf", "Seite 2", "zwei"), ("A.pdf", "Seite 3", "drei")]
    monkeypatch.setattr(plan_cards, "section_source_sections", lambda sec: list(sources))
    seen = []
    monkeypatch.setattr(practice_gen, "generate_practice_problem",
                        lambda **kw: seen.append([t for _l, t, _b in kw["source_sections"]]) or "p")
    sec = {"section_id": "s", "title": "Thema X",
           "source_refs": [{"doc_id": "A", "filename": "A.pdf", "section": "Seite 1"}]}
    plan_cards.create_section_practice(sec, subject="LA")
    _problem("Thema X", "A")                          # die erste Aufgabe existiert jetzt
    plan_cards.create_section_practice(sec, subject="LA")
    assert seen[0][0] == "Seite 1" and seen[1][0] == "Seite 2"


def test_create_section_practice_ohne_text_wirft_verstaendlichen_fehler(db, monkeypatch):
    from ragapp import practice_gen
    monkeypatch.setattr(plan_cards, "section_source_sections", lambda sec: [])
    with pytest.raises(practice_gen.PracticeGenError, match="keine indexierten"):
        plan_cards.create_section_practice(_section("s", ("A", "Seite 9")), subject="LA")


# --------------------------------------------------------------------------- #
# Der Tag im Lernplan
# --------------------------------------------------------------------------- #
def test_sections_for_day_nur_themen_dieses_tages_ohne_doppelte():
    secs = [{"section_id": "a", "title": "A"}, {"section_id": "b", "title": "B"},
            {"section_id": "c", "title": "C"}]
    blocks = [{"section_id": "a", "planned_date": "2026-10-01"},
              {"section_id": "a", "planned_date": "2026-10-01"},
              {"section_id": "b", "planned_date": "2026-10-01"},
              {"section_id": "c", "planned_date": "2026-10-02"},
              {"section_id": "gibt-es-nicht", "planned_date": "2026-10-01"}]
    assert [s["section_id"] for s in plan_cards.sections_for_day(blocks, secs, "2026-10-01")] == ["a", "b"]
    assert [s["section_id"] for s in plan_cards.sections_for_day(blocks, secs, "2026-10-02")] == ["c"]
    assert plan_cards.sections_for_day(blocks, secs, "2026-10-09") == []


def test_next_study_day_erster_tag_ab_heute_mit_offenen_bloecken():
    blocks = [{"planned_date": "2026-09-30", "done": 0},       # Rueckstand zaehlt nicht
              {"planned_date": "2026-10-02", "done": 1},       # erledigt zaehlt nicht
              {"planned_date": "2026-10-03", "done": 0},
              {"planned_date": "2026-10-05", "done": 0}]
    assert plan_cards.next_study_day(blocks, "2026-10-01") == "2026-10-03"
    assert plan_cards.next_study_day(blocks, "2026-10-06") is None


def test_day_card_ids_nur_karten_der_tagesthemen(db):
    _seed([_card("v1", "A", "Seite 1"), _card("v2", "A", "Seite 1"),
           _card("m1", "B", "Seite 1")])                      # m1 gehoert zu einem spaeteren Thema
    vek = _section("vek", ("A", "Seite 1"))
    ids = plan_cards.day_card_ids([vek])
    assert sorted(ids) == ["v1", "v2"] and "m1" not in ids
    assert len(plan_cards.day_card_ids([vek], per_topic=1)) == 1
    assert plan_cards.day_card_ids([]) == []


# --------------------------------------------------------------------------- #
# Einheiten fuellen: Karten + Uebung
# --------------------------------------------------------------------------- #
def test_sections_needing_cards_mit_uebung_nimmt_auch_themen_ohne_aufgabe():
    secs = [_section("voll"), _section("ohne_uebung")]
    stats = {"voll": {"cards": 4, "unanswered": 0, "problems": 1},
             "ohne_uebung": {"cards": 4, "unanswered": 0, "problems": 0}}
    assert plan_cards.sections_needing_cards(stats, secs) == []
    assert [s["section_id"] for s in plan_cards.sections_needing_cards(
        stats, secs, with_practice=True)] == ["ohne_uebung"]


def test_fill_plan_cards_mit_uebung_erzeugt_nur_fehlende_und_scheitern_stoppt_nicht(no_llm_task, monkeypatch):
    _scripted(monkeypatch, {
        "s1": {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "cards_total": 2},
        "s2": {"status": "ok", "questions": 1, "cards_new": 1, "answers": 1, "cards_total": 1},
        "s3": {"status": "ok", "questions": 1, "cards_new": 1, "answers": 1, "cards_total": 1},
    })
    have = {"s2"}                                       # s2 hat schon eine Aufgabe
    monkeypatch.setattr(plan_cards, "section_problems",
                        lambda sec, subject=None: [{"problem_id": "x"}] if sec["section_id"] in have else [])
    made = []

    def fake_practice(sec, *, subject, model=None, kind=None):
        made.append((sec["section_id"], subject, model))
        if sec["section_id"] == "s3":
            raise RuntimeError("Modell antwortet nicht")
        return "pid"

    monkeypatch.setattr(plan_cards, "create_section_practice", fake_practice)
    notes = []
    out = plan_cards.fill_plan_cards([_section("s1"), _section("s2"), _section("s3")],
                                     with_practice=True, subject="LA", progress=notes.append)
    assert [m[0] for m in made] == ["s1", "s3"]         # s2 hatte schon eine
    assert all(m[1] == "LA" for m in made)
    assert out["status"] == "ok" and out["topics_done"] == 3          # Karten bleiben erhalten
    assert (out["problems_new"], out["problems_failed"]) == (1, 1)
    assert "Modell antwortet nicht" in out["practice_error"]
    assert any("Übungsaufgabe" in n for n in notes)
    level, text = plan_cards.summarize_fill(out)
    assert level == "success" and "1 Übungsaufgabe erzeugt" in text and "ließen sich nicht erzeugen" in text


def test_fill_plan_cards_ohne_uebung_ruft_den_generator_nie_auf(no_llm_task, monkeypatch):
    _scripted(monkeypatch, {"s1": {"status": "ok", "cards_total": 1}})
    monkeypatch.setattr(plan_cards, "create_section_practice",
                        lambda *a, **k: pytest.fail("darf nicht laufen"))
    out = plan_cards.fill_plan_cards([_section("s1")], with_practice=False, subject="LA")
    assert out["problems_new"] == 0


def test_estimate_fill_minutes_beruecksichtigt_uebungen():
    assert plan_cards.estimate_fill_minutes(0, 0) == 1
    assert plan_cards.estimate_fill_minutes(
        10, 6) == round((10 * plan_cards.SEC_PER_CARD + 6 * plan_cards.SEC_PER_PROBLEM) / 60)


# --------------------------------------------------------------------------- #
# Lernstand und Wiederholen
# --------------------------------------------------------------------------- #
def test_learning_line_varianten():
    assert plan_cards.learning_line({"cards": 0}) == ""
    assert plan_cards.learning_line({"cards": 4, "reviewed": 0, "new": 4}) == "🆕 noch nicht gelernt"
    st = {"cards": 3, "reviewed": 2, "known": 1, "due": 1, "new": 1}
    assert plan_cards.learning_line(st) == "🧠 1 von 3 sitzen · 1 fällig · 1 neu"
    assert plan_cards.learning_line({"cards": 2, "reviewed": 2, "known": 2, "due": 0, "new": 0}) \
        == "🧠 2 von 2 sitzen"


def test_learning_bar_html_zeigt_nur_vorhandene_anteile():
    assert plan_cards.learning_bar_html({"cards": 0}) == ""
    html = plan_cards.learning_bar_html({"cards": 5, "known": 3, "due": 0, "new": 2})
    assert "splan-statebar" in html and "3 sitzen" in html and "2 neu" in html
    assert "fällig" not in html


def test_review_card_ids_nur_faellige_aelteste_zuerst_nie_neue(db):
    now = time.time()
    _seed([_card("neu", "A", "Seite 1"), _card("spaet", "A", "Seite 1"),
           _card("alt", "A", "Seite 1"), _card("neuer", "A", "Seite 1")])
    _set_progress("spaet", 2, now + 86400)        # nicht faellig
    _set_progress("alt", 3, now - 5000)
    _set_progress("neuer", 1, now - 100)
    sec = _section("s", ("A", "Seite 1"))
    assert plan_cards.review_card_ids(sec) == ["alt", "neuer"]
    assert plan_cards.review_card_ids(sec, limit=1) == ["alt"]
    assert plan_cards.review_card_ids(_section("leer", ("A", "Seite 7"))) == []


def _blk(sid, day, done=False):
    return {"section_id": sid, "planned_date": day, "planned_min": 25, "done": done}


def test_started_sections_nimmt_nur_bisherige_und_angefangene_themen():
    sections = [{"section_id": "geuebt"}, {"section_id": "frueher"}, {"section_id": "heute"},
                {"section_id": "spaeter"}, {"section_id": "erledigt", "done": True},
                {"section_id": "ohne_block"}]
    blocks = [_blk("frueher", "2026-10-01"), _blk("heute", "2026-10-05"),
              _blk("spaeter", "2026-10-09"), _blk("geuebt", "2026-10-20")]
    stats = {"geuebt": {"reviewed": 2}}
    got = plan_cards.started_sections(blocks, sections, stats, "2026-10-05")
    assert [s["section_id"] for s in got] == ["geuebt", "frueher", "heute", "erledigt"]


def test_started_sections_ein_zukuenftiges_thema_ohne_geuebte_karten_bleibt_aussen():
    sections = [{"section_id": "matrizen"}]
    assert plan_cards.started_sections([_blk("matrizen", "2026-10-09")], sections, {}, "2026-10-05") == []


def test_review_card_ids_for_ueberspringt_themen_ohne_faellige_und_deckelt(db):
    now = time.time()
    cards = [_card(f"a{i}", "A", "Seite 1") for i in range(5)] + [_card("b0", "A", "Seite 2")]
    _seed(cards)
    for c in cards[:5]:
        _set_progress(c["card_id"], 2, now - 100 - int(c["card_id"][1:]))
    s1, s2 = _section("s1", ("A", "Seite 1")), _section("s2", ("A", "Seite 2"))
    stats = {"s1": {"due": 5}, "s2": {"due": 0}}
    ids = plan_cards.review_card_ids_for([s1, s2], stats, per_topic=3, total=30)
    assert len(ids) == 3 and "b0" not in ids
    assert len(plan_cards.review_card_ids_for([s1], stats, per_topic=10, total=2)) == 2


# --------------------------------------------------------------------------- #
# Termine je Thema
# --------------------------------------------------------------------------- #
def test_fmt_day_und_day_phrase():
    assert plan_cards.fmt_day("2026-10-08") == "Do 08.10."
    assert plan_cards.fmt_day("2026-10-05") == "Mo 05.10."
    assert plan_cards.fmt_day("kaputt") == "" and plan_cards.fmt_day(None) == ""
    today = "2026-10-05"
    assert plan_cards.day_phrase("2026-10-05", today) == "heute"
    assert plan_cards.day_phrase("2026-10-06", today) == "morgen"
    assert plan_cards.day_phrase("2026-10-04", today) == "gestern"
    assert plan_cards.day_phrase("2026-10-08", today) == "in 3 Tagen"
    assert plan_cards.day_phrase("2026-10-02", today) == "vor 3 Tagen"
    assert plan_cards.day_phrase("kaputt", today) == ""


def test_section_schedule_fasst_bloecke_je_thema_zusammen():
    blocks = [_blk("a", "2026-10-05", done=True), _blk("a", "2026-10-07"), _blk("a", "2026-10-09"),
              _blk("b", "2026-10-06"), {"section_id": None, "planned_date": "2026-10-06"}]
    sched = plan_cards.section_schedule(blocks)
    assert set(sched) == {"a", "b"}
    a = sched["a"]
    assert (a["total"], a["done"], a["first"], a["last"]) == (3, 1, "2026-10-05", "2026-10-09")
    assert (a["open_first"], a["open_last"]) == ("2026-10-07", "2026-10-09")


def test_schedule_label_alle_faelle():
    today = "2026-10-05"
    label = lambda blocks, sid="a": plan_cards.schedule_label(  # noqa: E731
        plan_cards.section_schedule(blocks).get(sid), today)
    assert label([]) == ("none", "🗓️ noch nicht eingeplant")
    assert label([_blk("a", "2026-10-03", True)]) == ("done", "✅ erledigt")
    kind, text = label([_blk("a", "2026-10-03")])
    assert kind == "overdue" and "Sa 03.10." in text
    assert label([_blk("a", "2026-10-05")]) == ("today", "📅 heute")
    kind, text = label([_blk("a", "2026-10-05"), _blk("a", "2026-10-07")])
    assert kind == "today" and "bis Mi 07.10." in text
    kind, text = label([_blk("a", "2026-10-08")])
    assert kind == "later" and "kommt später" in text and "Do 08.10." in text and "in 3 Tagen" in text
    # Erledigte Bloecke zaehlen nicht: ein spaeterer offener Block bestimmt das Label.
    kind, _ = label([_blk("a", "2026-10-04", True), _blk("a", "2026-10-09")])
    assert kind == "later"


# --------------------------------------------------------------------------- #
# Kartenqualitaet pruefen und beheben
# --------------------------------------------------------------------------- #
def _flawed_card(cid, doc, topic, front, answer="Eine brauchbare Antwort mit Inhalt."):
    c = _card(cid, doc, topic, answer=answer)
    c["front"] = front
    return c


def _mark_edited(cid):
    with manifest._connect() as conn:
        conn.execute("UPDATE review_items SET edited=1 WHERE card_id=?", (cid,))


def test_plan_card_stats_zaehlt_maengel_je_thema(db):
    _seed([_flawed_card("gut", "A", "Seite 1", "Was ist ein Vektorraum?"),
           _flawed_card("quelle", "A", "Seite 1", "Wie lautet die Definition von OD im Abschnitt?"),
           _flawed_card("ok2", "A", "Seite 2", "Wie berechnet man das Skalarprodukt?")])
    stats = plan_cards.plan_card_stats(
        {"doc_ids": ["A"]}, [_section("s1", ("A", "Seite 1")), _section("s2", ("A", "Seite 2"))])
    assert stats["s1"]["flawed"] == 1 and stats["s1"]["flawed_ids"] == ["quelle"]
    assert stats["s2"]["flawed"] == 0


def test_plan_audit_ordnet_maengel_den_themen_zu_und_findet_dubletten_themenuebergreifend(db):
    _seed([_flawed_card("quelle", "A", "Seite 1", "Was zeigt Abbildung 2?"),
           _flawed_card("d1", "A", "Seite 1", "Wie lang ist ein Vektor?"),
           _flawed_card("d2", "A", "Seite 2", "Wie berechnet man die Länge eines Vektors?"),
           _flawed_card("andere", "A", "Seite 2", "Was ist eine Matrix?")])
    secs = [_section("s1", ("A", "Seite 1")), _section("s2", ("A", "Seite 2"))]
    vec = {"Was zeigt Abbildung 2?": [0, 0, 1], "Wie lang ist ein Vektor?": [1, 0, 0],
           "Wie berechnet man die Länge eines Vektors?": [0.99, 0.05, 0], "Was ist eine Matrix?": [0, 1, 0]}
    audit = plan_cards.plan_audit({"doc_ids": ["A"]}, secs, embed=lambda texts: [vec[t] for t in texts])
    assert set(audit) == {"quelle", "d2"}
    assert audit["quelle"]["section_id"] == "s1" and audit["quelle"]["question"] == ["quellenbezug"]
    assert audit["d2"]["section_id"] == "s2" and audit["d2"]["question"] == ["duplikat"]
    # Ohne Embedder: nur die regelbasierten Maengel.
    assert set(plan_cards.plan_audit({"doc_ids": ["A"]}, secs)) == {"quelle"}


def test_split_repairs_schuetzt_gelernte_und_bearbeitete_karten(db):
    _seed([_flawed_card("frage_neu", "A", "S1", "Was zeigt Abbildung 2?"),
           _flawed_card("frage_gelernt", "A", "S1", "Was zeigt Abbildung 3?"),
           _flawed_card("frage_bearbeitet", "A", "S1", "Was zeigt Abbildung 4?"),
           _flawed_card("antwort", "A", "S1", "Wie lang ist ein Vektor?", answer="Siehe Definition 8."),
           _flawed_card("antwort_bearbeitet", "A", "S1", "Wie breit ist ein Vektor?", answer="Siehe Definition 9."),
           _flawed_card("fremd", "A", "S1", "Was zeigt Abbildung 5?")])
    _set_progress("frage_gelernt", 3, time.time() + 1000)
    _mark_edited("frage_bearbeitet")
    _mark_edited("antwort_bearbeitet")
    cards = manifest.find_cards(doc_ids=["A"])
    audit = {c["card_id"]: {"question": ["quellenbezug"] if "Abbildung" in c["front"] else [],
                            "answer": ["quellenbezug"] if "Definition" in (c["answer"] or "") else []}
             for c in cards}
    plan = plan_cards.split_repairs(cards, audit)
    assert sorted(plan["replace"]) == ["frage_neu", "fremd"]
    assert plan["answers"] == ["antwort"]
    assert sorted(plan["protected"]) == ["antwort_bearbeitet", "frage_bearbeitet", "frage_gelernt"]


def test_split_repairs_ignoriert_karten_anderer_quellen(db):
    c = _flawed_card("klausur", "A", "S1", "Was zeigt Abbildung 2?")
    c["source"] = "exam_qa"
    _seed([c])
    cards = manifest.find_cards(doc_ids=["A"])
    plan = plan_cards.split_repairs(cards, {"klausur": {"question": ["quellenbezug"], "answer": []}})
    assert plan == {"replace": [], "answers": [], "protected": []}


class _IndexStore:
    def __init__(self):
        self.deleted: list[str] = []

    def delete_by_ids(self, ids):
        self.deleted += list(ids)


def test_repair_cards_loescht_unberuehrte_karten_samt_frage_im_index_und_laesst_gelernte_in_ruhe(db, monkeypatch):
    store = _IndexStore()
    monkeypatch.setattr("ragapp.retrieval.vectorstore.get_vectorstore", lambda: store)
    _seed([_flawed_card("weg", "A", "S1", "Was zeigt Abbildung 2?"),
           _flawed_card("gelernt", "A", "S1", "Was zeigt Abbildung 3?"),
           _flawed_card("gut", "A", "S1", "Was ist ein Vektorraum?")])
    _set_progress("gelernt", 2, time.time() + 1000)
    cards = manifest.find_cards(doc_ids=["A"])
    audit = {"weg": {"question": ["quellenbezug"], "answer": []},
             "gelernt": {"question": ["quellenbezug"], "answer": []}}
    out = plan_cards.repair_cards(cards, audit)
    assert out["deleted"] == 1 and out["protected"] == 1 and out["protected_ids"] == ["gelernt"]
    assert store.deleted == ["weg"]
    left = {c["card_id"] for c in manifest.find_cards(doc_ids=["A"])}
    assert left == {"gelernt", "gut"}


def test_repair_cards_erzeugt_antworten_neu_und_stellt_die_alte_wieder_her_wenn_es_scheitert(db, monkeypatch):
    _seed([_flawed_card("klappt", "A", "S1", "Wie lang ist ein Vektor?", answer="Siehe Definition 8."),
           _flawed_card("scheitert", "A", "S1", "Wie breit ist ein Vektor?", answer="Siehe Definition 9.")])
    seen = {}

    def fake_generate(**kw):
        seen["ids"] = sorted(kw["card_ids"])
        # Waehrend der Erzeugung sind die alten Antworten geleert (sonst wuerde nichts neu erzeugt).
        assert all(not (c["answer"] or "").strip() for c in manifest.get_cards_by_ids(kw["card_ids"]))
        manifest.set_answer("klappt", "Die Länge ist die Wurzel aus der Summe der Quadrate.")
        return {"status": "ok", "filled": 1}

    monkeypatch.setattr(study, "generate_answers", fake_generate)
    cards = manifest.find_cards(doc_ids=["A"])
    audit = {"klappt": {"question": [], "answer": ["quellenbezug"]},
             "scheitert": {"question": [], "answer": ["quellenbezug"]}}
    out = plan_cards.repair_cards(cards, audit)
    by_id = {c["card_id"]: c for c in manifest.get_cards_by_ids(["klappt", "scheitert"])}
    assert seen["ids"] == ["klappt", "scheitert"]
    assert "Wurzel" in by_id["klappt"]["answer"]
    assert by_id["scheitert"]["answer"] == "Siehe Definition 9."       # alte Antwort zurueck
    assert out["answers_new"] == 1 and out["answers_kept_old"] == 1 and out["status"] == "ok"


def test_repair_cards_meldet_vram_und_behaelt_alle_alten_antworten(db, monkeypatch):
    _seed([_flawed_card("a", "A", "S1", "Wie lang ist ein Vektor?", answer="Siehe Definition 8.")])
    monkeypatch.setattr(study, "generate_answers", lambda **kw: {
        "status": "llm_error", "error_msg": "Zu wenig freier Grafikspeicher (VRAM)."})
    out = plan_cards.repair_cards(manifest.find_cards(doc_ids=["A"]),
                                  {"a": {"question": [], "answer": ["quellenbezug"]}})
    assert out["status"] == "vram" and out["answers_kept_old"] == 1
    assert manifest.get_cards_by_ids(["a"])[0]["answer"] == "Siehe Definition 8."


def test_repair_cards_ohne_befund_tut_nichts(db):
    assert plan_cards.repair_cards([], {})["deleted"] == 0


def test_summarize_repair_nennt_nur_was_passiert_ist():
    assert plan_cards.summarize_repair({}) == ""
    text = plan_cards.summarize_repair({"deleted": 2, "answers_new": 1, "answers_kept_old": 1, "protected": 3})
    assert "2 fehlerhafte Karte(n) entfernt" in text and "1 Antwort(en) neu formuliert" in text
    assert "blieben unverändert" in text and "3 auffällige Karte(n) bleiben" in text


# --------------------------------------------------------------------------- #
# Abbrechen / Fortschritt / Zusammenfassung
# --------------------------------------------------------------------------- #
def test_fill_plan_cards_bricht_vor_dem_naechsten_thema_ab_und_meldet_schritte(no_llm_task, monkeypatch):
    calls = _scripted(monkeypatch, {
        "s1": {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "cards_total": 2},
        "s2": {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "cards_total": 2},
        "s3": {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "cards_total": 2},
    })
    steps = []

    out = plan_cards.fill_plan_cards([_section("s1"), _section("s2"), _section("s3")],
                                     should_cancel=lambda: len(calls) >= 1,       # nach dem ersten Thema
                                     on_step=lambda d, n: steps.append((d, n)))
    assert calls == ["s1"] and out["status"] == "cancelled" and out["topics_done"] == 1
    assert steps[0] == (0, 3)


def test_fill_plan_cards_bricht_mitten_im_thema_ab_und_behaelt_dessen_zwischenstand(no_llm_task, monkeypatch):
    calls = _scripted(monkeypatch, {
        "s1": {"status": "cancelled", "questions": 1, "cards_new": 1, "answers": 0, "cards_total": 1},
        "s2": {"status": "ok", "cards_total": 1},
    })
    out = plan_cards.fill_plan_cards([_section("s1"), _section("s2")])
    assert calls == ["s1"]
    assert out["status"] == "cancelled" and out["cards_new"] == 1 and out["topics_done"] == 1


def test_fill_plan_cards_reicht_should_cancel_an_die_kartenerzeugung_weiter(no_llm_task, monkeypatch):
    seen = {}

    def fake(section, **kw):
        seen["cancel"] = kw.get("should_cancel")
        return {"status": "ok", "cards_total": 1}

    monkeypatch.setattr(plan_cards, "create_section_cards", fake)
    stop = lambda: False  # noqa: E731
    plan_cards.fill_plan_cards([_section("s1")], should_cancel=stop)
    assert seen["cancel"] is stop


def test_fill_plan_cards_summiert_qualitaetszaehler(no_llm_task, monkeypatch):
    _scripted(monkeypatch, {
        "s1": {"status": "ok", "questions": 2, "cards_new": 2, "answers": 2, "cards_total": 2,
               "rejected": 3, "duplicates": 1},
        "s2": {"status": "ok", "questions": 1, "cards_new": 1, "answers": 1, "cards_total": 1,
               "rejected": 1, "duplicates": 0},
    })
    out = plan_cards.fill_plan_cards([_section("s1"), _section("s2")])
    assert out["rejected"] == 4 and out["duplicates"] == 1


def test_summarize_fill_abgebrochen_qualitaet_und_reparatur():
    lvl, text = plan_cards.summarize_fill({"status": "cancelled", "cards_new": 3, "questions": 3,
                                           "answers": 2, "topics_done": 1})
    assert lvl == "info" and "Abgebrochen" in text and "3 neue Karten" in text
    assert "macht dort weiter" in text
    lvl, text = plan_cards.summarize_fill({"status": "ok", "cards_new": 1, "questions": 1, "answers": 1,
                                           "topics_done": 1, "rejected": 2, "duplicates": 1,
                                           "repair": {"deleted": 1}})
    assert lvl == "success" and "2 Frage(n) mit Mängeln aussortiert" in text and "1 doppelte" in text
    assert "1 fehlerhafte Karte(n) entfernt" in text


def test_repair_and_fill_prueft_repariert_und_fuellt_nur_themen_mit_luecken(db, no_llm_task, monkeypatch):
    store = _IndexStore()
    monkeypatch.setattr("ragapp.retrieval.vectorstore.get_vectorstore", lambda: store)
    _seed([_flawed_card("weg", "A", "Seite 1", "Was zeigt Abbildung 2?"),
           _flawed_card("ok", "A", "Seite 2", "Was ist eine Matrix?")])
    s1, s2 = _section("s1", ("A", "Seite 1")), _section("s2", ("A", "Seite 2"))
    filled = {}

    def fake_fill(secs, **kw):
        filled["ids"] = [s["section_id"] for s in secs]
        return {"status": "ok", "topics": len(secs), "topics_done": len(secs), "topics_empty": 0,
                "questions": 1, "cards_new": 1, "answers": 1, "rejected": 0, "duplicates": 0,
                "problems_new": 0, "problems_failed": 0, "error_msg": None}

    monkeypatch.setattr(plan_cards, "fill_plan_cards", fake_fill)
    out = plan_cards.repair_and_fill({"doc_ids": ["A"], "subject": "LA"}, [s1, s2], subject="LA")
    assert filled["ids"] == ["s1"]                       # s1 hat nach dem Loeschen eine Luecke, s2 nicht
    assert out["repair"]["deleted"] == 1 and out["cards_new"] == 1


def test_repair_and_fill_ohne_luecken_meldet_ok_mit_reparaturbericht(db, no_llm_task, monkeypatch):
    _seed([_flawed_card("ok", "A", "Seite 1", "Was ist eine Matrix?")])
    monkeypatch.setattr(plan_cards, "fill_plan_cards",
                        lambda secs, **kw: pytest.fail("nichts zu fuellen") if secs else
                        {"status": "empty", "topics": 0, "topics_done": 0, "topics_empty": 0, "questions": 0,
                         "cards_new": 0, "answers": 0, "rejected": 0, "duplicates": 0,
                         "problems_new": 0, "problems_failed": 0, "error_msg": None})
    out = plan_cards.repair_and_fill({"doc_ids": ["A"], "subject": "LA"}, [_section("s1", ("A", "Seite 1"))],
                                     subject="LA")
    assert out["status"] == "ok" and out["repair"]["deleted"] == 0


def test_repair_and_fill_bricht_bei_vram_ab_ohne_zu_fuellen(db, no_llm_task, monkeypatch):
    _seed([_flawed_card("a", "A", "Seite 1", "Wie lang ist ein Vektor?", answer="Siehe Definition 8.")])
    monkeypatch.setattr(study, "generate_answers", lambda **kw: {
        "status": "llm_error", "error_msg": "Zu wenig freier Grafikspeicher (VRAM)."})
    monkeypatch.setattr(plan_cards, "section_problems", lambda *a, **k: [])
    real_fill = plan_cards.fill_plan_cards
    monkeypatch.setattr(plan_cards, "fill_plan_cards",
                        lambda secs, **kw: pytest.fail("nach VRAM-Fehler nicht weiterfuellen") if secs
                        else real_fill(secs, **kw))
    out = plan_cards.repair_and_fill({"doc_ids": ["A"], "subject": "LA"}, [_section("s1", ("A", "Seite 1"))],
                                     subject="LA")
    assert out["status"] == "vram" and out["repair"]["answers_kept_old"] == 1


# --------------------------------------------------------------------------- #
# Hintergrundauftrag
# --------------------------------------------------------------------------- #
def _wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_start_fill_job_laeuft_im_hintergrund_meldet_fortschritt_und_ergebnis(monkeypatch):
    import threading
    from ragapp import jobs
    jobs.reset_for_tests()
    gate = threading.Event()
    seen = {}

    def fake_fill(secs, **kw):
        seen["titles"] = [s["title"] for s in secs]
        seen["subject"], seen["practice"] = kw["subject"], kw["with_practice"]
        kw["progress"]("Thema 1/2 · A – Fragen …")
        kw["on_step"](1, 2)
        gate.wait(5)
        return {"status": "ok", "topics_done": 2, "cards_new": 4, "questions": 4, "answers": 4}

    monkeypatch.setattr(plan_cards, "fill_plan_cards", fake_fill)
    sections = [_section("s1"), _section("s2")]
    plan = {"plan_id": "p1", "subject": "LA"}
    try:
        job, started = plan_cards.start_fill_job(plan, sections, with_practice=True, title="Füllen")
        assert started
        assert _wait(lambda: jobs.get(plan_cards.job_key("p1")).step == 1)
        snap = jobs.get(plan_cards.job_key("p1"))
        assert snap.total == 2 and snap.message.startswith("Thema 1/2")
        # Zweiter Start unter demselben Plan: kein zweiter Lauf.
        _, again = plan_cards.start_fill_job(plan, sections, with_practice=True, title="Füllen")
        assert again is False
        gate.set()
        assert _wait(lambda: jobs.get(plan_cards.job_key("p1")).status != jobs.RUNNING)
        done = jobs.get(plan_cards.job_key("p1"))
        assert done.status == jobs.DONE and done.result["cards_new"] == 4
        assert seen == {"titles": ["Thema s1", "Thema s2"], "subject": "LA", "practice": True}
        assert plan_cards.summarize_job(done)[0] == "success"
    finally:
        gate.set()
        jobs.reset_for_tests()


def test_start_fill_job_abbrechen_wird_an_fill_plan_cards_weitergereicht(monkeypatch):
    import threading
    from ragapp import jobs
    jobs.reset_for_tests()
    started = threading.Event()

    def fake_fill(secs, **kw):
        started.set()
        for _ in range(2000):
            if kw["should_cancel"]():
                return {"status": "cancelled", "topics_done": 1, "cards_new": 2, "questions": 2, "answers": 2}
            time.sleep(0.002)
        return {"status": "ok"}

    monkeypatch.setattr(plan_cards, "fill_plan_cards", fake_fill)
    try:
        plan_cards.start_fill_job({"plan_id": "p2", "subject": "LA"}, [_section("s1")],
                                  with_practice=False, title="x")
        assert started.wait(5)
        assert jobs.cancel(plan_cards.job_key("p2"))
        assert _wait(lambda: jobs.get(plan_cards.job_key("p2")).status != jobs.RUNNING)
        job = jobs.get(plan_cards.job_key("p2"))
        assert job.status == jobs.CANCELLED
        level, text = plan_cards.summarize_job(job)
        assert level == "info" and "Abgebrochen" in text and "2 neue Karten" in text
    finally:
        jobs.reset_for_tests()


def test_start_fill_job_mit_reparatur_nutzt_repair_and_fill(monkeypatch):
    from ragapp import jobs
    jobs.reset_for_tests()
    got = {}

    def fake_repair(plan, secs, **kw):
        got["embed"] = kw.get("embed")
        got["ids"] = [s["section_id"] for s in secs]
        return {"status": "ok", "topics_done": 0, "cards_new": 0, "questions": 0, "answers": 0,
                "repair": {"deleted": 2}}

    monkeypatch.setattr(plan_cards, "repair_and_fill", fake_repair)
    monkeypatch.setattr("ragapp.retrieval.embeddings.get_embedder",
                        lambda: type("E", (), {"embed_texts": staticmethod(lambda t: [[1.0]] * len(t))})())
    try:
        plan_cards.start_fill_job({"plan_id": "p3", "subject": "LA"}, [_section("s1")],
                                  with_practice=False, title="x", repair=True)
        assert _wait(lambda: jobs.get(plan_cards.job_key("p3")).status != jobs.RUNNING)
        assert got["ids"] == ["s1"] and callable(got["embed"])
        assert "2 fehlerhafte" in plan_cards.summarize_job(jobs.get(plan_cards.job_key("p3")))[1]
    finally:
        jobs.reset_for_tests()


def test_summarize_job_fehler_und_abbruch_ohne_ergebnis():
    from ragapp import jobs
    err = jobs.Job(key="k", title="t", status=jobs.ERROR, error="Ollama nicht erreichbar")
    assert plan_cards.summarize_job(err) == (
        "error", "Der Lauf ist mit einem Fehler beendet worden: Ollama nicht erreichbar")
    cancelled = jobs.Job(key="k", title="t", status=jobs.CANCELLED)
    level, text = plan_cards.summarize_job(cancelled)
    assert level == "info" and "Abgebrochen" in text


# --------------------------------------------------------------------------- #
# Schrittleiste
# --------------------------------------------------------------------------- #
def _sec(sid, *docs, est=60):
    return {"section_id": sid, "title": f"T{sid}", "est_minutes": est,
            "source_refs": [{"doc_id": d, "filename": f"{d}.pdf", "section": "Seite 1"} for d in docs]}


FULL = {"cards": 5, "unanswered": 0, "problems": 1}
EMPTY = {"cards": 0, "unanswered": 0, "problems": 0}
TODAY = "2026-10-05"


def _states(steps):
    return [s["state"] for s in steps]


def _next(steps):
    return [s["n"] for s in steps if s["next"]]


def test_plan_steps_ohne_themen_beginnt_bei_der_gliederung():
    steps = plan_cards.plan_steps([], {}, {"state": "empty"}, [], TODAY)
    assert _states(steps) == ["todo"] * 4 and _next(steps) == [1]
    assert steps[0]["sub"] == "noch keine Themen"


def test_plan_steps_gemischte_dokumente_warnen_schon_in_schritt_eins():
    secs = [_sec("a", "A"), _sec("b", "A", "B")]
    steps = plan_cards.plan_steps(secs, {"a": FULL, "b": FULL}, {"state": "missing"}, [], TODAY)
    assert steps[0]["state"] == "warn" and "1 aus mehreren Dokumenten" in steps[0]["sub"]
    assert _next(steps) == [1]


def test_plan_steps_einheiten_offen_dann_ist_schritt_zwei_dran():
    secs = [_sec("a", "A"), _sec("b", "A")]
    steps = plan_cards.plan_steps(secs, {"a": FULL, "b": EMPTY}, {"state": "missing"}, [], TODAY)
    assert steps[0]["state"] == "done" and steps[1]["state"] == "todo"
    assert steps[1]["sub"] == "1 von 2 Themen komplett · 5 Karten" and _next(steps) == [2]


def test_plan_steps_veralteter_zeitplan_ist_eine_warnung_und_der_naechste_schritt():
    secs = [_sec("a", "A")]
    blocks = [{"section_id": "a", "planned_date": "2026-10-06", "planned_min": 25, "done": False}]
    steps = plan_cards.plan_steps(secs, {"a": FULL}, {"state": "stale"}, blocks, TODAY)
    assert _states(steps)[:3] == ["done", "done", "warn"] and _next(steps) == [3]
    assert "veraltet" in steps[2]["sub"]


def test_plan_steps_alles_bereit_dann_ist_lernen_dran_heute():
    secs = [_sec("a", "A"), _sec("b", "A")]
    blocks = [{"section_id": "a", "planned_date": TODAY, "planned_min": 25, "done": False},
              {"section_id": "a", "planned_date": TODAY, "planned_min": 25, "done": False},
              {"section_id": "b", "planned_date": "2026-10-09", "planned_min": 25, "done": False}]
    steps = plan_cards.plan_steps(secs, {"a": FULL, "b": FULL}, {"state": "ok"}, blocks, TODAY)
    assert _states(steps) == ["done", "done", "done", "todo"] and _next(steps) == [4]
    assert steps[2]["sub"] == "3 offene Blöcke · bis Fr 09.10."
    assert steps[3]["sub"] == "heute: 1 Thema/Themen · 50 Min"


def test_plan_steps_naechster_lerntag_und_ueberfaellig_und_fertig():
    secs = [_sec("a", "A")]
    st, ok = {"a": FULL}, {"state": "ok"}
    later = [{"section_id": "a", "planned_date": "2026-10-08", "planned_min": 25, "done": False}]
    assert plan_cards.plan_steps(secs, st, ok, later, TODAY)[3]["sub"] == "nächster Lerntag: Do 08.10."
    over = [{"section_id": "a", "planned_date": "2026-10-01", "planned_min": 25, "done": False}]
    assert plan_cards.plan_steps(secs, st, ok, over, TODAY)[3]["sub"] == "offen seit Do 01.10."
    done = [{"section_id": "a", "planned_date": "2026-10-01", "planned_min": 25, "done": True}]
    steps = plan_cards.plan_steps(secs, st, ok, done, TODAY)
    assert steps[3]["state"] == "done" and "erledigt" in steps[3]["sub"] and steps[2]["sub"] == "aktuell"
    assert _next(steps) == []                                  # alles erledigt: kein naechster Schritt


def test_plan_steps_genau_ein_naechster_schritt():
    secs = [_sec("a", "A")]
    for stats, stale in (({"a": EMPTY}, {"state": "missing"}), ({"a": FULL}, {"state": "stale"})):
        assert len(_next(plan_cards.plan_steps(secs, stats, stale, [], TODAY))) == 1


def test_repair_and_fill_fuellt_keine_themen_auf_die_nur_leer_sind_und_keine_uebungen(db, no_llm_task, monkeypatch):
    """Ein Klick auf "Maengel beheben" schliesst nur die selbst gerissenen Luecken. Ein Thema, das
    nie Karten hatte (s2), ist Sache von "Alle Themen fuellen" - nicht dieses Laufs."""
    store = _IndexStore()
    monkeypatch.setattr("ragapp.retrieval.vectorstore.get_vectorstore", lambda: store)
    _seed([_flawed_card("weg", "A", "Seite 1", "Was zeigt Abbildung 2?")])
    s1, s2 = _section("s1", ("A", "Seite 1")), _section("s2", ("A", "Seite 2"))     # s2: keine Karten
    filled = {}

    def fake_fill(secs, **kw):
        filled["ids"] = [s["section_id"] for s in secs]
        filled["practice"] = kw.get("with_practice")
        return {"status": "ok", "topics": len(secs), "topics_done": len(secs), "topics_empty": 0,
                "questions": 0, "cards_new": 0, "answers": 0, "rejected": 0, "duplicates": 0,
                "problems_new": 0, "problems_failed": 0, "error_msg": None}

    monkeypatch.setattr(plan_cards, "fill_plan_cards", fake_fill)
    out = plan_cards.repair_and_fill({"doc_ids": ["A"], "subject": "LA"}, [s1, s2], subject="LA")
    assert filled == {"ids": ["s1"], "practice": False}
    assert out["repair"]["replaced_ids"] == ["weg"]


def test_summarize_fill_beachtet_einzahl_und_mehrzahl():
    _, one = plan_cards.summarize_fill({"status": "ok", "cards_new": 1, "questions": 1, "answers": 1,
                                        "topics_done": 1, "problems_new": 1})
    assert "1 neue Karte (1 Frage, 1 Antwort) in 1 Thema." in one and "1 Übungsaufgabe erzeugt" in one
    _, many = plan_cards.summarize_fill({"status": "ok", "cards_new": 2, "questions": 3, "answers": 0,
                                         "topics_done": 5, "problems_new": 2})
    assert "2 neue Karten (3 Fragen, 0 Antworten) in 5 Themen." in many and "2 Übungsaufgaben erzeugt" in many
