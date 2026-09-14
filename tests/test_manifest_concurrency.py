"""SQLite-Konfiguration für parallele Streamlit-/Ingestion-Zugriffe."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_manifest_verwendet_wal_und_busy_timeout(isolated_db):
    with manifest._connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 10_000


def test_parallele_manifest_schreibvorgaenge_verlieren_nichts(isolated_db):
    def _write(i: int) -> None:
        manifest.enqueue_index_retry(
            source_path=f"parallel/{i}.pdf", subject="BWL",
            error="Test")

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_write, range(30)))
    assert len(manifest.list_index_retry_jobs(limit=100)) == 30


def test_retry_job_wird_parallel_nur_einmal_beansprucht(isolated_db):
    job_id = manifest.enqueue_index_retry(
        source_path="parallel/einmal.pdf", subject="BWL", error="Test")
    with ThreadPoolExecutor(max_workers=6) as pool:
        claimed = list(pool.map(
            lambda _: manifest.claim_index_retry_job(job_id, force=True),
            range(12)))
    assert claimed.count(True) == 1


def test_abgestuerzter_running_job_wird_nach_lease_neu_beansprucht(isolated_db):
    job_id = manifest.enqueue_index_retry(
        source_path="parallel/stale.pdf", subject="BWL", error="Test")
    assert manifest.claim_index_retry_job(job_id) is True
    assert manifest.claim_index_retry_job(job_id, force=True) is False
    with manifest._connect() as conn:
        conn.execute(
            "UPDATE index_retry_jobs SET updated_at=updated_at-901 "
            "WHERE job_id=?", (job_id,))
    assert manifest.claim_index_retry_job(job_id) is True


def test_heartbeat_verhindert_reclaim_eines_langen_jobs(
        isolated_db, monkeypatch):
    monkeypatch.setattr(manifest.time, "time", lambda: 1000.0)
    job_id = manifest.enqueue_index_retry(
        source_path="parallel/lang.pdf", subject="BWL", error="Test")
    assert manifest.claim_index_retry_job(job_id) is True
    monkeypatch.setattr(manifest.time, "time", lambda: 1800.0)
    assert manifest.heartbeat_index_retry_job(job_id) is True
    monkeypatch.setattr(manifest.time, "time", lambda: 2600.0)
    assert manifest.claim_index_retry_job(job_id, force=True) is False
