"""``enrich_questions``: Dubletten-Filter, Qualitäts-Statistik und Abbrechen - mit Attrappen für
Vektorspeicher, Embedder und Fragen-Erzeugung (kein Ollama, kein Chroma).

Wichtig: ``mark_needs_card_harvest`` würde ``data/config.json`` schreiben - hier immer gepatcht."""
from __future__ import annotations

import pytest

from ragapp.ingestion import enrich


class FakeCol:
    def __init__(self, questions=()):
        self.questions = list(questions)       # [{"id", "meta", "emb"}]

    def get(self, where=None, include=None):
        rows = self.questions
        if where and "$and" in where:
            doc = next(c["doc_id"] for c in where["$and"] if "doc_id" in c)
            rows = [r for r in rows if r["meta"].get("doc_id") == doc]
        out = {"ids": [r["id"] for r in rows], "metadatas": [r["meta"] for r in rows]}
        if include and "embeddings" in include:
            out["embeddings"] = [r["emb"] for r in rows]
        return out


class FakeStore:
    def __init__(self, chunks, questions=()):
        self._chunks = chunks
        self._col = FakeCol(questions)
        self.added: list[dict] = []

    def get_all_chunks(self):
        return self._chunks

    def get_by_ids(self, ids):
        return {c["id"]: c for c in self._chunks if c["id"] in ids}

    def add(self, ids, embeddings, documents, metadatas):
        for i, d, m in zip(ids, documents, metadatas):
            self.added.append({"id": i, "question": d, "meta": m})


class FakeEmbedder:
    def __init__(self, table):
        self.table = table

    def embed_texts(self, texts):
        return [self.table[t] for t in texts]


def chunk(cid, location, n_chars, doc="d1"):
    return {"id": cid, "document": ("Stoff " * n_chars)[:n_chars],
            "meta": {"doc_id": doc, "filename": "a.pdf", "location": location, "subject": "LA"}}


@pytest.fixture()
def env(monkeypatch):
    """Baut die Attrappen ein; Rueckgabe: Funktion zum Konfigurieren + Aufzeichnungen."""
    calls = {"answers": [], "questions": [], "progress": []}

    def setup(chunks, *, questions_by_chunk, vectors, existing=(), stats_by_chunk=None):
        store = FakeStore(chunks, existing)
        monkeypatch.setattr(enrich, "get_vectorstore", lambda: store)
        monkeypatch.setattr(enrich, "get_embedder", lambda: FakeEmbedder(vectors))
        monkeypatch.setattr(enrich, "require_vram", lambda model=None: {})
        monkeypatch.setattr(enrich, "probe_model", lambda model=None: (True, "ok"))
        monkeypatch.setattr(enrich, "release_llm_unless_in_task", lambda: 0)
        monkeypatch.setattr(enrich.manifest, "get_document", lambda did: None)
        monkeypatch.setattr("ragapp.study.mark_needs_card_harvest", lambda: None)

        def fake_questions(text, n=None, model=None, stats=None):
            cid = next(c["id"] for c in chunks if c["document"] == text)
            calls["questions"].append(cid)
            for k, v in (stats_by_chunk or {}).get(cid, {}).items():
                stats[k] = stats.get(k, 0) + v
            return list(questions_by_chunk[cid])

        def fake_answer(text, question, model=None):
            calls["answers"].append(question)
            return f"Antwort auf {question}"

        monkeypatch.setattr(enrich, "generate_questions", fake_questions)
        monkeypatch.setattr(enrich, "generate_answer", fake_answer)
        return store

    return setup, calls


def run(**kw):
    return enrich.enrich_questions(n_per_chunk=1, **kw)


def test_dublette_auf_derselben_fundstelle_wird_nicht_angelegt(env):
    setup, calls = env
    c = chunk("c1", "Seite 5", 300)
    store = setup([c], questions_by_chunk={"c1": ["Wie ändert sich die Richtung bei -1?"]},
                  vectors={"Wie ändert sich die Richtung bei -1?": [0.99, 0.05]},
                  existing=[{"id": "x::eq0", "meta": {"doc_id": "d1", "location": "Seite 5",
                                                       "parent_id": "other"}, "emb": [1.0, 0.0]}])
    out = run(with_answers=True)
    assert store.added == []
    assert out["duplicates"] == 1 and out["questions"] == 0 and out["status"] == "empty"
    assert calls["answers"] == []                   # keine Antwort fuer eine verworfene Dublette


def test_gleiche_frage_auf_anderer_fundstelle_bleibt_erhalten(env):
    setup, calls = env
    c = chunk("c1", "Seite 6", 300)
    store = setup([c], questions_by_chunk={"c1": ["Frage"]}, vectors={"Frage": [0.99, 0.05]},
                  existing=[{"id": "x::eq0", "meta": {"doc_id": "d1", "location": "Seite 5",
                                                       "parent_id": "other"}, "emb": [1.0, 0.0]}])
    out = run()
    assert [a["question"] for a in store.added] == ["Frage"]
    assert out["duplicates"] == 0 and out["questions"] == 1


