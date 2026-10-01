"""Lernplan-Gliederung (``ragapp.study_plan.generate_outline``): Fehlerfälle,
Fallback-Verhalten und die Trunkierungs-Warnung.

Regressionstest für dieselbe Ursache, die zuerst bei der Mindmap behoben
wurde (siehe ``tests/test_mindmap_generate.py``): ein Reasoning-Modell kann
sein Token-Budget komplett fürs interne "Nachdenken" verbrauchen, bevor der
Antwort-Kanal etwas enthält (``done_reason == 'length'``, ``generate_json()``
liefert ``None``) - der 1:1-Fallback greift dann OHNE dass die Nutzerin/der
Nutzer erfährt, warum. ``generate_outline`` trägt diesen Fall jetzt als
erklärende Warnung statt eines stillen Fallbacks.

Isoliert geladen (kein Vollimport von ``ragapp.study_plan``, das über
``ragapp.retrieval.vectorstore`` schwere Abhängigkeiten wie chromadb zieht) -
alle externen Aufrufe (LLM, Abschnitts-Ermittlung, Zeitschätzung, DB) werden
gefaked; ``_repair_outline``/``_toc_with_excerpts``/``_author_model`` werden
echt geladen (rein rechnerisch, keine DB-Abhängigkeit).
"""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(
        PLAN_MAX_TOC_CHARS=10000, PLAN_PROMPT_BUDGET_CHARS=9000,
        TOC_EXCERPT_MIN_CHARS=40, TOC_EXCERPT_MAX_CHARS=150,
        PLAN_MAX_OUTLINE_SECTIONS=15, LLM_MODEL_AUTHOR="", LLM_MODEL="fallback-model",
        PLAN_OUTLINE_BATCH_ENTRIES=30, PLAN_TOPIC_MAX_CHARS=12000,
    )
    base.update(overrides)
    ns = types.SimpleNamespace(**base)
    ns.author_model = lambda: (ns.LLM_MODEL_AUTHOR or "").strip() or ns.LLM_MODEL
    return ns


class _FakeLLM:
    def __init__(self, *, result=None, raise_exc=None, done_reason="stop",
                completion_tokens=500, model="test-model"):
        self._result = result
        self._raise_exc = raise_exc
        self.last_done_reason = done_reason
        self.last_completion_tokens = completion_tokens
        self.model = model
        self.prompts: list[str] = []

    def generate_json(self, prompt, system=None, temperature=None):
        self.prompts.append(prompt)
        if self._raise_exc:
            raise self._raise_exc
        if callable(self._result):
            return self._result(prompt)
        return self._result


class _FakeManifest:
    def log_eta_sample(self, *a, **kw):
        pass

    def get_document(self, doc_id):
        return {"doc_id": doc_id, "filename": "doc.pdf"}


def _fake_granular_sections_factory(n=5, docs=None):
    """n Abschnitte einer Quelle - oder ``docs={label: (anzahl, zeichen_je_abschnitt)}``
    fuer mehrere Quellen nacheinander (wie ``_granular_sections``: nach Dokument sortiert)."""
    def _fake(doc_ids):
        if docs:
            return [(label, f"Seite {i + 1}", "x" * chars)
                    for label, (count, chars) in docs.items() for i in range(count)]
        return [("doc.pdf", f"Seite {i}", f"Inhalt von Seite {i} " * 10) for i in range(n)]
    return _fake


def _identity_cap(granular, max_chars):
    return granular


@pytest.fixture
def generate_outline_funcs(load_functions, ragapp_dir):
    def _make(*, llm, settings_obj=None, n_sections=5, docs=None):
        settings = settings_obj or _fake_settings()
        return load_functions(
            ragapp_dir / "study_plan.py",
            ["generate_outline", "_author_model", "_repair_outline", "_toc_with_excerpts",
             "_outline_batches", "_split_oversized", "_pages_label", "_disambiguate_titles"],
            {
                "settings": settings,
                "math": __import__("math"),
                "re": __import__("re"),
                "get_llm": lambda model=None: llm,
                "manifest": _FakeManifest(),
                "_granular_sections": _fake_granular_sections_factory(n_sections, docs),
                "_cap_granular_for_prompt": _identity_cap,
                "_content_multiplier": lambda text: 1.0,
                "estimate_minutes": lambda chars, subject=None, content_multiplier=1.0: 10,
                "OutlineError": RuntimeError,
                "Optional": None,
                "time": __import__("time"),
                "llm_task": lambda model=None: __import__("contextlib").nullcontext(),
            },
            const_names=["_OUTLINE_SYSTEM", "_OUTLINE_PROMPT", "_PAGE_TITLE_RE"],
        )["generate_outline"]
    return _make


