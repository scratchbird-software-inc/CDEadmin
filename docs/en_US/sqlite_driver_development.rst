SQLite driver development and platform qualification
===================================================

The admitted profile is SQLite 3.53.0 through Python's ``sqlite3`` module.
The Python version alone does not identify the embedded SQLite runtime. Bundle
and test the actual library used by the application's Python interpreter;
never replace the operating system's SQLite library. This profile's native
qualification includes FTS5, R-tree and JSON. The runtime must support threads;
connections have exclusive execution ownership even when shared by application
request threads. Preserve platform architecture and extension-module ABI when
packaging ``_sqlite3`` and its native library.

.. note::

   Owner direction, 2026-10-29: SQLite is no longer limited to exactly 3.53.0.
   Any runtime at or above the declared floor (``version_range.minimum`` in
   ``web/pgadmin/cdeadmin/ui_descriptors/sqlite/capabilities.json``, currently
   3.35.0) is admitted; 3.53.0 remains the reference profile. Version-specific
   features are gated per runtime, and grammar/keyword tables track older and
   newer features until a version is explicitly retired. The exact-version text
   in this section is retained as the earlier rule and is being migrated in
   phases; components not yet migrated still require 3.53.0.

Check the interpreter which will run ScratchRobin::

    python -c "import sqlite3; print(sqlite3.sqlite_version, sqlite3.threadsafety)"

On Linux, an isolated library directory can be selected with
``LD_LIBRARY_PATH`` before starting Python **only when** its ``_sqlite3``
extension dynamically loads that library. Some managed Python builds embed
SQLite statically; changing the library path cannot change their reported
SQLite version. Build or choose an interpreter linked to the exact 3.53.0
library and verify ``sqlite3.sqlite_version`` in that process. Windows and
macOS teams should use
their application's packaged interpreter/library arrangement. A library change
inside an already running process is not an admitted runtime switch. The
portable gate records the actual SQLite source ID and compile options.

Driver behavior
---------------

Queries retain a native connection and run on one worker, publishing up to two
queued pages of 256 rows or a 1 MiB target. A single large cell can exceed the
byte target. A SQLite statement can contain a trigger body with semicolons;
the driver does not split SQL text. It does not silently substitute
``executescript`` for ``execute`` because their transaction behavior differs.
SQLite shell dot-commands belong to the separate native CLI interface; they
are not SQL accepted by this driver.

Named ``:name`` and positional ``?`` parameters are admitted. SQLite's native
storage classes remain authoritative: no DECIMAL type is invented. Unsafe
browser integers are decimal text; BLOBs are base64 objects containing
``encoding``, ``data`` and ``byte_length``. Bind exact signed 64-bit integers
with ``{"encoding":"integer","data":"9223372036854775807"}``; bind binary
with ``{"encoding":"base64","data":"AP8="}``. Ordinary JSON numbers must
fit the safe integer range or be finite floating-point values. Results preserve
floating-point representations as text. SQL NULL remains null.

Malformed UTF-8 TEXT is returned as base64 with
``native_storage_class: "text"``; no replacement characters are invented.
Rebinding its bytes as TEXT requires an explicit SQL cast. Result column keys
include ordinals because labels can repeat and a SQLite column can hold
multiple storage classes. Optional ``detect_types`` invokes Python's registered
converters and their own precision/timezone behavior; leave it at ``none`` to
retain native storage values.

On Python versions exposing ``LEGACY_TRANSACTION_CONTROL``, the connector
selects it explicitly so the route's ``isolation_level`` retains its documented
behavior across changes to Python defaults. The ``autocommit`` route selects
``isolation_level=None``; explicit SQL transactions remain native SQLite work.

Cancel requests SQLite interruption and observes its native result. It does
not claim that a write had no effects or that only one statement rolled back.
The actual ``in_transaction`` value remains authoritative. A busy COMMIT can
leave a transaction open for an explicit user retry; the driver never retries
the decision automatically. I/O/ownership uncertainty blocks reuse until
close. Closing cancels active work, drains presentation state and releases the
connection. If the worker or release has not finished, ownership is retained.

File operations
---------------

Read-only routes apply to configured attachments too. Attachment names are
quoted native identifiers and can contain Unicode or spaces. Connection paths
remain within the registered filesystem root. This route boundary is not a
sandbox for arbitrary SQL executed by an authorized SQLite user.

Backup and restore use SQLite's online backup API with a deadline checked
between native backup steps. The forms expose the deadline, defaulting to
30 seconds and capped at 3600. An active transaction must first be resolved.
Backup copies to an owned staging file, verifies ``quick_check``, flushes it
and publishes it atomically. Failure before publication preserves any old
backup. An existing destination is replaced only with explicit overwrite;
without overwrite, publication refuses a concurrent destination. POSIX
filesystems must support hard links for exclusive publication; Windows uses
native no-replace rename. Filesystem crash durability is distinct from atomic
publication. Backup artifacts must be offline: known attached destinations,
active-file aliases and destination journal sidecars are refused.

