"""Builders for hand-made job records and job directories, shared by the state and provider tests."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cure_job.events import Event
from cure_job.handoff import Device, Handoff
from cure_job.job import JobRecord
from cure_job.result import Result, ResultStatus

NOW = datetime(2026, 10, 13, 18, 0, 0, tzinfo=timezone.utc)
REPO = "/work/video-core"


def handoff_text(repos=(REPO,), device="none") -> str:
    lines = ["---", "repos:"] + [f"  - {repo}" for repo in repos] + [f"device: {device}", "---", "", "# Outcome", ""]
    return "\n".join(lines)


def make_record(job_id: str, *, repos=(REPO,), device: Device = Device.NONE, goal: bool = False,
                events: tuple[Event, ...] = (), result: Result | None = None,
                result_mtime: datetime | None = None, events_mtime: datetime | None = None) -> JobRecord:
    return JobRecord(
        id=job_id, dir=Path("/state/jobs") / job_id, handoff=Handoff(tuple(repos), device),
        has_goal=goal, events=tuple(events), result=result,
        result_mtime=result_mtime if result is not None else None, events_mtime=events_mtime,
    )


def result_of(status: ResultStatus, unproven: tuple[str, ...] = (), problem: str | None = None) -> Result:
    return Result(status, unproven, problem)


def set_age(path: Path, now: datetime, age: timedelta) -> None:
    """Back-date ``path`` so that its mtime is ``age`` before ``now``."""
    stamp = (now - age).timestamp()
    os.utime(path, (stamp, stamp))
