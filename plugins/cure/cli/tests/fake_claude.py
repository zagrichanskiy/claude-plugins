#!/usr/bin/env python3
"""Stand-in for the ``claude`` binary, driven by ``$FAKE_CLAUDE_STATE``.

Every call is appended to ``calls.jsonl``. ``agents --json --all`` prints ``agents.json`` (``[]`` when absent);
``--bg --name NAME ... PROMPT`` registers a live background session; anything else exits 2."""
import json
import os
import sys


def main(argv):
    state = os.environ["FAKE_CLAUDE_STATE"]
    with open(os.path.join(state, "calls.jsonl"), "a", encoding="utf-8") as calls:
        calls.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\n")
    agents_path = os.path.join(state, "agents.json")
    if argv == ["agents", "--json", "--all"]:
        if os.path.exists(agents_path):
            with open(agents_path, encoding="utf-8") as handle:
                sys.stdout.write(handle.read())
        else:
            sys.stdout.write("[]")
        return 0
    if len(argv) >= 4 and argv[0] == "--bg" and argv[1] == "--name":
        agents = []
        if os.path.exists(agents_path):
            with open(agents_path, encoding="utf-8") as handle:
                agents = json.load(handle)
        agents.append({"name": argv[2], "pid": os.getpid(), "state": "working", "status": "busy",
                       "kind": "background"})
        with open(agents_path, "w", encoding="utf-8") as handle:
            json.dump(agents, handle)
        print("started " + argv[2])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
