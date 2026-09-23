# C++ supplement — reviewer

Load this only when the change under review contains C++ (`.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`,
`.hxx`, or a `.h` included from C++). It lists the defects C++ makes easy to write, so that you look
for them deliberately. Where the project has its own C++ conventions, they win over this file.

Rule IDs are from the *C++ Core Guidelines* (Stroustrup & Sutter). Cite one when it helps the
author look the rule up; the finding is still the failing scenario.

**A pitfall is a finding only with a concrete failing scenario in this code.** "This pattern is
dangerous in general" is not a finding. If the project runs `clang-tidy` (`bugprone-*`,
`cppcoreguidelines-*`) or sanitizers in CI, do not repeat what they already report; spend the
review on what a tool cannot see — the scenario, the caller, the lifetime across a callback.

## Lifetime and dangling

- **Views outliving their source** — a `std::string_view` or `std::span` bound to a temporary, to
  `std::string` returned by value, or stored as a member past its source's lifetime; `c_str()` of a
  temporary passed on.
- **References and iterators invalidated** — a reference or iterator into a `std::vector` kept
  across `push_back`, `insert` or `erase`; erasing inside a range-`for` over the same container.
- **Range-`for` over a member of a temporary** — `for (auto& x : make().items())` dangles before
  C++23.
- **Returning a reference or view to a local.**
- **Lambdas that escape with reference captures** (`F.53`) — `[&]` in a callback, a stored
  `std::function`, a spawned coroutine, or a thread.
- **`this` captured in an asynchronous handler** with nothing guaranteeing the object outlives the
  operation; a member touched after `co_await` before the cancellation or liveness check.
- **Owner destroyed while the executor keeps running.** A runner that resets the service on
  SIGTERM and then keeps the `io_context` running completes every pending operation with
  `operation_aborted`, and each completion resumes its coroutine. A cancellation signal requests
  cancellation; it does not prevent the resume. Every member access between the resume and the
  liveness check runs on a destroyed object:

  ```cpp
  auto [ec, reply] = co_await m_client.call(...);
  m_in_flight.erase(file);            // use-after-free once the owner is gone
  if (ec == asio::error::operation_aborted || ct.expired())
      co_return;
  ```
- **Coroutine parameters by reference** (`CP.53`) and **capturing lambdas that are coroutines**
  (`CP.51`) — the referent is gone once the coroutine suspends.
- **Use after `std::move`** — a moved-from object read as if it still held its value (`ES.56`).

## Undefined behaviour

- **Uninitialised variables and members** (`ES.20`) — especially scalar members not set in every
  constructor.
- **Signed overflow, out-of-range shifts, out-of-bounds indexing**, and `operator[]` on an index
  that was never checked.
- **Data races** — any object written on one thread and read on another without synchronisation,
  including through a callback run on another executor.
- **Type punning through `reinterpret_cast`** where `std::memcpy` or `std::bit_cast` is needed.

## Integers and conversions

- **Unsigned subtraction that wraps** — `a - b` on `std::size_t` or `std::uintmax_t` when `b` can
  exceed `a` (`ES.106`); a loop counting an unsigned index down to zero.
- **Mixed signed and unsigned comparison** (`ES.100`) — `-1 < v.size()` is false.
- **Narrowing** (`ES.46`) — 64-bit sizes and offsets into `int`, `std::chrono` counts truncated by
  `duration_cast`, `time_t` into a 32-bit type.

## Exceptions and error codes

- **A destructor that throws** (`C.36`), or a `noexcept` function that can throw — both end in
  `std::terminate`.
- **Catch by value** slices the exception (`E.15`); catch by reference.
- **An exception escaping a constructor's member-initialiser list** or `main`, where the caller
  does not expect one.
- **`std::filesystem` throwing overloads** used where the `std::error_code` overload was intended,
  or the reverse: an `error_code` overload whose `ec` is never checked.
- **`errno` read late** — after a logging call or any other library call that can overwrite it.
- **An exception thrown inside an asynchronous handler or a detached `co_spawn`** with no
  completion handler that observes it — it is swallowed or terminates the process, depending on the
  framework.

## Classes and special members

- **Deleting through a base pointer without a virtual destructor** (`C.35`).
- **Slicing** (`ES.63`) — a derived object copied into a base value.
- **A user-declared destructor with the default copy operations** — two objects release one
  resource.
- **Self-assignment and self-move** that release before copying.

## Concurrency

- **Locking several mutexes in inconsistent order** — use `std::scoped_lock` (`CP.21`).
- **Waiting on a condition variable without a predicate** (`CP.42`) — spurious and lost wakeups.
- **Detached threads** (`CP.26`) that outlive the objects they use.
- **Work in a signal handler** that is not async-signal-safe (allocation, locking, logging).

## Asynchronous frameworks (Asio and similar)

- **`operation_aborted` treated as an error, or as success** — cancellation must end the operation
  quietly.
- **Edge-triggered notifications for a level condition** — a timer cancel or event notify with no
  waiter is lost; work queued meanwhile waits for the next unrelated event.
- **Blocking calls on the executor thread** — synchronous file or network I/O, `sleep`, long loops
  with no suspension point.
- **A remote call awaited with no deadline** — a peer that never replies holds the coroutine and
  everything it owns forever.

## Standard library traps

- **`std::map::operator[]` on a lookup** inserts a default element; on a `const` map it does not
  compile, which is the hint.
- **`std::remove` / `std::remove_if` without `erase`** — before C++20's `std::erase_if`.
- **`auto` in range-`for` copying** heavy elements, or binding a proxy (`std::vector<bool>`).
- **`std::accumulate` with an `int` initial value** over floating-point or 64-bit data.
- **A `std::string_view` passed to a C API** that expects a null-terminated string.

## POSIX and the filesystem

- **`EINTR` and partial `read`/`write`** not retried.
- **Descriptors leaked** on an error path, or inherited by a child process (`O_CLOEXEC`).
- **Durability claimed without it** — a file renamed into place without `fsync` of the file and of
  its directory, where the design says it survives power loss.
- **Time from the wall clock** (`system_clock`) used for durations or ordering, where a jump
  (NTP, a board with no RTC) breaks it; `steady_clock` for intervals.

## Headers and linkage

- **`using namespace` in a header** (`SF.7`).
- **One-definition-rule violations** — a non-`inline` function or variable defined in a header, or
  two definitions of one entity that differ.