Restore checks the SQLite header and integrity before using an escaped
read-only URI, so legal filenames containing ``?``, ``#``, ``%`` or Unicode do not
become URI options. Filename whitespace is preserved; platform filesystem
naming rules still apply. SQLite can refuse a cross-page-size restore into a
WAL destination. Preserve that native refusal and its code; do not change
journal mode automatically. Native page-size and journal behavior are preserved. SQLite
WAL remains supported as a SQLite feature. A restore I/O failure can quarantine
the destination session; investigate it before deliberate retry.

Portable qualification
----------------------

With the intended Python/SQLite runtime selected, run from the repository root::

    python tools/cdeadmin_sqlite_driver_platform_gate.py \
      --evidence /external/workarea/new-sqlite-proof

Use a new directory outside the repository. The gate creates and removes only
its owned fixture files, calls the production provider and driver, records
source hashes, and fails if checks or cleanup fail. It exercises exact values,
bindings, bounded fetch, transactions/savepoints, FTS5/R-tree/JSON, interruption,
WAL backup/restore, page size and read-only enforcement. Additional regression
tests in ``tools/tests/test_sqlite_driver.py`` cover busy decisions, backup
failure/deadline behavior, aliases, cleanup retry and session independence.

Linux evidence does not prove native Windows/macOS behavior. Those teams run
this gate with their packaged libraries and own UX, accessibility and platform
release acceptance; native driver defects they find remain backend work.

Native catalog declaration generation
-------------------------------------

DDN creation and replacement accept SQLite's stored declaration spellings,
including bare, bracketed, backtick and quoted identifiers. Native compilation
governs optional trigger timing and comments/spacing between header tokens.
Generation binds the created name to the exact DDN namespace and uses the
engine's identifier quoting. Identifier generation uses the statement byte budget;
native names longer than 256 bytes remain supported. Keywords follow SQLite's
ASCII case rules, preserving distinct Unicode identifier names.
Explicit contradictory namespaces, names and owners are refused. Expression,
constraint, SELECT and trigger bodies retain their original text. Header spelling
is normalized for definition comparison; the exported catalog retains its native
SQL. An existence clause is creation policy rather than an object property;
reviewed generation creates the object explicitly and checks native outcomes.

The declaration helper can bind TEMP and attached namespaces, with an explicit
observed owner for TEMP triggers. This does not authorize an independent file
migration from retained-session observations. That migration path continues
requiring its registered main file, while original-session DDN application
remains a separate implementation requirement. Native SQL compilation and
authorization own grammar, extension/function/collation binding and execution.

``tools/cdeadmin_sqlite_native_declaration_qualification.py`` qualifies native
catalog import through the authenticated application API, reviewed application,
independent data/schema observations and retained-scope refusal. Use the pinned
Python/SQLite runtime and a new external evidence directory. It does not start
database servers or exercise deferred ScratchBird history.

Catalog-derived column additions
--------------------------------

An existing table's desired native CREATE declaration and complete column and
constraint records generate reviewed ADD COLUMN stages automatically. Untyped
columns, declared types, defaults, CHECK/NOT NULL/REFERENCES constraints and
virtual or stored generated columns retain their native definitions. Several
columns can share an atomic batch, including generated expressions referring
to an earlier added column, new indexes/triggers using those columns and native
view projections. Existing columns, table constraints, STRICT/WITHOUT ROWID
options, rows, indexes and triggers are preserved. A change to an existing
definition requires its separately reviewed migration or table rebuild.

Preview prepares native statements and executes them only on an owned empty
prototype. This establishes the resulting schema, not suitability for existing
rows. The real write transaction revalidates the parent and child definitions,
then SQLite checks its actual data. In pinned SQLite 3.53 a stored generated
column, nonconstant default or NOT NULL column without a non-NULL default can
be added to an empty table; populated tables may refuse those operations.
CHECK/STRICT and foreign-key checks also remain native. A refusal rolls back
the entire batch, including earlier added columns, and records the native error.
Duplicate requests return the durable result without replay. Native column and
constraint facts are checked before commit and after independent rediscovery.
This workflow retains the independent main-file scope boundary described above.

