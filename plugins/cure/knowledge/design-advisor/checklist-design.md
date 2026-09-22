# Design checklist — module, class and interface level

Load this only in **design mode** (invoked as `designer`). Use the items as concrete checks. Each
names its source as rationale. Cite exactly one item per finding — the most specific that applies.
Pattern judgements are made against `patterns-design.md`; language idiom against the design
supplement for the target's language.

**Altitude test.** You are in the right mode when the question is *which types exist inside one
component, what each is responsible for, what its interface promises, and how the types depend on
one another*. Which components exist and what crosses between them belongs to `architect`; whether
a given line of code misbehaves belongs to `reviewer`.

## Responsibility assignment (Larman, *Applying UML and Patterns* — GRASP; Martin, SRP)

- **Single Responsibility / high cohesion** — a unit should do one thing and have one reason to
  change. Flag grab-bag classes (the god class in `patterns-design.md`), and functions that mix
  unrelated responsibilities.
- **Information Expert** — behaviour lives with the data it needs. Flag feature envy: a method that
  reads another object's fields to make a decision that object should make.
- **Tell, don't ask; Law of Demeter** (Hunt & Thomas, *The Pragmatic Programmer*) — callers ask an
  object to act, not for its state so they can act on its behalf. Flag chains that reach through
  one object into another, and coordinators that query then decide for their collaborators.
- **Controller and Pure Fabrication** — a coordinating class is legitimate when it only wires and
  sequences; flag one that also holds the policies it coordinates.
- **Creator** — the type that owns or aggregates another creates it. Flag construction scattered
  among unrelated callers, and collaborators built inside a class that should receive them
  (hidden dependency, untestable).

## Class interface: contract (Meyer, *Object-Oriented Software Construction* — Design by Contract)

- **The constructor establishes the invariant.** After construction the object is usable and
  valid. Flag two-phase initialisation (`init()`, `start()` that must precede any use), and
  `is_valid()`-style zombie states a caller must check.
- **Invariants live in one type.** A rule that relates two fields is enforced by the type that
  holds them, at its construction or mutation — not by a caller, and not by a function 100 lines
  away that happens to run first.
- **Preconditions and postconditions are stated** where they are not obvious from the types, and
  violated preconditions have one defined behaviour (reject, clamp, or fall back — one of them,
  documented).
- **Command–query separation** (Meyer) — a function either changes state or answers a question.
  Flag a query with a side effect, and a command whose result the caller must inspect to learn
  whether anything happened, where the interface does not say so.
- **The signature is honest.** Mutability, ownership, failure and blocking are visible in the
  signature, not only in the comment. Flag a read-only marker on an operation that changes what a
  caller can observe, a non-owning parameter that is stored, a function that can fail but returns a
  plain value, and a "fast" accessor that performs I/O.
- **Substitutability** (Liskov) — every implementation of an interface honours its contract: no
  stronger precondition, no weaker postcondition, no new failure mode the interface does not name.

## Class interface: completeness and minimality (Meyers, *Effective C++* item 18 — "easy to use correctly, hard to use incorrectly"; Ousterhout)

- **Complete for its abstraction.** The operations form the set the concept needs: what can be
  acquired can be released, what can be added can be removed, every state the object can be in
  can be queried by a caller who must act on it. **The evidence of incompleteness is a caller
  working around it** — re-deriving state the object holds, reaching into internals, duplicating
  a computation, or keeping a shadow copy.
- **Minimal.** Every public member has a production caller that needs it. Flag members that exist
  only for tests (prefer a test seam that does not widen the production interface), and
  convenience overloads that duplicate one another.
- **Symmetric and consistent.** Paired operations have paired names and shapes; similar types
  expose similar interfaces for the same job.
- **Hard to misuse.** Parameters are typed by their domain, not by their representation (primitive
  obsession); no boolean flags that select behaviour (the boolean trap); no argument order that
  two parameters of the same type make easy to swap.
- **Outcome reporting.** An operation that can do nothing, succeed or fail distinguishes the three
  for the caller; one flag with two meanings is a defect in the interface.

## Encapsulation and data modeling

- **Information hiding** (Ousterhout) — flag implementation details (data formats, protocols,
  algorithms, container types) that leak through an interface and force callers to know them.
  Flag accessors that return mutable internals, and getter/setter pairs that expose a
  representation instead of an operation.
