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

Original native parser context
------------------------------

Editor validation uses the retained connection's native statement extractor,
under the same session lock as execution. Native parser settings and installed
parser callbacks therefore belong to the selected instance. An unrelated default
Python connection cannot substitute its parser configuration. Native catalog or
binding failures during parsing remain unknown grammar coverage, rather than
being reported as invalid SQL. Uncertain native failures block session reuse.

``tools/cdeadmin_duckdb_session_parser_qualification.py`` verifies changed native
expression-depth limits, pending rows, temporary objects and the unchanged native
transaction identity for file and authorized memory sessions. Parsing CREATE,
INSERT, DELETE, transaction commands, INSTALL, LOAD and SET does not submit those
commands for execution. Invalid source is not echoed in diagnostics. When native
PRAGMA expansion produces generated SQL, DuckDB's own lexical tokens identify
the original script units. UTF-8 byte boundaries are mapped to the exact original
Unicode source; comments, quoted semicolons and dollar strings remain intact.
Script execution submits the original PRAGMA once, preserving its native
expansion and transaction behavior. Installed third-party parser callbacks
retain separate capability qualification; unframed source remains unavailable.

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
Installation supports FORCE, native repository aliases, HTTP(S)
repositories, authorized repository directories and exact version selection.
Inline credentials, URL queries and fragments are refused. Native HTTP-secret
source admission is described below; wider installed-capability reconciliation
remains separate work.

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
Unknown outcomes block session reuse. Live application remains bound to the
original session. Read-only durable receipts retain its acknowledgements and
observations after closing the instance; see the durable receipt scope below.

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

Attachment controls also support exact unsigned decimal ``BLOCK_SIZE`` and
``ROW_GROUP_SIZE``, native ``STORAGE_VERSION``, and explicitly authorized writable
``:memory:`` catalogs with optional Boolean ``COMPRESS``. Omitted options stay
omitted; native defaults and semantic limits belong to DuckDB. COMPRESS is only
offered for memory targets. Encryption keys and extension-specific options use
separate admission paths and cannot enter these public reviews.

Receipts retain the safe native attachment options and independently observed
storage block counts/sizes as exact decimal text. Existing file headers can
retain their original format: opening a file with an option does not establish
that its storage has been rewritten. Remote paths and confidential attachment
options are withheld. Native refusal and observation failure retain the usual
one-use receipt and caller transaction rules.

The pinned runtime can invalidate a connection when a detached alias is reused
in the same transaction. The reviewed workflow retains successful detachment
identities and refuses their reuse before dispatch until the caller explicitly
commits or rolls back. It never makes that transaction decision itself. This
guard covers detachments made through the attachment workflow; arbitrary SQL
and administration by another connection retain native failure handling.

Encrypted native files use a separately admitted private key bound to the
native ATTACH parameter. Optional GCM/CTR selection preserves the engine's
cipher and file-format rules. An unused review key is admitted for five minutes
before dispatch; it expires unused, can be explicitly discarded,
and is released after an attempted operation or session closure. Keys are absent
from SQL previews, downloaded SQL, public review fingerprints and receipts.
The native cipher and encrypted flag remain observable. Reading an encrypted
file does not change its existing cipher or rekey the file.
The pinned runtime requires explicit CTR selection when reopening a CTR file;
choosing the native default does not bypass that security admission.
The key text retains DuckDB's native VARCHAR-to-BLOB representation: non-ASCII
bytes and literal backslashes use hexadecimal byte escapes. Invalid native
encoding produces a safe ``native-key-encoding`` reason without the private
input or native error text.

The UI requires explicit encryption intent and clears the submitted key after
review. It cannot silently replace an encrypted review with a plaintext review
when that key field is cleared. Native wrong-key/crypto refusal retains the
usual terminal receipt and never authorizes replay. Archived observations never
retain the private key or authorize another native session; encrypted remote attachment
types and encryption transformations require their own adapters.

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
namespace refusal, original-session binding and failed observations. Storage
options are also checked against actual catalog facts, pending work and
transaction identity. The qualifier writes and independently reopens 9,000 rows
with a quoted nested type, checks native block size, and uses compressed memory
attachments. Encrypted
attachment options and remote extension-backed attachment types retain their
separate capability and credential-admission obligations.

