from pathlib import Path

from shuttle_s3.jobs import JobStore, SavedJob


def test_round_trip_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "nested" / "jobs.json")
    job = SavedJob(
        name="Monthly reports",
        profile="analyst",
        bucket="reports",
        source="monthly/",
        destination="/tmp/reports",
        mode="mirror",
        overwrite=True,
    )
    store.save_all([job])
    assert store.load() == [job]


def test_invalid_json_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("{not json", encoding="utf-8")
    assert JobStore(path).load() == []

