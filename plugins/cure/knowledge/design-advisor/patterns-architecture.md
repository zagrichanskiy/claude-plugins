# Architectural patterns — system level

Load this only in **architecture mode** (invoked as `architect`), together with
`checklist-architecture.md`. It is language-neutral; language-specific system concerns live in the
architecture supplement for that language under `lang/`.

An architectural pattern resolves **forces** that act across components: rates that differ, links
that fail, owners that restart, hardware that changes. Judge every pattern by its forces, never by
its name.

## How to judge pattern use

Every pattern observation in a review is exactly one of these five, and the review says which:

| Verdict | Meaning | What to write |
|---|---|---|
| **Fits** | The forces are present and the pattern resolves them | One line in the pattern assessment; it is part of what is sound |
| **Missing** | The forces are present, the system resolves them ad hoc or not at all | The pattern, the forces, the scenario that fails without it |
| **Misapplied** | The pattern is present but the forces are not, or are different | The forces it assumes, the forces actually present, the simpler structure |
| **Half-applied** | Some participants are missing (a retry with no timeout, a watchdog with no escalation) | The missing participant and the field scenario it causes |
| **Re-implemented** | The platform already provides it (the init system, the IPC bus, a platform service) | The existing mechanism, and the divergence the copy introduces |

- **The failure scenario is the evidence.** State the concrete sequence of events — link drops,
  power cut, restart, flood — in which the missing or misapplied pattern bites.
- **Every pattern costs indirection, latency or resources.** Say what it costs on the target
  hardware, and demand a present force for each one; the rest are speculative (YAGNI).
- **Prefer the platform's instance.** A service that hand-rolls reconnection, supervision or
  configuration layering beside the platform's own mechanism creates two behaviours to debug.

## Structure (Buschmann, Meunier, Rohnert, Sommerlad & Stal, *POSA 1*; Bass, Clements & Kazman)

- **Layers** — *fits when* dependencies must run one way (hardware → platform → services → apps).
  *Misuse*: sideways calls between peers, a lower layer that knows its callers, layers that only
  forward.
- **Pipes and filters** — *fits* media, log and sensor pipelines where stages transform a stream.
  The contract per pipe is rate, buffering and drop policy. *Misuse*: filters that share state
  outside the pipe; a pipeline with no stated behaviour when a stage is slower than its producer.
- **Ports and adapters (hexagonal)** (Cockburn) — *fits when* the domain must survive a change of
  vendor SDK, transport or storage. *Missing* when vendor types appear in more than one component.
- **Microkernel / plugin** — *fits when* third parties or product variants extend a stable core.
  *Misuse*: a plugin loader with one plugin; plugins that depend on core internals.
- **Broker / message bus** — *fits when* components must be located and addressed indirectly and
  restarted independently. *Misuse*: synchronous chains of calls through the bus that turn one
  slow service into a system stall.
- **Publish–subscribe** — *fits* state and event distribution with an open set of consumers.
  *Misuse*: using a lossy event for a condition a late subscriber must see (use a state with an
  initial value); ordering relied on across publishers.
- **Request–reply** — *fits* commands with an outcome. Every request needs a deadline, and the
  reply must report the outcome, not only acceptance.
- **Blackboard** — *fits when* several independent specialists (detectors, classifiers,
  estimators) each contribute partial results to one shared picture, and no fixed order of
  processing is known in advance: sensor fusion, multi-model inference. A control component decides
  which specialist runs next. *Misuse*: a blackboard used as a global bag of shared state with no
  control component and no owner per entry; one where the processing order is in fact fixed, which
  is a pipeline.
- **Shared repository / shared filesystem as integration** — *fits* only with one writer per
  datum and a stated naming and locking protocol. *Misuse*: two components coordinating through
  files with no stated owner (hidden coupling).

## Event-handling model per process (Schmidt et al., *POSA 2*)

- **Name the model each process runs**: Reactor or Proactor on one thread, Half-Sync/Half-Async
  (an event loop in front of blocking workers), or Leader/Followers (a pool on one event source).
  Every component sharing a process inherits its model; flag a component whose blocking work, or
  whose assumption of a single thread, contradicts it.

## Resource management (Kircher & Jain, *POSA 3*)

Resources here are anything finite on the device: flash space and write bandwidth, memory,
descriptors, connections, CPU at boot.

- **Lazy versus Eager Acquisition** — acquire at first use (faster start, latency and failure on
  the first request) or at start-up (slower boot, failure surfaces early). State the choice for
  every expensive resource, and count eager acquisition in the boot budget.
- **Partial Acquisition** — acquire a large resource in bounded steps (a backlog drained in
  batches). *Missing* when a start-up step's duration depends on data of unknown size.
- **Caching** — keep a resource instead of re-acquiring it. *Half-applied*: a cache with no bound
  and no invalidation.
- **Pooling** — recycle resources whose acquisition is expensive. *Misuse*: pooling cheap
  resources; a pool with no ceiling.
