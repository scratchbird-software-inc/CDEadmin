DuckDB driver development and platform qualification
===================================================

The admitted native profile is DuckDB 1.5.2 with PyArrow 25.0.1. Install both
into the application's Python environment, matching its platform architecture.
The driver is embedded; it does not invent network authentication, TLS,
server roles or savepoints which this engine does not provide.

Execution and values
--------------------

One worker owns each retained connection until its result is observed or
closed. DuckDB ``cursor()`` creates a separate session, so retained metadata,
SQL and transaction decisions must use the original connection. Native
``extract_statements`` parses scripts; parsing must succeed for the complete script before any statement runs.
Statements execute in order, preserve
each result and stop at the first error. Parameters are permitted for a single
statement; multi-statement parameter requests are rejected before execution.
No text splitting or automatic replay is permitted.

Two presentation pages are queued, each at most 256 rows or a 1 MiB target;
a single large cell can exceed that target. Native DuckDB query memory and
Arrow batch memory are separate from this bound. Cancellation calls native
``interrupt`` and drains the original execution. Neither cancellation nor a
presentation error proves that prior statements or file exports had no effects.

Lossless Arrow conversion is selected for each statement. Result columns have
ordinal keys, native DuckDB types and Arrow type metadata. DuckDB's materialized
relational API can disambiguate duplicate labels with suffixes, including bound
queries and RETURNING; the driver preserves those native labels and ordinals
rather than guessing the original names. Integers beyond the
browser safe range and decimals are exact strings; BLOBs are base64. Temporal
values carry exact native ticks and their Arrow unit/timezone rather than being
truncated to Python datetime precision. Interval months, days and nanoseconds
remain separate. Maps retain ordered key/value pairs, unions retain their tag,
and lists/structs retain their children. Native Arrow union export loses parent
NULL validity. The provider captures union validity and tags in a native
relation projection before export, including nested unions. Each original
value is bound once inside a native lambda; the original SQL is not replayed.
SQL NULL and a tagged NULL remain distinct. RETURNING results retain the native
materialized DML result. Non-returning DML through the relational API exposes no
row count; the driver reports it as unavailable rather than rerunning SQL. DuckDB opaque Arrow types retain native
type, vendor and exact storage bytes; no lossy double or offset-free time is
substituted. UUIDs retain their text representation. SQL NULL remains null.

Named and positional parameters are accepted. Exact integer, decimal and binary
envelopes use ``encoding`` and ``data``; other type-specific values can use
text with an explicit native SQL cast. Unsafe JSON numeric integers and
non-finite raw JSON numbers are refused before execution. Arbitrary nested
JSON values remain DuckDB-native list/struct parameters, not SQL fragments.

Transactions and ownership
--------------------------

Data Studio starts an explicit native transaction. The provider observes native
transaction viability before its COMMIT/ROLLBACK control. DuckDB can return
success from COMMIT of an aborted transaction while discarding its changes;
that case must be reported as rollback. A successful decision and a failure to
start the following transaction are recorded separately. The original decision
is never replayed. I/O, fatal errors or uncertain ownership quarantine the
session. Ordinary native execution errors preserve native transaction behavior.
No common-layer transaction inference is used.

Close interrupts an active worker, waits for release, and closes the original
connection; native release failure retains ownership for cleanup retry.
Shutdown attempts every owned connection. Metadata requests on a retained
connection cannot race with execution or create an unrelated cursor session.
Configured attachments use quoted native identifiers and inherit read-only
routes unless the native engine's stricter rules refuse them. Paths are checked
against the endpoint's registered filesystem root; this is not a sandbox for
arbitrary SQL or extensions executed by an authorized user.

COPY, EXPORT DATABASE and IMPORT DATABASE remain native SQL workflows. Native
file format, filesystem permissions, extension installation, locking and
multi-database write restrictions apply. SQL transaction rollback does not
promise to remove externally written files. DuckDB's own recovery files remain
native DuckDB behavior, unrelated to ScratchBird's MGA contract.

References
----------

* `Python connection ownership <https://duckdb.org/docs/api/python/overview>`_
* `Native transaction behavior <https://duckdb.org/2024/09/25/changing-data-with-confidence-and-acid>`_
* `Lossless Arrow types <https://r.duckdb.org/reference/duckdb_types_arrow.html>`_
* `Arrow export <https://duckdb.org/docs/current/guides/python/export_arrow>`_

Windows and macOS teams run the portable native gate with their packaged
interpreter and actual libraries. Linux evidence does not imply native platform
or UX acceptance. Their discovered native defects remain backend obligations.

Portable native gate
--------------------

From the repository root, with the packaged interpreter::

    python tools/cdeadmin_duckdb_driver_platform_gate.py \
      --evidence /external/workarea/new-duckdb-proof

The evidence directory must be new and outside the repository. The gate calls
the production provider, records source and runtime identities, and removes
only its owned fixture. It checks exact scalar/nested values, ordered scripts,
page bounds, native transaction decisions including aborted COMMIT, same-session
metadata, interruption, Parquet COPY, export/import, read-only mode, release and
independent final effects. A failure or incomplete cleanup is a failing exit.
Additional regression cases cover conflict handling, catalog-qualified keys,
backpressure shutdown, parse refusal and decision/restart failure injection.

The query result envelopes above are the native execution interface. Structured
administration and editable-grid contracts retain their separately qualified
forms and row-identity rules; this gate is not a claim that every GUI workflow
or extension has been exercised on every receiving platform.
