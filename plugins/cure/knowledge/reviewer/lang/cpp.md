# C++ supplement — reviewer

Load this only when the change under review contains C++ (`.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`,
`.hxx`, or a `.h` included from C++). It lists the defects C++ makes easy to write, so that you look
for them deliberately. Where the project has its own C++ conventions, they win over this file.

Rule IDs are from the *C++ Core Guidelines* (Stroustrup & Sutter). Cite one when it helps the
author look the rule up; the finding is still the failing scenario. This file does not restate
Core Guidelines rules. When `review-change` dispatches the `cg-*` agents, they check the code
against the rules of their sections. An entry here is a defect the rules do not name, or the
project- or domain-specific form of one.

When the brief has no `Core Guidelines:` line naming `cg-*` report paths, no Core Guidelines rule
is checked in this run. State in the report, on its own line before the reading footer:
`Core Guidelines not checked: no cg-* agent ran.` Do not read the condensed section files instead.

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
- **Use after `std::move`** — a moved-from object read as if it still held its value. Related:
  `ES.56`, `C.64`.

## Undefined behaviour

- **Data races through a callback run on another executor** (extends `CP.2`) — a completion
  handler that writes state another executor or thread reads without synchronisation.
- **Out-of-range shifts** — a shift by a negative amount or by at least the bit width of the
  promoted operand.
- **Unchecked indexing** — `operator[]` on an index that was never checked against the size.
- **Type punning through `reinterpret_cast`** where `std::memcpy` or `std::bit_cast` is needed.

## Integers and conversions

- **Time truncated** (extends `ES.46`) — `std::chrono` counts truncated by `duration_cast`;
  `time_t` stored in a 32-bit type.

## Exceptions and error codes

- **A function that mutates state and then throws.** The function writes a member, an
  out-parameter or a global, then throws or calls something that can throw. The caller sees a
  partial update: a container half-filled, a member set and its counterpart not, a file renamed
  before the index is written. Check which guarantee the function gives and that its callers need
  no more: strong (build the result on the side and commit at the end with non-throwing
  operations, or roll back in a scope guard), or basic (invariants hold, the state is valid but
  changed). A throw after the first observable write with neither is the defect.
- **An exception escaping a constructor's member-initialiser list** or `main`, where the caller
  does not expect one.
- **`std::filesystem` throwing overloads** used where the `std::error_code` overload was intended,
  or the reverse: an `error_code` overload whose `ec` is never checked.
- **`errno` read late** — after a logging call or any other library call that can overwrite it.
- **An exception thrown inside an asynchronous handler or a detached `co_spawn`** with no
  completion handler that observes it — it is swallowed or terminates the process, depending on the
  framework.

## Concurrency

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

- **One-definition-rule violations** — two definitions of one entity that differ, for example a
  type built under different preprocessor flags in two libraries.
