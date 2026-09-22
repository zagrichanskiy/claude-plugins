# Design patterns — module, class and interface level

Load this only in **design mode** (invoked as `designer`), together with `checklist-design.md`. It
is language-neutral; the idiomatic form of each pattern in a given language lives in that
language's design supplement under `lang/`.

A pattern is a named solution to a recurring set of **forces** (the pressures a design must
balance: variation, lifetime, coupling, cost). Judge every pattern by its forces, never by its name.

## How to judge pattern use

Every pattern observation in a review is exactly one of these five, and the review says which:

| Verdict | Meaning | What to write |
|---|---|---|
| **Fits** | The forces are present and the pattern resolves them | One line in the pattern assessment; it is part of what is well designed |
| **Missing** | The forces are present, the code resolves them ad hoc | The pattern, the forces you observed, the ad hoc code it replaces |
| **Misapplied** | The pattern is present but the forces are not, or are different | The forces it assumes, the forces actually present, the simpler structure |
| **Half-applied** | The pattern is started but its participants are incomplete | The missing participant and the defect its absence causes |
| **Re-implemented** | The project or a library already provides it | The existing implementation, and the divergence the copy introduces |

- **The forces are the evidence.** "This should be a Strategy" is not a finding. "Retention has two
  policies selected by config, and `if (policy == pinned)` appears in four functions of two
  classes" is the evidence that makes it one.
- **Speculative patterns are a finding too.** An interface with one implementation, a factory that
  builds one type, an observer with one subscriber are costs with no present force (YAGNI). Keep one
  only when a second case is already known, or when it is the seam a test needs.
- **Prefer the project's existing instance** of a pattern over a new one (Ousterhout —
  consistency). Two Observer mechanisms in one codebase are worse than one imperfect one.
- **Name the pattern in the suggested change** so the author can look it up, and give the
  participants as declarations in the target language, not as prose.

## Creational (Gamma, Helm, Johnson & Vlissides, *Design Patterns* — GoF)

- **Factory Method / Abstract Factory** — *fits when* the concrete type is chosen at run time from
  config or input, or a family of related objects must be created consistently. *Misuse*: a factory
  with one product and no run-time choice; a factory whose callers down-cast the result.
- **Builder** — *fits when* construction has many optional parts, must be validated as a whole, or
  must produce an immutable object. *Misuse*: a builder for a type with two required fields; a
  builder that can emit an object violating its invariant.
- **Singleton** — almost always a finding. *Fits* only for a resource that is unique by nature
  *and* whose access must be lazily initialised. *Misuse signs*: it hides a dependency (callers
  reach it instead of receiving it), it makes tests order-dependent, it carries mutable state. The
  usual fix is **Dependency Injection**: construct once at the composition root and pass it down.
- **Dependency Injection / composition root** (Seemann, *Dependency Injection*) — *fits* almost
  always: collaborators are passed in through the constructor, and one place (usually `main`)
  wires the graph. *Misuse*: a DI container or service locator where plain constructor arguments
  suffice; injecting a collaborator the class never varies over, and never needs to fake.
- **Object Pool** (also *POSA 3* — Pooling) — *fits when* acquisition is measurably expensive or allocation is forbidden on
  a hot path. *Misuse*: pooling cheap objects; a pool that returns objects with stale state.

## Structural (GoF)

- **Adapter** — *fits when* a third-party or remote interface must be made to look like the one
  the domain wants. It is the local form of ports and adapters. *Missing* when vendor or transport
  types appear in domain signatures.
- **Facade** — *fits when* a subsystem needs one simple entry point for the common case. *Misuse*:
  a facade that forwards every method one to one (a shallow module); a facade callers bypass.
- **Decorator** — *fits when* behaviour (caching, retry, logging, metrics) is layered on an
  interface without the wrapped type knowing. *Misuse*: a decorator that changes the contract
  (adds a precondition, swallows an error the interface promises to report).
- **Proxy** (also *POSA 1*) — *fits when* access needs control, laziness or remoting behind the same interface.
  *Misuse*: a remote proxy that hides latency and failure the caller must handle; a remote call
  must look remote.
- **Composite** — *fits when* a tree of parts and wholes is treated uniformly. *Misuse*: a
  uniform interface that forces leaves to implement meaningless child operations.
- **Bridge** — *fits when* an abstraction and its implementation vary independently, or an
  implementation must be hidden from a stable public interface (the compilation firewall).

## Behavioural (GoF)

- **Strategy** — *fits when* one decision has several interchangeable algorithms selected by
  configuration or context. *Missing* when the same `if`/`switch` on a policy value recurs in
  several functions. *Misuse*: a strategy interface with one implementation and no second in
  sight; strategies that need to know about each other.
- **State** — *fits when* an object's behaviour depends on a mode with explicit transitions: a
  connection, a link, a protocol, a degradation ladder. *Missing* when mode is a set of booleans
  and counters (`m_ready`, `m_failed`, `m_step`) whose legal combinations are implied, not
  enforced. *Misuse*: a State hierarchy for two states with no per-state behaviour.
- **Observer / publish–subscribe** — *fits when* one producer notifies an open set of consumers
  that it must not know. *Misuse signs*: subscriber lifetime is undefined (a notification into a
  destroyed subscriber), notifications re-enter the producer, ordering between subscribers is
  relied on but not specified, an edge-triggered notification is used for a level condition (work
  is pending) and a notification with no waiter is lost.
- **Command** — *fits when* requests must be queued, retried, logged, undone or sent elsewhere.
  *Missing* when a retry or queue stores loose arguments and re-derives the action.
