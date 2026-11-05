"""The generic session surface: ``start``, ``end`` and ``stop ID [KIND]``, the ``session-*`` lines, the input
copy and the ``next`` actions of a session of a kind other than work."""
from __future__ import annotations

import io
import json
import stat
from dataclasses import replace
from datetime import timedelta

import pytest

from cure_job.actions import actions
from cure_job.claude import SessionStatus
from cure_job.errors import ClaudeError
from cure_job.events import SessionEnded, SessionStarted, SessionStopped, decode, encode
from cure_job.kinds import KINDS, WORK, End, Recovery
from cure_job.rules import Artifact
from cure_job.sessions import fold
from cure_job.state import State, derive
from cure_job.store import JobStore
from tests.builders import NOW, listed, make_record
from tests.fakes import fake_id
from tests.test_review_round1 import Harness

A = "261013-1000-video-core-a"
AT = "2026-10-13T17:42:05+00:00"
OLD = timedelta(minutes=5)

PROBE = replace(WORK, name="probe", agent=lambda ctx: None, allow=(), start_states=frozenset({State.APPROVED}),
                start_guards=(), end_guards=(), writes=frozenset(), end=End.EVENT, summary_lines=1,
                recovery=Recovery.RESTART, resumable=False, input="input",
                session_name=lambda job_id, n: f"{job_id}-probe-{n}", prepare=lambda ctx: f"probe {ctx.inputs}")
KINDS_WITH_PROBE = {**KINDS, PROBE.name: PROBE}


# --- event lines ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("event, line", [
    (SessionStarted("probe", 2, "s", NOW, 1, ("input-2.md",)),
     '{"event":"session-started","kind":"probe","n":2,"session":"s","run":1,"inputs":["input-2.md"],"at":"%s"}'),
    (SessionStopped("probe", 2, NOW), '{"event":"session-stopped","kind":"probe","n":2,"at":"%s"}'),
    (SessionEnded("probe", 2, ("one",), NOW),
     '{"event":"session-ended","kind":"probe","n":2,"summary":["one"],"at":"%s"}'),
])
def test_a_session_line_of_another_kind_has_its_shape_and_decodes_back(event, line):
    at = encode(SessionStopped("work", 1, NOW)).split('"at":"')[1][:-2]
    assert encode(event) == line % at
    assert decode(encode(event)) == event


@pytest.mark.parametrize("line", [
    '{"event":"session-started","kind":"work","n":1,"session":"s","run":1,"inputs":[],"at":"%s"}' % AT,
    '{"event":"session-stopped","kind":"work","n":1,"at":"%s"}' % AT,
    '{"event":"session-ended","kind":"work","n":1,"summary":[],"at":"%s"}' % AT,
    '{"event":"session-started","kind":"probe","n":1,"session":"s","run":0,"inputs":[1],"at":"%s"}' % AT,
    '{"event":"session-ended","kind":"probe","n":"1","summary":[],"at":"%s"}' % AT,
])
def test_a_work_session_line_or_a_malformed_one_does_not_read(line):
    with pytest.raises(ValueError):
        decode(line)


def test_session_ended_ends_its_session_and_keeps_the_summary():
    started = SessionStarted("probe", 1, "s", NOW, 0)
    assert fold((started,), has_result=False)[0].ended is False
    session = fold((started, SessionEnded("probe", 1, ("a", "b"), NOW)), has_result=False)[0]
    assert (session.ended, session.summary) == (True, ("a", "b"))


def test_write_input_replaces_the_copy_of_the_same_session_and_is_private(tmp_path):
    store = JobStore(tmp_path / "state")
    store.job_dir(A).mkdir(parents=True)
    store.write_input(A, "input", 1, "first")
    path = store.write_input(A, "input", 1, "second")
    assert path == store.job_dir(A) / "input-1.md"
    assert path.read_text(encoding="utf-8") == "second"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [entry.name for entry in store.job_dir(A).iterdir()] == ["input-1.md"]


# --- start, end, stop -------------------------------------------------------------------------------------------------