Independent-file DDN fingerprints exclude transient table and column-owner OIDs
while retaining their native catalog observations. Rebuilt-table verification
compares exact column semantics and confirms the observed columns' owner OID
matches the newly observed table. A new native table identity must not make a
successful constraint rebuild fail its schema postconditions.
Native DDN identifier quoting has no separate 256-byte cutoff. Long quoted
schema, table and column names retain their exact Unicode and punctuation,
subject to the existing complete-catalog, SQL-source and durable-review bounds.
Native create/review/apply qualification includes independent observation and
data access through those names, with one-use receipt reuse.
Reviewed native database copy
-----------------------------

The native attachment workspace also exposes copying between two attached
DuckDB catalogs on the original authorized query session. Select exact source
and destination aliases and schema, data, or schema-and-data mode. Review reads
the native definitions and per-table row aggregates; apply revalidates catalog
identities, file identities, transaction, definitions and data before dispatch.
The destination must be writable and both catalogs must be within the registered
file/memory authorization. Internal and extension-backed foreign catalogs are
not admitted through this core DuckDB workflow.

Schema-and-data mode dispatches explicit native COPY FROM DATABASE SCHEMA and
DATA statements in order. It does not use the default pragma expansion's
transaction wrapper. Native row conversion, constraints, conflicts and the
one-writable-database-per-transaction rule remain native decisions. Data mode
appends rows; no conflict is silently converted into replacement or an implicit
commit. The original transaction owns copy effects and rollback remains the
caller's decision.

Review and application have background workers, phase receipts, cancellation,
independent native acknowledgement for each copy step and no automatic replay.
A failure after the schema step remains partial. A lost mutation reply remains
unknown; a post-acknowledgement observation failure remains acknowledged but
unverified and blocks further session use. Repeated apply requests read the
existing live receipt. Durable observations survive original-session release and
application restart without granting application on another session.

Postconditions compare native object identities and each table's native count,
XOR and sum of native physical-row hashes. Virtual generated columns are
recomputed by the engine and do not enter the fingerprints. DATA copies with different source/destination
column names or types retain native conversion behavior and use row counts;
cross-type hashes are not compared. Each receipt identifies its method. These
bounded metadata and aggregate checks are not a collision-free data proof.
Qualification additionally compares exact
native nested/enum/decimal values, macros, views, indexes and sequences, observes
pending/committed data on an independent connection and reopens the copied file.
``tools/cdeadmin_duckdb_database_copy_qualification.py`` preserves the native
file/in-memory-root evidence and source hashes outside the implementation tree.

Encryption transformations use that same native workflow. Attach a separate
destination with the intended encryption key and cipher (or without encryption),
review its observed storage facts, copy, explicitly commit, detach and reopen
with the intended key before retiring the source. Reviews show both stores'
native encryption/cipher facts and warn when encrypted source data will enter
an unencrypted destination. Keys remain in the private attachment binding; copy
SQL and durable copy receipts contain no keys. Native catalog identity, access,
encryption and cipher are reobserved after acknowledgement, separately from the
data/schema postconditions. A failed storage observation retains acknowledgement
and blocks session reuse.

The pinned source implements encrypted-to-encrypted changes through database
copy (``test/sql/copy/encryption/reencrypt.test_slow`` and native COPY DATABASE
execution). Its attachment storage options open/create stores with a key; they
do not provide an in-place SQL REKEY operation. ScratchRobin does not replace
the source file or infer whether two attached stores use different keys.
Qualification covers encrypt, decrypt and GCM/CTR encrypted-to-encrypted copies,
caller-owned rollback/commit, original temporary state, repeated apply without
replay, exact independent file data and reopening each store with its own key.
For encrypted stores the other store's key must fail independently.

Authenticated native extension sources
---------------------------------------

Native secret properties preserve JSON scalar, list and map constants. Multiple
scope strings can be supplied through the sensitive ``properties`` JSON object.
Booleans remain native Boolean constants; HTTP headers use a native map rather
than Python dictionary text. The native map constructor is explicitly qualified
in the system catalog, preventing a same-named caller macro from running while
constructing a constant. Preview SQL withholds property values and scopes.
The compiler bounds statements to 1 MiB, 16,384 constant nodes and 32 traversal
levels. This constant interface does not interpret text values as SQL expressions.
Remaining session/storage identities and native expression workflows retain their
own acceptance scope.

