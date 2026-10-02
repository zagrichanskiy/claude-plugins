# C++ supplement — design mode

Load this only in **design mode** when the target contains C++ (`.cpp`, `.cc`, `.cxx`, `.hpp`,
`.hh`, `.hxx`, or a `.h` included from C++). It adds C++ idiom to `checklist-design.md` and gives
the C++ form of the patterns in `patterns-design.md`; it does not repeat them. Where the project
has its own C++ conventions, they win over this file — cite them.

Sources are cited by their usual short names: the *C++ Core Guidelines* (Stroustrup & Sutter,
rule IDs such as `C.20`), Meyers (*Effective C++*, *Effective Modern C++*), Sutter & Alexandrescu
(*C++ Coding Standards*), Lakos (*Large-Scale C++ Software Design*).

This file does not restate Core Guidelines rules. The `cg-*` agents check the code against every
rule. An entry here adds design content beyond the rule it cites.

## Types and invariants

- **Common origin is not an invariant** (qualifies `C.2`). Fields that must come from one call but
  may diverge afterwards by design — a result a later stage updates — stay a `struct`. A private
  constructor restricts who builds a value; it checks nothing about the values. Ask for a class
  only when a relation between field values can be broken by a hand-built value (`x ⊆ y`,
  `a ⇒ b`).
- **Construction that can fail as a normal outcome** is a factory returning `std::expected<T, E>`
  (or `std::optional<T>`), not a half-built object with an `is_valid()` check (extends `C.41`).
- **An enum over a `bool` parameter that selects behaviour.**
- **Sum types for closed sets** — `std::variant` over two `std::optional` members of which one is
  set, and over a `kind` field with members that are meaningful only for some kinds.

## Ownership in the signature

- **A reference member means "something else outlives me"** and needs the owner that guarantees
  it stated.
- **Views do not outlive their source.** A `std::string_view` or `std::span` member, or one
  returned from a function, is a lifetime claim; flag one whose source is a temporary or a member
  that can change.
- **Returning references to internals** exposes the representation and ties the caller to the
  object's lifetime; prefer returning values or a view with a stated lifetime.

## Special members and value semantics

- **Ordering operators state the type's natural order.** `operator<` (or `<=>`) must agree with
  `==` (Sutter, *Consistent comparison*, P0515 — the model C++20 `<=>` is built on): two values
  neither less nor greater are equal. Flag an ordering operator added for one sort whose key skips
  a field `==` compares, or whose order is one caller's policy; that order is a named projection or
  comparator at the caller (`std::ranges::sort(v, {}, key)`). A defaulted `<=>` orders by
  declaration order, which is rarely the policy order.

## `const` and logical constness

- **`const` means "does not change what a caller can observe"**, not "does not touch a member"
  (extends `Con.2`). Flag a `const` member that renames, deletes or writes through a held
  descriptor: the keyword then lies about the most destructive operations. Flag `mutable` used for
  anything but caches, mutexes and counters invisible to callers.

## Polymorphism choice

- **Virtual interface** (`C.121`, `C.129`) — open set, chosen at run time, cost of one indirect call.
- **`std::variant` + `std::visit`** — closed set, value semantics, exhaustive at compile time.
- **Templates and concepts** — variation fixed at build time; flag a template parameter nobody
  varies, and a concept-constrained template where a plain function suffices.
- **Type erasure** (`std::function`, `std::move_only_function`, hand-written) — value-semantic
  polymorphism for callbacks and strategies.
- **CRTP** — static polymorphism or mix-ins; flag it where a free function or a virtual call on a
  cold path would do.
- **Non-virtual interface** (Sutter) — a public non-virtual function that calls a private virtual;
  fits when the base must enforce pre/postconditions around every implementation.

## Members versus free functions

- **The member-or-free test runs in both directions** (extends `C.4`; Meyers, *Effective C++*
  item 23): a free function that enforces a type's invariant (`add_entry(registry&, ...)`) belongs
  in that type, and so does a function that only asks questions of one type. Flag callers that
  mutate fields directly and bypass the function that enforces the invariant.
- **Decompose orchestrators into stages** (extends `F.2`). Stages are pure functions from inputs to
  a named struct; see the pipeline item in `checklist-design.md`.
- **Pure logic in an anonymous namespace is untestable.** A string transformation or a decision
  function reachable only through a class that does I/O is a finding under §15 (Testability); the
  fix is an internal header or a small value type, not a friend test.

## Error strategy

- **One mechanism per layer** — exceptions, `std::expected`, or `std::error_code`; flag mixtures
  in one interface.
- **Exceptions are caught by the concrete type the code can act on** (extends `E.14`); flag
  `catch (const std::exception&)` used as a fallback trigger where one type is expected.

## Coroutines, executors and asynchronous lifetime

