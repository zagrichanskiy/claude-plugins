# C++ supplement — design mode

Load this only in **design mode** when the target contains C++ (`.cpp`, `.cc`, `.cxx`, `.hpp`,
`.hh`, `.hxx`, or a `.h` included from C++). It adds C++ idiom to `checklist-design.md` and gives
the C++ form of the patterns in `patterns-design.md`; it does not repeat them. Where the project
has its own C++ conventions, they win over this file — cite them.

Sources are cited by their usual short names: the *C++ Core Guidelines* (Stroustrup & Sutter,
rule IDs such as `C.20`), Meyers (*Effective C++*, *Effective Modern C++*), Sutter & Alexandrescu
(*C++ Coding Standards*), Lakos (*Large-Scale C++ Software Design*).

## Types and invariants

- **`class` when there is an invariant, `struct` when members vary independently** (Core
  Guidelines `C.2`). Flag a `struct` whose fields must agree and a `class` that is a plain
  aggregate hidden behind accessors.
- **A constructor creates a fully initialised object** (`C.41`). Flag `init()`/`open()` that must
  follow construction, and members that stay in a moved-from or empty state the rest of the class
  must test. When construction can fail as a normal outcome, prefer a factory returning
  `std::expected<T, E>` (or `std::optional<T>`) over a half-built object.
- **Single-argument constructors are `explicit`** (`C.46`).
- **Strong types at interfaces** (`I.4`) — a size, a duration, an identifier or a pattern is its
  own type (or `std::chrono` type), not a `std::uintmax_t` or a `std::string`. `enum class` over
  plain `enum` (`Enum.3`); an enum over a `bool` parameter that selects behaviour.
- **Sum types for closed sets** — `std::variant` over two `std::optional` members of which one is
  set, and over a `kind` field with members that are meaningful only for some kinds.

## Ownership in the signature (Core Guidelines, section R and I)

- **Raw pointers and references never own** (`I.11`, `R.3`). A parameter a callee stores must say
  so in its type; a reference member means "something else outlives me" and needs that stated.
- **`std::unique_ptr` for sole ownership; `std::shared_ptr` only for ownership that is genuinely
  shared** (`R.20`, `R.21`). Flag `shared_ptr` used to avoid thinking about lifetime.
- **Take smart pointers as parameters only to express a lifetime transfer** (`R.30`); otherwise
  take `T&` or `T*` (`F.7`).
- **Views do not outlive their source.** A `std::string_view` or `std::span` member, or one
  returned from a function, is a lifetime claim; flag one whose source is a temporary or a member
  that can change.
- **Returning references to internals** exposes the representation and ties the caller to the
  object's lifetime; prefer returning values or a view with a stated lifetime.

## Special members and value semantics

- **Rule of zero** (`C.20`) — a type that owns through RAII members needs no user-declared copy,
  move or destructor. **Rule of five** (`C.21`) — if one is declared, all five are considered.
- **Polymorphic bases**: destructor public and virtual, or protected and non-virtual (`C.35`);
  suppress public copy and move (`C.67`) to prevent slicing.
- **Moves are `noexcept`** where possible; containers depend on it.
- **Value types are regular** — copyable, comparable, no hidden sharing. Flag a "value" that shares
  mutable state through a pointer.

## `const` and logical constness

- **Member functions are `const` by default** (`Con.2`) — and **`const` means "does not change what
  a caller can observe"**, not "does not touch a member". Flag a `const` member that renames,
  deletes or writes through a held descriptor: the keyword then lies about the most destructive
  operations. Flag `mutable` used for anything but caches, mutexes and counters invisible to
  callers.

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

- **Make a function a member only if it needs direct access to the representation** (`C.4`);
  non-member non-friend functions increase encapsulation (Meyers, *Effective C++* item 23).
- **Pure logic in an anonymous namespace is untestable.** A string transformation or a decision
  function reachable only through a class that does I/O is a finding under *Testability*; the fix
  is an internal header or a small value type, not a friend test.

## Error strategy

- **One mechanism per layer** — exceptions, `std::expected`, or `std::error_code`; flag mixtures
  in one interface.
- **Exceptions are specific types** (`E.14`) and are caught by the concrete type the code can act
  on; flag `catch (const std::exception&)` used as a fallback trigger where one type is expected.
