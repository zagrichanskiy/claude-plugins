# Python supplement — design mode

Load this only in **design mode** when the target contains Python (`.py`, `.pyi`). It adds Python
idiom to `checklist-design.md` and gives the Python form of the patterns in `patterns-design.md`;
it does not repeat them. Where the project has its own Python conventions, they win over this
file — cite them.

Sources: PEP 8, PEP 20 (the Zen of Python), PEP 484/544 (typing, protocols), Ramalho (*Fluent
Python*), Slatkin (*Effective Python*).

## Types and interfaces

- **Prefer composition, plain functions and dataclasses over class hierarchies** (PEP 20 —
  "simple is better than complex"). Flag a class with one method and no state (it is a function),
  and a hierarchy built only to share helpers.
- **`typing.Protocol` for structural interfaces, `abc.ABC` when implementations must inherit
  shared behaviour or be registered** (PEP 544). Flag an ABC whose only purpose is a type hint.
- **Value objects are frozen dataclasses** (`@dataclass(frozen=True, slots=True)`) or `NamedTuple`,
  validated in `__post_init__`. Flag dictionaries passed through several layers as a data model,
  and domain values as bare `str`/`int` (primitive obsession).
- **`enum.Enum` for closed sets and modes**, not string constants or booleans.
- **Type hints are the interface contract.** Flag public functions without them, overrides that
  narrow parameter types or widen return types (Liskov), and `Any` at a boundary.
- **Properties for computed attributes only** — a property that performs I/O or is expensive lies
  about its cost; make it a method.

## Construction and module state

- **`__init__` establishes the invariant and performs no I/O** a test cannot avoid; use a
  classmethod factory (`from_config`, `connect`) for construction that reads files or opens
  connections.
- **Import-time side effects** (opening connections, reading config, spawning threads at module
  level) are hidden global state; flag them.
- **A module is already a singleton.** Flag a Singleton class, and module-level mutable state used
  as a service registry.
- **Mutable default arguments** are shared state across calls; flag them in public signatures.

## Error strategy

- **Each package defines its own exception hierarchy** rooted in one base class, and raises the
  specific type; callers catch what they can act on. Flag bare `except:`, `except Exception:` used
  as control flow, and errors returned as `None`.
- **EAFP versus LBYL** — prefer trying and handling the specific exception to checking first where
  the check races with the action (files, network).

## Resources

- **Context managers** (`with`, `contextlib`) for every acquired resource; flag `close()` a caller
  must remember and `__del__` used for cleanup.
- **Generators and iterators** over materialised lists for streams; flag a generator that holds a
  resource and is never exhausted or closed.

## asyncio

These are design questions about structure; a single missing `await` is a `reviewer` bug.

- **Structured concurrency** — tasks are owned by an `asyncio.TaskGroup` (3.11+) or an owner that
  cancels and awaits them. Flag `create_task` results that are dropped (they can be garbage
  collected mid-run) and tasks that outlive their owner.
- **Cancellation propagates** — flag swallowed or unpropagated `CancelledError`, and cleanup that
  awaits without shielding what must complete.
- **Nothing blocks the loop** — flag synchronous I/O, `time.sleep` and CPU-bound work in
  coroutines; move them to `asyncio.to_thread` or a process.
- **Async resources use `async with` / `async for`.**
- **Shared mutable state has single-threaded reasoning written down**, or a lock, and never both a
  thread and the loop touching it without `call_soon_threadsafe`.

## Python forms of common patterns

| Pattern | Idiomatic Python form | Misuse sign |
|---|---|---|
| Strategy | A callable parameter, or a `Protocol` with one method | A class hierarchy whose subclasses override one method |
| Singleton | A module, or one instance created in `main` and passed down | A metaclass or `__new__` override |
| Factory | A classmethod or a plain function | A factory class with one `create` method |
| Observer | Callbacks held by `weakref` or an explicit unsubscribe | Strong references keeping subscribers alive forever |
| Decorator (GoF) | A wrapper object implementing the same `Protocol` | Confused with `@decorator` syntax, which wraps functions |
| Registry / plugin | Entry points (`importlib.metadata`) or an explicit dict | Import-time self-registration as a side effect |
| Resource management | Context manager | `try/finally` repeated at every call site |
| Value Object | Frozen dataclass | A dict whose keys are validated at every use |
