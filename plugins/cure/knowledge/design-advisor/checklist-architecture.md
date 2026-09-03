# Architecture checklist — system level

Load this only in **architecture mode** (invoked as `architect`). It is written for this
organisation's systems: networked embedded devices that fly or are carried into the field —
Raspberry Pi and SoC-class Linux boards (Yocto BSPs), MCU firmware, cameras and inference on board,
radio and video links, flight controllers, ground stations. Where a subject is plain application
software, the generic items still apply; the hardware-flavoured ones simply do not fire.

**Altitude test.** You are in the right mode when the question is *which components exist, what
crosses the boundary between them, what the system does when something is late or missing, and what
it costs on the hardware we actually have*. Questions about how one component is factored into
classes belong to `designer`.

Cite exactly one item per finding — the most specific that applies.

## 1. Quality attributes, with numbers

- **Name the number the work exists to produce.** Most embedded architecture turns on a handful of
  measurable attributes: end-to-end latency, sustained frame or message rate, CPU headroom, memory
  ceiling, power, boot time, range. Flag a document that discusses structure without ever stating a
  target for any of them.
- **Attributes come as scenarios, not adjectives** (ATAM). "Low latency" is not a requirement.
  "Operator sees a box within 150 ms of the frame that contains it, at 30 fps, on four Cortex-A76
  cores" is one, and it can be falsified.
- **Requirements the team already wrote down beat requirements you invent.** Look for them (task
  tracker, a requirements document, an epic) before assuming none exist, and say plainly when the
  budget in the document has no stated source.
- **Flag attributes in tension** and say which one wins. Resolution versus frame rate, image quality
  versus detectability, latency versus buffering, accuracy versus quantization.

## 2. Boundaries and contracts

- **Define each boundary by what crosses it**, not by which module sits on either side. A component
  is understood by its inputs, its outputs and their format, timing and ownership.
- **Say who owns state and identity.** Where several components touch the same entity, exactly one
  assigns and retires its identity. Flag a design where two components can both create or expire the
  same thing.
- **One source of truth per fact, with all consumers derived from it.** Flag two paths that compute
  the same answer independently — they will disagree in the field, and the disagreement will be
  reported as a bug in whichever one is easier to blame.
- **Zero-copy and buffer ownership are contract, not optimization.** On a DMA/ISP path, say who owns
  the buffer, how long a handle stays valid, and what happens when a consumer holds one too long.
- **Timing is part of the contract.** For every pipe: does the producer block, drop, or queue, and
  how deep? Flag any boundary where the answer is unstated — it is the most common source of an
  architecture that works on the bench and collapses under load.

## 3. Classify every fork

Every unsettled thing in the document is exactly one of three kinds, and each has a different
obligation. Flag a document that mixes them into one list.

| Kind | Obligation | Belongs in |
|---|---|---|
| **Decided** | rationale + the alternative you rejected | the body |
| **Deferred to measurement** | the experiment that settles it, and the interface that keeps it swappable until then | the body + the evaluation section |
| **Not ours** (hardware, procurement, a model somebody else trains) | treat as a constraint; the test is that the structure survives any outcome | constraints + risks |

- **A deferral is only legitimate if something keeps it open.** "We will decide later" without a
  stable interface behind which the choice hides is not a deferral, it is an omission.
- **Deferring to measurement obliges you to specify the measurement.** One variable, the same input,
  results stored with the exact configuration and artifact identity that produced them.

## 4. Resource reality on fixed hardware

- **Every per-item cost is a line item.** On a fixed board, anything that runs per frame, per packet
  or per control cycle competes with everything else that does. Flag a stage treated as free —
  especially encode, decode, resize, colour conversion and serialization, which people assume are
  hardware-accelerated until they check.
- **Check the accelerator is real.** Hardware blocks vary by SoC revision and are commonly absent
  (a board with hardware decode may have no encoder at all). An accelerated path that silently falls
  back to CPU — an unsupported NPU operator, a missing codec — is worse than no accelerator, because
  it fails as a performance mystery rather than an error.
- **Aggregate specs hide per-instance limits.** "6 TOPS" may be three cores at 2 TOPS, one per
  model. "Four cores" is not four cores once the kernel, the network stack and the encoder are on
  them.
- **State the worst case as the baseline** and treat the accelerator as an optimization, never a
  dependency, unless procurement is already committed.

## 5. Failure, degradation and the link

- **Say what the system does when it cannot keep up**, per stage: drop, degrade, or fall behind.
  "Slow" is not a behaviour; dropping the oldest frame is.
- **Assume the radio link is lossy, asymmetric and sometimes one-way.** Flag any design that needs a
  clean round trip in the normal case, and any that re-associates two independently dropping streams
  at the far end.
- **Partial failure has a defined state.** A stage that dies, a camera that stops producing, a
  sensor that returns stale data — say what the rest of the system does, and whether it is
  distinguishable from working normally.
- **Configuration errors fail at startup, never at frame 4000.** On something that flies, validate
  the whole binding once at construction. Flag lazy or per-item validation of static configuration.
- **Say what happens on restart mid-flight** — whether it is possible, how long it takes, and what
  state is lost.

## 6. Diagnosability in the field