def test_generate_outline_erfolgsfall_gibt_repariertes_ergebnis_ohne_warnung(
        generate_outline_funcs):
    good_data = [{"title": "Thema A", "summary": "worum es geht", "indices": [0, 1]}]
    llm = _FakeLLM(result=good_data)
    f = generate_outline_funcs(llm=llm)
    sections, warning = f(["doc1"], "DSA")
    assert warning is None
    assert sections[0]["title"] == "Thema A"
    assert sections[0]["source_refs"][:2] == [
        {"doc_id": "doc1", "filename": "doc.pdf", "section": "Seite 0"},
        {"doc_id": "doc1", "filename": "doc.pdf", "section": "Seite 1"},
    ]
    assert len(sections[0]["source_refs"]) == 5


def test_generate_outline_keine_abschnitte_wirft_outline_error(generate_outline_funcs):
    llm = _FakeLLM(result=[])
    f = generate_outline_funcs(llm=llm, n_sections=0)
    with pytest.raises(RuntimeError):
        f(["doc1"], "DSA")


def test_generate_outline_llm_exception_wirft_outline_error(generate_outline_funcs):
    llm = _FakeLLM(raise_exc=ConnectionError("Ollama nicht erreichbar"))
    f = generate_outline_funcs(llm=llm)
    with pytest.raises(RuntimeError, match="fehlgeschlagen"):
        f(["doc1"], "DSA")


def test_generate_outline_truncation_faellt_zurueck_MIT_warnung(generate_outline_funcs):
    # Genau der real beobachtete Fall: generate_json() liefert None (Parsen
    # gescheitert) UND done_reason=='length' (Token-Budget aufgebraucht).
    llm = _FakeLLM(result=None, done_reason="length", completion_tokens=1024,
                   model="gpt-oss:20b")
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="gpt-oss:20b")
    f = generate_outline_funcs(llm=llm, settings_obj=settings_obj, n_sections=5)
    sections, warning = f(["doc1"], "DSA")
    # Fallback (1 Abschnitt je Original-Abschnitt) greift trotzdem.
    assert len(sections) == 5
    assert warning is not None
    assert "gpt-oss:20b" in warning
    assert "1024" in warning


def test_generate_outline_andere_reparatur_fehlschlaege_bleiben_ohne_warnung(
        generate_outline_funcs):
    # generate_json() liefert etwas Geparstes, das aber KEIN brauchbares
    # Gliederungs-Ergebnis ist (leere Liste) - kein Trunkierungsfall, also
    # auch keine (irrefuehrende) Trunkierungs-Warnung.
    llm = _FakeLLM(result=[], done_reason="stop")
    f = generate_outline_funcs(llm=llm, n_sections=3)
    sections, warning = f(["doc1"], "DSA")
    assert len(sections) == 3
    assert warning is None


def test_generate_outline_verwendet_autoren_modell_wenn_kein_modell_angegeben(
        generate_outline_funcs):
    good_data = [{"title": "Thema A", "summary": "", "indices": [0]}]
    llm = _FakeLLM(result=good_data)
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="mein-autoren-modell")
    f = generate_outline_funcs(llm=llm, settings_obj=settings_obj)
    sections, warning = f(["doc1"], "DSA", model=None)
    assert warning is None
    assert sections[0]["title"] == "Thema A"


# --------------------------------------------------------------------------- #
# Gruppenweise Gliederung + Aufteilen uebergrosser Themen. Regression: Bei 8 PDFs
# (165 Abschnitte, gemma3:4b) ordnete die KI nur die ersten ~25 zu; der Rest (85 % des
# Stoffs, 3396 Minuten) landete in EINEM Thema "Gauß-Jordan-Verfahren".
# --------------------------------------------------------------------------- #
@pytest.fixture
def batch_funcs(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "study_plan.py", ["_outline_batches", "_split_oversized", "_pages_label"],
        {"math": __import__("math"), "re": __import__("re")}, const_names=["_PAGE_TITLE_RE"])


def _capped(*counts):
    out = []
    for d, n in enumerate(counts):
        out += [(f"doc{d}", f"Seite {i}", "x" * 1000) for i in range(n)]
    return out


def test_outline_batches_kleine_liste_eines_dokuments_bleibt_eine_gruppe(batch_funcs):
    assert batch_funcs["_outline_batches"](_capped(10), 30) == [list(range(10))]
    assert batch_funcs["_outline_batches"]([], 30) == [[]]