@pytest.fixture
def h(root):
    return Harness(root, kinds=KINDS_WITH_PROBE)


def events(h, job_id):
    return [json.loads(line) for line in (h.root / "jobs" / job_id / "dispatch.jsonl").read_text().splitlines()]


def start_probe(h, tmp_path, *extra):
    job_id = h.new(tmp_path)
    source = tmp_path / "input.txt"
    source.write_text("answers", encoding="utf-8")
    assert h.run("start", job_id, "probe", "--input", str(source), *extra) == 0
    return job_id, h.lines[0]


def test_start_prints_the_name_copies_the_input_and_records_the_start(h, tmp_path):
    job_id, name = start_probe(h, tmp_path, "--", "--permission-mode", "auto")
    assert name == f"{job_id}-probe-1"
    assert (h.root / "jobs" / job_id / "input-1.md").read_text(encoding="utf-8") == "answers"
    started = events(h, job_id)[-1]
    assert {key: started[key] for key in ("event", "kind", "n", "session", "run", "inputs")} == {
        "event": "session-started", "kind": "probe", "n": 1, "session": name, "run": 0, "inputs": ["input-1.md"]}
    (started_name, _, prompt, arguments), = h.claude.started
    assert started_name == name and "input-1.md" in prompt
    assert arguments[-2:] == ("--permission-mode", "auto")
    row = h.listed()[job_id]
    assert (row["state"], row["sessions"]["probe"]["liveness"]) == ("approved", "busy")


def test_start_reads_the_input_from_stdin_as_utf8_in_any_locale(h, tmp_path, monkeypatch):
    job_id = h.new(tmp_path)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO("from stdin \u2014 \u00e9".encode("utf-8")),
                                                      encoding="latin-1"))
    assert h.run("start", job_id, "probe", "--input", "-") == 0
    assert (h.root / "jobs" / job_id / "input-1.md").read_text(encoding="utf-8") == "from stdin \u2014 \u00e9"


def test_start_reads_crlf_from_stdin_as_from_a_file(h, tmp_path, monkeypatch):
    from_file, from_stdin = h.new(tmp_path), h.new(tmp_path)
    source = tmp_path / "crlf.md"
    source.write_bytes(b"one\r\ntwo\r\n")
    assert h.run("start", from_file, "probe", "--input", str(source)) == 0
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"one\r\ntwo\r\n"), encoding="latin-1"))
    assert h.run("start", from_stdin, "probe", "--input", "-") == 0
    copied = [(h.root / "jobs" / job_id / "input-1.md").read_bytes() for job_id in (from_file, from_stdin)]
    assert copied == [b"one\ntwo\n", b"one\ntwo\n"]


def test_start_refuses_stdin_that_is_not_utf8(h, tmp_path, monkeypatch, capsys):
    job_id = h.new(tmp_path)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"\xff\xfe"), encoding="latin-1"))
    assert h.run("start", job_id, "probe", "--input", "-") == 1
    assert "cannot read the input -: 'utf-8' codec can't decode" in capsys.readouterr().err
    assert h.claude.started == []


def test_a_failed_start_records_nothing_and_its_retry_reuses_the_number(h, tmp_path):
    job_id = h.new(tmp_path)
    h.claude.fail_start = ClaudeError("down")
    assert h.run("start", job_id, "probe") == 1
    assert all(event["event"] != "session-started" for event in events(h, job_id))
    h.claude.fail_start = None
    assert h.run("start", job_id, "probe") == 0
    assert h.lines == [f"{job_id}-probe-1"]


@pytest.mark.parametrize("command", [["start"], ["end"]])
@pytest.mark.parametrize("kind", ["work", "nope"])
def test_start_and_end_refuse_work_and_an_unknown_kind_as_usage(h, tmp_path, command, kind, capsys):
    job_id = h.new(tmp_path)
    with pytest.raises(SystemExit) as caught:
        h.run(*command, job_id, kind)
    assert caught.value.code == 2
    expected = {"work": f"work {command[0]}s with cure-job {'launch' if command == ['start'] else 'finish'}",
                "nope": "unknown session kind 'nope'; expected goal, probe"}[kind]
    assert expected in capsys.readouterr().err