- **Make illegal states unrepresentable** — flag models that permit invalid combinations the code
  must then defend against: two optional members of which exactly one is set, a mode expressed as
  independent booleans. The fix is a sum type or a State (see `patterns-design.md`).
- **Parse, don't validate** — validate at the trust boundary and convert to a typed, known-good
  representation once (a Value Object), rather than re-checking raw data deep inside the system.
- **Model the domain's real multiplicity** (Evans, *Domain-Driven Design* — associations; Chen, the
  entity-relationship model — relationship cardinality) — relationships in the model should mirror
  the cardinality of the problem domain. Flag a hardcoded one-to-one where the domain relationship
  is genuinely one-to-many. Distinguish from YAGNI: model the multiplicity the domain *actually
  exhibits*, not multiplicity that is merely conceivable.

## Modules & abstractions (Ousterhout, *A Philosophy of Software Design*)

- **Deep, not shallow modules** — a good module hides substantial complexity behind a simple
  interface. Flag classes/functions whose interface is nearly as complex as their implementation
  (pass-through wrappers, thin managers).
- **Define errors out of existence** — prefer designs where whole error classes cannot occur over
  designs that detect and handle them everywhere.
- **Right degree of generality** — flag interfaces overfitted to a single caller *and* generality
  added with no present need. Tie-breaker: prefer the more general interface only when it is simpler
  now, or a second concrete caller is already known; otherwise treat the extra generality as
  speculative (see YAGNI).

## Inheritance, composition and polymorphism (GoF — "favour composition over inheritance")

- **Interface inheritance versus implementation inheritance** — inherit to be substitutable, not to
  reuse code. Flag a base class used as a bag of shared helpers, and hierarchies deeper than the
  variation they model.
- **Pick the polymorphism that matches the variation.** An open set of variants chosen at run time
  wants an interface; a closed set known at compile time wants a sum type; a variation fixed at
  build time wants a template or a parameter. Flag a mismatch (a virtual hierarchy for a closed set
  of three, a type switch over an open set).
- **Open/Closed** — flag designs where adding a case means editing many `if`/`switch` ladders.
- **Interface Segregation** — flag fat interfaces that force callers to depend on methods they do
  not use.

## Coupling & dependencies (Martin, SOLID / Clean Architecture; Pragmatic Programmer)

- **Complexity = dependencies + obscurity** — treat non-obvious coupling and behavior that cannot be
  understood locally as the core cost you are hunting.
- **Orthogonality / low coupling** — changes to one concern should not ripple. Flag shotgun surgery
  (one change touching many modules), inappropriate intimacy (reaching into another module's
  internals), and temporal coupling.
- **Dependency direction & inversion** — high-level policy must not depend on low-level detail; both
  depend on abstractions. Flag business logic importing I/O, transport, or framework specifics
  directly, and concrete dependencies hard-wired where they should be injected.
- **Layer separation & sibling coupling** (Buschmann et al., *POSA* — the Layers pattern) — units
  within a layer should depend downward, not sideways. Flag peers in one layer that import or call
  one another; when two units in the same layer need the same capability, lift it into the layer
  below and inject it rather than letting one sibling reach into another.
- **Isolate external systems** — third-party libraries and remote systems belong behind a thin
  adapter (ports/adapters), not scattered through the domain.
- **Reuse the project's mechanisms** — flag a class that re-implements a pattern or utility the
  project or its libraries already provide (see *Re-implemented* in `patterns-design.md`).
- **DRY** — flag duplicated *knowledge* (the same decision expressed twice), not incidental
  similarity that is not the same decision.

## Error handling strategy

- **Explicit strategy** — errors should propagate by one consistent mechanism per layer (exceptions
  vs. result values), caught at a layer that can act on them, not swallowed. Flag silent failure
  and error handling smeared across layers.
- **Partial failure & idempotency** — for multi-step operations, the design defines the state after
  each step fails, and repeated failure does not repeat the expensive part. Flag operations that are
  unsafe to retry when they should be idempotent.

## Ownership, lifetime and concurrency model

These are design questions about **structure**; an individual use-after-free or race is a bug for
`reviewer`, listed under *Out of altitude*.

- **One owner per resource, visible in the types** — every acquired resource (descriptor,
  connection, buffer, subprocess, task) has exactly one owner and a deterministic release path,
  including on error and cancellation.