def test_outline_batches_mischt_nie_verschiedene_dokumente_auch_wenn_alles_klein_ist(batch_funcs):
    # Zwei kleine Dokumente passten frueher in EINE Gruppe - die KI bildete dann Themen
    # ueber die Dokumentgrenze (z. B. Vektorrechnung + LGS). Jetzt: je Dokument eine Gruppe.
    capped = _capped(10, 5)
    assert batch_funcs["_outline_batches"](capped, 30) == [list(range(10)), list(range(10, 15))]


def test_outline_batches_teilt_dokumentweise_und_verliert_nichts(batch_funcs):
    f = batch_funcs["_outline_batches"]
    capped = _capped(19, 9, 14, 31, 34, 22, 18, 16)          # der echte Plan (163 Eintraege)
    batches = f(capped, 30)
    assert all(0 < len(b) <= 30 for b in batches)
    assert [i for b in batches for i in b] == list(range(len(capped)))   # lueckenlos, geordnet
    # Jede Gruppe stammt aus GENAU EINEM Dokument.
    assert all(len({capped[i][0] for i in b}) == 1 for b in batches)
    # 6 kleine Dokumente je eine Gruppe + die zwei grossen (31 und 34) je zweigeteilt.
    assert len(batches) == 10


def test_outline_batches_ein_riesen_dokument_wird_gleichmaessig_geteilt(batch_funcs):
    batches = batch_funcs["_outline_batches"](_capped(100), 30)
    assert [len(b) for b in batches] == [25, 25, 25, 25]


def _topic(title, indices):
    return {"title": title, "summary": "s", "indices": indices}


def test_split_oversized_laesst_normale_themen_unveraendert(batch_funcs):
    topics = [_topic("A", [0, 1, 2]), _topic("B", [3, 4])]
    assert batch_funcs["_split_oversized"](topics, _capped(5), 12000) == topics


def test_split_oversized_teilt_riesenthema_in_gleich_grosse_teile_mit_seitenbereich(batch_funcs):
    capped = _capped(40)                                      # 40.000 Zeichen, "Seite 0" … "Seite 39"
    out = batch_funcs["_split_oversized"]([_topic("Sammelthema", list(range(40)))], capped, 12000)
    assert len(out) == 4
    # Der Titel zeigt, WO im Dokument das Teilthema liegt (statt "Teil 1/4").
    assert [t["title"] for t in out] == [
        "Sammelthema (S. 0–9)", "Sammelthema (S. 10–19)",
        "Sammelthema (S. 20–29)", "Sammelthema (S. 30–39)"]
    assert [i for t in out for i in t["indices"]] == list(range(40))     # nichts verloren
    assert all(abs(len(t["indices"]) - 10) <= 1 for t in out)           # ausgewogen


def test_split_oversized_ohne_seitentitel_nummeriert_die_teile(batch_funcs):
    capped = [("doc", f"Kapitel {i}", "x" * 1000) for i in range(30)]
    out = batch_funcs["_split_oversized"]([_topic("Alles", list(range(30)))], capped, 12000)
    assert [t["title"] for t in out] == ["Alles (Teil 1/3)", "Alles (Teil 2/3)", "Alles (Teil 3/3)"]


def test_pages_label_nur_wenn_alle_titel_seitenangaben_sind(batch_funcs):
    f = batch_funcs["_pages_label"]
    assert f(["Seite 4", "Seite 5", "Seite 7"]) == "S. 4–5, 7"     # Luecken bleiben sichtbar
    assert f(["Seite 12", "Seite 13", "Seite 16", "Seite 17", "Seite 19"]) == "S. 12–13, 16–17, 19"
    assert f(["Seite 9", "Seite 9"]) == "S. 9"
    assert f(["Seite 9"]) == "S. 9"
    assert f(["Seite 4", "Einleitung"]) == ""
    assert f([]) == ""


def test_split_oversized_einzelner_riesen_abschnitt_bleibt_ganz(batch_funcs):
    capped = [("doc", "Seite 1", "x" * 50000)]
    topics = [_topic("Ein Block", [0])]
    assert batch_funcs["_split_oversized"](topics, capped, 12000) == topics


def test_split_oversized_null_schaltet_ab(batch_funcs):
    topics = [_topic("Riesig", list(range(40)))]
    assert batch_funcs["_split_oversized"](topics, _capped(40), 0) == topics


