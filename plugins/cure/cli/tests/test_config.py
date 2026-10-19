"""Issue 41: ``config.json`` replaces ``defaults.md``.

Each test names the "Done when" item of the issue it pins."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cure_job.claude import SessionStatus
from cure_job.cli import Cli
from cure_job.config import DEFAULTS
from tests.builders import set_age
from tests.test_cli import Harness

BAD_CONFIGS = {
    "unknown-key": ({"bogus.key": 1}, "bogus.key", None),
    "wrong-type": ({"split.limit": "800"}, "split.limit", 800),
    "out-of-range": ({"prune.done-days": 0}, "prune.done-days", 14),
}


@pytest.fixture
def h(root):
    return Harness(root)


def configure(h, data):
    """Write ``config.json`` and rebuild the CLI over the same fakes, as a new process would."""
    h.root.mkdir(parents=True, exist_ok=True)
    (h.root / "config.json").write_text(json.dumps(data), encoding="utf-8")
    h.cli = Cli(root=h.root, claude=h.claude, clock=h.clock, out=h.lines.append)


def launched_job(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    return job_id


def run_silently(h, *argv):
    h.lines.clear()
    return h.run(*argv)


# --- Done when 1 ---------------------------------------------------------------------------------------

def test_done_when_1_config_get_without_a_file_prints_every_key_with_its_default(h):
    assert h.run("config", "get") == 0
    assert json.loads(h.lines[0]) == DEFAULTS
    assert len(DEFAULTS) == 13


def test_config_get_with_a_key_prints_that_value_as_json(h):
    configure(h, {"handoff.resource-risk": [{"scope": "all", "text": "r"}], "split.limit": 900})
    assert h.run("config", "get", "split.limit") == 0
    assert h.run("config", "get", "handoff.delivery") == 0
    assert h.lines == ["900", '"commit"']


def test_config_get_with_an_unknown_key_exits_one(h, capsys):
    assert h.run("config", "get", "no.such-key") == 1
    assert "no.such-key" in capsys.readouterr().err


# --- Done when 2 ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["check", "next"])
@pytest.mark.parametrize("data, key, _default", BAD_CONFIGS.values(), ids=BAD_CONFIGS)
def test_done_when_2_config_check_and_next_exit_one_naming_the_key(h, capsys, command, data, key, _default):
    configure(h, data)
    argv = ("config", "check") if command == "check" else ("next", "--json")
    assert h.run(*argv) == 1
    assert f"config.json: {key}: " in capsys.readouterr().err


def test_config_check_without_a_file_exits_zero(h):
    assert h.run("config", "check") == 0


@pytest.mark.parametrize("data, key, default", BAD_CONFIGS.values(), ids=BAD_CONFIGS)
@pytest.mark.parametrize("command", ["list", "claim", "release", "finish"])
def test_done_when_2_other_commands_exit_zero_and_report_the_default_used(
        h, tmp_path, capsys, command, data, key, default):
    job_id = launched_job(h, tmp_path)
    if command == "release":
        assert h.run("claim", job_id, "device:bench") == 0
    configure(h, data)
    argv = {"list": ("list",), "claim": ("claim", job_id, "device:bench"), "release": ("release", job_id, "device:bench"),
            "finish": ("finish", job_id, "--status", "done")}[command]
    capsys.readouterr()
    assert h.run(*argv) == 0
    err = capsys.readouterr().err
    assert f"config.json: {key}: " in err
    if default is not None:
        assert f"using default {default}" in err


# --- Done when 3 ---------------------------------------------------------------------------------------

DEFAULTS_MD = """# Defaults

| key | value | scope |
|---|---|---|
| delivery | pr | all |
| resource risk | battery may drain | device: bench |
"""


def test_done_when_3_config_init_converts_defaults_md_and_a_second_init_exits_one(h, capsys):
    h.root.mkdir(parents=True)
    (h.root / "defaults.md").write_text(DEFAULTS_MD, encoding="utf-8")
    assert h.run("config", "init") == 0
    written = json.loads((h.root / "config.json").read_text(encoding="utf-8"))
    assert written["handoff.delivery"] == "pr"
    assert written["handoff.resource-risk"] == [{"scope": "device: bench", "text": "battery may drain"}]
    assert written["split.limit"] == DEFAULTS["split.limit"]
    assert not (h.root / "defaults.md").exists()
    assert (h.root / "defaults.md.bak").read_text(encoding="utf-8") == DEFAULTS_MD
    capsys.readouterr()
    assert h.run("config", "init") == 1
    assert "config.json" in capsys.readouterr().err


def test_config_init_without_defaults_md_writes_the_built_in_defaults(h):
    assert h.run("config", "init") == 0
    assert json.loads((h.root / "config.json").read_text(encoding="utf-8")) == DEFAULTS


# --- Done when 4 ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("age, pruned", [(timedelta(days=1), False), (timedelta(days=1, seconds=1), True)])
def test_done_when_4_prune_done_days_one_prunes_a_done_job_only_after_one_day(h, tmp_path, age, pruned):
    job_id = launched_job(h, tmp_path)
    assert h.run("finish", job_id, "--status", "done") == 0
    configure(h, {"prune.done-days": 1})
    set_age(h.root / "jobs" / job_id / "result.md", h.clock(), age)
    assert run_silently(h, "prune") == 0
    assert (h.lines == [job_id]) is pruned
    assert (h.root / "jobs" / job_id).exists() is not pruned


# --- consumers of the values ---------------------------------------------------------------------------

def test_stalled_confirm_seconds_reaches_the_confirm_stalled_args_of_next(h, tmp_path):
    job_id = launched_job(h, tmp_path)
    configure(h, {"dispatcher.stalled-confirm-seconds": 120})
    h.claude.statuses[job_id] = SessionStatus.IDLE
    h.clock.advance(timedelta(minutes=5))
    assert run_silently(h, "next", "--json") == 0
    (row,) = json.loads(h.lines[0])
    assert row["args"]["confirm-stalled"] == {"stalled-confirm-seconds": 120}


@pytest.mark.parametrize("seconds, state", [(30, "running"), (31, "stalled")])
def test_launch_grace_seconds_sets_when_an_idle_session_is_stalled(h, tmp_path, seconds, state):
    job_id = launched_job(h, tmp_path)
    configure(h, {"launch-grace-seconds": 30})
    h.claude.statuses[job_id] = SessionStatus.IDLE
    h.clock.advance(timedelta(seconds=seconds))
    assert run_silently(h, "list", "--json") == 0
    (row,) = json.loads(h.lines[0])
    assert row["state"] == state