The catalog dialog's ``Native column additions`` controls generate the desired
DDN from structured properties. Several columns can be designed together without
writing a CREATE/ALTER command or constructing native_json. Fields preserve a
blank declared type, nullability, default and generated expressions/storage,
collation, CHECK expressions, named constraints and REFERENCES targets/actions,
MATCH and deferrable/initial timing. Selecting no referenced column uses the
native referenced primary key. Generation observes the registered baseline and
materializes schema definitions only on an owned empty prototype; it never
copies user rows or applies SQL to the registered file. The generated design
uses the existing separate preview/review/confirmation and durable receipts.
Changing targets discards late generator replies. Stale, retained-session and
cross-target/URL-bound designs are refused by the backend.

Installed functions/collations and custom virtual modules still need matching
owned preview adapters. The generator can reproduce core FTS3/4/5 and RTree
declarations; it refuses an unknown module rather than invoking its arbitrary
creation callback during schema-only generation. This is an explicit preview
implementation boundary, not a declaration that the native module is absent.

Original query-connection DDN
----------------------------

``Original-session SQLite design`` in the Query Tool's engine controls captures
TEMP, attached and pending schema definitions from the existing query connection.
Its DDN preview, review and application use that same handle. Begin a transaction
with the Query Tool controls before preparing a review. No file reopening or
namespace projection grants authority over these definitions. The independent
registered-file migration continues refusing retained-session provenance.

Native table/view/index/trigger creation, explicit removal, view/index/trigger
replacement and ordinary-table column additions use ordered native stages.
Structured column properties support main, TEMP and attached tables, including
same-named relations in different namespaces. The DDN designer is the paired
sister-project editor. An empty owned schema establishes native grammar and
resulting facts without copying user rows or executing mutations on the query
connection during preview. Native callbacks and actual write-time checks remain
authoritative at each application stage. Unimplemented preservation transforms,
unobservable trigger owners and unreproducible installed capabilities remain
explicit gaps; they are not engine features to discard from the product matrix.

Application owns only its nested savepoint and never commits the caller's
transaction. The acknowledgement is ``applied_pending_caller_transaction``;
later commit/rollback decisions are not inferred from closing a session. A
review binds native schema/settings, attachments, authorization and the original
request revision. Intervening query or transaction work requires a new review.
SQLite cancellation/severe errors can end a whole transaction, so cancellation
does not promise that every preexisting pending row survives. Receipts preserve
the observed native transaction state, cleanup and unknown outcomes separately.

Durable uncertainty precedes dispatch. Duplicate tokens never redispatch, and
receipt inspection/retention does not require opening a SQL workspace after the
original connection closes. Unresolved dispatch evidence is retained. Native
acknowledgement is saved before releasing the session for reuse; receipt-storage
failures do not erase a known engine acknowledgement. Constructor-observed
virtual-module storage remains module managed even when SQLite's transient
``table_list`` flags expose it as ordinary storage under namespace shadowing.
Native table definitions and storage facts are verified separately from that
classification. No name-suffix guess establishes module ownership.

Original-session native ALTER TABLE
----------------------------------

The original-session design controls generate desired DDN for ordinary native
table/column renames, column removal, named constraint removal, SET/DROP NOT
NULL and named/unnamed CHECK additions. Native constraint conflict policies are
preserved. The selected table and its namespace come from the captured original
catalog; same-named main, TEMP and attached relations remain distinct. Ordered
backend batches bind later operations to the table's current native name.
The native empty prototype uses the original foreign-key, legacy-alter and
recursive-trigger modes. Generation and review do not mutate caller data.

Application uses the original authorized handle and the retained DDL receipt
workflow. Native column-removal effects and existing-row checks occur within
the owned savepoint. Successful DDL stays pending the caller's commit/rollback;
a later refused constraint restores earlier stages and caller work. Native
authorizer column arguments for DROP COLUMN and SET/DROP NOT NULL are preserved
exactly. Normal native dependency rewriting includes views, triggers, indexes
and foreign keys. Identity/projection changes affecting external-content FTS
require their explicit preservation adapter; unrelated namespaces remain usable.

The pinned SQLite3.53.0 runtime refuses quoted DROP CONSTRAINT lookup and can
refuse table rename with a dependent trigger when TEMP shadows the table name.
Direct native reproductions establish these limitations. Constraint removal
requires one identifier token whose raw spelling equals the actual name,
including literal quote characters where present. Names requiring additional
quoting need a preservation rebuild; they are refused before native dispatch.
Other native refusals leave original state untouched during generation. These limitations,
broader module transformations and original-session rebuild work remain visible
in the product backlog. This workflow does not establish full SQLite acceptance.

The native declaration qualification command additionally exercises all seven
ALTER families through authenticated generation/preview/review/apply in main,
TEMP and an attached namespace, original pending data/savepoint preservation,
native data-dependent refusal and durable duplicate dispatch refusal. The
source packet remains structurally complete rather than release proven;
recorded runtime evidence qualifies only its stated installation and scope.
