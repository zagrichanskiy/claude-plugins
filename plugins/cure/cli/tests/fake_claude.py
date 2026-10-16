#!/usr/bin/env python3
"""Stand-in for the ``claude`` binary, driven by ``$FAKE_CLAUDE_STATE``.

Every call is appended to ``calls.jsonl``. ``agents --json --all`` prints ``agents.json`` (``[]`` when absent);
``--bg --name NAME ... PROMPT`` registers a live background session; ``--bg --resume UUID ... PROMPT`` gives
the entry with that ``sessionId`` a ``pid`` again; ``stop ID`` removes the ``pid`` of the live entry with that
``id``; ``rm ID`` deletes every entry with that ``id``. Each of the last three exits 1 when no entry matches;
anything else exits 2."""
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
        short = f"{len(agents) + 1:08x}"
        agents.append({"id": short, "sessionId": f"{short}-uuid", "name": argv[2], "pid": os.getpid(),
                       "state": "working", "status": "busy", "kind": "background"})
        with open(agents_path, "w", encoding="utf-8") as handle:
            json.dump(agents, handle)
        print("started " + argv[2])
        return 0
    if len(argv) >= 4 and argv[0] == "--bg" and argv[1] == "--resume":
        return _change(agents_path, lambda agent: agent.get("sessionId") == argv[2],
                       lambda agents, agent: agent.update(pid=os.getpid(), status="busy"), argv[2])
    if len(argv) == 2 and argv[0] == "rm":
        return _change(agents_path, lambda agent: agent.get("id") == argv[1],
                       lambda agents, agent: agents.remove(agent), argv[1])
    if len(argv) == 2 and argv[0] == "stop":
        agents = []
        if os.path.exists(agents_path):
            with open(agents_path, encoding="utf-8") as handle:
                agents = json.load(handle)
        live = [agent for agent in agents if agent.get("id") == argv[1] and "pid" in agent]
        if not live:
            sys.stderr.write(f"no live session {argv[1]}\n")
            return 1
        for agent in live:
            del agent["pid"]
        with open(agents_path, "w", encoding="utf-8") as handle:
            json.dump(agents, handle)
        print("stopped " + argv[1])
        return 0
    return 2


def _change(agents_path, matches, change, key):
    agents = []
    if os.path.exists(agents_path):
        with open(agents_path, encoding="utf-8") as handle:
            agents = json.load(handle)
    found = [agent for agent in agents if matches(agent)]
    if not found:
        sys.stderr.write(f"no session {key}\n")
        return 1
    for agent in found:
        change(agents, agent)
    with open(agents_path, "w", encoding="utf-8") as handle:
        json.dump(agents, handle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