- **What outlives what is structural.** Flag designs in which the correctness of teardown rests on
  every author repeating an idiom at every suspension point or callback; the structure (a scope
  that outlives its tasks, an owner that joins what it spawned) should make the idiom unnecessary.
- **The concurrency model is stated** — which executor or thread each type runs on, and which
  state is shared. Flag types usable from more than one thread with no statement either way.

## Interface & data evolution

- **Compatibility** — flag public interfaces (APIs, CLI surface) and persisted formats (on-disk
  files, wire formats) that cannot change without breaking existing callers or stored data, when
  evolution is foreseeable. Look for a versioning or migration path where one is needed.

## Naming, consistency & self-documentation

- **Names reveal intent** — flag names that mislead, abbreviations that obscure, and asymmetry in
  paired concepts; two members with one name and two meanings. The interface should read well at
  the call site.
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

## Testability

- Flag designs that are hard to test: hidden dependencies, I/O and logic fused together, global
  state, no seam to inject fakes, pure logic reachable only through the filesystem or a live
  service. Good design and testable design usually coincide; treat difficulty writing a unit test
  as a design signal, not a testing problem.

## Severity — design mode

- **MUST-FIX** — a structural defect whose cost grows with every line built on it: a type whose
  interface lies about its contract, a missing or misapplied pattern the rest of the component is
  already being built around, a public or persisted interface that cannot evolve, a god class that
  makes the component's policy untestable. The test: will fixing it later force callers to change?
- **SHOULD-CONSIDER** — a real design cost that stays local: an incomplete or non-minimal
  interface with few callers, a duplicated decision, a leaky representation inside the component.
- **NITPICK** — naming, placement and consistency with no behavioural or evolutionary cost.

A correctness bug is never ranked here, whatever its severity; it goes under *Out of altitude*.

## Review skeleton — design mode

A design review has these sections in this order. The first two are required even when there are
no findings: they are what distinguishes a design review from a bug list.

1. **Structure assessment** — one row per significant type (every public type, and every internal
   type that owns a resource, a policy or state):

   `| Type | Responsibility (one line) | Contract | Complete / minimal | Ownership | Verdict |`

   *Contract*: are the invariant and the pre/postconditions established and enforced by the type?
   *Complete / minimal*: what is missing (a caller works around it) and what is surplus (no
   production caller). *Verdict*: `sound`, or the number of the finding that addresses it. A type
   whose responsibility needs "and" to state is itself a finding.
2. **Pattern assessment** — every pattern present, named or de facto, and every place the forces
   call for one that is absent, each with its verdict from `patterns-design.md` (fits, missing,
   misapplied, half-applied, re-implemented) and the forces observed. Anti-patterns observed are
   listed here by name. List a pattern that fits only when the rest of the design depends on it;
   skip textbook confirmations. Keep each row to one or two lines — the reasoning lives in the
   finding it points to.
3. **What is well designed** — specific, with evidence.
4. **Findings** — ranked by the severity above, in the finding shape from `core.md`. A finding
   that proposes a new decomposition or a changed interface gives the proposed types as
   declarations in the target language (signatures and members, no bodies), and, when more than
   two types change, a Mermaid `classDiagram` of the proposed structure.
5. **Out of altitude** — one line each, unranked: correctness bugs (for `reviewer`) and
   system-level concerns (for `architect`), with `path:line`.
6. **Assumptions / open questions.**
7. **Overall assessment** — two lines, as in `core.md`.

## Document skeleton — design document

1. **Structure** — a Mermaid `classDiagram` of the key types, their operations and their
   relationships (association, composition, inheritance, dependency), with a legend. This opens the
   document: every later section details one type from it, so a reader meets the whole before any
   part. A design document without it is incomplete.
2. **One section per type** — its responsibility, its contract (invariant, pre/postconditions),
   its own API, how it is built inside, the order its steps run in.
3. **Patterns** — the patterns the design uses, each with the forces that justify it.
4. **Key flows** — the important runtime sequences, as a Mermaid `sequenceDiagram` where it adds
   clarity.
5. **Design decisions** — the choices made and why. Where the project keeps a separate architecture
   document, the options and the rejected alternatives live there and this section cites it.

Proportional: a small component's document is short. Cut a section the subject does not need rather
than padding it.
