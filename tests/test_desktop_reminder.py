"""Tests für die native Desktop-Erinnerung in ragapp/desktop.py
(_notify_desktop()/_maybe_remind_due_cards()) - bewusst KEIN Smartphone-Push,
höchstens einmal pro Tag ab einer konfigurierten Uhrzeit, wenn heute noch
nichts geübt wurde. subprocess.run wird überall gemockt (keine echten
Systembenachrichtigungen während des Testlaufs, keine Ollama-/DB-Abhängigkeit)."""
from __future__ import annotations

import time

import pytest

import ragapp.desktop as desktop
from ragapp.config import settings


@pytest.fixture(autouse=True)
def _reset_settings():
    # Settings sind ein einziges, geteiltes Objekt - nach jedem Test wieder auf
    # den Ausgangswert zuruecksetzen, damit Tests sich nicht gegenseitig beeinflussen.
    orig_enabled = settings.DESKTOP_REMINDERS_ENABLED
    orig_hour = settings.STREAK_RISK_HOUR
    yield
    settings.DESKTOP_REMINDERS_ENABLED = orig_enabled
    settings.STREAK_RISK_HOUR = orig_hour


@pytest.fixture()
def no_state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "REMINDER_STATE_FILE", tmp_path / ".last_reminder_date")
    return tmp_path


# --------------------------------------------------------------------------- #
# _notify_desktop(): richtiger Befehl je Plattform, nie fatal
# --------------------------------------------------------------------------- #
def test_notify_desktop_linux_ruft_notify_send(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    monkeypatch.setattr(desktop.subprocess, "run",
                        lambda *a, **kw: calls.append((a, kw)))
    desktop._notify_desktop("Titel", "Nachricht")
    assert len(calls) == 1
    cmd = calls[0][0][0]
    assert cmd[0] == "notify-send"
    assert "Titel" in cmd and "Nachricht" in cmd


def test_notify_desktop_macos_ruft_osascript(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop.subprocess, "run",
                        lambda *a, **kw: calls.append((a, kw)))
    desktop._notify_desktop("Titel", "Nachricht")
    cmd = calls[0][0][0]
    assert cmd[0] == "osascript"
    assert "Nachricht" in cmd[2] and "Titel" in cmd[2]


def test_notify_desktop_windows_ruft_powershell(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(desktop.os, "name", "nt")
    monkeypatch.setattr(desktop.subprocess, "run",
                        lambda *a, **kw: calls.append((a, kw)))
    desktop._notify_desktop("Titel", "Nachricht")
    cmd = calls[0][0][0]
    assert cmd[0] == "powershell"
    assert any("ShowBalloonTip" in part for part in cmd)


def test_notify_desktop_fehler_wird_verschluckt(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "linux")

    def _boom(*a, **kw):
        raise OSError("notify-send nicht gefunden")

    monkeypatch.setattr(desktop.subprocess, "run", _boom)
    desktop._notify_desktop("x", "y")   # darf NICHT werfen


# --------------------------------------------------------------------------- #
# _maybe_remind_due_cards()
# --------------------------------------------------------------------------- #
def test_erinnerung_vor_der_risiko_uhrzeit_bleibt_stumm(monkeypatch, no_state_file):
    settings.STREAK_RISK_HOUR = 17
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time(
        (2026, 1, 1, 9, 0, 0, 0, 1, 0)))
    calls = []
    monkeypatch.setattr(desktop, "_notify_desktop", lambda *a: calls.append(a))
    desktop._maybe_remind_due_cards()
    assert calls == []


def test_erinnerung_ab_risiko_uhrzeit_bei_faelligen_unbeuebten_karten(monkeypatch, no_state_file):
    settings.STREAK_RISK_HOUR = 17
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time(
        (2026, 1, 1, 20, 0, 0, 0, 1, 0)))
    monkeypatch.setattr("ragapp.analytics.overview",
                        lambda subject: {"due": 5, "reviews_today": 0})
    calls = []
    monkeypatch.setattr(desktop, "_notify_desktop", lambda *a: calls.append(a))
    desktop._maybe_remind_due_cards()
    assert len(calls) == 1
    assert "5 Karte" in calls[0][1]
    assert desktop.REMINDER_STATE_FILE.read_text(encoding="utf-8").strip() == "2026-01-01"


def test_erinnerung_bleibt_stumm_wenn_heute_schon_geuebt(monkeypatch, no_state_file):
    settings.STREAK_RISK_HOUR = 17
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time(
        (2026, 1, 1, 20, 0, 0, 0, 1, 0)))
    monkeypatch.setattr("ragapp.analytics.overview",
                        lambda subject: {"due": 5, "reviews_today": 3})
    calls = []
    monkeypatch.setattr(desktop, "_notify_desktop", lambda *a: calls.append(a))
    desktop._maybe_remind_due_cards()
    assert calls == []


def test_erinnerung_nur_einmal_pro_tag(monkeypatch, no_state_file):
    settings.STREAK_RISK_HOUR = 17
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time(
        (2026, 1, 1, 20, 0, 0, 0, 1, 0)))
    monkeypatch.setattr("ragapp.analytics.overview",
                        lambda subject: {"due": 5, "reviews_today": 0})
    calls = []
    monkeypatch.setattr(desktop, "_notify_desktop", lambda *a: calls.append(a))
    desktop._maybe_remind_due_cards()
    desktop._maybe_remind_due_cards()
    desktop._maybe_remind_due_cards()
    assert len(calls) == 1


def test_erinnerung_ohne_faellige_karten_schreibt_kein_datum_und_erlaubt_spaeteren_check(
        monkeypatch, no_state_file):
    # Kein Datum festschreiben, solange nichts zu erinnern gab - ein frueher,
    # ruhiger Check am selben Tag darf einen SPAETEREN, echten Bedarf nicht
    # verhindern (siehe Docstring von _maybe_remind_due_cards).
    settings.STREAK_RISK_HOUR = 17
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time(
        (2026, 1, 1, 20, 0, 0, 0, 1, 0)))
    monkeypatch.setattr("ragapp.analytics.overview",
                        lambda subject: {"due": 0, "reviews_today": 0})
    calls = []
    monkeypatch.setattr(desktop, "_notify_desktop", lambda *a: calls.append(a))
    desktop._maybe_remind_due_cards()
    assert calls == []
    assert not desktop.REMINDER_STATE_FILE.exists()


def test_erinnerung_abschaltbar_per_einstellung(monkeypatch, no_state_file):
    settings.DESKTOP_REMINDERS_ENABLED = False
    settings.STREAK_RISK_HOUR = 17
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time(
        (2026, 1, 1, 20, 0, 0, 0, 1, 0)))
    monkeypatch.setattr("ragapp.analytics.overview",
                        lambda subject: {"due": 5, "reviews_today": 0})
    calls = []
    monkeypatch.setattr(desktop, "_notify_desktop", lambda *a: calls.append(a))
    desktop._maybe_remind_due_cards()
    assert calls == []


def test_erinnerung_fehler_wird_verschluckt(monkeypatch, no_state_file):
    def _boom(*a):
        raise RuntimeError("boom")

    monkeypatch.setattr(time, "localtime", _boom)
    desktop._maybe_remind_due_cards()   # darf NICHT werfen
