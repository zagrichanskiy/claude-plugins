"""``SessionRunner`` and the kind declarations: settings bytes, start order and the stop of ended sessions."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from cure_job.claude import SessionStatus
from cure_job.errors import PluginError
from cure_job.events import SessionStarted
from cure_job.kinds import KINDS, WORK, End, StartContext, settings_arguments
from cure_job.providers.jobs import JobsProvider
from cure_job.runner import SessionRunner
from cure_job.store import JobStore
from tests.builders import NOW, handoff_text, make_record
from tests.fakes import FakeClaude, FakeClock, fake_id

JOB = "261013-1000-video-core-a"
PLUGIN = Path("/plugins/cure")
NEEDS_INPUT = "---\nstatus: needs-input\nquestion: which?\n---\n"

#: ``WorkerSettings(Path("/plugins/cure"), JOB).arguments()[1]`` as commit c0eee6f prints it.
MAIN_WORK_SETTINGS = (
    '{"permissions":{"allow":["Bash(/plugins/cure/bin/cure-job finish 261013-1000-video-core-a *)",'
    '"Bash(/plugins/cure/bin/cure-job claim 261013-1000-video-core-a *)",'
    '"Bash(/plugins/cure/bin/cure-job release 261013-1000-video-core-a *)",'
    '"Bash(/plugins/cure/bin/cure-job config get *)","Bash(/plugins/cure/bin/cure-job list *)",'
    '"Bash(/plugins/cure/bin/cure-job finish --help)"]},"env":{"CURE_JOB_ID":"261013-1000-video-core-a"}}'
)


def context() -> StartContext:
    return StartContext(make_record(JOB), None, PLUGIN, "launch", 1, JOB, {})


def test_work_settings_are_byte_identical_to_main():
    assert settings_arguments(WORK, context()) == ["--settings", MAIN_WORK_SETTINGS]


def test_only_work_ends_with_the_result():
    assert [kind.name for kind in KINDS.values() if kind.end is End.RESULT] == ["work"]


@pytest.mark.parametrize("deny, expected_deny", [
    ((), None),
    (("Bash(rm {job_dir} *)",), [f"Bash(rm /state/jobs/{JOB} *)"]),
])
@pytest.mark.parametrize("summary_lines, bare", [(0, [f"Bash(/plugins/cure/bin/cure-job end {JOB} probe)"]), (1, [])])
def test_an_event_kind_gets_its_end_rule_and_a_deny_key_only_when_it_denies(deny, expected_deny, summary_lines, bare):
    kind = replace(WORK, name="probe", end=End.EVENT, allow=("Bash({cure_job} list *)",), deny=deny,
                   summary_lines=summary_lines)
    settings = json.loads(settings_arguments(kind, context())[1])
    assert list(settings) == ["permissions", "env"]
    assert settings["permissions"]["allow"] == ["Bash(/plugins/cure/bin/cure-job list *)", *bare,
                                                f"Bash(/plugins/cure/bin/cure-job end {JOB} probe *)"]
    assert settings["permissions"].get("deny") == expected_deny
    assert ("deny" in settings["permissions"]) is bool(deny)


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "state")


@pytest.fixture
def claude():
    return FakeClaude()


def needs_input_job(store, claude, clock) -> str:
    """A job whose run 1 ended needs-input while its session is still listed live."""
    job_id = JobsProvider(store, claude, clock).new(handoff_text(), "x")
    store.goal_path(job_id).write_text("goal", encoding="utf-8")
    store.append_event(job_id, SessionStarted("work", 1, job_id, NOW, 1))
    store.result_path(job_id).write_text(NEEDS_INPUT, encoding="utf-8")
    claude.statuses[job_id] = SessionStatus.IDLE
    return job_id


def test_a_refused_resume_stops_nothing_and_archives_nothing(store, claude, tmp_path):
    clock = FakeClock(NOW)
    job_id = needs_input_job(store, claude, clock)
    jobs = JobsProvider(store, claude, clock, plugin_root=tmp_path / "no-plugin")
    with pytest.raises(PluginError):
        jobs.resume(job_id)
    assert claude.stopped == [] and claude.resumed == []
    assert store.result_path(job_id).read_text(encoding="utf-8") == NEEDS_INPUT


@pytest.mark.parametrize("resumable", [True, False])
def test_a_start_stops_a_live_ended_session_only_of_a_kind_that_is_not_resumable(store, claude, resumable):
    clock = FakeClock(NOW)
    job_id = needs_input_job(store, claude, clock)
    kind = replace(WORK, resumable=resumable, prepare=lambda ctx: "prompt", agent=lambda ctx: None)
    runner = SessionRunner(store, claude, clock, PLUGIN, lambda seconds: None, lambda: 0.0, kinds={"work": kind})
    assert runner.start(store.load(job_id), kind, "launch") == f"{job_id}-r2"
    assert claude.stopped == ([] if resumable else [fake_id(job_id)])
    assert store.job_dir(job_id).joinpath("result-1.md").read_text(encoding="utf-8") == NEEDS_INPUT
