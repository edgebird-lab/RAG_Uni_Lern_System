"""Mindmap-JSON-Reparatur (``ragapp.mindmap._repair_mindmap``): doppelte IDs,
ungültige/zyklische Eltern-Referenzen, halluzinierte (unbelegte, kinderlose)
Knoten, Knoten-Obergrenze, Querverbindungs-Validierung.

Rein rechnerisch, isoliert geladen, weil ein Vollimport von ``ragapp.mindmap``
über ``ragapp.study_plan`` schwere Abhängigkeiten (chromadb) zieht.
"""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(MINDMAP_MAX_NODES=40, MINDMAP_PROMPT_BUDGET_CHARS=9000,
               MINDMAP_EXCERPT_MIN_CHARS=40, MINDMAP_EXCERPT_MAX_CHARS=150)
    base.update(overrides)
    return types.SimpleNamespace(**base)


@pytest.fixture
def repair_mindmap(load_functions, ragapp_dir):
    def _make(**settings_overrides):
        funcs = load_functions(
            ragapp_dir / "mindmap.py", ["_repair_mindmap"],
            {"settings": _fake_settings(**settings_overrides), "Optional": None},
        )
        return funcs["_repair_mindmap"]
    return _make


@pytest.fixture
def toc_with_excerpts(load_functions, ragapp_dir):
    def _make(**settings_overrides):
        funcs = load_functions(
            ragapp_dir / "mindmap.py", ["_toc_with_excerpts"],
            {"settings": _fake_settings(**settings_overrides)},
        )
        return funcs["_toc_with_excerpts"]
    return _make


def _valid_data(**overrides):
    base = dict(
        root="Algorithmen",
        nodes=[
            {"id": "n1", "title": "Sortieren", "parent": None, "indices": [0]},
            {"id": "n2", "title": "Graphen", "parent": None, "indices": [1]},
            {"id": "n3", "title": "QuickSort", "parent": "n1", "indices": [2]},
        ],
        links=[{"from": "n1", "to": "n2", "label": "vgl."}],
    )
    base.update(overrides)
    return base


def test_repair_mindmap_gueltige_daten_bleiben_erhalten(repair_mindmap):
    f = repair_mindmap()
    out = f(_valid_data(), 5)
    assert out["root"] == "Algorithmen"
    assert {n["id"] for n in out["nodes"]} == {"n1", "n2", "n3"}
    assert out["links"] == [{"from": "n1", "to": "n2", "label": "vgl."}]


def test_repair_mindmap_none_bei_nicht_dict(repair_mindmap):
    f = repair_mindmap()
    assert f(None, 5) is None
    assert f([1, 2], 5) is None
    assert f("kein json", 5) is None


def test_repair_mindmap_none_bei_leeren_oder_fehlenden_nodes(repair_mindmap):
    f = repair_mindmap()
    assert f({"root": "X", "nodes": []}, 5) is None
    assert f({"root": "X"}, 5) is None
    assert f({"root": "X", "nodes": "kein array"}, 5) is None


def test_repair_mindmap_root_fallback_bei_fehlendem_titel(repair_mindmap):
    f = repair_mindmap()
    out = f(_valid_data(root=""), 5)
    assert out["root"] == "Übersicht"
    out2 = f(_valid_data(root=None), 5)
    assert out2["root"] == "Übersicht"


def test_repair_mindmap_verwirft_knoten_ohne_id_oder_titel(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "", "title": "Ohne ID", "parent": None, "indices": [0]},
        {"id": "n1", "title": "", "parent": None, "indices": [0]},
        {"id": "n2", "title": "Gueltig", "parent": None, "indices": [0]},
    ])
    out = f(data, 5)
    assert [n["id"] for n in out["nodes"]] == ["n2"]


def test_repair_mindmap_doppelte_ids_nur_erstes_vorkommen(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "Erstes", "parent": None, "indices": [0]},
        {"id": "n1", "title": "Zweites (Duplikat)", "parent": None, "indices": [1]},
    ])
    out = f(data, 5)
    assert len(out["nodes"]) == 1
    assert out["nodes"][0]["title"] == "Erstes"


