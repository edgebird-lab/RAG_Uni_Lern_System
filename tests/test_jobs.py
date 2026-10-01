"""Hintergrundaufträge (``ragapp.jobs``): Start, Fortschritt, Abbrechen, Fehler, Register.

Rein offline und ohne feste Wartezeiten: die Aufträge warten auf ``threading.Event``s, die der
Test setzt; ``wait_until`` pollt nur, bis ein Zustand erreicht ist (mit Obergrenze)."""
from __future__ import annotations

import threading
import time

import pytest

from ragapp import jobs


@pytest.fixture(autouse=True)
def clean_registry():
    jobs.reset_for_tests()
    yield
    jobs.reset_for_tests()


def wait_until(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def finished(key):
    j = jobs.get(key)
    return j is not None and j.status != jobs.RUNNING


def test_auftrag_laeuft_im_hintergrund_und_liefert_das_ergebnis():
    gate = threading.Event()

    def work(ctx):
        ctx.progress("Thema 1/2", step=1, total=2)
        gate.wait(5)
        return {"cards_new": 7}

    job, started = jobs.start("plan:a", "Karten füllen", work)
    assert started and job.status == jobs.RUNNING
    assert wait_until(lambda: jobs.get("plan:a").message == "Thema 1/2")
    snap = jobs.get("plan:a")
    assert (snap.step, snap.total, snap.status) == (1, 2, jobs.RUNNING)
    assert jobs.any_running()
    gate.set()
    assert wait_until(lambda: finished("plan:a"))
    done = jobs.get("plan:a")
    assert done.status == jobs.DONE and done.result == {"cards_new": 7} and done.error is None
    assert done.finished is not None
    assert not jobs.any_running()


def test_zweiter_start_unter_demselben_schluessel_startet_keinen_zweiten_lauf():
    gate = threading.Event()
    runs = []

    def work(ctx):
        runs.append(1)
        gate.wait(5)

    first, started1 = jobs.start("plan:a", "A", work)
    second, started2 = jobs.start("plan:a", "A nochmal", work)
    assert started1 and not started2
    assert second.job_id == first.job_id
    gate.set()
    assert wait_until(lambda: finished("plan:a"))
    assert runs == [1]


def test_nach_dem_ende_darf_unter_demselben_schluessel_neu_gestartet_werden():
    jobs.start("plan:a", "erster", lambda ctx: "eins")
    assert wait_until(lambda: finished("plan:a"))
    job, started = jobs.start("plan:a", "zweiter", lambda ctx: "zwei")
    assert started
    assert wait_until(lambda: finished("plan:a"))
    assert jobs.get("plan:a").result == "zwei"


def test_abbrechen_stoppt_kooperativ_und_behaelt_das_zwischenergebnis():
    in_loop = threading.Event()

    def work(ctx):
        done = 0
        for i in range(1000):
            if ctx.cancelled():
                break
            done += 1
            ctx.progress(f"Thema {i + 1}", step=i + 1, total=1000)
            in_loop.set()
            time.sleep(0.002)
        return {"topics_done": done}

    jobs.start("plan:a", "Karten", work)
    assert in_loop.wait(5)
    assert jobs.cancel("plan:a") is True
    assert jobs.get("plan:a").cancel_requested
    assert wait_until(lambda: finished("plan:a"))
    j = jobs.get("plan:a")
    assert j.status == jobs.CANCELLED
    assert 0 < j.result["topics_done"] < 1000        # Zwischenstand bleibt erhalten


def test_cancel_ohne_laufenden_auftrag_ist_wirkungslos():
    assert jobs.cancel("gibt-es-nicht") is False
    jobs.start("plan:a", "x", lambda ctx: None)
    assert wait_until(lambda: finished("plan:a"))
    assert jobs.cancel("plan:a") is False
    assert jobs.get("plan:a").status == jobs.DONE


def test_zu_spaet_gekommener_abbruch_macht_aus_einem_fertigen_lauf_keinen_abbruch():
    """Der Auftrag prueft das Flag nie (er war schon fertig): Status bleibt "done"."""
    gate = threading.Event()

    def work(ctx):
        gate.wait(5)
        return "alles fertig"

    jobs.start("plan:a", "x", work)
    jobs.cancel("plan:a")
    gate.set()
    assert wait_until(lambda: finished("plan:a"))
    assert jobs.get("plan:a").status == jobs.DONE


def test_check_wirft_jobcancelled_und_der_status_ist_abgebrochen():
    started = threading.Event()

    def work(ctx):
        started.set()
        while True:
            ctx.check()
            time.sleep(0.002)

    jobs.start("plan:a", "x", work)
    assert started.wait(5)
    jobs.cancel("plan:a")
    assert wait_until(lambda: finished("plan:a"))
    j = jobs.get("plan:a")
    assert j.status == jobs.CANCELLED and j.error is None


def test_fehler_im_auftrag_wird_gemeldet_statt_verschluckt():
    def work(ctx):
        raise RuntimeError("Ollama nicht erreichbar")

    jobs.start("plan:a", "x", work)
    assert wait_until(lambda: finished("plan:a"))
    j = jobs.get("plan:a")
    assert j.status == jobs.ERROR and "Ollama nicht erreichbar" in j.error
    assert not jobs.any_running()          # ein gescheiterter Lauf haelt nichts mehr auf


def test_dismiss_entfernt_nur_beendete_auftraege():
    gate = threading.Event()
    jobs.start("lauf", "laeuft", lambda ctx: gate.wait(5))
    jobs.dismiss("lauf")
    assert jobs.get("lauf") is not None            # laufend: bleibt
    gate.set()
    assert wait_until(lambda: finished("lauf"))
    jobs.dismiss("lauf")
    assert jobs.get("lauf") is None


def test_get_liefert_eine_kopie():
    jobs.start("plan:a", "x", lambda ctx: None)
    assert wait_until(lambda: finished("plan:a"))
    snap = jobs.get("plan:a")
    snap.status = "kaputt"
    snap.message = "veraendert"
    assert jobs.get("plan:a").status == jobs.DONE


def test_get_unbekannter_schluessel_ist_none():
    assert jobs.get("nix") is None


def test_register_behaelt_nur_begrenzt_viele_beendete_auftraege(monkeypatch):
    monkeypatch.setattr(jobs, "_KEEP_FINISHED", 3)
    for i in range(8):
        jobs.start(f"k{i}", "x", lambda ctx: None)
        assert wait_until(lambda i=i: finished(f"k{i}"))
    kept = [k for k in (f"k{i}" for i in range(8)) if jobs.get(k) is not None]
    assert len(kept) <= 4          # 3 beendete + ggf. der zuletzt gestartete


def test_ein_uralter_haengender_auftrag_haelt_das_beenden_nicht_ewig_auf(monkeypatch):
    gate = threading.Event()
    jobs.start("haengt", "x", lambda ctx: gate.wait(5))
    assert jobs.any_running()
    monkeypatch.setattr(jobs, "MAX_BUSY_SECONDS", -1)      # "laeuft schon laenger als erlaubt"
    assert not jobs.any_running()
    gate.set()
    assert wait_until(lambda: finished("haengt"))


def test_mehrere_auftraege_unterschiedlicher_schluessel_laufen_unabhaengig():
    gate = threading.Event()
    jobs.start("plan:a", "A", lambda ctx: gate.wait(5))
    jobs.start("plan:b", "B", lambda ctx: gate.wait(5))
    assert jobs.cancel("plan:a")
    assert not jobs.get("plan:b").cancel_requested
    gate.set()
    assert wait_until(lambda: finished("plan:a") and finished("plan:b"))
