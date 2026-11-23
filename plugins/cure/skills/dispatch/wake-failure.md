# Dispatch: SendMessage to the dispatcher failed

A message does not reach a stopped session.

1. Run `claude agents --json`. If an entry named `dispatcher` is live (it has a `pid`), start nothing. Tell the user the message failed and the job is queued.
2. Otherwise start the dispatcher in the working directory of this session:

```sh
claude --bg --name dispatcher --agent cure:dispatcher --settings '{"crossSessionInbound":"accept","autoCompactWindow":200000,"permissions":{"allow":["Bash(cure-job *)"],"deny":["Bash(claude *)"]}}'
```

3. Send the `notify:` line again with `SendMessage`. If this send fails, tell the user the job is queued and the dispatcher may not wake until its next start.

Tell the user in one line: job queued, dispatcher started, pin it with ctrl+t in the agents view.

