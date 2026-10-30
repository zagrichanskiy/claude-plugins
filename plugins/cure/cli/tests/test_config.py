"""Issue 41: ``config.json`` replaces ``defaults.md``.

Each test names the "Done when" item of the issue it pins."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cure_job.claude import SessionStatus
from cure_job.cli import Cli
from cure_job.config import DEFAULTS, plugin_version
from cure_job.goal import PLUGIN_ROOT
from tests.builders import set_age
from tests.test_cli import Harness

BAD_CONFIGS = {
    "unknown-key": ({"bogus": 1}, "bogus", None),
    "wrong-type": ({"split": {"limit": "800"}}, "split.limit", 1200),
    "wrong-type-factor": ({"split": {"factor": "1.5"}}, "split.factor", 1.5),
    "out-of-range": ({"prune": {"failed-days": 0}}, "prune.failed-days", 30),
}


REMOVED_KEY = ".".join(("handoff", "base"))
DROPPED_PRUNE_MESSAGES = {
    "prune.done-days": 'prune: "done-days" is removed; a done job is pruned once its finish is reported '
                       "and its sessions are removed",
    "prune.abandoned-days": 'prune: "abandoned-days" is removed; an abandoned job is pruned once its '
                            "sessions are removed",
}
DROPPED_PRUNE_KEYS = tuple(DROPPED_PRUNE_MESSAGES)
REMOVED_MESSAGE = ('handoff: "base" is removed; a job\'s base is the base stated in the handoff, '
                   "else the repository's default branch")
INIT_DROPPED = ('defaults.md: handoff: "base" is removed; row dropped; a job\'s base is the base stated '
                "in the handoff, else the repository's default branch")


def nest(flat):
    """Turn dotted lookup names into the nested form of ``config.json``."""
    out = {}
    for key, value in flat.items():
        group, _, name = key.partition(".")
        if name:
            out.setdefault(group, {})[name] = value
        else:
            out[group] = value
    return out


@pytest.fixture
def h(root):
    return Harness(root)


def configure(h, data):
    """Write ``config.json`` and rebuild the CLI over the same fakes, as a new process would."""
    h.root.mkdir(parents=True, exist_ok=True)
    (h.root / "config.json").write_text(json.dumps(data), encoding="utf-8")
    reload(h)


def reload(h):
    h.cli = Cli(root=h.root, config_path=h.root / "config.json", claude=h.claude, clock=h.clock, out=h.lines.append)


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
    assert json.loads(h.lines[0]) == nest(DEFAULTS)
    assert len(DEFAULTS) == 17
    assert REMOVED_KEY not in DEFAULTS
    assert not [key for key in DEFAULTS if key in DROPPED_PRUNE_KEYS]


def test_config_get_with_a_key_prints_that_value_as_json(h):
    configure(h, {"handoff": {"resource-risk": [{"scope": "all", "text": "r"}]}, "split": {"limit": 900}})
    assert h.run("config", "get", "split.limit") == 0
    assert h.run("config", "get", "handoff.delivery") == 0
    assert h.lines == ["900", '"commit"']


def test_config_get_split_tracker_without_a_file_prints_github(h):
    assert h.run("config", "get", "split.tracker") == 0
    assert h.lines == ['"github"']


def test_config_get_split_factor_without_a_file_prints_1_5(h):
    assert h.run("config", "get", "split.factor") == 0
    assert h.lines == ["1.5"]


def test_config_get_band_jira_url_without_a_file_prints_the_default(h):
    assert h.run("config", "get", "band.jira-url") == 0
    assert h.lines == ['"https://ienso-team.atlassian.net"']


def test_config_get_band_jira_url_prints_the_file_value(h):
    configure(h, {"band": {"jira-url": "https://example.atlassian.net"}})
    assert h.run("config", "get", "band.jira-url") == 0
    assert h.lines == ['"https://example.atlassian.net"']


@pytest.mark.parametrize("value", ["http://example.atlassian.net", "example.atlassian.net", "", 5])
def test_config_check_rejects_a_band_jira_url_that_is_not_https(h, capsys, value):
    configure(h, {"band": {"jira-url": value}})
    assert h.run("config", "check") == 1
    assert "config.json: band.jira-url: expected an https URL" in capsys.readouterr().err
    assert h.run("config", "get", "band.jira-url") == 0
    assert h.lines[-1] == '"https://ienso-team.atlassian.net"'


def test_config_get_handoff_branch_without_a_file_prints_new(h):
    assert h.run("config", "get", "handoff.branch") == 0
    assert h.lines == ['"new"']


def test_config_get_without_a_key_prints_the_nested_object_with_file_values(h):
    configure(h, {"split": {"limit": 900}})
    assert h.run("config", "get") == 0
    printed = json.loads(h.lines[0])
    assert printed["split"] == {"limit": 900, "factor": 1.5, "tracker": "github", "jira-command": ""}
    assert printed["handoff"] == {"delivery": "commit", "branch": "new", "resource-risk": []}
    assert printed["launch-grace-seconds"] == 60


@pytest.mark.parametrize("tier, rounds", [("Solo", 0), ("Light", 2), ("Full", 3)])
def test_config_get_reviews_tier_without_a_file_prints_its_default_round_count(h, tier, rounds):
    assert h.run("config", "get", f"reviews.{tier}") == 0
    assert h.lines == [str(rounds)]


def test_config_get_without_a_file_prints_the_reviews_group(h):
    assert h.run("config", "get") == 0
    assert json.loads(h.lines[0])["reviews"] == {"Solo": 0, "Light": 2, "Full": 3}


def test_config_get_reviews_tier_prints_the_file_value(h):
    configure(h, {"reviews": {"Full": 5, "Solo": 0}})
    assert h.run("config", "get", "reviews.Full") == 0
    assert h.run("config", "get", "reviews.Light") == 0
    assert h.lines == ["5", "2"]


@pytest.mark.parametrize("value, problem", [
    (0, "0 is below 1"),
    (1.5, "expected an integer, got 1.5"),
    ("2", 'expected an integer, got "2"'),
    (True, "expected an integer, got true"),
])
def test_config_check_rejects_a_reviews_light_value_that_is_not_a_positive_integer(h, capsys, value, problem):
    configure(h, {"reviews": {"Light": value}})
    assert h.run("config", "check") == 1
    assert f"config.json: reviews.Light: {problem}" in capsys.readouterr().err
    assert h.run("config", "get", "reviews.Light") == 0
    assert h.lines[-1] == "2"


@pytest.mark.parametrize("tier, value, problem, default", [
    ("Solo", 1, "1 is outside 0..0", "0"),
    ("Full", 1, "1 is below 2", "3"),
])
def test_config_check_rejects_a_reviews_value_below_its_tier_bound(h, capsys, tier, value, problem, default):
    configure(h, {"reviews": {tier: value}})
    assert h.run("config", "check") == 1
    assert f"config.json: reviews.{tier}: {problem}" in capsys.readouterr().err
    assert h.run("config", "get", f"reviews.{tier}") == 0
    assert h.lines[-1] == default


def test_config_check_accepts_the_lowest_reviews_value_of_each_tier(h):
    configure(h, {"reviews": {"Solo": 0, "Light": 1, "Full": 2}})
    assert h.run("config", "check") == 0
    for tier in ("Solo", "Light", "Full"):
        assert h.run("config", "get", f"reviews.{tier}") == 0
    assert h.lines[-3:] == ["0", "1", "2"]


def test_config_check_rejects_an_unknown_reviews_tier(h, capsys):
    configure(h, {"reviews": {"Huge": 2}})
    assert h.run("config", "check") == 1
    assert "config.json: reviews.Huge: unknown to " in capsys.readouterr().err


def test_config_get_reads_a_nested_top_level_scalar_by_its_name(h):
    configure(h, {"launch-grace-seconds": 30})
    assert h.run("config", "get", "launch-grace-seconds") == 0
    assert h.lines == ["30"]


def test_config_get_of_the_removed_base_key_exits_one(h, capsys):
    assert h.run("config", "get", REMOVED_KEY) == 1
    assert f"error: {REMOVED_MESSAGE}" in capsys.readouterr().err


def test_config_get_with_an_unknown_key_exits_one(h, capsys):
    assert h.run("config", "get", "no.such-key") == 1
    assert "no.such-key" in capsys.readouterr().err


# --- Done when 2 ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["check", "next"])
@pytest.mark.parametrize("data, key, _default", BAD_CONFIGS.values(), ids=BAD_CONFIGS)
def test_done_when_2_config_check_exits_one_and_next_reports_a_config_error_naming_the_key(
        h, capsys, command, data, key, _default):
    configure(h, data)
    if command == "check":
        assert h.run("config", "check") == 1
        assert f"config.json: {key}: " in capsys.readouterr().err
    else:
        assert h.run("next", "--json") == 0
        element = json.loads(h.lines[-1])[-1]
        assert element["id"] is None and element["actions"] == ["config-error"]
        assert any(error.startswith(f"config.json: {key}: ") for error in element["args"]["errors"])


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
    assert written["handoff"]["delivery"] == "pr"
    assert written["handoff"]["resource-risk"] == [{"scope": "device: bench", "text": "battery may drain"}]
    assert written["split"]["limit"] == DEFAULTS["split.limit"]
    assert "handoff.delivery" not in written
    assert "base" not in written["handoff"]
    assert not (h.root / "defaults.md").exists()
    assert (h.root / "defaults.md.bak").read_text(encoding="utf-8") == DEFAULTS_MD
    capsys.readouterr()
    assert h.run("config", "init") == 1
    assert "config.json" in capsys.readouterr().err


def test_config_init_moving_a_config_from_the_old_location_leaves_it_private(h, tmp_path):
    new = tmp_path / "xdg" / "cure" / "config.json"
    h.root.mkdir(parents=True)
    old = h.root / "config.json"
    old.write_text("{}", encoding="utf-8")
    old.chmod(0o644)
    h.cli = Cli(root=h.root, config_path=new, claude=h.claude, clock=h.clock, out=h.lines.append)
    assert h.run("config", "init") == 0
    assert not old.exists()
    assert new.read_text(encoding="utf-8") == "{}"
    assert new.stat().st_mode & 0o777 == 0o600
    assert new.parent.stat().st_mode & 0o777 == 0o700


def test_config_init_without_defaults_md_writes_the_built_in_defaults(h):
    assert h.run("config", "init") == 0
    assert json.loads((h.root / "config.json").read_text(encoding="utf-8")) == nest(DEFAULTS)


# --- Done when 4 ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", DROPPED_PRUNE_KEYS)
def test_done_when_4_a_dropped_prune_key_is_reported_as_removed_and_ignored(h, capsys, key):
    group, _, name = key.partition(".")
    configure(h, {group: {name: 1}})
    assert h.run("list") == 0
    assert f"config.json: {DROPPED_PRUNE_MESSAGES[key]}; ignored" in capsys.readouterr().err


@pytest.mark.parametrize("key", DROPPED_PRUNE_KEYS)
def test_done_when_4_config_get_of_a_dropped_prune_key_exits_one(h, capsys, key):
    assert h.run("config", "get", key) == 1
    assert f"error: {DROPPED_PRUNE_MESSAGES[key]}" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [("config", "check"), ("next", "--json")], ids=["check", "next"])
def test_done_when_4_check_and_next_report_both_dropped_prune_keys(h, capsys, argv):
    configure(h, {"prune": {"done-days": 7, "abandoned-days": 7}})
    if argv[0] == "next":
        assert h.run(*argv) == 0
        reported = "\n".join(json.loads(h.lines[-1])[-1]["args"]["errors"])
    else:
        assert h.run(*argv) == 1
        reported = capsys.readouterr().err
    for message in DROPPED_PRUNE_MESSAGES.values():
        assert f"config.json: {message}" in reported


# --- review finding 9: rejecting branches -------------------------------------------------------------

RISK = {"scope": "all", "text": "r"}
REJECTED = {
    "delivery-unknown": {"handoff": {"delivery": "push"}},
    "branch-not-a-string": {"handoff": {"branch": 3}},
    "tracker-unknown": {"split": {"tracker": "gitlab"}},
    "tracker-not-a-string": {"split": {"tracker": 1}},
    "jira-command-not-a-string": {"split": {"jira-command": 1}},
    "factor-bool": {"split": {"factor": True}},
    "factor-string": {"split": {"factor": "1.5"}},
    "factor-below-range": {"split": {"factor": 0.9}},
    "factor-above-range": {"split": {"factor": 1.95}},
    "factor-two": {"split": {"factor": 2}},
    "factor-three": {"split": {"factor": 3}},
    "tier-unknown": {"dispatcher": {"auto-approve-tiers": ["Solo", "Heavy"]}},
    "tier-duplicate": {"dispatcher": {"auto-approve-tiers": ["Solo", "Solo"]}},
    "tiers-not-a-list": {"dispatcher": {"auto-approve-tiers": "Solo"}},
    "risk-bad-scope": {"handoff": {"resource-risk": [{**RISK, "scope": "device:"}]}},
    "risk-empty-text": {"handoff": {"resource-risk": [{**RISK, "text": "  "}]}},
    "risk-extra-key": {"handoff": {"resource-risk": [{**RISK, "note": "n"}]}},
    "risk-not-a-list": {"handoff": {"resource-risk": RISK}},
}


@pytest.mark.parametrize("data", REJECTED.values(), ids=REJECTED)
def test_a_rejected_value_is_named_by_check_and_replaced_by_its_default_elsewhere(h, capsys, data):
    ((group, inner),) = data.items()
    (name,) = inner
    key = f"{group}.{name}"
    configure(h, data)
    assert h.run("config", "check") == 1
    assert f"config.json: {key}: " in capsys.readouterr().err
    assert run_silently(h, "config", "get", key) == 0
    assert json.loads(h.lines[0]) == DEFAULTS[key]
    assert f"using default {json.dumps(DEFAULTS[key])}" in capsys.readouterr().err


@pytest.mark.parametrize("data", [
    {"handoff": {"delivery": "pr"}}, {"handoff": {"branch": "feature/x"}},
    {"handoff": {"branch": "new"}}, {"handoff": {"branch": "current"}},
    {"dispatcher": {"auto-approve-tiers": []}},
    {"handoff": {"resource-risk": [RISK, {"scope": "repo: /work/a", "text": "t"}]}},
    {"launch-grace-seconds": 30}, {"split": {"limit": 900}},
    {"split": {"tracker": "github"}}, {"split": {"tracker": "jira"}},
    {"split": {"jira-command": "jira-create <title> <body>"}},
    {"split": {"factor": 1}}, {"split": {"factor": 1.0}}, {"split": {"factor": 1.5}}, {"split": {"factor": 1.9}}])
def test_an_accepted_value_passes_check(h, data):
    configure(h, data)
    assert h.run("config", "check") == 0


SHAPE_REJECTED = {
    "flat-key": ({"handoff.delivery": "pr"},
                 ['config.json: handoff.delivery: flat key; write it as {"handoff": {"delivery": ...}}']),
    "flat-scalar-group-key": ({"split.limit": 900},
                              ['config.json: split.limit: flat key; write it as {"split": {"limit": ...}}']),
    "base-flat": ({REMOVED_KEY: "main"}, [f"config.json: {REMOVED_MESSAGE}"]),
    "base-nested": ({"handoff": {"base": "main"}}, [f"config.json: {REMOVED_MESSAGE}"]),
    "unknown-in-group": ({"handoff": {"foo": 1}}, ['handoff.foo']),
    "unknown-top-level": ({"bogus": 1}, ['bogus']),
    "group-not-an-object": ({"handoff": "pr"}, ['handoff']),
    "group-is-a-list": ({"split": [800]}, ['split']),
}


@pytest.mark.parametrize("data, fragments", SHAPE_REJECTED.values(), ids=SHAPE_REJECTED)
def test_config_check_rejects_a_misshapen_file_naming_the_key_and_the_nested_form(h, capsys, data, fragments):
    configure(h, data)
    assert h.run("config", "check") == 1
    err = capsys.readouterr().err
    for fragment in fragments:
        assert fragment in err


def test_a_flat_key_value_is_not_read_as_a_nested_value(h):
    configure(h, {"split.limit": 900})
    assert run_silently(h, "config", "get", "split.limit") == 0
    assert h.lines == [str(DEFAULTS["split.limit"])]


def test_a_value_beside_a_rejected_key_is_still_read(h):
    configure(h, {"handoff": {"foo": 1, "delivery": "pr"}})
    assert run_silently(h, "config", "get", "handoff.delivery") == 0
    assert h.lines == ['"pr"']


WHOLE_FILE = {
    "invalid-json": ("{not json", "invalid JSON"),
    "not-an-object": ("[1]", "not a JSON object"),
}


@pytest.mark.parametrize("text, problem", WHOLE_FILE.values(), ids=WHOLE_FILE)
def test_a_whole_file_error_stops_check_and_falls_back_to_every_default_elsewhere(h, capsys, text, problem):
    h.root.mkdir(parents=True)
    (h.root / "config.json").write_text(text, encoding="utf-8")
    reload(h)
    assert h.run("config", "check") == 1
    assert f"config.json: {problem}" in capsys.readouterr().err
    assert h.run("list") == 0
    err = capsys.readouterr().err
    assert f"config.json: {problem}" in err
    assert err.rstrip().endswith("; using every default")


def test_an_unreadable_config_file_is_a_whole_file_error(h, capsys):
    (h.root / "config.json").mkdir(parents=True)
    reload(h)
    assert h.run("config", "check") == 1
    assert "config.json: cannot read" in capsys.readouterr().err
    assert h.run("list") == 0
    assert "; using every default" in capsys.readouterr().err


def test_an_unknown_key_is_reported_as_ignored_by_a_lenient_command(h, capsys):
    configure(h, {"handoff": {"bogus": 1}})
    assert h.run("list") == 0
    version = plugin_version(PLUGIN_ROOT)
    assert (f"config.json: handoff.bogus: unknown to cure {version}; restart the dispatcher after an update; ignored"
            in capsys.readouterr().err)


def test_a_file_with_flat_and_nested_base_prints_the_removed_line_once(h, capsys):
    configure(h, {REMOVED_KEY: "main", "handoff": {"base": "main"}})
    assert h.run("config", "check") == 1
    assert capsys.readouterr().err.count(REMOVED_MESSAGE) == 1


@pytest.mark.parametrize("data", [{REMOVED_KEY: "main"}, {"handoff": {"base": "main"}}], ids=["flat", "nested"])
def test_a_lenient_command_reports_the_removed_key_as_ignored(h, capsys, data):
    configure(h, data)
    assert h.run("list") == 0
    assert f"config.json: {REMOVED_MESSAGE}; ignored" in capsys.readouterr().err


def init_refused(h, capsys, defaults_md, expect="error:"):
    h.root.mkdir(parents=True)
    (h.root / "defaults.md").write_text(defaults_md, encoding="utf-8")
    assert h.run("config", "init") == 1
    assert expect in capsys.readouterr().err
    assert not (h.root / "config.json").exists()
    assert (h.root / "defaults.md").read_text(encoding="utf-8") == defaults_md
    assert not (h.root / "defaults.md.bak").exists()


def table(*rows):
    return "| key | value | scope |\n|---|---|---|\n" + "".join(row + "\n" for row in rows)


INIT_REFUSED = {
    "delivery-scoped": "| delivery | pr | device: bench |",
    "branch-scoped": "| branch | feature | device: bench |",
    "invalid-value": "| delivery | push | all |",
    "escaped-pipe": "| resource risk | a \\| b | all |",
    "no-leading-pipe": "delivery | pr | all |",
    "two-cells": "| delivery | pr |",
    "four-cells": "| delivery | pr | all | extra |",
    "empty-key": "|  | pr | all |",
}


@pytest.mark.parametrize("row", ["| base | develop | all |", "| base | develop | repo: /work/a |"])
def test_config_init_drops_a_base_row_with_a_notice_and_succeeds(h, capsys, row):
    h.root.mkdir(parents=True)
    (h.root / "defaults.md").write_text(table(row, "| delivery | pr | all |"), encoding="utf-8")
    assert h.run("config", "init") == 0
    assert INIT_DROPPED in capsys.readouterr().err
    written = json.loads((h.root / "config.json").read_text(encoding="utf-8"))
    assert "base" not in written["handoff"]
    assert written["handoff"]["delivery"] == "pr"


@pytest.mark.parametrize("row", INIT_REFUSED.values(), ids=INIT_REFUSED)
def test_config_init_refuses_a_defaults_md_it_cannot_convert_and_writes_nothing(h, capsys, row):
    init_refused(h, capsys, table(row))


# --- prune retention by state --------------------------------------------------------------------------

@pytest.mark.parametrize("age, pruned", [(timedelta(days=1), False), (timedelta(days=1, seconds=1), True)])
def test_prune_failed_days_sets_the_retention_of_a_failed_job(h, tmp_path, age, pruned):
    job_id = launched_job(h, tmp_path)
    assert h.run("finish", job_id, "--status", "failed") == 0
    configure(h, {"prune": {"failed-days": 1}})
    set_age(h.root / "jobs" / job_id / "result.md", h.clock(), age)
    assert run_silently(h, "prune") == 0
    assert (h.lines == [job_id]) is pruned
    assert (h.root / "jobs" / job_id).exists() is not pruned


# --- consumers of the values ---------------------------------------------------------------------------

def test_stalled_confirm_seconds_reaches_the_confirm_stalled_args_of_next(h, tmp_path):
    job_id = launched_job(h, tmp_path)
    configure(h, {"dispatcher": {"stalled-confirm-seconds": 120}})
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
