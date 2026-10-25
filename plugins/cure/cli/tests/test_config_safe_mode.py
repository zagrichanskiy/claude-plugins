"""Issue 79: a config error puts cure in safe mode; ``config.json`` lives under ``~/.config/cure``.

Each test names the "Done when" item of the issue it pins."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cure_job import config
from cure_job.cli import Cli, main
from tests.test_cli import Harness, _launched, _write_result
from tests.test_config import configure, nest, reload

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
BAD_VALUE = json.dumps({"prune": {"failed-days": 90}, "split": {"limit": "x"}})
BROKEN_FILES = {"bad-value": BAD_VALUE, "truncated": '{"prune": {'}


@pytest.fixture
def h(root):
    return Harness(root)


def write_raw(h, text):
    h.root.mkdir(parents=True, exist_ok=True)
    (h.root / "config.json").write_text(text, encoding="utf-8")
    reload(h)


def finished_job(h, tmp_path):
    job_id = _launched(h, tmp_path)
    _write_result(h, job_id, "---\nstatus: done\n---\n")
    assert h.run("reported", job_id) == 0
    assert h.run("remove-sessions", job_id) == 0
    return job_id


@pytest.mark.parametrize("text", BROKEN_FILES.values(), ids=BROKEN_FILES)
def test_done_when_1_prune_removes_no_job_and_exits_one_on_a_config_error(h, tmp_path, capsys, text):
    job_id = finished_job(h, tmp_path)
    write_raw(h, text)
    assert h.run("prune") == 1
    assert (h.root / "jobs" / job_id).is_dir()
    err = capsys.readouterr().err
    assert "no job removed" in err
    if text == BAD_VALUE:
        assert "config.json: split.limit: " in err


def test_done_when_2_config_get_reads_the_valid_key_beside_a_bad_one(h):
    write_raw(h, BAD_VALUE)
    assert h.run("config", "get", "prune.failed-days") == 0
    assert h.lines == ["90"]


@pytest.mark.parametrize("text", BROKEN_FILES.values(), ids=BROKEN_FILES)
def test_done_when_3_next_reports_config_error_and_approve_auto_exits_one(h, tmp_path, text):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    write_raw(h, text)
    assert h.run("next", "--json") == 0
    assert any(e["id"] is None and e["actions"] == ["config-error"] for e in json.loads(h.lines[-1]))
    assert h.run("approve", job_id, "--by", "auto") == 1
    h.lines.clear()
    assert h.run("list") == 0
    assert h.lines[0].endswith("awaiting-approval")


def test_done_when_4_an_unknown_key_is_safe_mode_for_next_and_an_error_for_check(h, capsys):
    version = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    write_raw(h, '{"no-such-key": 1}')
    assert h.run("next", "--json") == 0
    assert json.loads(h.lines[-1])[-1]["actions"] == ["config-error"]
    capsys.readouterr()
    assert h.run("config", "check") == 1
    assert f"unknown to cure {version}" in capsys.readouterr().err


def test_done_when_5_config_example_json_equals_config_get_and_example(h):
    on_disk = json.loads((PLUGIN_ROOT / "skills" / "dispatch" / "config.example.json").read_text(encoding="utf-8"))
    assert h.run("config", "get") == 0
    assert on_disk == json.loads(h.lines[0]) == json.loads(config.example()) == nest(config.DEFAULTS)


def test_done_when_6_the_harness_ignores_a_broken_file_named_by_the_environment(tmp_path_factory, root, monkeypatch):
    outside = tmp_path_factory.mktemp("outside") / "config.json"
    outside.write_text("{", encoding="utf-8")
    monkeypatch.setenv("CURE_JOB_CONFIG", str(outside))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(outside.parent))
    h = Harness(root)
    assert h.run("config", "check") == 0


@pytest.fixture
def seen_path(monkeypatch):
    seen = []

    def fake_init(self, *, root, config_path, **kwargs):
        seen.append(config_path)

    monkeypatch.setattr(Cli, "__init__", fake_init)
    monkeypatch.setattr(Cli, "run", lambda self, argv: 0)
    return seen


def test_done_when_6_main_resolves_the_config_path_from_the_environment(seen_path, tmp_path, monkeypatch):
    monkeypatch.setenv("CURE_JOB_CONFIG", str(tmp_path / "explicit.json"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    main([])
    monkeypatch.delenv("CURE_JOB_CONFIG")
    main([])
    monkeypatch.delenv("XDG_CONFIG_HOME")
    main([])
    assert seen_path == [tmp_path / "explicit.json", tmp_path / "xdg" / "cure" / "config.json",
                         tmp_path / "home" / ".config" / "cure" / "config.json"]


def test_done_when_7_config_init_moves_the_old_file_when_the_new_path_is_free(root, tmp_path):
    h = Harness(root)
    h.cli = Cli(root=root, config_path=tmp_path / "new" / "config.json", claude=h.claude, out=h.lines.append)
    root.mkdir(parents=True)
    (root / "config.json").write_text('{"split": {"limit": 900}}', encoding="utf-8")
    assert h.run("config", "init") == 0
    assert not (root / "config.json").exists()
    assert json.loads((tmp_path / "new" / "config.json").read_text(encoding="utf-8")) == {"split": {"limit": 900}}


def test_done_when_7_config_init_leaves_both_files_when_the_new_path_exists(root, tmp_path):
    h = Harness(root)
    new = tmp_path / "new" / "config.json"
    h.cli = Cli(root=root, config_path=new, claude=h.claude, out=h.lines.append)
    root.mkdir(parents=True)
    new.parent.mkdir()
    (root / "config.json").write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    assert h.run("config", "init") == 1
    assert (root / "config.json").read_text(encoding="utf-8") == "old"
    assert new.read_text(encoding="utf-8") == "new"
