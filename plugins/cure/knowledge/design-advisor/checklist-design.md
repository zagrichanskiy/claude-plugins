# Design checklist — module, class and interface level

Load this only in **design mode** (invoked as `designer`). Use the items as concrete checks. Each
names its source as rationale. Cite exactly one item per finding — the most specific that applies.

## Modules & abstractions (Ousterhout, *A Philosophy of Software Design*)

- **Deep, not shallow modules** — a good module hides substantial complexity behind a simple
  interface. Flag classes/functions whose interface is nearly as complex as their implementation
  (pass-through wrappers, thin managers).
- **Information hiding** — flag implementation details (data formats, protocols, algorithms) that
  leak through an interface and force callers to know them.
- **Define errors out of existence** — prefer designs where whole error classes cannot occur over
  designs that detect and handle them everywhere.
- **Right degree of generality** — flag interfaces overfitted to a single caller *and* generality
  added with no present need. Tie-breaker: prefer the more general interface only when it is simpler
  now, or a second concrete caller is already known; otherwise treat the extra generality as
  speculative (see YAGNI).

## Coupling & cohesion (Martin, SRP; Pragmatic Programmer; structured design)

- **Complexity = dependencies + obscurity** — treat non-obvious coupling and behavior that cannot be
  understood locally as the core cost you are hunting.
- **Single Responsibility / high cohesion** — a unit should do one thing and have one reason to
  change. Flag grab-bag modules, and functions that mix unrelated responsibilities.
- **Orthogonality / low coupling** — changes to one concern should not ripple. Flag shotgun surgery
  (one change touching many modules), inappropriate intimacy (reaching into another module's
  internals), and temporal coupling.
- **DRY** — flag duplicated *knowledge* (the same decision expressed twice), not incidental
  similarity that is not the same decision.

## Dependencies & layering (Martin, SOLID / Clean Architecture)

- **Dependency direction & inversion** — high-level policy must not depend on low-level detail; both
  depend on abstractions. Flag business logic importing I/O, transport, or framework specifics
  directly, and concrete dependencies hard-wired where they should be injected.
- **Layer separation & sibling coupling** (Buschmann et al., *POSA* — the Layers pattern) — units
  within a layer should depend downward, not sideways. Flag peers in one layer that import or call
  one another; when two units in the same layer need the same capability, lift it into the layer
  below and inject it rather than letting one sibling reach into another. This keeps each unit in
  the layer independently replaceable.
- **Open/Closed & Liskov** — flag hierarchies where subtypes are not substitutable, or where adding
  a case means editing many `if/elif` ladders.
- **Interface Segregation** — flag fat interfaces that force callers to depend on methods they do
  not use.
- **Isolate external systems** — third-party libraries and remote systems belong behind a thin
  adapter (ports/adapters), not scattered through the domain.

## Error handling & failure modes

- **Explicit strategy** — errors should propagate by one consistent mechanism (exceptions vs. result
  values), caught at a layer that can act on them, not swallowed. Flag bare `except`, silent
  failure, and error handling smeared across layers.
- **Partial failure & idempotency** — for I/O, retries, and multi-step operations, flag designs with
  no defined behavior on partial failure, and operations that are unsafe to retry when they should
  be idempotent.

## Data modeling & invariants

- **Make illegal states unrepresentable** — flag models that permit invalid combinations the code
  must then defend against everywhere.
- **Parse, don't validate** — validate at the trust boundary and convert to a typed, known-good
  representation once, rather than re-checking raw data deep inside the system.
- **Model the domain's real multiplicity** (Evans, *Domain-Driven Design* — associations; Chen, the
  entity-relationship model — relationship cardinality) — relationships in the model should mirror
  the cardinality of the problem domain. Flag a hardcoded one-to-one where the domain relationship
  is genuinely one-to-many; getting this wrong forces rework the moment the second instance appears.
  Distinguish from YAGNI: model the multiplicity the domain *actually exhibits*, not multiplicity
  that is merely conceivable.

## Interface & data evolution

- **Compatibility** — flag public interfaces (APIs, CLI surface) and persisted formats (on-disk
  files, wire formats) that cannot change without breaking existing callers or stored data, when
  evolution is foreseeable. Look for a versioning or migration path where one is needed.

## Naming, consistency & self-documentation

- **Names reveal intent** — flag names that mislead, abbreviations that obscure, and asymmetry in
  paired concepts. The interface should read well at the call site.
- **Conceptual integrity — one concept per type** (Brooks, *The Mythical Man-Month*; Evans —
  ubiquitous language) — each type should model exactly one domain concept, and its name must denote
  that concept honestly. Flag types that fuse two distinct concepts (an identity and a live
  connection to it; a value and the mechanism that produces it) and names that assert a concept the
  type does not model. The fix is to split the concepts and name each for what it truly is.
- **Consistency** (Ousterhout) — similar things should be done similarly. Flag divergent patterns
  for the same job that raise the reader's cognitive load.
- **Document the non-obvious** — comments and docstrings that capture *why* and the non-obvious
  contract are part of the design. Flag missing rationale on subtle decisions; do not reward
  comments that merely restate the code.

## Complexity & simplicity

- **Essential vs. accidental complexity** — ask whether complexity is inherent to the problem or
  self-inflicted. Flag accidental complexity.
- **YAGNI** — flag speculative generality, configurability, and abstraction built for requirements
  that do not exist yet.

## Observability (a design concern, not an afterthought)

- Flag designs with no way to diagnose failures in the field: absent or unstructured logging,
  missing log levels, and no seam to observe key state or transitions.

## Safety & security by design

- **Trust boundaries & least privilege** — flag inputs crossing a trust boundary without a defined
  validation point, and components granted more capability than they need.
- **Guard destructive operations** — irreversible or dangerous actions should be hard to trigger
  accidentally (confirmation, dry-run, backup-before-write). Respect any project-specific safety
  constraints stated in the codebase.

## Python & asyncio specifics

- **Pythonic idioms** (PEP 20 / PEP 8) — prefer composition and plain functions/dataclasses over
  needless class hierarchies; context managers for resources; iterators/generators over manual
  accumulation where clearer.
- **Async discipline** — flag blocking calls (sync I/O, `time.sleep`, CPU-bound work) inside
  coroutines; missing `async with`/`async for` for async resources; swallowed or unpropagated
  `CancelledError`; tasks created and never awaited or cancelled; shared mutable state without clear
  single-threaded reasoning.
- **Resource & lifetime safety** — every acquired resource (fd, subprocess, connection, serial port)
  has a clear owner and deterministic release path, including on error and cancellation.

## Testability

- Flag designs that are hard to test: hidden dependencies, I/O and logic fused together, global
  state, no seam to inject fakes. Good design and testable design usually coincide; treat difficulty
  writing a unit test as a design signal, not a testing problem.

## Document skeleton — design document

1. **Structure** — a Mermaid `classDiagram` of the key types, their operations and their
   relationships (association, composition, inheritance, dependency), with a legend. This opens the
   document: every later section details one type from it, so a reader meets the whole before any
   part. A design document without it is incomplete.
2. **One section per type** — how it is built inside, its own API, the order its steps run in.
3. **Key flows** — the important runtime sequences, as a Mermaid `sequenceDiagram` where it adds
   clarity.
4. **Design decisions** — the choices made and why. Where the project keeps a separate architecture
   document, the options and the rejected alternatives live there and this section cites it.

Proportional: a small component's document is short. Cut a section the subject does not need rather
than padding it.