def test_repair_mindmap_kappt_unbekannte_parent_referenz(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "Verwaist", "parent": "existiert-nicht", "indices": [0]},
    ])
    out = f(data, 5)
    assert out["nodes"][0]["parent"] is None


def test_repair_mindmap_kappt_selbstreferenz(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "Selbst", "parent": "n1", "indices": [0]},
    ])
    out = f(data, 5)
    assert out["nodes"][0]["parent"] is None


def test_repair_mindmap_kappt_zyklus(repair_mindmap):
    f = repair_mindmap()
    # n1 -> n2 -> n3 -> n1 (Zyklus, alle mit Beleg, damit sie nicht als
    # "halluziniert" ohnehin entfernt wuerden)
    data = _valid_data(nodes=[
        {"id": "n1", "title": "A", "parent": "n3", "indices": [0]},
        {"id": "n2", "title": "B", "parent": "n1", "indices": [1]},
        {"id": "n3", "title": "C", "parent": "n2", "indices": [2]},
    ])
    out = f(data, 5)
    # Der Zyklus MUSS irgendwo gekappt sein (mind. ein Knoten mit parent=None),
    # und es darf keine Endlosschleife/Exception aufgetreten sein.
    by_id = {n["id"]: n for n in out["nodes"]}
    assert any(n["parent"] is None for n in out["nodes"])
    # von JEDEM Knoten aus muss man in endlich vielen Schritten die Wurzel (None) erreichen
    for nid in by_id:
        cur = nid
        steps = 0
        while by_id[cur]["parent"] is not None:
            cur = by_id[cur]["parent"]
            steps += 1
            assert steps <= len(by_id), "Zyklus nicht aufgeloest"


def test_repair_mindmap_entfernt_halluzinierte_knoten_ohne_beleg_und_kinder(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "Gegroundet", "parent": None, "indices": [0]},
        {"id": "n2", "title": "Erfunden", "parent": None, "indices": []},
    ])
    out = f(data, 5)
    assert [n["id"] for n in out["nodes"]] == ["n1"]


def test_repair_mindmap_behaelt_gruppierungsknoten_ohne_beleg_aber_mit_kindern(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "Gruppe (kein eigener Beleg)", "parent": None, "indices": []},
        {"id": "n2", "title": "Kind mit Beleg", "parent": "n1", "indices": [0]},
    ])
    out = f(data, 5)
    assert {n["id"] for n in out["nodes"]} == {"n1", "n2"}


def test_repair_mindmap_kaskadierende_entfernung(repair_mindmap):
    f = repair_mindmap()
    # n3 hat keinen Beleg und keine Kinder -> entfernt. Dadurch verliert n2
    # (auch kein Beleg) sein einziges Kind -> im naechsten Durchlauf ebenfalls
    # entfernt. n1 hat einen echten Beleg und bleibt.
    data = _valid_data(nodes=[
        {"id": "n1", "title": "Bleibt", "parent": None, "indices": [0]},
        {"id": "n2", "title": "Nur Gruppe", "parent": None, "indices": []},
        {"id": "n3", "title": "Erfunden", "parent": "n2", "indices": []},
    ])
    out = f(data, 5)
    assert [n["id"] for n in out["nodes"]] == ["n1"]


def test_repair_mindmap_indices_werden_auf_gueltigen_bereich_begrenzt_und_dedupliziert(
        repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "X", "parent": None, "indices": [0, 0, 1, 99, -1, "x"]},
    ])
    out = f(data, 3)   # n=3 -> gueltig sind nur 0,1,2
    assert out["nodes"][0]["indices"] == [0, 1]


def test_repair_mindmap_kappt_auf_max_nodes(repair_mindmap):
    f = repair_mindmap(MINDMAP_MAX_NODES=2)
    data = _valid_data(nodes=[
        {"id": "n1", "title": "A", "parent": None, "indices": [0]},
        {"id": "n2", "title": "B", "parent": None, "indices": [1]},
        {"id": "n3", "title": "C", "parent": None, "indices": [2]},
    ])
    out = f(data, 5)
    assert len(out["nodes"]) == 2