- **`noexcept` is a contract** — declare it where the design relies on it (moves, destructors,
  swap), and never where the function can throw.

## Coroutines, executors and asynchronous lifetime

These are design questions: *which structure guarantees an object outlives the coroutine that uses
it*. A single unguarded resumption is a `reviewer` bug; the structure that makes it possible is
yours.

- **Coroutine parameters are taken by value** (`CP.53`) and **lambdas that are coroutines do not
  capture** (`CP.51`) — references and captures dangle once the coroutine suspends past the
  caller's frame.
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
- **Pimpl** (`I.27`) — fits a public library interface that must keep a stable ABI or hide heavy
  dependencies; misuse on internal types that pay an allocation for nothing.
- **Internal versus public headers** are separated by directory, and tests reach internals through
  the internal headers, not through the public ones.

## C++ idioms

Idioms that exist only because of how C++ works. Raise one only where it changes a decision the
developer is making — the idiom's name is the lookup handle, the finding is the cost it removes.

| Idiom | Use it when | Signal in the code under review |
|---|---|---|
| **RAII** (`R.1`) | Any resource with a release step: descriptors, locks, mappings, registrations, subscriptions | A release call on every exit path, or a `close()` the caller must remember |
| **Scope guard** | One-off cleanup or rollback that no type owns | `goto cleanup`, or cleanup duplicated in several `catch` blocks |
| **Rule of zero / rule of five** (`C.20`, `C.21`) | Always; five only when the type itself manages a resource | A user-declared destructor with default copy operations (double release) |
| **Pimpl** (`I.27`) | A public library type whose ABI or header dependencies must stay stable | A public header pulling in third-party headers for a private member |
| **Non-virtual interface** | A base must enforce checks or logging around every override | Every override repeating the same pre/post steps |
| **Type erasure** | Value-semantic polymorphism for callbacks and strategies, without a hierarchy | A one-method interface plus a heap-allocated implementation per call site |
| **`std::variant` + overload set** | A closed set of alternatives, visited exhaustively | A `kind` enum with members valid only for some kinds |
| **Strong typedef** (tagged wrapper type) | Two parameters of one primitive type that mean different things | `f(std::uintmax_t size, std::uintmax_t limit)` with the arguments swappable |
| **Named constructor / factory returning `std::expected`** | Construction that can fail as a normal outcome, or several ways to build one type | A constructor that throws on bad config, or an `is_valid()` checked after construction |
| **Immediately invoked lambda** | A `const` member or local whose initialisation needs several statements | A non-`const` member assigned in the constructor body only because the initialiser was complex |
| **Passkey** | A constructor that must be public for `std::make_shared` / `std::make_unique` but callable only by the factory | A public constructor with a comment saying "do not call" |
| **`enable_shared_from_this` / `weak_from_this`** | An object must keep itself alive, or check it is alive, across an asynchronous callback | `this` captured in a completion handler with nothing guaranteeing the object outlives it |
| **Hidden friend** | Operators and customisation points for a type, found only by argument-dependent lookup | Free operators in a namespace that make overload resolution slow or ambiguous |
| **Scoped locking** (*POSA 2*; `std::scoped_lock`) | Every mutex acquisition | Manual `lock()` / `unlock()` |
| **Thread-safe interface** (*POSA 2*) | A class locked internally: public members lock, private members assume the lock | Public members calling each other and self-deadlocking, or a recursive mutex added to hide it |

**Idioms not to recommend any more** — flag them where they appear, with the modern replacement:

- **Double-checked locking** → a function-local `static` (thread-safe since C++11) or
  `std::call_once`.
- **Thread-specific storage by hand** → `thread_local`.
- **Safe bool** → `explicit operator bool`.
- **SFINAE / `std::enable_if`** in new code on C++20 → concepts and `requires`.
- **Erase–remove** on C++20 → `std::erase` / `std::erase_if`.
- **Copy-and-swap** written by hand for a type that could follow the rule of zero → the rule of
  zero; keep copy-and-swap only where the strong exception guarantee is required and measured
  acceptable.
- **`std::auto_ptr`, owning raw `new`/`delete`** → `std::unique_ptr` and `std::make_unique`.

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
