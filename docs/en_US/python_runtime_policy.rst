*********************
Python runtime policy
*********************

Status: 14 October 2026
=======================

ScratchRobin requires Python **3.14 or newer**. The standard CPython 3.14
build is the first installation baseline for this policy. Python 3.15.0 was
released on 9 October 2026 and is the next version to qualify; a version
number accepted by the entry point does not by itself establish dependency,
provider or platform qualification. Older Python 3.9–3.13 dependency branches
and development/CI targets have been retired.

Free-threaded CPython is a separate interpreter build, usually named
``python3.14t`` or ``python3.15t``. Merely installing Python 3.14 or 3.15 does
not disable the GIL. For a candidate free-threaded process, check both
``sysconfig.get_config_var('Py_GIL_DISABLED') == 1`` and
``sys._is_gil_enabled() is False`` *after* importing the application and the
providers in scope. An unsupported native extension can re-enable the GIL.
Do not force ``PYTHON_GIL=0`` around an extension whose free-threading safety
has not been established.

Qualification state
===================

The application and the current root, regression and reference-engine demo
requirements installed under standard Linux CPython 3.14.6. The application
module and representative PostgreSQL, grammar, Arrow and Milvus dependencies
imported. CPython 3.14.8 was also built with the SQLite 3.53.0 library required
by the exact SQLite provider profile; the generic 3.14.6 build bundled SQLite
3.53.1 and was correctly refused by that profile. An interpreter version does
not override a provider's exact native-runtime requirement. With that exact
3.14.8/SQLite 3.53.0 runtime, 1,496 selected PostgreSQL, SQLite, DuckDB and
affected shared Python tests passed, with 174 additional subtests. The portable
SQLite exact-runtime platform gate also completed with no failures. This does
not replace each provider's live or platform qualification. Existing Python
3.12 receipts remain historical evidence only.

The root requirement set did **not** install under Linux CPython 3.14.6t.
``pymilvus==2.6.5`` depends on ``orjson``; the selected ``orjson==3.13.0``
source build rejects free-threaded Python explicitly. ``psycopg[c]`` is also
under upstream free-threading qualification. Therefore ScratchRobin does not
yet claim a GIL-free full-product runtime, even though the CPython 3.14t
interpreter itself starts with the GIL disabled.

An isolated ``psycopg[c]==3.3.4`` build and import on 3.14t left the GIL
disabled, but that observation is not a concurrency-safety approval. A
temporary install with Milvus omitted then stopped while compiling the
``cassandra-driver`` extension because the local build environment lacked
``ev.h``. That is a build-prerequisite failure, not a demonstrated
free-threading defect. The complete dependency set still has no successful
3.14t installation receipt.

The stable Python 3.15.0 source interpreter also loaded the exact SQLite
3.53.0 library, but the full dependency install did not finish: the pinned
``pyarrow==25.0.1`` selected a source build on this Linux CPython 3.15 ABI
and that build lacked the Arrow C++ package configuration. This is a packaging
dependency gap, not evidence that the application code failed. The 3.15
standard and 3.15t runtimes require separate exact-release qualification.

The next admission gate is a reproducible install of all required providers,
followed by app startup, imports with the GIL still disabled, connection and
session ownership tests under concurrent requests, monitoring/worker tests,
and CPU/memory/latency comparisons with standard CPython. Provider-specific
native modules must be reviewed individually; excluding a provider from a
test is not full-product acceptance. Each platform team must qualify its own
native extensions and client libraries.

References: `Python 3.14 free-threading guide
<https://docs.python.org/3.14/howto/free-threading-python.html>`_,
`Python 3.15.0 release <https://www.python.org/downloads/release/python-3150/>`_,
`orjson free-threading statement <https://github.com/ijl/orjson>`_, and
`Psycopg free-threading tracking <https://github.com/psycopg/psycopg/issues/1095>`_.
