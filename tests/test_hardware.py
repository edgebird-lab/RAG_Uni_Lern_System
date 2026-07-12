"""Reine Rechenlogik der Modell-Empfehlung (``ragapp.hardware``).

``hardware.py`` importiert oben nur die Standardbibliothek (os/platform/shutil/
subprocess) - schwere Pakete (ollama/psutil) werden erst in einzelnen Funktionen
importiert. Deshalb ist der direkte Import hier torch-/ollama-frei. Getestet wird
mit FINGIERTEN Hardware-Dicts (kein Zugriff auf echte GPU/CPU).
"""
import ragapp.hardware as hw


def _hw(vendor, vram=None, ram=16.0, is_igpu=False):
    """Baut ein fingiertes Hardware-Dict im Format von ``detect_hardware``."""
    return {
        "os": "Linux", "os_release": "test", "cpu": "Test-CPU", "ram_gb": ram,
        "gpu": {"vendor": vendor, "name": f"{vendor} GPU",
                "vram_gb": vram, "is_igpu": is_igpu},
    }


# --------------------------------------------------------------------------- #
# _fit_budget
# --------------------------------------------------------------------------- #
def test_fit_budget_nvidia_grosser_vram_reserve_3():
    fit, hard, on, note = hw._fit_budget(_hw("nvidia", vram=24.0))
    assert on == "GPU"
    assert fit == 21.0        # 24 - 3.0 Reserve (>9 GB VRAM)
    assert hard == 24.5       # vram + 0.5
    assert "24" in note


def test_fit_budget_nvidia_kleiner_vram_reserve_1_5():
    fit, hard, on, _note = hw._fit_budget(_hw("nvidia", vram=6.0))
    assert on == "GPU"
    assert fit == 4.5         # 6 - 1.5 Reserve (<=6 GB)
    assert hard == 6.5


def test_fit_budget_mittlerer_vram_reserve_2():
    fit, hard, _on, _note = hw._fit_budget(_hw("amd", vram=8.0))
    assert fit == 6.0         # 8 - 2.0 Reserve (<=9 GB)
    assert hard == 8.5


def test_fit_budget_gpu_ohne_vram_konservativ():
    fit, hard, on, note = hw._fit_budget(_hw("amd", vram=None))
    assert on == "GPU"
    assert (fit, hard) == (5.5, 8.0)
    assert "unbekannt" in note.lower()


def test_fit_budget_apple_metal_nutzt_ram_anteil():
    fit, hard, on, _note = hw._fit_budget(_hw("apple", vram=None, ram=16.0))
    assert on.startswith("GPU")
    assert fit == 16.0 * 0.5
    assert hard == 16.0 * 0.7


def test_fit_budget_cpu_nutzt_ram_drittel_und_haelfte():
    fit, hard, on, _note = hw._fit_budget(_hw("none", vram=None, ram=24.0))
    assert on == "CPU"
    assert fit == max(3.0, 24.0 / 3)
    assert hard == 24.0 / 2


# --------------------------------------------------------------------------- #
# recommend_models
# --------------------------------------------------------------------------- #
def test_recommend_intel_nutzt_kompatible_kleine_modelle():
    rec = hw.recommend_models(_hw("intel", vram=None, is_igpu=True))
    tags = [m["tag"] for m in rec["models"]]
    assert tags == ["gemma3:4b", "qwen2.5:3b-instruct"]
    assert rec["embed_model"] == "bge-m3"
    assert rec["budget_gb"] is None


def test_recommend_grosser_nvidia_nimmt_staerkstes_passendes():
    rec = hw.recommend_models(_hw("nvidia", vram=24.0))
    assert rec["budget_gb"] == 21.0
    assert rec["models"], "es muss Empfehlungen geben"
    assert rec["models"][0]["tag"] == "gemma3:27b"   # staerkstes, das KOMPLETT passt
    assert len(rec["models"]) <= 5
    # Bei 24 GB passt alles komplett in den Speicher (kein Spill).
    for m in rec["models"]:
        assert m["gb"] <= rec["budget_gb"]


def test_recommend_kleiner_nvidia_liefert_passende_modelle():
    rec = hw.recommend_models(_hw("nvidia", vram=6.0))
    assert rec["budget_gb"] == 4.5
    gbs = [m["gb"] for m in rec["models"]]
    assert min(gbs) <= 4.5                            # mind. ein komplett passendes Modell
    assert any(g <= 4.5 for g in gbs)


def test_recommend_cpu_nur_kleine_modelle_mit_hinweis():
    rec = hw.recommend_models(_hw("none", vram=None, ram=8.0))
    assert rec["budget_gb"] == 3.0
    assert "CPU" in rec["reason"]
    assert rec["models"]
    # hard_budget = ram/2 = 4.0 -> nichts Groesseres wird vorgeschlagen.
    assert all(m["gb"] <= 4.0 for m in rec["models"])


def test_recommend_winziger_vram_faellt_auf_kleinste_modelle_zurueck():
    rec = hw.recommend_models(_hw("nvidia", vram=2.0))
    # fit_budget = max(2.0, 2.0 - 1.5) = 2.0 -> nichts passt komplett -> kleinste zuerst.
    assert rec["budget_gb"] == 2.0
    assert rec["models"][0]["tag"] == "qwen3:4b"     # kleinstes Katalog-Modell