These are design questions: *which structure guarantees an object outlives the coroutine that uses
it*. A single unguarded resumption is a `reviewer` bug; the structure that makes it possible is
yours.

- **Pick one lifetime model per project and apply it everywhere**: structured scopes that join
  their tasks; `shared_from_this` keeping the owner alive; or a cancellation token checked after
  every suspension. Flag a class whose coroutines use a different model from each other, and a
  design where the token must be re-checked by hand at every `co_await` — that is the structural
  defect, and the usual fix is fewer, smaller coroutines owned by collaborators with their own
  scope.
- **Blocking work on the executor thread** stalls every coroutine on it; flag synchronous I/O,
  long loops without a suspension point, and blocking calls inside constructors that run before the
  loop starts.
- **Level versus edge** — a condition such as "work is pending" modelled by an event or timer
  cancellation loses notifications with no waiter; the design needs a latched flag or a re-check.

## Physical design (Lakos)

- **Headers are the compile-time contract.** Flag a public header that includes third-party or
  internal headers its callers do not need, exposes implementation types, or defines what could be
  declared.
- **Pimpl on an internal type** pays an allocation for nothing; flag it where no ABI or header
  dependency needs hiding (qualifies `I.27`).
- **Internal versus public headers** are separated by directory, and tests reach internals through
  the internal headers, not through the public ones.

## C++ idioms

Idioms that exist only because of how C++ works. Raise one only where it changes a decision the
developer is making — the idiom's name is the lookup handle, the finding is the cost it removes.

| Idiom | Use it when | Signal in the code under review |
|---|---|---|
| **Scope guard** | One-off cleanup or rollback that no type owns | `goto cleanup`, or cleanup duplicated in several `catch` blocks |
| **Non-virtual interface** | A base must enforce checks or logging around every override | Every override repeating the same pre/post steps |
| **Type erasure** | Value-semantic polymorphism for callbacks and strategies, without a hierarchy | A one-method interface plus a heap-allocated implementation per call site |
| **`std::variant` + overload set** | A closed set of alternatives, visited exhaustively | A `kind` enum with members valid only for some kinds |
| **Strong typedef** (tagged wrapper type) | Two parameters of one primitive type that mean different things | `f(std::uintmax_t size, std::uintmax_t limit)` with the arguments swappable |
| **Named constructor / factory returning `std::expected`** | Construction that can fail as a normal outcome, or several ways to build one type | A constructor that throws on bad config, or an `is_valid()` checked after construction |
| **Immediately invoked lambda** | A `const` member or local whose initialisation needs several statements | A non-`const` member assigned in the constructor body only because the initialiser was complex |
| **Passkey** | A constructor that must be public for `std::make_shared` / `std::make_unique` but callable only by the factory | A public constructor with a comment saying "do not call" |
| **`enable_shared_from_this` / `weak_from_this`** | An object must keep itself alive, or check it is alive, across an asynchronous callback | `this` captured in a completion handler with nothing guaranteeing the object outlives it |
| **Hidden friend** | Operators and customisation points for a type, found only by argument-dependent lookup | Free operators in a namespace that make overload resolution slow or ambiguous |
| **Thread-safe interface** (*POSA 2*) | A class locked internally: public members lock, private members assume the lock | Public members calling each other and self-deadlocking, or a recursive mutex added to hide it |

**Idioms not to recommend any more** — flag them where they appear, with the modern replacement:

- **Thread-specific storage by hand** → `thread_local`.
- **Safe bool** → `explicit operator bool`.
- **SFINAE / `std::enable_if`** in new code on C++20 → concepts and `requires`.
- **Erase–remove** on C++20 → `std::erase` / `std::erase_if`.
- **Copy-and-swap** written by hand for a type that could follow the rule of zero → the rule of
  zero; keep copy-and-swap only where the strong exception guarantee is required and measured
  acceptable.

## C++ forms of common patterns

| Pattern | Idiomatic C++ form | Misuse sign |
|---|---|---|
| Resource management | RAII (`R.1`), scope guards | A `close()` the caller must remember |
| Strategy | `std::function` or a small interface injected at construction | An `if` on a policy enum in several members |
| State | `std::variant` of state structs, transition functions returning the next state | Booleans and counters whose combinations are implied |
| Observer | Signals with connection objects, or `std::weak_ptr` to subscribers | Raw `this` captured in a callback with no disconnect |
| Singleton | A function-local static (thread-safe since C++11), injected where possible | Static init order across translation units or shared libraries |
| Visitor | `std::visit` with an overload set | A virtual `accept()` hierarchy for a closed set |
| Factory | A free function or static member returning a value or `std::expected` | Returning `std::shared_ptr` by default |
| Value Object | A small regular type with a validating constructor | A `std::string` re-parsed at every use |
