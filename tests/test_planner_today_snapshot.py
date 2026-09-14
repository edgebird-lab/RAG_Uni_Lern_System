"""Tests für planner.today_snapshot() - insbesondere die drei neuen Signale:
Lernplan-Rückstand (overdue_plan_blocks), Streak-Gefährdung (streak_at_risk)
und Cram-Modus (cram_active). Isolierte Temp-DB, niemals die echte
data/manifest.db (gleiches Muster wie test_manifest_audio_overviews.py)."""
from __future__ import annotations

import time as _time
from datetime import date, timedelta

import pytest

from ragapp import analytics, manifest, planner


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    # analytics.py haelt eine EIGENE MANIFEST_DB-Referenz (siehe bereits
    # bestehendes Muster in test_analytics_progress_snapshot.py).
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    return db_path


def _iso(delta_days: int) -> str:
    return (date.today() + timedelta(days=delta_days)).isoformat()


# --------------------------------------------------------------------------- #
# Lernplan-Rueckstand
# --------------------------------------------------------------------------- #
def test_overdue_plan_blocks_leer_ohne_plaene(isolated_db):
    snap = planner.today_snapshot()
    assert snap["overdue_plan_blocks"] == []
    assert snap["overdue_plan_min"] == 0


def test_today_snapshot_ignoriert_bloecke_aus_entwurfsplan(isolated_db):
    pid = manifest.create_study_plan(
        title="Entwurf", subject="BWL", doc_ids=[], deadline=None,
        daily_minutes=30)
    sid = manifest.append_plan_section(pid, title="Noch nicht aktiv", est_minutes=30)
    manifest.append_plan_block(
        pid, section_id=sid, planned_date=_iso(0), planned_min=30)
    snap = planner.today_snapshot()
    assert snap["plan_blocks_today"] == []
    assert snap["plan_min_today"] == 0


def test_overdue_plan_blocks_zeigt_verpassten_block(isolated_db):
    pid = manifest.create_study_plan(
        title="Testplan", subject="mathe", doc_ids=[], deadline=None, daily_minutes=60)
    manifest.update_study_plan(pid, status="active")
    manifest.replace_plan_blocks(pid, [
        {"section_id": None, "planned_date": _iso(-2), "planned_min": 25},
        {"section_id": None, "planned_date": _iso(3), "planned_min": 25},
    ])
    snap = planner.today_snapshot()
    assert snap["overdue_plan_min"] == 25
    assert len(snap["overdue_plan_blocks"]) == 1
    assert snap["overdue_plan_blocks"][0]["planned_date"] == _iso(-2)


# --------------------------------------------------------------------------- #
# Streak-Gefaehrdung
# --------------------------------------------------------------------------- #
def _insert_card_with_review(subject: str, reviewed_at: float) -> None:
    with manifest._connect() as conn:
        cid = f"c-{reviewed_at}"
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, created_at) VALUES (?,?,?,?,0,1,1,?)",
            (cid, subject, "F", "A", _time.time()))
        conn.execute(
            "INSERT INTO review_log (card_id, subject, rating, reviewed_at) "
            "VALUES (?,?,2,?)", (cid, subject, reviewed_at))


