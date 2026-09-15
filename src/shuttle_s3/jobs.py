from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SavedJob:
    name: str
    profile: str
    bucket: str
    source: str
    destination: str
    mode: str = "download"
    overwrite: bool = False


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[SavedJob]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            jobs = [SavedJob(**item) for item in raw]
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            return []
        return sorted(jobs, key=lambda job: job.name.casefold())

    def save_all(self, jobs: list[SavedJob]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps([asdict(job) for job in jobs], indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

