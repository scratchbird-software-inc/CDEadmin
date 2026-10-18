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

Native object comments
----------------------

The existing object task menu exposes reviewed native comments for tables,
columns, views, indexes, sequences, user types and SQL macros. Scalar and table
macros use their distinct native keywords. Indexes remain displayed under their
owner table but are addressed by their catalog/schema/index name. The multiline
field preserves empty text separately from the explicit remove-comment option.

Review retains the native object identity and previous comment. Application
rechecks both on the execution attachment before dispatch and refuses a changed
baseline. Independently owned operations use a native transaction and close the
attachment after commit or failure. Retained-session operations preserve the
caller's pending rows, temporary objects and transaction decision. A failed
observation after native acknowledgement does not trigger a retry or an implicit
rollback of the caller's work; uncertain sessions are blocked from further use.

The pinned DuckDB 1.5.2 runtime rejects database and schema comments as
unimplemented, despite recognizing their syntax. Its FUNCTION comment syntax
addresses SQL macros, not native scalar/table functions. These are not exposed
as additional supported comment targets. Native tags remain observational until
their applicable native interface has been reconciled.

``tools/cdeadmin_duckdb_metadata_qualification.py`` records native effects through
independent catalog queries, including Unicode/quoted names, multiline literals,
empty versus NULL comments, overloaded scalar/table macros, changed reviews and
retained transaction rollback. This evidence covers the object-comment workflow;
the broader six-engine inventory and acceptance remain open.

Native extension discovery and updates
--------------------------------------

Extension discovery preserves all nine fields of DuckDB 1.5.2's native
``duckdb_extensions()`` table: name, loaded/installed state, installation path,
description, aliases, extension version, installation mode and repository/source.
Repository credentials are redacted while the owning extension remains visible.
The Extensions branch offers a reviewed update for installed extension files;
the database task menu offers an update of all installed extension files.
Statically linked built-ins have no separately updateable native file.

Review captures the visible installation facts and native extension/home
directory settings. Dispatch rechecks that installation and resource address.
Results preserve each native extension name, repository, status, previous version
and current installed version. Loaded native code is not replaced by a file
update; a new native database instance loads the updated binary. The native
status ``NO_UPDATE_AVAILABLE`` remains distinct from an installed version change.

Native extension files are outside database rollback. These controls do not
commit or roll back a retained query session, and pending rows and temporary
objects retain the caller's transaction decision. Updating several extensions
can change files before a later failure. Dispatch, acknowledgement, native
results and subsequent observations remain separate; no failure authorizes
automatic replay. An uncertain borrowed session is blocked from further use.

``tools/cdeadmin_duckdb_extensions_qualification.py`` uses an independently owned
installation directory and a signed native repository extension. It compares
all native catalog fields, verifies individual/all update results, changed
installation refusal, corrupt-file refusal and retained transaction behavior.
The receipt records the repository artifact and observed native status.

Original-session extension installation and loading
---------------------------------------------------

The SQL editor's Engine options panel provides typed native INSTALL and LOAD
controls on its original query connection. Select a native name, an authorized
local extension file or a direct public HTTP(S) installation URL. Direct remote
files are installed before their native name is loaded; a remote URL is not
passed to the desktop native loader.
Installation supports FORCE, native repository aliases, public HTTP(S)
repositories, authorized repository directories and exact version selection.
Inline credentials, URL queries and fragments are refused; authenticated remote
source admission and wider installed-capability reconciliation remain separate work.

Review retains all nine extension facts, installation/home directories, native
signature/external-access settings and original catalog/session identity.
Local sources and installed files selected for loading are bound to file bytes
and identity. Native extension aliases resolve to the observed canonical name.
Apply requires exact confirmation, rechecks the baseline and executes once.
Receipts distinguish dispatch, native acknowledgement, observed effects and
uncertain outcomes; a repeated request reads the receipt without executing again.
An acknowledged operation can have unverified subsequent observations.

Loaded code and installed files survive ordinary database rollback; the controls
do not commit or roll back pending rows or temporary objects. FORCE replaces
installation files while existing native code remains loaded. DuckDB can upgrade
an HTTP repository URL to HTTPS after HTTPFS has loaded. Native signature,
repository, external-access and compile-time policies remain engine decisions.
Unknown outcomes block session reuse. Receipts remain bound to the live original
session; durable reconciliation after closing that instance remains open.

``tools/cdeadmin_duckdb_extension_actions_qualification.py`` uses an actual signed
HTTPFS binary and owned repositories. It verifies local/direct-URL installation, canonical
alias loading, HTTPFS execution, versioned repository/FORCE and directory
installation, preserved pending rows and temporaries, rollback distinctions,
changed-file/policy refusal and non-replay for file and authorized memory roots.

Reviewed native file attachments
--------------------------------

The attachment workspace can inspect, review and apply directly on its original
retained query connection. It supports existing files, explicit native file
creation, read-only/read-write access, IF NOT EXISTS, OR REPLACE and DETACH IF
EXISTS under the registered filesystem policy. Exact native aliases, including
long quoted Unicode names, retain DuckDB's ASCII case comparison. The original
registered catalog and internal catalogs are protected from replacement/removal.

Review binds the native connection identity, registration, original catalog OID,
observed attachment namespace and applicable file identity. Dispatch checks those
facts again. A changed namespace or file retires the review before dispatch.
Repeated submissions return the stored session receipt, including after an
uncertain reply. A lost apply reply locks the form until the receipt is read.
An uncertain native session remains blocked; a closed original connection cannot
be replaced with another connection to continue that review.

Operations leave commit and rollback to the caller. In the pinned native engine,
an attachment created in a transaction disappears on rollback; a detached
catalog is not restored by rollback. A newly created file is not deleted by
rollback. Catalog changes can be visible to other connections sharing the native
instance. Registered automatic attachments may be restored when another
connection opens. Native acknowledgement, rediscovery and possible catalog/file
effects are recorded separately; external file/instance administration is not
fenced and no failure authorizes automatic replay.

The original SQL-preview endpoint remains available. Direct execution uses the
new session-bound workflow. ``tools/cdeadmin_duckdb_attachment_qualification.py``
exercises it for file and explicitly authorized memory roots, pending rows and
temporary objects, creation/conflict modes, rollback distinctions, stale
namespace refusal, original-session binding and failed observations. Encrypted
attachment options and remote extension-backed attachment types retain their
separate capability and credential-admission obligations.
