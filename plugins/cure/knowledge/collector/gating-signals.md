# Gating signals: definitions and searches

The `collector` agent reads this file before it writes §10 of the digest. Run each search as written.

## Definitions

- *Added lines* are the `+` lines of the target's diff (`git diff <base>...<head>` or
  `gh pr diff <number>`).
- *Whole files at HEAD* are the changed files at the target's head commit: the working tree when that
  commit is checked out; otherwise `git show <head>:<path>`, after `git fetch origin <head>` for a pull
  request whose head (`gh pr view <number> --json headRefOid`) is not local.

## Searches

- `concurrency`: this search over the changed C++ files, whole files at HEAD:
  `grep -nE '\b(j?thread|this_thread|async|atomic[a-z_]*|(recursive_|shared_|timed_|recursive_timed_|shared_timed_)?mutex|condition_variable(_any)?|lock_guard|unique_lock|shared_lock|scoped_lock|(shared_)?future|promise|packaged_task|latch|barrier|(counting|binary)_semaphore|call_once|once_flag|stop_(token|source|callback)|execution::[a-z_]+|pthread_[a-z_]+|sem_[a-z_]+|thread_local|co_await|co_yield|co_return|co_spawn|strand|__atomic_[a-z_]+|__sync_[a-z_]+|g_(thread|mutex|rec_mutex|rw_lock|cond|atomic|once|async_queue|thread_pool)_[a-z_]+|G(Mutex|RecMutex|RWLock|Cond|Thread|ThreadPool|AsyncQueue|Once)|GST_[A-Z_]*LOCK|tbb::[a-z_]+|QtConcurrent|Q(Thread|ThreadPool|Runnable|Mutex|MutexLocker|RecursiveMutex|ReadWriteLock|ReadLocker|WriteLocker|WaitCondition|Semaphore|SemaphoreReleaser|Future|FutureWatcher|Promise|Atomic[A-Za-z]*))\b|#\s*pragma\s+omp'`
  The search also covers the GCC `__atomic_`/`__sync_` builtins, GLib and GStreamer locking, and OpenMP
  pragmas.
- `templates`: this search over the changed C++ files, whole files at HEAD:
  `grep -nE '\btemplate\b|\bconcept\b|\brequires\b|(^|[(,])\s*(\[\[[^]]*\]\]\s*)?(const\s+)?([A-Za-z_][A-Za-z0-9_:]*(<[^;{}()]*>)?\s+)?auto(\s+const)?\s*(&&|&|\*)?\s*(\.\.\.)?\s*[A-Za-z_]*\s*[,)]'`
  The last alternative matches an `auto` parameter, with or without an attribute, a `const` or a type
  constraint (template arguments included): an abbreviated function template, a constrained `auto`
  parameter, or a generic lambda. It misses an `auto` parameter with a default argument
  (`void f(auto x = 0)`).
- `public_header`: a changed header (`.h`, `.hh`, `.hpp`, `.hxx`) whose path has an `include/`
  component, or whose file name appears in an install rule (`install(FILES`, `PUBLIC_HEADER`,
  `install_headers(`, `FILES:${PN}-dev`) found by `grep -rn '<file name>'` over the build files of
  the repository.
- `ipc_surface`: a changed file with extension `.proto`, `.idl`, `.fidl`, `.aidl`, `.capnp`,
  `.thrift` or `.socket`; a changed `.xml` file containing `<interface name=`; or an added line
  matching
  `grep -nE 'sd_bus_|g_dbus_|dbus_|grpc::|zmq_|\bsocket\(|\bbind\(|\blisten\(|mq_open|shm_open'`.
- `build_dependency`: an added line in a changed `CMakeLists.txt`, `*.cmake`, `meson.build`,
  `Makefile*`, `*.bb`, `*.bbappend`, `*.bbclass`, `*.inc`, `conanfile.*`, `vcpkg.json`,
  `package.json`, `pyproject.toml`, `Cargo.toml` or `go.mod` matching
  `grep -nE 'find_package|target_link_libraries|pkg_check_modules|dependency\(|DEPENDS|RDEPENDS|requires|"dependencies"'`.
- `config_schema`: a changed file with extension `.conf`, `.cfg`, `.ini`, `.toml`, `.yaml`,
  `.yml`, `.json`, `.xsd`, `.service` or `.timer`; a changed file under an `etc/` directory; or a
  changed file whose path contains `schema`.
- `design_document`: a changed `.md`, `.rst` or `.adoc` file under a `doc/`, `docs/`, `design/`,
  `adr/` or `sdk-docs/` directory, or whose file name contains `design` or `adr`.