def test_repair_mindmap_links_nur_zwischen_vorhandenen_knoten(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "A", "parent": None, "indices": [0]},
    ], links=[
        {"from": "n1", "to": "unbekannt", "label": "x"},
        {"from": "n1", "to": "n1", "label": "selbst"},
    ])
    out = f(data, 5)
    assert out["links"] == []


def test_repair_mindmap_links_ohne_label_bekommen_leeren_string(repair_mindmap):
    f = repair_mindmap()
    data = _valid_data(nodes=[
        {"id": "n1", "title": "A", "parent": None, "indices": [0]},
        {"id": "n2", "title": "B", "parent": None, "indices": [1]},
    ], links=[{"from": "n1", "to": "n2"}])
    out = f(data, 5)
    assert out["links"] == [{"from": "n1", "to": "n2", "label": ""}]


# ---------------------------------------------------------------------------
# _toc_with_excerpts: anders als study_plan._toc_text bekommt jede Zeile
# zusaetzlich einen Inhalts-Ausschnitt, weil generische Titel (z. B. "Seite N"
# bei Foliensaetzen ohne Kapitelstruktur) dem Modell sonst kein Signal geben,
# um sinnvolle Themennamen zu vergeben (siehe mindmap.py-Modul-Docstring).
# ---------------------------------------------------------------------------

def test_toc_with_excerpts_enthaelt_titel_zeichenzahl_und_ausschnitt(toc_with_excerpts):
    f = toc_with_excerpts()
    capped = [("doc.pdf", "Seite 7", "Verfügbarkeit bedeutet, dass Systeme erreichbar sind.")]
    out = f(capped, 9000)
    assert out.startswith("0. Seite 7")
    assert "(~53 Zeichen)" in out
    assert "Verfügbarkeit bedeutet" in out


def test_toc_with_excerpts_glaettet_mehrfache_leerzeichen_und_zeilenumbrueche(toc_with_excerpts):
    f = toc_with_excerpts()
    capped = [("doc.pdf", "X", "Zeile 1\n\n   Zeile 2  mit   vielen Leerzeichen")]
    out = f(capped, 9000)
    assert "\n\n" not in out.split(":", 1)[1]
    assert "  " not in out.split('"', 1)[1]


def test_toc_with_excerpts_ausschnitt_schrumpft_bei_vielen_abschnitten(toc_with_excerpts):
    f = toc_with_excerpts()
    long_body = "x" * 1000
    capped_few = [("doc.pdf", f"S{i}", long_body) for i in range(3)]
    capped_many = [("doc.pdf", f"S{i}", long_body) for i in range(300)]
    out_few = f(capped_few, 9000)
    out_many = f(capped_many, 9000)
    # bei wenigen Abschnitten volle MAX-Laenge, bei vielen Abschnitten kuerzer
    first_excerpt_few = out_few.split('"')[1]
    first_excerpt_many = out_many.split('"')[1]
    assert len(first_excerpt_few) > len(first_excerpt_many)


def test_toc_with_excerpts_haelt_untergrenze_ein(toc_with_excerpts):
    f = toc_with_excerpts(MINDMAP_EXCERPT_MIN_CHARS=40)
    long_body = "x" * 1000
    capped = [("doc.pdf", f"S{i}", long_body) for i in range(1000)]
    out = f(capped, 9000)
    first_excerpt = out.split('"')[1]
    assert len(first_excerpt) >= 40 - 1  # -1 wegen moeglichem .strip() am Rand


def test_toc_with_excerpts_eine_zeile_je_abschnitt(toc_with_excerpts):
    f = toc_with_excerpts()
    capped = [("doc.pdf", f"S{i}", "Inhalt " * 20) for i in range(5)]
    out = f(capped, 9000)
    assert len(out.splitlines()) == 5
    for i in range(5):
        assert out.splitlines()[i].startswith(f"{i}. S{i}")