def test_gleiche_frage_in_anderem_dokument_bleibt_erhalten(env):
    setup, _ = env
    c = chunk("c1", "Seite 5", 300, doc="d2")
    store = setup([c], questions_by_chunk={"c1": ["Frage"]}, vectors={"Frage": [0.99, 0.05]},
                  existing=[{"id": "x::eq0", "meta": {"doc_id": "d1", "location": "Seite 5",
                                                       "parent_id": "other"}, "emb": [1.0, 0.0]}])
    assert run()["duplicates"] == 0 and len(store.added) == 1


def test_dubletten_innerhalb_eines_laufs_werden_erkannt(env):
    setup, calls = env
    a, b = chunk("c1", "Seite 5", 400), chunk("c2", "Seite 5", 300)      # a zuerst (laenger)
    store = setup([a, b], questions_by_chunk={"c1": ["Frage A"], "c2": ["Frage A leicht anders"]},
                  vectors={"Frage A": [1.0, 0.0], "Frage A leicht anders": [0.98, 0.1]})
    out = run(with_answers=True)
    assert [x["question"] for x in store.added] == ["Frage A"]
    assert out["duplicates"] == 1 and out["questions"] == 1
    assert calls["answers"] == ["Frage A"]


def test_verschiedene_fragen_auf_derselben_seite_bleiben_beide(env):
    setup, _ = env
    a, b = chunk("c1", "Seite 5", 400), chunk("c2", "Seite 5", 300)
    store = setup([a, b], questions_by_chunk={"c1": ["Frage A"], "c2": ["Frage B"]},
                  vectors={"Frage A": [1.0, 0.0], "Frage B": [0.0, 1.0]})
    out = run()
    assert len(store.added) == 2 and out["duplicates"] == 0


def test_antwort_wird_in_den_fragen_metadaten_gespeichert(env):
    setup, _ = env
    store = setup([chunk("c1", "Seite 5", 300)], questions_by_chunk={"c1": ["Frage"]},
                  vectors={"Frage": [1.0, 0.0]})
    run(with_answers=True)
    assert store.added[0]["meta"]["answer"] == "Antwort auf Frage"
    assert store.added[0]["meta"]["parent_id"] == "c1" and store.added[0]["meta"]["type"] == "question"


def test_qualitaets_statistik_wird_aufsummiert(env):
    setup, _ = env
    a, b = chunk("c1", "Seite 5", 400), chunk("c2", "Seite 6", 300)
    setup([a, b], questions_by_chunk={"c1": ["A"], "c2": ["B"]},
          vectors={"A": [1.0, 0.0], "B": [0.0, 1.0]},
          stats_by_chunk={"c1": {"rejected": 2, "retries": 1}, "c2": {"rejected": 1, "retries": 1}})
    out = run()
    assert out["rejected"] == 3 and out["retries"] == 2


def test_abbrechen_beendet_nach_dem_zuletzt_gespeicherten_chunk(env):
    setup, calls = env
    a, b, c = chunk("c1", "Seite 1", 500), chunk("c2", "Seite 2", 400), chunk("c3", "Seite 3", 300)
    store = setup([a, b, c], questions_by_chunk={"c1": ["A"], "c2": ["B"], "c3": ["C"]},
                  vectors={"A": [1.0, 0.0, 0.0], "B": [0.0, 1.0, 0.0], "C": [0.0, 0.0, 1.0]})
    asked = {"n": 0}

    def should_cancel():
        asked["n"] += 1
        return asked["n"] > 1             # vor dem ersten Chunk nein, danach ja

    out = run(should_cancel=should_cancel)
    assert [x["question"] for x in store.added] == ["A"]
    assert calls["questions"] == ["c1"]
    assert out["cancelled"] is True and out["status"] == "ok" and out["questions"] == 1


def test_sofortiger_abbruch_ohne_ergebnis_hat_status_cancelled(env):
    setup, calls = env
    store = setup([chunk("c1", "Seite 1", 500)], questions_by_chunk={"c1": ["A"]},
                  vectors={"A": [1.0, 0.0]})
    out = run(should_cancel=lambda: True)
    assert out["status"] == "cancelled" and out["questions"] == 0 and store.added == []
    assert calls["questions"] == []


def test_chunk_ids_beschraenken_auf_genau_diese_abschnitte(env):
    setup, calls = env
    a, b = chunk("c1", "Seite 1", 500), chunk("c2", "Seite 2", 400)
    store = setup([a, b], questions_by_chunk={"c1": ["A"], "c2": ["B"]},
                  vectors={"A": [1.0, 0.0], "B": [0.0, 1.0]})
    run(chunk_ids=["c2"])
    assert [x["question"] for x in store.added] == ["B"]


def test_schon_angereicherte_chunks_werden_uebersprungen(env):
    setup, calls = env
    a = chunk("c1", "Seite 1", 500)
    store = setup([a], questions_by_chunk={"c1": ["A"]}, vectors={"A": [1.0, 0.0]},
                  existing=[{"id": "c1::eq0", "meta": {"doc_id": "d1", "location": "Seite 1",
                                                        "parent_id": "c1"}, "emb": [0.0, 1.0]}])
    out = run()
    assert out["status"] == "nothing_to_do" and store.added == []