def test_without_a_kind_beside_work_start_names_no_kind(root, capsys):
    with pytest.raises(SystemExit):
        Harness(root, kinds={WORK.name: WORK}).run("start", A, "probe")
    assert "unknown session kind 'probe'; expected none" in capsys.readouterr().err


def test_start_refuses_an_input_for_a_kind_without_one(root, tmp_path, capsys):
    h = Harness(root, kinds={**KINDS, "probe": replace(PROBE, input=None)})
    job_id = h.new(tmp_path)
    source = tmp_path / "input.txt"
    source.write_text("answers", encoding="utf-8")
    assert h.run("start", job_id, "probe", "--input", str(source)) == 1
    assert "a probe session takes no input" in capsys.readouterr().err
    assert h.claude.started == []


def test_end_records_the_summary_prints_the_notify_line_and_derives_ended(h, tmp_path):
    job_id, name = start_probe(h, tmp_path)
    assert h.run("end", job_id, "probe", "--summary", " settled ") == 0
    assert h.lines == [f'notify: SendMessage dispatcher "job {job_id}"']
    assert {key: events(h, job_id)[-1][key] for key in ("event", "kind", "n", "summary")} == {
        "event": "session-ended", "kind": "probe", "n": 1, "summary": ["settled"]}
    session = h.listed()[job_id]["sessions"]["probe"]
    assert (session["liveness"], session["summary"]) == ("ended", ["settled"])


@pytest.mark.parametrize("started, summary, text", [
    (False, ["one"], "has no open probe session; nothing to end"),
    (True, [], "end of a probe session needs 1 summary line(s), got 0"),
    (True, ["one", "two"], "end of a probe session needs 1 summary line(s), got 2"),
])
def test_end_refuses_without_an_open_session_or_with_the_wrong_summary(h, tmp_path, capsys, started, summary, text):
    job_id = start_probe(h, tmp_path)[0] if started else h.new(tmp_path)
    before = events(h, job_id)
    assert h.run("end", job_id, "probe", *[part for line in summary for part in ("--summary", line)]) == 1
    assert text in capsys.readouterr().err
    assert events(h, job_id) == before


def test_launch_stops_the_ended_probe_session_and_stop_without_a_kind_reports_work_first(h, tmp_path):
    job_id, probe = start_probe(h, tmp_path)
    assert h.run("end", job_id, "probe", "--summary", "done") == 0
    assert h.run("launch", job_id) == 0
    work = h.lines[0]
    assert h.claude.stopped == [fake_id(probe)]
    assert h.run("stop", job_id) == 0
    assert h.lines == [work, f"{probe} not live"]
    assert [event["event"] for event in events(h, job_id)[-2:]] == ["stopped", "session-stopped"]
    assert h.listed()[job_id]["state"] == "lost"


def test_stop_help_names_the_latest_session_of_one_kind_or_every_kind(h, capsys):
    with pytest.raises(SystemExit):
        h.cli.run(["-h"])
    assert "stop the latest session of a job, of one kind or of every kind" in " ".join(capsys.readouterr().out.split())


def test_stop_with_a_kind_stops_only_that_kind(h, tmp_path):
    job_id, probe = start_probe(h, tmp_path)
    assert h.run("stop", job_id, "probe") == 0
    assert h.lines == [probe]
    assert events(h, job_id)[-1]["event"] == "session-stopped"
    assert h.listed()[job_id]["sessions"]["probe"]["liveness"] == "gone"


@pytest.mark.parametrize("kind, text", [("probe", "has no probe session; nothing to stop"),
                                        ("work", "has no work session; nothing to stop")])
def test_stop_with_a_kind_the_job_has_no_session_of_is_refused(h, tmp_path, capsys, kind, text):
    job_id = h.new(tmp_path)
    assert h.run("stop", job_id, kind) == 1
    assert f"job {job_id} {text}" in capsys.readouterr().err