def _patch_current_hour(monkeypatch, hour: int) -> None:
    """Faelscht NUR die stunden-lose ``time.localtime()``-Momentaufnahme (wie sie
    ``planner.today_snapshot()`` fuer die Streak-Risiko-Uhrzeit nutzt) - ein
    ``time.localtime(ts)``-Aufruf MIT explizitem Zeitstempel (z. B. analytics.py's
    ``_day_key``/``_day_start``, die echte Tagesgrenzen aus review_log-
    Zeitstempeln berechnen) muss weiterhin die ECHTE Umrechnung liefern, sonst
    faellt jeder Zeitstempel auf denselben Tag und ``streak()``s Rueckwaerts-
    Schleife wird endlos (real beobachtet: kompletter Test-Hang)."""
    real_localtime = _time.localtime

    def _fake(secs=None):
        if secs is None:
            now = real_localtime()
            return _time.struct_time((now.tm_year, now.tm_mon, now.tm_mday, hour,
                                      0, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
        return real_localtime(secs)

    monkeypatch.setattr(_time, "localtime", _fake)


def test_streak_at_risk_wenn_spaet_und_heute_nichts_geuebt(isolated_db, monkeypatch):
    # Streak von 1 Tag: gestern geuebt, heute noch nicht.
    _insert_card_with_review("mathe", _time.time() - 86400)
    _patch_current_hour(monkeypatch, 20)
    snap = planner.today_snapshot()
    assert snap["streak"] >= 1
    assert snap["reviews_today"] == 0
    assert snap["streak_at_risk"] is True


def test_streak_at_risk_falsch_vor_der_risiko_uhrzeit(isolated_db, monkeypatch):
    _insert_card_with_review("mathe", _time.time() - 86400)
    _patch_current_hour(monkeypatch, 9)
    snap = planner.today_snapshot()
    assert snap["streak_at_risk"] is False


def test_streak_at_risk_falsch_wenn_heute_schon_geuebt(isolated_db, monkeypatch):
    _insert_card_with_review("mathe", _time.time())
    _patch_current_hour(monkeypatch, 20)
    snap = planner.today_snapshot()
    assert snap["reviews_today"] >= 1
    assert snap["streak_at_risk"] is False


def test_streak_at_risk_falsch_ohne_streak(isolated_db, monkeypatch):
    _patch_current_hour(monkeypatch, 20)
    snap = planner.today_snapshot()
    assert snap["streak"] == 0
    assert snap["streak_at_risk"] is False


# --------------------------------------------------------------------------- #
# Cram-Modus
# --------------------------------------------------------------------------- #
def test_cram_active_innerhalb_der_frist(isolated_db):
    manifest.upsert_exam("mathe", exam_date=_iso(2))
    assert planner.today_snapshot()["cram_active"] is True


def test_cram_active_falsch_weit_vor_der_klausur(isolated_db):
    manifest.upsert_exam("mathe", exam_date=_iso(30))
    assert planner.today_snapshot()["cram_active"] is False


def test_cram_active_falsch_ohne_termin(isolated_db):
    assert planner.today_snapshot()["cram_active"] is False


def test_cram_active_am_klausurtag_selbst(isolated_db):
    manifest.upsert_exam("mathe", exam_date=_iso(0))
    assert planner.today_snapshot()["cram_active"] is True


def test_daily_missions_leer_ohne_stoff(isolated_db):
    from ragapp import student_flow
    assert student_flow.daily_missions() == []


def test_daily_missions_faellige_karten_und_planblock(isolated_db, monkeypatch):
    from ragapp import student_flow, study_plan
    monkeypatch.setattr(study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 40, raising=False)
    monkeypatch.setattr("ragapp.config.settings.PLAN_MAX_DAILY_FOCUS_MIN", 40, raising=False)
    now = _time.time()
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, topic, front, back, "
            "suspended, use_flashcard, reps, created_at, due) "
            "VALUES (?,?,?,?,?,0,1,3,?,?)",
            ("c-due", "BWL", "Kosten", "Fällige Frage zu Kosten", "A", now, now - 3600))
    pid = manifest.create_study_plan(
        title="BWL", subject="BWL", doc_ids=[], deadline=None, daily_minutes=45)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(pid, title="Kapitel Kosten", est_minutes=90)
    manifest.append_plan_block(pid, section_id=sid,
                               planned_date=date.today().isoformat(), planned_min=90)
    missions = student_flow.daily_missions()
    kinds = [m["kind"] for m in missions]
    assert "reviews" in kinds
    assert "plan" in kinds
    plan = next(m for m in missions if m["kind"] == "plan")
    assert plan["minutes"] == 40
    assert plan["reason"]
    assert len(missions) <= 3
    for m in missions:
        assert m["minutes"] > 0 and m["reason"]


def test_daily_missions_bevorzugt_sicher_falsche_karte(isolated_db):
    from ragapp import student_flow
    now = _time.time()
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, created_at, due) VALUES (?,?,?,?,0,1,3,?,?)",
            ("c-over", "BWL", "Frage", "Antwort", now, now - 3600))
    student_flow.record_error(
        source="card", card_id="c-over", subject="BWL", front="Frage",
        detail="Sicher eingeschätzt, aber nicht gewusst")
    mission = student_flow.daily_missions()[0]
    assert mission["kind"] == "reviews"
    assert mission["prefer_overconfidence"] is True
    assert mission["subject"] == "BWL"
    assert mission["card_ids"] == ["c-over"]
    picked = student_flow.today_session_cards(
        subject="BWL", preferred_card_ids=mission["card_ids"])
    assert [c["card_id"] for c in picked] == ["c-over"]