Native administration errors do not authorize rollback of a borrowed query
connection. The shared executor rolls back only connections it owns; Firebird's
original task savepoint remains native and separate. Native statement/row-count
refusals preserve caller decisions and any state the engine itself retains.
DuckDB and SQLite failure qualification verifies pending rows remain until an
explicit caller rollback. A native engine can still abort its transaction on its
own errors; the application does not claim to undo that engine behavior.

The database context menu opens ``Install or load DuckDB extensions...`` on an
original native session. HTTP(S) source URLs and repositories exclude inline
credentials, query strings and fragments. Existing native HTTP secrets supply
authentication; their values are never read by this adapter or copied into its
SQL and receipts. Using a selected secret requires secret-read authority and loaded
native ``httpfs``. An optional expected name binds the review to the secret
selected by native ``which_secret`` for the exact version/platform download
URL, including more-specific scopes. Public sources can have no selected secret.

Review exposes native selection identity, effective lookup URL and transport
settings, separately from successful authentication. Before dispatch these facts
are observed again. Selection changes refuse dispatch. Secret value changes and
external certificate/repository changes are not fenced; no value fingerprint or
authentication success is inferred. Remote failures retain native error type and
available HTTP status without persisting opaque response text. Terminal receipts
cannot replay installation and remain readable after original-session release.

The native HTTPFS implementation used for qualification is source available:
``duckdb/duckdb-httpfs`` revision
``13e18b3c9f3810334f5972b76a3acc247b28e537`` under the MIT license. Its native
HTTP parameter initialization consumes HTTP-secret bearer/proxy/header values.
``tools/cdeadmin_duckdb_authenticated_extensions_qualification.py`` records the
actual signed binary hash and version, an owned HTTPS repository with an
explicitly trusted certificate, native longest-scope selection, secret-read
denial, changed selection, native credential refusal, transaction ownership and
credential absence from durable receipts. Browser qualification additionally
uses the context-menu workflow and actual dock close.

``DU-NATIVE-HTTPS-DIRECT`` records a pinned-engine limitation, separately from
missing adapters: direct ``INSTALL 'https://...'`` and explicit HTTPS repository
arguments in the qualified 1.5.2 build take a native local-filesystem path and
refuse before an HTTP request. The native source's ``IsHTTP`` predicate in
``src/main/extension/extension_install.cpp`` and independent native probes agree.
An HTTP repository argument with HTTPFS loaded uses the engine's native HTTPS
upgrade and its context-bound HTTP credentials; that HTTPS transport is
independently qualified. ScratchRobin does not substitute its own downloader or
report the failing direct-HTTPS interface as successful. Native HTTPS attachment
and other installed-capability acceptance remain separate.

Durable original-session operation receipts
-------------------------------------------

The SQL editor and attachment workspace provide a saved-receipt browser for
attachment, extension and database-copy operations. It reads owner, endpoint and
database-target-scoped application storage without opening a native connection,
including after the original session closes or the application restarts.
The archive supports bounded pages and individual inspection. It never exposes
apply, reconnect or replay operations.
The registered database context menu opens this archive directly, bypassing live
catalog bootstrap. Docked provider panels now run their registered close guards
before removal, awaiting native session release and retaining busy or failed
release tasks for inspection.

Dispatch intent must be durably saved before native execution. Native command
acknowledgements are saved before later rediscovery; database copies retain each
step separately. A failure to save an intent refuses that dispatch. A failure
after native return retains the in-memory acknowledgement and leaves the prior
durable observation unresolved until an existing live receipt can be recorded.
A stopped original process cannot establish an unrecorded outcome. Automatic
replay is unavailable even when a receipt is incomplete.

Confirmed native session release has a separate durable observation. A storage
failure cannot prevent native connection cleanup; its close result reports
whether the release observation was saved. Neither acknowledgement, rediscovery
nor release establishes that the caller committed. Private encryption keys,
compiled credential bindings and private schema/data baselines are excluded;
common credential forms in native observations are redacted. These receipts are
application operation evidence, separate from owner-deferred ScratchBird SQL
and monitoring-history qualification.