- There is no debugger on a flying aircraft. Flag a design with no way to answer "why did it do
  that" after the fact: no structured logging, no way to record inputs, no seam to replay a
  recorded run on a desk.
- **Prefer a design where the field artifact is replayable input.** If a recorded stream plus the
  stored configuration reproduces the run offline, most field debugging becomes desk work — and the
  same seam gives you the evaluation harness for free.
- Flag telemetry that exists only as a side effect of the display path; if the operator's view is
  the only record, there is no record.

## 7. Portability and vendor lock-in

- **Name what a board change would cost**, in the units that matter: BSP layer work, vendor
  userspace (codec, NPU runtime, camera ISP tuning), model artifact conversion, and the ongoing tax
  of maintaining two BSPs. Do not hand-wave it in either direction — "it's just a layer" and "it's a
  rewrite" are both usually wrong.
- **Vendor SDKs belong behind an adapter** the rest of the system does not see, and the artifact
  they consume (`.rknn`, `.hef`, `.engine`) is a build-time output, not a source-level dependency.
- **Sensor and ISP tuning does not port.** Treat it as per-sensor, per-SoC effort with an equipment
  and skills prerequisite, and put it on the schedule rather than in the assumptions.
- Flag an architecture whose correctness depends on a specific vendor's behaviour that is not
  written down anywhere.

## 8. Staging and incremental validation

- **Every stage should produce a number or a decision**, not just working code. A stage that
  produces neither is sequencing, not validation.
- **Order stages to remove the largest unknown earliest**, and to keep long-lead work (hardware
  bring-up, procurement, hiring) off the critical path of everything else.
- **Staging is evidence for the architecture.** If a claimed extension point is real, some stage
  swaps an implementation and touches nothing else — say which stage, and which components stay
  untouched.
- Flag a plan whose first measurable result comes after most of the build.

## 9. Risks

Keep a register, and keep it separate from the open decisions (§3 of this checklist). Columns:

`| Risk | Attaches to | Impact if real | Early signal | Mitigation | Cost of mitigation |`

- **The early-signal column is what makes the table operational** — what we would observe, and at
  which stage, if this were true. A risk nobody can detect until the end is a risk nobody manages.
- **No probability scoring.** High/medium/low columns turn into theatre. Use real units
  (person-weeks, currency) where they exist and mark them as estimates.
- **Capability and procurement risks belong in the table** alongside technical ones — expertise the
  team does not have, an export-controlled part, a single-source component, a board with no
  industrial variant. They are usually the ones with the longest lead time.
- Flag a risk that has no owner and no next action; it is a worry, not a risk.

## 10. Trust boundaries

Identify where untrusted data or untrusted parties touch the system — links, removable media, model
artifacts, update paths — and name the boundary. Do not attempt a full threat model or key-management
design here: state where security attaches and recommend the caller invoke the `security-expert`
agent. If the document declares security out of scope, that is legitimate for an MVP, but the
attachment points still get named.

## 11. Hygiene of the document itself

- **Research is not architecture.** Component comparisons, vendor surveys, measurements and market
  facts belong in their own catalog or evaluation document, linked, with only the binding constraint
  restated here — one line each. Flag an architecture document turning into a research dump.
- **Proportion to the decision.** A document for an MVP whose whole question is "does this run fast
  enough" should not carry twelve sections of design for the version after next.
- **Speculative extension points are the standard failure.** Every plug point costs indirection.
  Demand a *currently required* second implementation for each one; flag the rest as YAGNI.
- **Configuration becomes a framework if unattended.** State the ceiling explicitly — a typed
  structure and a graph description, not a DSL, not a plugin loader — or it will drift into one.
- **A diagram's line styles must mean one thing each** (core rules). Flag a diagram where dotted
  means "optional", "future" and "hypothetical" at once.
- **Forward references should be citable** — `§6 (Performance & Latency Budget)`, not `§6`.

## Document skeleton — architecture document

Adapt, and cut what the subject does not need. This ordering answers a reader's questions in the
order they occur to them.

1. **Motivation & scope** — the problem, the goal, why now, what is in and out. Non-goals are load
   bearing: they are how you stop the document growing.
2. **High-level structure** — the component diagram, a legend directly under it, the properties of
   the structure that a reader would otherwise get wrong, and the shared state if there is one.
   Detail belonging to one component goes in its own subsection with its own diagram.
3. **Component responsibilities** — one subsection each: responsibility, inputs, outputs, and the
   data contract at every boundary.
4. **Strategy sections** — whatever the subject turns on (model strategy, protocol design,
   partitioning between MCU and Linux). Usually one or two.
5. **Constraints & assumptions** — one line each with a link to the catalog or evaluation document
   that holds the detail.
6. **Performance & resource budget** — the target, the per-stage line items, the main lever.
7. **Evaluation / validation** — how a claim in this document gets measured, what is recorded, and
   what makes two runs comparable.
8. **Configuration & deployment** — process/thread model, what is configurable, and the ceiling on
   how configurable it becomes.
9. **Milestone stages** — the build order, with what each stage proves.
10. **Security considerations** — trust boundaries and where the work attaches, even when deferred.
11. **Open decisions & risks** — the two tables. Never one list.

Not every document needs a full set. A protocol specification, an interface contract or a
board-partitioning note is the same discipline at a smaller size.