def test_overconfidence_prioritaet_schliesst_andere_faellige_karten_nicht_aus(
        isolated_db):
    from ragapp import student_flow
    now = _time.time()
    with manifest._connect() as conn:
        for cid in ("c-over", "c-due"):
            conn.execute(
                "INSERT INTO review_items (card_id, subject, front, back, "
                "suspended, use_flashcard, reps, created_at, due) "
                "VALUES (?,?,?,?,0,1,3,?,?)",
                (cid, "BWL", cid, "Antwort", now, now - 3600))
    picked = student_flow.today_session_cards(
        subject="BWL", preferred_card_ids=["c-over"], limit=10)
    assert [c["card_id"] for c in picked] == ["c-over", "c-due"]


def test_repair_all_overdue_plans_liefert_vorschau_und_wendet_an(
        isolated_db, monkeypatch):
    from ragapp import student_flow, study_plan
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 60, raising=False)
    monkeypatch.setattr(
        study_plan.settings, "PLAN_REST_WEEKDAYS", [], raising=False)
    pid = manifest.create_study_plan(
        title="Plan", subject=None, doc_ids=[], deadline=None, daily_minutes=60)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(pid, title="Alt", est_minutes=30)
    manifest.append_plan_block(
        pid, section_id=sid, planned_date=_iso(-2), planned_min=30)
    preview = student_flow.repair_all_overdue_plans(apply=False)
    assert preview["moved_blocks"] == 1
    assert len(manifest.list_overdue_plan_blocks(_iso(0))) == 1
    applied = student_flow.repair_all_overdue_plans(apply=True)
    assert applied["moved_blocks"] == 1
    assert manifest.list_overdue_plan_blocks(_iso(0)) == []


def test_all_priorities_ueberspringt_importreste(isolated_db):
    manifest.upsert_exam("31", ects=5)
    manifest.upsert_exam("IT-Recht und IT-Comp", ects=5)
    manifest.upsert_exam("Livetest", exam_date=_iso(4), ects=5)
    manifest.upsert_exam("BWL", exam_date=_iso(10), ects=5)
    prios = planner.all_priorities()
    codes = [p["subject"] for p in prios]
    assert "31" not in codes
    assert "IT-Recht und IT-Comp" not in codes
    assert "Livetest" not in codes
    assert "BWL" in codes


def test_today_snapshot_nimmt_keine_livetest_klausur(isolated_db):
    manifest.upsert_exam("Livetest", exam_date=_iso(3), ects=5)
    manifest.upsert_exam("BWL", exam_date=_iso(20), ects=5)
    snap = planner.today_snapshot()
    assert snap["next_exam"]["subject"] == "BWL"
    assert snap["days_to_exam"] == 20


def test_today_snapshot_ohne_echte_klausur_hat_keinen_termin(isolated_db):
    manifest.upsert_exam("Livetest", exam_date=_iso(3), ects=5)
    snap = planner.today_snapshot()
    assert snap["next_exam"] is None
    assert snap["days_to_exam"] is None
    assert snap["cram_active"] is False
