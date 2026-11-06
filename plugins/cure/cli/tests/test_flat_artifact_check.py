"""``flat-artifact-check.sh``: work-item and step references are allowed, other bare identifiers are denied."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "flat-artifact-check.sh"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("sh", "perl", "jq")),
    reason="the hook needs sh, perl and jq",
)


def run_hook(message):
    command = 'git commit -m "' + message + '"'
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    "message",
    [
        "Fix the parser for work item 3",
        "Cover work items 2.1",
        "Close Work Item 5",
        "Finish step 2",
        "Finish steps 3-5",
    ],
)
def test_work_item_and_step_references_are_allowed(message):
    result = run_hook(message)

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "tool_name, tool_input",
    [
        ("Bash", {"command": 'gh pr create --body "Fix the parser for work item 3"'}),
        ("Bash", {"command": 'gh pr create --body "Finish steps 3-5"'}),
        ("mcp__claude_ai_ClickUp__clickup_create_task", {"description": "Fix the parser for work item 3"}),
        ("mcp__claude_ai_ClickUp__clickup_create_task", {"description": "Finish steps 3-5"}),
    ],
)
def test_references_are_denied_outside_commit_messages(tool_name, tool_input):
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    result = subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, check=False
    )

    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "bare identifier: " in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "message, identifier",
    [
        ("Fix item 4", "item 4"),
        ("Finish task 7", "task 7"),
        ("Track RND-12", "RND-12"),
    ],
)
def test_other_bare_identifiers_are_denied(message, identifier):
    result = run_hook(message)

    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "bare identifier: " + identifier in output["permissionDecisionReason"]


def run_tool(tool_name, tool_input):
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__claude_ai_ClickUp__get_task_comments",
        "mcp__claude_ai_ClickUp__get_task",
        "mcp__tracker2__get_task_comments",
        "mcp__slack__get_task",
    ],
)
def test_mcp_read_with_bare_identifier_in_id_passes(tool_name):
    result = run_tool(tool_name, {"task_id": "RND-123"})

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "tool_name, tool_input",
    [
        ("mcp__claude_ai_ClickUp__create_task_comment", {"task_id": "RND-123", "comment_text": "Fix the parser"}),
        ("mcp__claude_ai_ClickUp__update_task", {"task_id": "RND-123", "description": "Fix the parser"}),
        ("mcp__tracker2__create_task_comment", {"task_id": "RND-123", "comment_text": "Fix the parser"}),
        ("mcp__slack__updateTask", {"issue_id": "RND-123", "description": "Fix the parser"}),
    ],
)
def test_mcp_write_with_bare_identifier_in_id_and_clean_prose_passes(tool_name, tool_input):
    result = run_tool(tool_name, tool_input)

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "tool_name, tool_input",
    [
        ("mcp__claude_ai_ClickUp__create_task_comment", {"task_id": "RND-1", "comment_text": "Blocks RND-123"}),
        ("mcp__claude_ai_ClickUp__update_task", {"task_id": "RND-1", "description": "Blocks RND-123"}),
        (
            "mcp__claude_ai_ClickUp__create_task_comment",
            {"task_id": "RND-1", "content": [{"type": "text", "text": "Blocks RND-123"}]},
        ),
        ("mcp__tracker2__create_task_comment", {"task_id": "RND-1", "comment_text": "Blocks RND-123"}),
        ("mcp__slack__update_task", {"task_id": "RND-1", "description": "Blocks RND-123"}),
        (
            "mcp__slack__post_message",
            {"channel": "C1", "content": [{"type": "text", "text": "Blocks RND-123"}]},
        ),
    ],
)
def test_mcp_write_with_bare_identifier_in_prose_is_denied(tool_name, tool_input):
    result = run_tool(tool_name, tool_input)

    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "bare identifier: RND-123" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__claude_ai_ClickUp__delete_task",
        "mcp__claude_ai_ClickUp__creator_lookup",
        "mcp__tracker2__search_tasks",
    ],
)
def test_mcp_tool_without_write_verb_passes(tool_name):
    result = run_tool(tool_name, {"task_id": "RND-1", "description": "Blocks RND-123"})

    assert result.returncode == 0
    assert result.stdout == ""