- **Template Method** — *fits when* a fixed algorithm has a few varying steps and the variants are
  a closed family. *Misuse*: deep hierarchies where each level overrides a different step; prefer
  Strategy (composition) when the steps vary independently.
- **Visitor** — *fits when* a closed set of types needs an open set of operations. *Misuse*: an
  open set of types (every new type edits every visitor).
- **Iterator / range** — *fits when* callers traverse without knowing the representation.
  *Missing* when a container's internals are returned for callers to walk.
- **Chain of Responsibility / pipeline** — *fits when* a request passes through ordered, optional
  handlers. *Misuse*: order dependencies between handlers that nothing states.
- **Mediator** — *fits when* many peers would otherwise reference one another. *Misuse*: a
  mediator that has become the god class — it decides for everyone instead of routing.
- **Null Object** — *fits when* "absent" has a sensible do-nothing behaviour and null checks recur.
  *Misuse*: hiding an absence the caller must react to.

## Domain and data (Evans, *Domain-Driven Design*; Fowler, *Patterns of Enterprise Application Architecture*)

- **Value Object** — equality by value, immutable, validated at construction. *Missing* when a
  domain quantity (a size, a duration, a pattern, an identifier) travels as a raw string or integer
  and is re-parsed or re-validated at each use (primitive obsession).
- **Entity** — identity that persists while attributes change. Flag a type that mixes identity with
  a live connection or handle to it (see conceptual integrity in the checklist).
- **Repository** — *fits when* a collection of persisted entities is accessed by domain queries and
  the storage must be hidden or faked. *Misuse*: a repository that exposes the storage format.
- **Specification / policy object** — *fits when* a business rule is composed and reused. Often
  simpler as a pure function.

## Concurrency and networked objects (Schmidt, Stal, Rohnert & Buschmann, *POSA 2*)

Most of this volume is the vocabulary of the asynchronous frameworks the code already runs on;
use it to say which model a component follows and where it departs from it, not to recommend
rebuilding what the framework provides.

- **Reactor** — one thread demultiplexes readiness events to handlers. **Proactor** — the
  framework starts asynchronous operations and dispatches their completions (Boost.Asio and
  standalone Asio are built on it). *Misuse*: a component that blocks the loop, or builds a second
  loop beside the framework's.
- **Asynchronous Completion Token** — the context a completion needs travels with the operation
  (a handler, a captured state object). *Misuse*: completions that look their context up in shared
  state that may have changed or been destroyed since the operation started.
- **Acceptor–Connector** — connection establishment is separated from the service that uses the
  connection. *Missing* when reconnection logic is interleaved with protocol logic in one class.
- **Half-Sync/Half-Async** — blocking work runs on its own thread or process, behind a queue, while
  the event loop stays asynchronous. *Missing* when blocking I/O or long computation runs on the
  loop.
- **Leader/Followers** — several threads take turns on one event source. *Misuse*: on a component
  whose state is not thread-safe, which the single-threaded design was relying on.
- **Active Object** — an object's methods run on its own executor, decoupled from the caller's
  thread. *Misuse*: on a single-threaded loop it adds a queue and no concurrency.
- **Monitor Object** — shared state is accessed from several threads under one lock. *Misuse*:
  locks in code that runs on one thread by construction.
- **Wrapper Facade** — an OS or C interface wrapped in a type that owns its handles and reports
  errors in the language's way. *Missing* when raw OS or C-library calls and their error codes are
  scattered through domain classes.
- **Component Configurator** — components linked or configured at run time without rebuilding.
  *Misuse*: dynamic loading for a set of components known at build time.
- **Interceptor** — a framework lets callers insert behaviour at defined points. *Misuse*: hooks
  nobody installs.

Newer practice extends this volume:

- **Structured concurrency** (Sústrik; Smith, *Notes on structured concurrency*) — every task has a
  parent scope that outlives it and waits for it. *Missing* when spawned tasks outlive their owner
  and each must defend itself against a destroyed owner at every suspension point. That defence,
  repeated by hand, is a design finding: the structure should make the idiom unnecessary.
- **Producer–consumer with a bounded queue** — *fits when* rates differ. *Misuse*: an unbounded
  queue (a memory leak that waits for load).

## Anti-patterns (Brown et al., *AntiPatterns*; Fowler, *Refactoring* — code smells)

Each is a finding when observed; cite it by name.

- **God class / blob** — one class owns most of the component's policy, state and I/O. Signs: many
  unrelated members, many handlers or asynchronous tasks, most tests impossible without the whole
  environment. Fix: extract collaborators by responsibility (GRASP), keep the class as the
  coordinator.
- **Feature envy** — a method uses another object's data more than its own; move it there.
- **Inappropriate intimacy / Law of Demeter violation** — `a.b().c().d()`, or a class reading
  another's internals to decide for it.
- **Primitive obsession** — domain concepts as strings, integers and booleans.
- **Boolean trap** — `f(x, true, false)`; the meaning is invisible at the call site. Use an enum
  or two functions.
- **Speculative generality** — hooks, parameters and interfaces for cases that do not exist.
- **Refused bequest** — a subclass that disables or ignores inherited operations (a Liskov
  violation).
- **Shotgun surgery / divergent change** — one change edits many classes, or one class changes for
  many reasons.
- **Temporal coupling** — calls must happen in an order nothing enforces (`init()` before use, a
  notify that must follow a spawn). Fix: make the order structural — a constructor that completes
  initialisation, a type returned only by the step that must come first.
- **Poltergeist** — a short-lived class that only passes calls through.
- **Anemic model** — data classes with all behaviour in a separate manager. A finding only where
  the invariants of the data are enforced by the manager instead of the type.
