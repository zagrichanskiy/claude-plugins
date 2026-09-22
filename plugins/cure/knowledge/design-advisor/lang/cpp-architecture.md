# C++ supplement — architecture mode

Load this only in **architecture mode** when the system under review contains C++ components. It
adds the system-level consequences of choosing C++ to `checklist-architecture.md`; it does not
cover how a component is factored into classes. Where the project has its own conventions, they
win over this file — cite them.

## Library boundaries and ABI

- **A shared library's ABI is a contract across the fleet.** State whether a library promises ABI
  stability, and how its version and `SONAME` move with it. Changes that break ABI silently: adding
  a virtual function, changing member layout or a default argument, changing an inline function or
  a template in a public header.
- **A stable boundary is a narrow one** — pimpl, an opaque handle, or a C interface. Header-only or
  template-heavy public interfaces make every dependent rebuild on every change; say whether the
  build system and the release process can carry that.
- **Public headers define the dependency graph.** A public header that includes a third-party
  library makes every consumer depend on it; flag vendor types in a cross-component header.
- **Cross-compiled dependents link against a copy.** In a sysroot-based build (Yocto, a vendor SDK)
  a dependent built against a stale copy of a library links and runs with the old behaviour; state
  how a library change reaches its dependents, and flag a release plan that assumes it happens by
  itself.

## Error model across boundaries

- **Exceptions never cross** a C interface, a `dlopen` plugin boundary, a thread boundary without
  `std::exception_ptr`, or an IPC boundary. Name the error model at each boundary.
- **A throw that escapes `main` is a crash**, and under a supervisor that escalates (restart
  budget, reboot) a deterministic startup throw is a reboot loop. State which startup failures are
  fatal and which fall back.

## Process and thread model

- **State the executor model per process** — one event loop on one thread, a loop per thread, or a
  pool — and which components share it. On a single-threaded loop, every blocking call is a
  latency line item for every other component on that loop.
- **Static initialisation order** across translation units and shared libraries is unspecified;
  flag global objects with dependencies on one another, and singletons duplicated per shared
  library.

## Memory and hot paths

- **Allocation per item** (per frame, per message, per log line) is a budget line on a
  long-running device: cost, fragmentation over weeks of uptime, and behaviour at the memory
  ceiling. State the allocation strategy where rates are high.
- **Exceptions and RTTI** have code-size and latency cost on constrained targets; if the project
  disables either, the design must not depend on them.

## Build and dependency graph

- **Link-time coupling is architecture.** Cyclic library dependencies, `PUBLIC` link dependencies
  that should be `PRIVATE`, and a component that links another's implementation library instead of
  its API library are boundary violations.
- **The toolchain is fixed by the BSP.** The C++ standard level and library features available are
  those of the SDK compiler, not the developer's host; flag a design that depends on newer ones.

## Contracts shared between C++ components

- **One definition of every wire contract** — IPC method names, message schemas and constants are
  defined once (an API library, a generated header) and consumed, not duplicated as string
  literals in each peer.
- **Serialized formats carry a version** or are read tolerantly, so components built from
  different releases can coexist during a staged rollout.