def test_generate_outline_faule_ki_erzeugt_kein_sammelthema(generate_outline_funcs):
    """Die KI ordnet in jeder Gruppe nur die ersten drei Abschnitte zu (so verhielt sich
    gemma3:4b). Frueher: alles Uebrige im letzten Thema. Jetzt: gruppenweise, Rest bleibt
    in seiner Gruppe und uebergrosse Themen werden geteilt."""
    def lazy(prompt):
        return [{"title": "Anfang", "summary": "", "indices": [0, 1, 2]}]
    llm = _FakeLLM(result=lazy)
    docs = {"d1": (40, 1000), "d2": (40, 1000), "d3": (40, 1000)}        # 120.000 Zeichen
    f = generate_outline_funcs(llm=llm, docs=docs)
    sections, warning = f(["d1", "d2", "d3"], "LA")
    assert warning is None
    assert len(llm.prompts) == 6                  # 3 Dokumente x 2 gleich grosse Gruppen (je 20)
    assert max(s["est_chars"] for s in sections) <= 12000 + 1000          # kein Riesenthema
    assert sum(s["est_chars"] for s in sections) == 120000                # nichts geht verloren
    # Reihenfolge der Quellen bleibt erhalten (Dokument 1 vor 2 vor 3).
    first_docs = [s["source_refs"][0]["doc_id"] for s in sections]
    assert first_docs == sorted(first_docs)


def test_generate_outline_gruppen_bekommen_nur_ihre_eintraege_im_prompt(generate_outline_funcs):
    seen = []

    def echo(prompt):
        seen.append(prompt)
        n = int(__import__("re").search(r"(\d+) Original-Abschnitten", prompt).group(1))
        return [{"title": f"Thema {len(seen)}", "summary": "", "indices": list(range(n))}]
    llm = _FakeLLM(result=echo)
    f = generate_outline_funcs(llm=llm, docs={"d1": (45, 500), "d2": (10, 500)})
    sections, _ = f(["d1", "d2"], "LA")
    assert len(sections) == 3
    # Jede Gruppe nummeriert lokal ab 0 - die Zuordnung zurueck zu den echten Abschnitten stimmt.
    assert [len(s["source_refs"]) for s in sections] == [23, 22, 10]
    assert sections[2]["source_refs"][0]["section"] == "Seite 1"
    assert sections[0]["source_refs"][0]["doc_id"] == "d1"


def test_generate_outline_truncation_warnung_nennt_bei_gruppen_die_anzahl(generate_outline_funcs):
    llm = _FakeLLM(result=None, done_reason="length", completion_tokens=1024)
    f = generate_outline_funcs(llm=llm, docs={"d1": (40, 300), "d2": (40, 300)})
    sections, warning = f(["d1", "d2"], "LA")
    assert "2 von 3" in warning or "3 von 3" in warning or "von" in warning
    assert len(sections) == 80                          # Fallback: jeder Abschnitt einzeln


def test_generate_outline_ein_thema_stammt_immer_aus_genau_einem_dokument(generate_outline_funcs):
    """Die Referenz fuer Karten/Uebungen ist das Dokument des Themas. Selbst eine KI, die
    in jeder Gruppe ALLE Eintraege zu einem einzigen Thema zusammenwirft, kann keine
    Dokumentgrenze ueberschreiten - sie sieht je Aufruf nur ein Dokument."""
    def alles_in_ein_thema(prompt):
        n = int(__import__("re").search(r"(\d+) Original-Abschnitten", prompt).group(1))
        return [{"title": "Alles", "summary": "", "indices": list(range(n))}]
    llm = _FakeLLM(result=alles_in_ein_thema)
    f = generate_outline_funcs(llm=llm, docs={"vektoren": (8, 500), "lgs": (6, 500), "matrizen": (7, 500)})
    sections, _ = f(["vektoren", "lgs", "matrizen"], "LA")
    assert len(sections) == 3
    for sec in sections:
        assert len({r["doc_id"] for r in sec["source_refs"]}) == 1, sec["source_refs"]
    assert [s["source_refs"][0]["doc_id"] for s in sections] == ["vektoren", "lgs", "matrizen"]


def test_generate_outline_themenkontingent_waechst_mit_der_abschnittszahl_der_gruppe(generate_outline_funcs):
    seen = []

    def merke(prompt):
        seen.append(int(__import__("re").search(r"HOECHSTENS (\d+)", prompt).group(1)))
        return [{"title": "T", "summary": "", "indices": [0]}]
    llm = _FakeLLM(result=merke)
    # 19 Abschnitte (kleiner Anteil am Gesamtstoff) sollen trotzdem mehr als 1 Thema erlauben.
    f = generate_outline_funcs(llm=llm, docs={"klein": (19, 100), "gross": (30, 5000)})
    f(["klein", "gross"], "LA")
    assert seen[0] >= 4 and seen[1] >= 5