- **Evictor** — release resources by a stated policy (oldest, least recently used, lowest
  priority) when a budget is reached. *Half-applied*: eviction that runs only on a path that can
  fail, or whose ordering key can be wrong (a wall clock on a device without one).
- **Leasing** — a resource granted to a remote party expires unless renewed, so a dead holder
  cannot keep it forever. *Missing* when a resource held for a remote call (a file marked in use,
  a connection) is released only when the call completes, and the call has no deadline.
- **Resource Lifecycle Manager** — one component owns acquisition and release for a class of
  resources. *Missing* when several components each acquire and release the same resource type
  their own way.
- **Coordinator** — a multi-party update either completes everywhere or is undone everywhere.
  *Missing* when a change spanning components (a migration, a cutover) can stop half-way.

## Reliability and degradation (Nygard, *Release It!*; Hanmer, *Patterns for Fault Tolerant Software*)

- **Timeout** — every call that crosses a process or network boundary has one. A call without a
  deadline is a resource leak that waits for a peer to hang.
- **Retry with bounded, jittered backoff** — *fits* transient failures of idempotent operations.
  *Half-applied*: retry without timeout, without a ceiling, or on a non-idempotent operation.
  *Missing*: progress that depends on an unrelated event (the next rotation, the next state edge).
- **Circuit breaker** — *fits when* a failing dependency must not be hammered, and the caller has
  a degraded behaviour meanwhile. *Misuse*: on a single dependency the caller cannot work without
  and has no fallback for.
- **Bulkhead** — *fits when* one consumer's load must not exhaust a shared resource (CPU, flash
  bandwidth, file descriptors, a journal's rate limit). Look for it wherever a flood in one
  service can starve another.
- **Backpressure / load shedding** — *fits* every producer faster than its consumer. The design
  states which it does: block, drop oldest, drop newest, sample, or degrade fidelity.
- **Supervisor / watchdog** (Armstrong, *let it crash*) — *fits* long-running services: the
  supervisor (the init system, a parent) restarts on failure and escalates after a budget. *Half-
  applied*: a watchdog fed from a thread that is not the one doing the work; an escalation (reboot)
  reachable from a deterministic startup failure, which turns a bad config into a reboot loop.
- **Heartbeat / health state** — *fits when* a component must be known alive and working, not
  merely running. Publish health as observable state, not only as log lines.
- **Safe mode / graceful degradation** — *fits* field devices: a defined reduced behaviour when a
  dependency, a budget or the config is bad, distinguishable from normal operation.
- **Idempotent receiver** — *fits* any at-least-once delivery. A duplicate must be harmless.

## Persistence and state on devices

- **Store-and-forward / outbox** — *fits* intermittent links: persist first, forward when
  connected, mark done durably. *Half-applied*: the "done" mark is not durable, so a power cut
  re-sends, or the queue has no bound and no eviction policy.
- **Atomic replace (write-temp, fsync, rename, fsync directory)** — *fits* every persisted file
  that must survive power loss whole. *Missing* when a file is rewritten in place.
- **Write-ahead log / journal** — *fits* multi-step state changes that must be recoverable.
- **Monotonic sequence as identity** — *fits* ordering on devices without a trustworthy clock.
  *Missing* when wall-clock time orders data on hardware with no battery-backed clock.
- **Single writer** — exactly one component owns writes to a datum; others read or request.
- **Configuration layering** — base, machine, model, runtime override, merged by one mechanism.
  *Re-implemented* when a component carries its own override scheme beside the platform's.

## Evolution and migration (Fowler; Hohpe & Woolf, *Enterprise Integration Patterns*)

- **Strangler fig** — replace a mechanism incrementally, both running until the new one is
  proven. *Missing* when a platform-wide mechanism is replaced in one cutover with no fallback.
- **Parallel run / feature toggle** — the new path can be switched off per device without a
  reflash.
- **Anti-corruption layer** (Evans) — a translation boundary where a legacy or foreign model meets
  the new one.
- **Versioned contract / tolerant reader** — IPC messages, persisted formats and config keys carry
  a version or are read tolerantly, so old and new peers coexist during a staged rollout.
- **A/B (dual-slot) update with rollback** — firmware changes that can be rolled back; any
  persisted-state migration must be readable by the previous version or be reversible.

## Anti-patterns (Brown et al., *AntiPatterns*; Richards & Ford, *Fundamentals of Software Architecture*)

Each is a finding when observed; cite it by name.

- **Distributed monolith** — services that must be deployed and upgraded together.
- **Chatty interface** — many fine-grained calls where one coarse contract would do.
- **Big-bang cutover** — every repository changes at once and nothing can be staged or reverted.
- **Hidden coupling** — components coordinated through file names, timing or log text that no
  contract states.
- **Golden hammer** — one mechanism (the bus, a database, a thread pool) applied where its forces
  are absent.
- **Stovepipe** — each component re-implements a cross-cutting concern (reconnection, retry,
  health, config) its own way.
- **Lava flow** — dead compatibility code and unused mechanisms nobody dares remove.
- **Feedback loop** — a component's diagnostics become its own input (it logs into what it reads).