def test_a_session_of_a_kind_this_version_does_not_know_reads_and_gets_no_action(root, tmp_path):
    h = Harness(root)
    job_id = h.new(tmp_path)
    started = SessionStarted("later", 1, f"{job_id}-later", h.clock(), 0)
    with (root / "jobs" / job_id / "dispatch.jsonl").open("a") as log:
        log.write(encode(started) + "\n")
    assert h.listed()[job_id]["sessions"]["later"]["liveness"] == "starting"
    assert h.run("next", "--json") == 0
    assert json.loads(h.lines[0])[0]["actions"] == ["launch"]


# --- next ------------------------------------------------------------------------------------------------------------

def test_next_gives_each_action_its_own_args_when_two_sessions_restart(root, tmp_path):
    second = replace(PROBE, name="second", session_name=lambda job_id, n: f"{job_id}-second-{n}")
    h = Harness(root, kinds={**KINDS_WITH_PROBE, second.name: second})
    job_id = h.new(tmp_path)
    with (root / "jobs" / job_id / "dispatch.jsonl").open("a") as log:
        for kind in (PROBE, second):
            log.write(encode(SessionStarted(kind.name, 1, kind.session_name(job_id, 1), h.clock(), 0,
                                            ("input-1.md",))) + "\n")
    h.clock.advance(OLD)
    assert h.run("next", "--json") == 0
    [row] = json.loads(h.lines[-1])
    assert row["actions"] == ["launch", "restart-session", "restart-session"]
    assert row["args"] == [{}, {"kind": "probe", "inputs": ["input-1.md"], "restarts": 0},
                           {"kind": "second", "inputs": ["input-1.md"], "restarts": 0}]


def probe_record(status, *, kind=PROBE, inputs=("input-1.md",)):
    record = make_record(A, approved=True, events=(SessionStarted(kind.name, 1, "p", NOW - OLD, 0, inputs),))
    view = derive([record], listed({"p": status} if status is not None else {}), NOW, frozenset())[0]
    found = actions(view, {}, kinds={**KINDS, kind.name: kind})
    return {action.name: dict(action.args) for action in found}


@pytest.mark.parametrize("recovery, status, expected", [
    (Recovery.RESTART, SessionStatus.WAITING, {"tell-blocked": {"kind": "probe", "session": "p", "waiting-for": None}}),
    (Recovery.RESTART, SessionStatus.IDLE, {"restart-session": {"kind": "probe", "inputs": ["input-1.md"],
                                                                "restarts": 0}}),
    (Recovery.RESTART, None, {"restart-session": {"kind": "probe", "inputs": ["input-1.md"], "restarts": 0}}),
    (Recovery.ASK, SessionStatus.IDLE, {"confirm-stalled": {"kind": "probe", "session": "p",
                                                            "stalled-confirm-seconds": 60}}),
    (Recovery.ASK, None, {"ask-relaunch": {"kind": "probe", "session": "p"}}),
    (Recovery.ASK, SessionStatus.BUSY, {}),
])
def test_a_session_of_another_kind_gets_the_action_of_its_recovery(recovery, status, expected):
    found = probe_record(status, kind=replace(PROBE, recovery=recovery))
    found.pop("launch", None)
    assert found == expected


@pytest.mark.parametrize("approved, withheld", [(True, "launch"), (False, "ask-approval")])
def test_launch_and_ask_approval_wait_while_a_session_writes_the_goal(approved, withheld):
    writer = replace(PROBE, writes=frozenset({Artifact.GOAL}))
    record = make_record(A, goal=True, approved=approved,
                         events=(SessionStarted(writer.name, 1, "p", NOW - OLD, 0),))
    view = derive([record], listed({"p": SessionStatus.BUSY}), NOW, frozenset())[0]
    assert [action.name for action in actions(view, {})] == [withheld]
    assert [action.name for action in actions(view, {}, kinds={**KINDS, writer.name: writer})] == []
