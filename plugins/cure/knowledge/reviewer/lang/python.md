# Python supplement — reviewer

Load this only when the change under review contains Python (`.py`, `.pyi`). It lists the defects
Python makes easy to write, so that you look for them deliberately. Where the project has its own
Python conventions, they win over this file.

Python has no single equivalent of the C++ Core Guidelines. The closest sources, cited here, are
the rule catalogues of the linters that encode the community's accumulated pitfalls — Ruff, which
implements `flake8-bugbear` (`B`), `flake8-async` (`ASYNC`), Bandit (`S`) and Pylint (`PL`) rules
under their original codes — together with the Python documentation (notably *Developing with
asyncio*) and the *Google Python Style Guide*. Cite a rule code when it helps the author look it up;
the finding is still the failing scenario.

**A pitfall is a finding only with a concrete failing scenario in this code.** If the project runs
Ruff, Pylint, mypy or Bandit in CI, do not repeat what they already report; spend the review on what
a tool cannot see — the input that triggers it, the caller that depends on it.

## Values, defaults and truthiness

- **Mutable default arguments** (`B006`) and **calls in default arguments** (`B008`) — evaluated
  once, shared by every call.
- **Mutable class attributes** used as per-instance state — every instance shares the list.
- **Truthiness where zero or empty is valid** — `if timeout:` treats `0` as "not given";
  `x or default` replaces a legitimate `0`, `""` or `[]`.
- **`is` compared with a literal** (`F632`) — works for small integers by accident.
- **`__eq__` defined without `__hash__`** — instances become unhashable, or hash inconsistently.
- **Float equality**, and `round()` rounding half to even.

## Closures, iteration and generators

- **Late-binding closures in a loop** (`B023`) — every lambda or inner function sees the last value
  of the loop variable.
- **Mutating a collection while iterating it** — a `dict` raises; a `list` silently skips elements.
- **An iterator or generator consumed twice** — the second pass sees nothing.
- **`zip()` truncating silently** (`B905`) where the inputs must be the same length; use
  `strict=True`.

## Exceptions

- **Bare `except:` or `except BaseException:`** (`E722`) — also catches `KeyboardInterrupt`,
  `SystemExit` and `asyncio.CancelledError`, which breaks shutdown and cancellation.
- **`raise` inside `except` without `from`** (`B904`) — the original cause is lost or misattributed.
- **An error logged without its traceback** — `logger.error(e)` instead of `logger.exception(...)`
  or `exc_info=True`.
- **Errors returned as `None`** that callers never check.

## Resources, files and time

- **`open()` without a context manager** (`SIM115`) — the descriptor leaks on the error path.
- **`open()` without `encoding=`** (`PLW1514`) — the default follows the locale, which on an
  embedded image is often `C`/POSIX, so non-ASCII text fails on the device and not on the desk.
- **Naive datetimes** — `datetime.utcnow()` (`DTZ003`, deprecated since 3.12) and mixing naive
  with aware values; **`time.time()` for durations** where `time.monotonic()` is needed (a clock
  jump, or a board with no RTC, breaks it).

## Subprocesses and untrusted input (Bandit)

- **`shell=True` with interpolated input** (`S602`) — command injection.
- **`subprocess.run` without `check=True` or a checked return code**, and **without `timeout=`** — a
  failed or hung command passes unnoticed.
- **`pickle` on data that crosses a trust boundary** (`S301`), **`yaml.load` without a safe loader**
  (`S506`), **`tempfile.mktemp`** (`S306`).

## asyncio

- **A dropped `create_task` result** (`RUF006`) — the task can be garbage-collected mid-run, and
  its exception is never observed.
- **Blocking calls in a coroutine** (`ASYNC` rules) — `time.sleep`, synchronous file or network
  I/O, CPU-bound loops; every other task on the loop stalls.
- **`CancelledError` swallowed** — a broad `except` in a coroutine, or `finally` that awaits
  without re-raising.
- **`asyncio.gather` without `return_exceptions` or a `TaskGroup`** — on the first failure the
  other tasks keep running unobserved.
- **An awaited call with no timeout** (`asyncio.timeout`, `wait_for`) on a peer that can hang.
- **Loop objects touched from another thread** without `call_soon_threadsafe` or
  `run_coroutine_threadsafe`.

## Threads, processes and signals

- **Compound operations assumed atomic because of the GIL** — `counter += 1`, check-then-set on a
  `dict`.
- **`fork` after threads have started** — locks held by other threads stay locked in the child.
- **Signal handlers installed outside the main thread**, or a `SIGTERM` with no handler, so
  `finally` blocks and context managers never run on shutdown.

## Imports and typing

- **Circular imports** that work only in one import order — a partially initialised module.
- **Side effects at import time** that a test or another entry point triggers unintentionally.
- **Type hints that lie** — `Optional` omitted where `None` is returned, an override that narrows a
  parameter type; hints are not enforced at run time, so the lie reaches production.
