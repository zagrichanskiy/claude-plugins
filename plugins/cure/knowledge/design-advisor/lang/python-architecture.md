# Python supplement — architecture mode

Load this only in **architecture mode** when the system under review contains Python components.
It adds the system-level consequences of choosing Python to `checklist-architecture.md`; it does
not cover how a component is factored into classes. Where the project has its own conventions,
they win over this file — cite them.

## Process model and the interpreter

- **The GIL bounds CPU parallelism per process** (free-threaded builds aside, which the target
  interpreter must actually be). CPU-bound stages need processes or native extensions; state which
  and what crosses the process boundary.
- **One event loop per process.** Components sharing a loop share its latency; a blocking call in
  one stalls all of them.
- **Each interpreter process costs memory and start-up time.** On a small board, state the resident
  size per process and the import time, and count them in the RAM and boot budgets.
- **`multiprocessing` start method** (`fork`, `spawn`, `forkserver`) changes what is inherited and
  what is safe after threads exist; name the one used.
- **Long-running services** need a stated answer for memory growth (reference cycles, caches without
  bounds, fragmentation) over weeks of uptime.

## Packaging and deployment

- **The interpreter version is fixed by the image or BSP.** Flag a design that depends on language
  or library features newer than the deployed interpreter.
- **Dependencies are pinned** and delivered the way the image builds them (system packages, a
  vendored wheel set, a virtual environment); native extensions must be cross-compiled for the
  target. Flag a dependency that exists only on a developer's host.
- **Plugins through entry points** (`importlib.metadata`) rather than path scanning; the plugin
  contract is versioned.

## Boundaries and contracts

- **Import cycles are layer violations.** The package layout expresses the dependency direction;
  flag sibling packages importing one another.
- **Parse at the boundary** — IPC messages, config and files are parsed into typed models once
  (dataclasses, `pydantic`, `msgspec`) where they enter the process.
- **Serialization formats are language-neutral and versioned** when a non-Python peer or an older
  release can read them; flag `pickle` across a trust or version boundary.

## Failure and supervision

- **An uncaught exception ends the process**; state whether the supervisor restarts it, and
  whether a deterministic startup failure can exhaust the restart budget.
- **Signals are delivered to the main thread only**; the shutdown path must reach the event loop
  and the worker processes from there.
