.. _cdeadmin_architecture:

*************************************
ScratchRobin CDE Admin architecture
*************************************

ScratchRobin CDE Admin is a provider-driven administration platform. Shared
code owns presentation, security boundaries, persistence, orchestration and
audit behavior. A provider owns the exact semantics of an engine. Common code
must not infer that an engine accepts PostgreSQL SQL, object names, metadata,
transactions, maintenance operations, or connection behavior.

Product layers
==============

The principal layers are:

* the Python/Flask application and authenticated HTTP boundary;
* the React browser client and Electron desktop host;
* the command registry, which binds stable command identifiers to labels,
  icons, permissions, visibility and enablement rules;
* connector and endpoint services for user-owned connection profiles, routes,
  credentials, discovery, failover and session state;
* exact engine providers for dialects, metadata, metrics, object models,
  graphical forms, queries, data mutation and administration;
* shared workspaces for object exploration, data, queries, properties,
  operations, control planes and semantic analysis; and
* fail-closed structural, browser and live-engine qualification gates.

Engine authority
================

An exact provider declares only capabilities implemented by the corresponding
engine. Unsupported capabilities are not simulated, inherited from another
engine or exposed through a generic raw-command substitute. ScratchBird legacy
interfaces will use the same provider experience as the corresponding original
engine. Native ScratchBird will have its own provider when that stage begins.

The delivery target is full replacement of each engine's own management
console. Shared components must accommodate the union of native workflows,
while each endpoint exposes only the workflows applicable to its engine,
version, edition, installed extensions and attachment mode. Similar names do
not establish equivalent behavior. Engine-specific options must remain
available even when other providers have no corresponding option.

Coverage must be inventoried from native documentation, source and management
workflows independently of the implemented provider catalog. Each obligation
records its native applicability, backend implementation, functional form,
qualification evidence and remaining work. An unsupported native feature,
an unavailable permission, an unknown capability and an unimplemented adapter
are different states. Missing implementation must never be reclassified as
native non-support to make a coverage gate pass. Offline catalog checks prove
declarations only; they do not prove full native-console parity.

Connection hierarchy
====================

The explorer hierarchy is ``Connectors -> engine -> server/instance ->
database -> native objects``. An endpoint identifies a network or embedded
engine boundary. A database target is separate and may be absent, named, or a
filesystem path according to the engine. This distinction permits Firebird
server/service operations without pretending that a default database exists.

Connection profiles support arbitrary IP addresses or DNS names, ports,
multiple routes, a default principal, encrypted saved credentials, password
visibility while editing, and a transient *connect as another user* principal.
Provider contracts add only the authentication, TLS, discovery, routing,
compression, consistency, pooling and session controls that the exact engine
supports.

Firebird native client configuration
-----------------------------------

The Firebird network profile accepts an optional per-connection configuration
text containing ``WireCrypt``, ``WireCryptPlugin``, ``AuthClient``,
``WireCompression``, ``TcpNoNagle``, ``ConnectionTimeout``,
``DummyPacketInterval`` and ``ClientBatchBuffer``. This is a client override,
not a server configuration-file editor. It is not exposed for embedded
attachments. Other native settings require their own appropriate workflow;
their absence from this field does not mean Firebird lacks them.

The backend validates the text before saving or native attachment/creation.
Valid comments, newlines, quoted values and native integer suffixes are
preserved. Input is limited to 16 KiB of UTF-8 and flat assignments; includes,
macros, blocks, duplicate keys and invalid values are rejected. Explicit
authentication, encryption, compression and dummy-packet fields may not be
duplicated in the text. An explicit connection timeout takes precedence over
the corresponding text setting, matching the native parameter-block behavior.
Clearing the field removes the override. Database attachment, database
creation and Services API attachment must isolate each endpoint's selection
from unrelated driver defaults and named driver configurations.

Firebird embedded contract scope
-------------------------------

The embedded profile has its own provider identity and activation artifacts.
It shares the Firebird 5.0.4 SQL compiler, grammar and statement evidence with
the network profile only while their generated SQL task inventories and
compiler implementations remain equivalent. This reuse qualifies the SQL
language contract; it does not transfer network authentication, transport,
Services API or platform qualification to embedded mode.

Embedded activation additionally requires native Engine13 attachment evidence,
exact engine identity, independently observed commit/rollback, and collection
of its declared monitoring columns. Its metric contract contains database
monitoring observations only, excluding Services API observations. Contract
generation must reject stale source bindings, missing native evidence or
compiler divergence. Embedded access continues to require explicit filesystem
and embedded-runtime authorization; no network permission is added.

Coordinated Firebird recovery requirements
-----------------------------------------

The coordinated recovery workflow must extend the existing native prepared
transaction recovery implementation. Each participant is an explicitly
selected, independently authorized registered endpoint and database target,
paired with its exact decimal native transaction ID. Stored transaction
descriptions supply review evidence only: they must never select routes,
credentials or permissions automatically. A truncated description or an
unreachable participant remains unresolved.

The review must show every selected database, local transaction ID, current
native observation, observation time and requested decision. The operator
must acknowledge the coordinator decision and participant review, confirm
each database/transaction pair, and choose one commit or rollback decision
for the group. Duplicate participant identities, mixed decisions, missing
confirmations and non-Firebird endpoints must be rejected before dispatch.
Endpoint registration, route, principal, database-target and permission
changes invalidate the review and require a new preview.

Execution must reauthorize all participants before reconnecting any prepared
handle. It must use fresh provider-owned attachments with no borrowed query
transactions. The existing native recovery owner performs reconstruction and
the native decision; the workspace does not implement a substitute transaction
coordinator. Repeated submissions must refer to a retained operation identity
and must never replay a dispatched decision automatically.

Dispatch is sequential through the existing single-participant native owner;
it is not an atomic group commit facility. Any uncertain native result or
unconfirmed attachment release stops later dispatch. Known returned decisions
remain recorded even when an explorer refresh fails. The review admits 1--64
participants, at most 1 MiB of stored review data, and expires after five
minutes; expiration is checked again after preflight inspection. Each selected
database is bound to its native DB_GUID and DB_FILE_ID as well as its endpoint
context and route. Neither identity is a substitute for independent access
authorization.

Attachment mode comes from each admitted registration, never from stored
transaction descriptions or the recovery request. Network participants use
their own native authentication. Embedded participants require embedded-runtime
and filesystem grants, a contained local database path, and no network
credential reference. The same native identity, review and dispatch rules
apply in both modes; embedded recovery must not start a server or substitute
password authentication for filesystem authorization.

The existing single-process persistent operation store owns these workflow
records. Intent is retained before each participant call. Reopening an
interrupted executing group reports uncertainty without resending decisions;
reading status and repeated apply requests do not perform recovery. This
contract does not claim multiple application writers or power-loss durability.
The operator may start a separate explicit review of remaining limbo work;
that review must satisfy all original authorization and confirmation rules.

The application must retain its intended decision and dispatch state before
calling native recovery. This is workflow evidence, not database transaction
authority. Failure to retain that state prevents dispatch. A process restart,
lost response or partial native failure leaves affected participant outcomes
unknown until independently observed. Absence from the limbo inventory alone
does not establish whether a participant committed or rolled back. The result
must preserve per-participant observations, native receipts and cleanup state;
it must not claim a global outcome from successful HTTP delivery or attachment
release. Cleanup must not choose an outcome for a prepared transaction.

The functional form must support independent endpoint selection, participant
review, explicit confirmation, bounded progress and per-participant results.
Cancellation before dispatch may release the review; after dispatch it must
not promise transaction rollback. Qualification requires real independently
authorized endpoints, native commit and rollback observation, stale reviews,
denied permissions, duplicate submissions, interruption and restart with
unknown outcomes preserved. These are requirements for the coordinated
workflow; existing single-participant controls do not satisfy this scope.

Firebird streaming upload resource ownership
===========================================

The opt-in Firebird streaming path stages one BLOB upload per native session
in an anonymous temporary file. Chunks are at most 64 KiB and each upload is
limited to 256 MiB. Network and embedded Firebird providers share a process
budget of 16 open upload files and 1 GiB of reserved upload bytes. These are
application resource limits, not engine limits. Separate application workers
have separate budgets; deployment-wide disk quotas and idle-session leases
remain additional requirements.

Admission reserves a file slot before creating the spool and reserves each
chunk's complete byte count before writing. Concurrent sessions cannot exceed
either process limit. A refused reservation does not write or poison an upload;
the caller can retry after another upload is closed. Repeating the last accepted
chunk does not reserve or write its bytes again. Finishing an upload retains
its reservation until its spool is successfully closed after use or explicit
cleanup. Failed file creation releases the slot. Failed or short writes make
the upload unusable and retain the entire attempted reservation until cleanup,
because the amount actually written is uncertain. Failed cleanup retains its
owner and reservation for a later close attempt. Successful close is idempotent
and prohibits subsequent writes or use. Resource cleanup does not commit or
roll back the native transaction, and quota refusal never replays SQL.

Firebird streamed BLOB file saving
=================================

Both the network and embedded Firebird providers admit the same retained-session
streaming operations through Data Studio. Embedded execution retains its local
filesystem/Engine13 authorization and adds no network credential or Services
API capability. The application boundary must accept the admitted embedded
provider identity; native-library tests alone do not prove this integration.
Session, database target, workspace-owner, lease, upload and transaction rules
apply to both profiles without substituting a network connection.

Firebird stream resources have a five-minute idle lease, measured with a
monotonic clock from completion of the last owner request. A process-local
background sweep checks approximately every 30 seconds. Busy attachments and
running native calls are skipped. Time spent executing a streaming request
is not idle time.
Cleanup uses two daemon workers and a bounded queue so one stalled native
cleanup does not stop all other cleanup or prevent application shutdown.
Cleanup timing is best effort, not a native I/O deadline.

Expiry releases only the cursor, BLOB readers and staged upload file. The
attachment and transaction remain owned; expiry does not commit, roll back,
detach, or replay SQL. The expired owner's marker remains until explicit
stream/session close. Requests cannot renew an expired lease or resume its
discarded cursor. Failed cleanup retains resource ownership and reservations
for retry and quarantines the session under existing cleanup rules. Other
workspaces cannot clear the owner's marker. Idle attachment/transaction
resolution and deployment-wide quotas remain separate requirements.

An unread BLOB in the current streaming page can be saved as raw bytes through
a browser-provided file picker and writable file stream. Where available, this action uses
the File System Access picker. A portable download action instead delegates
the destination to the browser download manager through an authenticated,
CSRF-protected POST response. Both network and embedded profiles admit it.
The picker implementation follows the
`File System Access picker contract <https://wicg.github.io/file-system-access/#api-showsavefilepicker>`_
and `File System writable contract <https://fs.spec.whatwg.org/#api-filesystemfilehandle-createwritable>`_.

Portable delivery reserves one unread BLOB or ARRAY from the current page
under the existing session and workspace owner. The reservation has a random,
one-use identifier sent in the POST body, never a URL capability. Endpoint
ownership, database target and operational session admission are checked for
that POST and every subsequent provider pull. A claimed reservation cannot
be claimed again. Other page/value reads are refused while reserved or sending;
status observation, cancellation and explicit stream close remain available.
Status polls do not renew the idle lease. Delivery status and stop flags are
local observations independent of native attachment admission; they must not
make a simultaneous file read fail as busy. Stop prevents further pulls and
discards a native read still in progress when it settles. Bytes already handed
to HTTP or the browser may still arrive. No download restarts SQL or rewinds
a consumed native value after interruption.

The HTTP iterator pulls at most one 64 KiB BLOB chunk or one bounded ARRAY
slice at a time. It never collects the complete file in application memory or
stages it on the application filesystem. BLOB responses declare the native
byte length and preserve all subtypes as raw bytes. ARRAY responses use the
same versioned JSON Lines header, coordinates, bounded slices and mandatory
completion footer as picker saves. Invalid offsets, identities, lengths or
serialization abort delivery. Disconnect, Stop and application shutdown may
leave a partial browser download; they do not commit, roll back or replay.
Responses disable caching and buffering where the HTTP stack supports it.

A status of sent means the application yielded the complete verified payload
to HTTP; it does not prove that the browser saved the file. The form instructs
the user to inspect browser download completion. A missing or failed response
remains unconfirmed until status is observed; a reserved request not claimed
within the client wait interval is cancelled, not retried automatically.
The browser controls destination prompts, naming conflicts and partial-file
cleanup. There is no range/resume contract for discarded native readers.

The user chooses the destination before any native BLOB read. Each response
must match the BLOB identity and exact byte offset, contain valid base64 of at
most 64 KiB, and make progress unless it is the terminal response. Each write
finishes before the next read starts. The application does not accumulate the
complete BLOB, decode text, or change transaction finality. Success is displayed
only after the file stream closes successfully. Stop and workspace closure
prevent further pulls and request file abort once any outstanding read/write
settles. They do not promise immediate interruption of browser filesystem I/O.
Failure to close or abort is reported without claiming a completed file.

Page advancement, chunk inspection and stream closure are disabled during
saving. A BLOB whose read was attempted cannot start a second file save from
byte zero: the provider retains only the most recent chunk for retry, not the
entire prefix. A failed download therefore never automatically re-executes SQL
or offers a truncated suffix as a complete file. Cancelling the file picker
before reading leaves the BLOB available. Other unread BLOBs remain available.

Application qualification must open the studio with an explicitly registered
database target. A server-scoped registration alone does not admit a native
query session. File-transfer checks cover binary and UTF-8 content, empty BLOBs,
exact chunk boundaries, cancellation after a write has begun, staged upload
readback, invisibility of pending writes to an independent observer, and
explicit rollback. An automated substitute for the operating-system picker
must be identified in the evidence; it does not qualify the real picker gesture
or other browser/platform combinations.

Firebird streamed ARRAY reads
============================

The streaming cursor returns references for non-null native ARRAY values.
References belong to the current result page and native transaction, like
BLOB references. A reference includes native dimension bounds and element
metadata; a pull returns a row-major run within one innermost dimension,
starting at an exact flattened element offset. Each pull contains at most
256 elements and each native buffer is at most 64 KiB. Character conversion
may require several such bounded buffers. The response preserves native
coordinates, values and the next offset; only the immediately previous pull
is retryable without another native read. Page advance, close and idle expiry
invalidate references. No operation re-executes the original SQL.

Scalar element types use the existing qualified array decoders. Character
arrays preserve fixed padding and variable lengths through the existing
charset-specific slice adapters. Unsupported element/charset combinations
fail explicitly and retain cleanup ownership. Ordinary array query and write
paths keep their existing behavior; bounded ARRAY parameter staging and full
ARRAY file export require separate contracts and qualification.

The native ARRAY qualification checks signed dimension bounds, all scalar
families admitted by the slice decoder, fixed and variable OCTETS, UTF8,
ASCII, WIN1252 and ISO8859_1 variable text. It compares ordinary and streamed
reads with known values, measures every native allocation, verifies copied
identities across fetched rows and retries without native reads, then rolls
back the pending inserts explicitly. The application browser gate checks
all 1,200 INTEGER elements across six rendered slices. These checks do not
establish other stored character sets, operating systems or ARRAY file export.

Character ARRAY adapters must preserve embedded NULs and trailing data for
the built-in Firebird character sets. Native Firebird performs character
conversion to the attachment encoding. Stored single-byte lengths are counted
as bytes; multi-byte lengths use the corresponding character decoder only to
recover element length, not to replace native transliteration. NONE has no
transliteration: its retained bytes use the attachment decoder, with fixed
padding measured in stored bytes. Invalid encoding remains an explicit error.
Unknown custom variable character sets must not fall back to a C-string read
which would silently truncate embedded NULs.

Fixed CHAR query results in two-byte attachment character sets must remove
only transport expansion beyond the declared character capacity. Preserve
padding within that capacity. The scoped cursor corrects the qualified
driver's excess padding for these encodings, without changing driver globals
or mutating shared statement metadata. GBK length recovery admits Firebird's
single-byte Euro representation while preserving multi-byte trail boundaries.

ARRAY grid editors use the destination's native charset ID and the same
qualified adapter registry as normal and streamed reads. Every built-in
character set covered by that registry exposes its text editor; OCTETS exposes
the binary editor. Missing/unknown charset metadata does not advertise a
lossless editor. Native dimension, length, scale and type checks still apply
to each submitted change; charset names supplied by a client are not authority.

Complete ARRAY file export
--------------------------

An unread current-page ARRAY reference can be exported through a browser file
writer. The export is UTF-8 JSON Lines: a header with format
``cdeadmin.firebird-array.v1``, dimension bounds, element count, native element
type, scale, subtype and charset ID; one record per native pull containing
offset, coordinates and normalized values; and a final record containing
``complete: true`` and the element count. Exact numeric text and encoded binary
values retain the existing query-value representation. Connection-scoped
references are not persisted. The footer must be present for a complete file.

The client verifies reference, contiguous offsets, row-major coordinates,
slice limits and final element count before accepting completion. It awaits
each bounded file write before requesting another slice. Stop, malformed or
lost responses and writer failures abort the destination; cleanup failure is
reported explicitly. An attempted native pull prevents restarting a complete
export at zero. There is no SQL replay, commit or rollback. Unsupported file
writers leave slice inspection available. ARRAY file import uses the staging
contract below.

ARRAY file parameter staging
----------------------------

The ARRAY export format can be staged as a single query parameter using the
same session-owned disk spool and process quota as BLOB uploads. Staging does
not execute SQL. Finish validates every bounded UTF-8 JSON Lines record,
contiguous coordinates, declared count and completion footer. Invalid files
retain cleanup ownership and cannot be bound. Uploads remain subject to the
existing 256 MiB per-file admission and idle lease.

Binding uses ``{"array_upload": "reference"}`` once in the next streaming
statement. Prepared destination metadata owns bounds, element type, scale,
subtype and charset; those must match the file. Every value passes application
type, shape and encoding validation against that destination before any
uploaded ARRAY slice is written. Native conversion/admission can still fail
during writing; this does not decide the transaction outcome. A second
pass writes bounded native slices into a new transaction-owned ARRAY identity
and supplies that identity to the prepared statement. Neither pass constructs
the whole ARRAY in memory. Each native buffer is at most 64 KiB. Native write
or execute failure never causes automatic replay, commit or rollback; pending
work remains subject to the explicit session transaction controls. The spool
is consumed once and released after the execution attempt, including failure.
Temporal input accepts ISO fractions up to six digits when exactly aligned
to Firebird's 100-microsecond precision, including the trailing zeroes emitted
by the query serializer. Additional nonzero precision is rejected, not rounded.
Negative floating zero is serialized as the exact text ``-0.0`` so browser
JSON serialization cannot silently turn it into positive zero. Typed ARRAY
binding recovers its native sign through the existing floating-value binder.

Native ARRAY bounds and bindings
-------------------------------

ARRAY layout comes from the destination database catalogs, preserving signed
32-bit lower/upper bounds and complete relation/field identifiers. The legacy
16-bit array descriptor is not authoritative: narrowing coordinates or names
can address the wrong slice or omit retained elements. Slice descriptors use
the public native SDL interface with explicit 32-bit coordinates, exact element
type/scale and complete encoded names. Relative loop counters prevent an
overflow after visiting an upper coordinate of INT32_MAX. The stored element
width owns the total native-size check; attachment charset expansion does not
turn the size of a whole converted result into a native storage limit.
ARRAY references and versioned files
retain those bounds. Existing per-slice and total native-size limits apply.

All ARRAY parameter forms, including ordinary JSON arrays, use prepared
destination metadata and the same bounded writer as staged files. Validate
every dimension and every element before the first native slice publication;
reject numeric overflow, inexact scale, NULL leaves and incompatible types.
Do not rely on driver ctypes packing to reject overflow. A later native write
failure leaves transaction outcome explicit and never replays the statement.

Materialized result admission
-----------------------------

Ordinary Firebird query and grid results have a per-execution materialization
budget: 16 MiB of conservative value charges and 100,000 scalar/container
nodes. This is an application admission policy, not a database size limit or
a measurement of process resident memory. Scalar charges include 256 bytes
of overhead and up to six bytes per native text/binary byte for JSON expansion.
ARRAY metadata reserves all element and nested-container charges before the
first slice is read. BLOB lengths are checked before reading their content.
The budget accumulates across rows and resets only for an explicit execution.

Exceeding admission fails the result explicitly and directs the user to Run
streaming or a smaller explicit projection. It does not silently truncate,
rewrite or replay the statement, commit or roll back. Selectable routines and
RETURNING statements may already have performed work; session transaction
controls remain authoritative. Readers are released through existing guarded
cursor cleanup. A failed budget cannot resume a partial ordinary result.
The dedicated streaming path retains its bounded page, slice and file-transfer
contracts and is not subject to whole-result materialization admission.

Zoned temporal values
---------------------

Native TIME/TIMESTAMP WITH TIME ZONE values use explicit JSON envelopes with
``encoding`` equal to ``firebird-time-tz`` or ``firebird-timestamp-tz``,
``utc`` containing the stored UTC clock or timestamp, and ``time_zone``
containing the database region name or signed fixed offset. UTC text has
100-microsecond precision. A TIME value does not acquire an invented date.
The database zone catalog resolves region identities; the native fixed-offset
encoding resolves offsets. Neither Python nor browser time-zone rules may
reconstruct the stored instant from a local wall clock. Thus repeated DST
hours remain distinct and TIME values retain named regions.

Query parameters, grid drafts and ARRAY leaves accept the same strict envelope.
Binding requires matching native temporal metadata, validates UTC range and
precision, and resolves the zone against the destination attachment. Unknown
zones, extra fields and lossy precision are rejected. Native UTC fields and
zone identity are packed directly; NULL stays NULL. ARRAY inspection, bounded
file export and staged import preserve these envelopes. Grid controls expose
the UTC value and zone explicitly; local wall-time conversion is not implicit.

Exact scalar grid identity
--------------------------

A retained Firebird grid identity includes stored representations for zoned
TIME/TIMESTAMP and binary FLOAT/DOUBLE columns as well as ARRAY contents.
Native equality alone cannot establish an unchanged value: a time zone may
change while UTC stays equal, and positive and negative floating-point zero
compare equal. Before update or delete, compare the exact retained native
values in the caller's task savepoint. Zoned snapshots include UTC and zone;
binary floating snapshots include the native decoded bit representation.
Protect the following DML with the retained native record version to cover a
competing commit between preflight and execution. Same-transaction changes
must also invalidate the retained identity even when record version is equal.
Apply the guard to admitted tables and views, including changes to columns
other than the column being edited. Conflict handling preserves unrelated
pending work and transaction ownership; it does not commit, replay or silently
refresh the original row identity.

Binary floating-point special values
------------------------------------

Firebird FLOAT and DOUBLE parameters support explicit NaN and positive or
negative infinity through native numeric bindings. Query parameter envelopes
and grid drafts use ``float32`` or ``float64`` with textual ``data``. Accept
case-insensitive ``NaN``, ``Inf`` and ``Infinity`` with optional sign, alongside
finite decimal/exponent text. Do not reinterpret ordinary SQL text as a typed
number. Finite input that overflows to infinity or underflows to zero remains
an error; explicit infinity is a separate intentional value. ARRAY leaves use
the destination's native floating type and the same numeric admission rules.

Results stay valid JSON: nonfinite numbers are textual ``nan``, ``inf`` and
``-inf``; negative zero is retained. Editors accept those returned spellings.
NaN payload bits and signaling-NaN construction are not exposed by this numeric
editor contract; NaN is an explicit numeric class, not a raw-bit editor.
Exact native snapshots still protect unchanged rows against stale mutations.
Native text CAST behavior is not evidence of numeric-parameter support: use
real native bindings, storage, result reads and explicit transaction outcomes
for qualification.

Firebird view row admission
--------------------------

View INSERT and DEFAULT VALUES admission does not require a projected primary
key. Prepare each target-view operation and column independently using the
current attachment and privileges; never execute discovery DML or infer one
permission from another. Surface insertion for native-admitted keyless,
joined, nested and trigger-backed views independently of grid update/delete
identity availability. Preserve omission, NULL and native defaults as distinct
inputs. Issued insert authority remains target-, session- and route-bound.

For grid update/delete, a complete, unambiguous primary-key projection through
one source at each nested view level can retain the underlying key identity.
Resolve each alias and view context from native catalogs without bypassing the
target view or requiring direct DML privileges on its sources. Active view
triggers do not alone make such a projection read-only. Native preparation of
the final target operation remains required; execution uses the target view,
its triggers and CHECK OPTION, within the caller's task savepoint. Exact value
and version protections continue to apply to ARRAY and scalar representations.
Do not infer a unique key for joined, aggregate or ambiguous projections.
Lack of safe grid identity is an editor limitation, not a claim that the native
view is read-only; independently admitted insertion and explicit SQL remain
available. Native errors, privilege changes and concurrent DDL do not trigger
base-table fallback, implicit commit or replay.

Firebird physical row identities
-------------------------------

When a retained Firebird data session has no admitted projected primary key,
the grid may use an opaque native ``RDB$DB_KEY`` together with the native integer
``RDB$RECORD_VERSION``. Admit this path only when the target's native filtered
identity query prepares with the expected binary-key/version metadata. Fetch
both identity values in the same SELECT as the visible row; keep them out of
visible columns. Do not parse key bytes, manufacture a key from row values, or
reuse it as a durable external identifier. This identifies individual duplicate
rows in keyless tables and single-source views without pretending a primary
key exists. Native temporary relations and their direct/nested key projections
retain their engine-defined attachment and ON COMMIT lifetimes.

Bind every physical identity to the issuing attachment and active transaction.
Before any task savepoint or DML, require that same active owner; commit,
rollback, reconnect or attachment replacement requires a fresh row page. A
new transaction is not started merely to retry an expired identity. Compare
all retained visible native values before mutation and require the retained
record version in the actual UPDATE/DELETE predicate. This catches changes
inside the same transaction and competing commits between preflight and DML.
Use only target-view operations and independently prepared native column and
operation permissions. Preserve unrelated pending work on rejection.

Joined views with composite keys but no supported native record-version
expression, and aggregate views with NULL or unusable physical identities,
do not acquire this editing contract. Their independently admitted insertion
and explicit SQL are unaffected. Failed metadata or ownership checks must not
fall back to an all-values guessed key or bypass a view's triggers.

Native-admitted negative user-defined BLOB subtypes expose binary value controls
and preserve raw bytes, including NULs, through the existing Base64 envelope.
Do not reinterpret these bytes as text or silently install a BLOB filter.
Subtype 1 keeps its text contract; positive reserved subtypes do not become
user-creatable merely because the editor can render their catalog bytes.

Inline grid buttons must remain under the pointer when receiving focus inside
a horizontally scrollable grid. Primary pointer activation focuses the button
without scrolling before click dispatch; keyboard focus and the independent
delete-confirmation step remain available.

Firebird transaction replies and transport loss
-----------------------------------------------

A lost commit response is an unconfirmed command outcome even when another
attachment can observe the committed changes. Do not replay the command or
infer rollback from attachment cleanup. Retain bounded native status codes
without credentials or transport payloads. A later successful cleanup does
not revise the earlier command's outcome.

The Firebird 5 native client may suppress a network error during ordinary
rollback. A returned driver method therefore records only that observation,
not independent proof of a received server response. The retained-session
control workflow also requests the provider's native transaction observation.
Before advertising an active or idle session, use the native attachment ping,
which does not start or finish a transaction. A failed ping makes the state
explicitly unknown and the attachment cleanup-only; cached driver transaction
wrappers are not evidence that a dead connection is idle or usable.
These rules apply independently to command execution and resource release.
Explicit reconnection does not replay prior statements or transaction commands.

Firebird effective configuration inspection
-------------------------------------------

Discover every row visible through RDB$CONFIG as a read-only configuration
setting under the selected database. Show the native configuration ID, exact
value, compiled default, explicit-setting flag and value source. Preserve NULL,
empty text and significant whitespace. Describe the exact 5.0.4 key's native
type and global versus database-overridable scope separately from its observed
value. Unknown keys remain inspectable without invented scope or type.

This is the database configuration snapshot reported by the engine, not proof
of the current client/session overrides or installed plugin binaries. Plugin
preference entries are configuration settings, not installable SQL objects;
replace the former plugin-only discovery group with the complete configuration
group. Native authentication and encryption controls keep their own contracts.
The read-only plugin concept refers to these configuration observations;
it does not claim installation, loaded-module enumeration or SQL lifecycle
operations for plugins.

Use the selected attachment's native visibility. An empty RDB$CONFIG result
may reflect privileges and must not be described as absence of configuration.
Record unavailable catalog queries through the normal observation contract;
never retry as another principal. Inspection does not write configuration
files, install plugins, reload a server, or offer nonexistent SQL setters.
Changes to file-managed settings and their deployment/reopen/restart procedures
remain outside this read-only native SQL interface. Dedicated supported
database/session controls remain independently available.

Provider-owned objects and forms
================================

Every admitted mutation has a provider-owned form contract. Layout controls may
be reused, but field identity, validation, preview and execution remain owned by
the selected provider. Forms are single-task windows and can be docked or
grouped by the workspace manager; unrelated tasks are not forced into a common
compound form.

Reuse forms and controls wherever their provider contracts permit it. Render
only applicable fields and actions, and enforce those same constraints at the
backend boundary when a request is submitted. Provider changes must also
prevent hidden values from another engine or attachment mode from affecting
execution. Permission and capability checks remain necessary at dispatch,
even when the corresponding action was visible when the form opened.

Backend development includes functional forms: native field names and help,
defaults, dependencies, validation, preview, execution, progress, errors and
outcome handling. The human-interface team refines their presentation. Visual
refinement is a separate acceptance item and must not stand in for missing
native operations. Work on reference-engine providers prepares reusable
components for ScratchBird; its native provider still needs its own explicit
contracts and qualification.

Properties are informational. Providers may expose summary fields, creation
DDL or native definition, forward and reverse dependencies, privileges,
columns, constraints, indexes, triggers, parameters, runtime state and other
engine-specific observations. A section appears only when the provider can
obtain it honestly.

Workspaces
==========

The Object Explorer is accompanied by engine-aware workspaces:

* Data Studio uses grids for relational rows and specialized document, graph,
  key-value, time-series, vector, search and analytical views.
* Query workspaces run provider-declared languages such as SQL, CQL, Cypher,
  PPL, InfluxQL and native commands.
* Operations and control-plane workspaces expose health, topology,
  replication, backup/restore, maintenance, security, logs and long-running
  operation state where the engine provides them.
* Semantic workspaces support relational, multidimensional and
  provider-specific analytical models without requiring every engine to
  pretend it implements a common cube model.

Security and transaction authority
==================================

Secrets are stored separately from route metadata and are encrypted through
the CDEadmin credential boundary. Transient alternate principals are not saved
as defaults. Common failover may select a route before a session exists, but it
does not replay mutations. Commit, rollback and transaction/session state are
reported by the provider that owns the native session.

Delivery modes
==============

The same application supports a standalone development web server, deployment
behind a production WSGI/Apache environment, container operation, and a desktop
runtime that embeds the browser engine and Python application. Packaged desktop
users do not need to install Python or a separate browser.


Firebird SQL script execution
----------------------------

SQL script execution is a distinct, explicit Data Studio action on the selected
retained Firebird session, for both network and embedded profiles. Ordinary Run
continues to execute one native statement. Parse the complete script before any
native work: retain source locations, SQL text and statement ordering; recognize
single/double quoted strings, doubled quotes, alternate q-quoting, line comments
and Firebird's non-nested block comments. Delimiters inside those constructs do
not end statements. SET TERM changes the delimiter for subsequent statements;
the directive itself ends with the previous delimiter. Omission of the new
delimiter resets it to semicolon. The admitted delimiter is one to 31 ASCII
bytes without whitespace or native isql-forbidden quote, minus, asterisk or
slash characters. Source remains UTF-8 text, without NUL. Unterminated
statements or lexical constructs are errors before dispatch. Application limits
are 1 MiB of UTF-8 source and 1,000 statement/directive entries.

The script preview identifies its statement count, source positions, delimiter
and dialect directives, transaction statements and automatic-DDL policy. Script
execution has no positional parameter bindings; single-statement execution and
staged streaming parameters remain separate native workflows. Native SQL, PSQL,
SET TRANSACTION and explicit COMMIT/ROLLBACK use the existing provider execution
and transaction authority. No SQL keyword approximation may finalize work that
the native parser would refuse. EOF, client disconnection and script failure do
not imply commit or rollback of the user's transaction.

SET SQL DIALECT 1/2/3 applies to subsequent script statements without changing
the saved profile or attachment default. SET BAIL ON/OFF selects stop-on-error
or continuation after an observed ordinary statement failure. Default execution
stops on the first error. Cancellation, lost attachment, unconfirmed transaction
completion, failed cleanup and exceeded result budgets always stop further
statements, even with BAIL OFF. Already completed entries and not-run entries
remain distinguishable. There is no automatic resume or replay.

The default script mode retains DDL in the user's transaction, consistent with
ordinary Data Studio execution. AUTODDL ON is an explicit native compatibility
option, also selectable by SET AUTODDL ON/OFF. It uses an auxiliary native
read-committed, wait, no-record-version transaction for DDL and SET GENERATOR;
it must never be implemented by committing the user's transaction. Native
prepared statement classification determines this routing. The auxiliary
commit/rollback observations are reported separately. As in native isql,
failed auxiliary commits request auxiliary rollback, preserving an unknown
outcome when native confirmation is unavailable. Failed auxiliary cleanup keeps
ownership and blocks reuse until explicit session cleanup; it is not success.
The original transaction, its pending DML and its identity remain independent.

Host/client commands such as CONNECT, INPUT, OUTPUT, SHELL, EDIT, EXIT/QUIT,
CREATE/DROP DATABASE, and client-only display or connection settings are not
forwarded as SQL or silently discarded. The complete preflight identifies them
and directs the operator to the corresponding connection, file, database,
transaction, plan or presentation workflow. Script execution never gains host
shell access or changes the selected endpoint because of imported text. These
are client-command boundaries, not claims that Firebird lacks the associated
native capabilities. No native isql subprocess is launched behind this action.

One provider worker owns the full script on its retained session. Cancellation
uses the existing native cancellation path and prevents subsequent dispatch.
Statement results preserve native typed values, bounded error identities,
row-count and fetch observations, and distinct transaction receipts. The
materialization budget is shared across the entire script, not reset to admit
an unbounded collection of individually bounded results. BLOB/ARRAY streaming
remains a separately selected workflow. Results and failure history must not
copy secret-bearing source text into logs or error messages.

Script workspace admission and results
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Both Firebird attachment profiles expose provider-owned script preflight on
an authorized retained session. Preview reports only source positions, directive
values, counts and the SHA-256 of the exact UTF-8 source; it executes no SQL.
The separate Run script control requires a current preview of the editor text.
Execution independently repeats complete preflight and accepts no parameter
bindings. Preview is not native preparation, permission validation or an outcome
guarantee. Only the existing asynchronous execution channel dispatches SQL.

The workspace retains per-entry outcomes, typed materialized results and native
status codes, including partial results after failure or cancellation. A bounded
statement-result viewer and local JSON export use those retained results without
replaying SQL. Export contains user-selected result data, not source SQL or
credentials. An unknown outcome is displayed explicitly and never retried.

The script workspace can load a user-selected local UTF-8 file (at most 1 MiB,
strict decoding) into the editor and save the current editor text as UTF-8.
Loading does not execute or include another file; imported INPUT/SHELL commands
remain refused. No server-side path is accepted. Source changes invalidate the
preview. Safe, source-free preflight diagnostics retain their source line in
the form. Lost attachment or interrupted worker state blocks session reuse in
both the backend and the returned workspace presentation.

Firebird prepare-only query plans
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Both Firebird profiles expose a distinct Explain / query plan action through
the existing retained-session asynchronous execution boundary. It prepares one
native SQL statement with the selected client dialect and requests legacy and
detailed optimizer plans; it never requests statement execution, binds parameter
values, fetches query rows, or rewrites the source with another engine's EXPLAIN
syntax. Script and plan modes are mutually exclusive. Plan input is bounded to
1 MiB UTF-8 without NUL. Native preparation determines SQL validity, permissions,
statement type and input/output counts. Compilation may resolve dependencies or
load external modules; this is not an isolated SQL sandbox.

Preparation uses the user's existing transaction, or explicitly starts the
normal retained transaction if idle. It never implicitly commits or rolls back
that transaction. Preparation of COMMIT, ROLLBACK, DDL or modifying statements
does not authorize their execution. The result states whether preparation
started a transaction, and whether the engine supplied a plan. No-plan is a
valid native observation, not a fabricated empty successful query.

Plan information is acquired through IStatement.getInfo, including the native
end/truncation markers. Firebird 5 encodes this text in the attachment charset,
and its item payload has a 65,535-byte native limit. Use an owned 65,539-byte
response buffer per format, strictly validate item lengths and final markers,
decode using the admitted attachment encoding and preserve native truncation.
Never label a truncated plan complete or silently decode non-UTF8 identifiers
as UTF-8. A malformed response or decoding failure is a bounded diagnostic.
The native optimizer can allocate additional internal memory during compilation;
the response-buffer bound is not an engine working-memory limit.

The prepared owner and metadata interfaces remain tracked until release.
Cleanup failure blocks session reuse, preserves ownership for explicit release,
and cannot trigger execution or replay. Cancellation uses the existing native
query cancellation channel. Results display both original native plan formats,
statement classification, parameter/column counts, transaction observations and
truncation/no-plan notices. Stored/exported results reuse that observation and
do not prepare or execute SQL again.


MariaDB native query fidelity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MariaDB query cursors must preserve SQL NULL separately from zero and partial
calendar dates, negative and extended TIME values, and fractional seconds.
Connector/Python 1.1.14 converts some valid MariaDB temporal values to Python
None or raises before converter callbacks run. The pinned ScratchRobin build
therefore applies the opt-in ``cdeadmin_exact_temporals`` cursor extension in
``tools/driver_patches/mariadb-1.1.14-exact-temporals.patch``. It returns temporal
text from both native text and binary result protocols. Catalog cursors retain
the connector's default behavior. Query cursors require the extension; silently
falling back to lossy decoding is prohibited. SQL and parameter parsing remain
the native connector's responsibility. Platform receipts must exercise both
protocols, including zero dates, SQL NULL and negative fractional TIME.

Browser-facing integers outside the exact JavaScript range and decimal values
are strings. Binary values carry base64 data and byte length. Ordered parameter
arrays and named parameter objects admit explicit integer, decimal and base64
envelopes. Integer envelopes wider than native signed/unsigned 64-bit bounds
bind through exact DECIMAL, avoiding the connector's binary-integer truncation.
Result sets keep separate native metadata, ordinal column identities
and row offsets; repeated labels must not overwrite values. Streaming consumes
all native result sets with bounded queued pages. Terminal errors follow any
already queued pages. The pinned connector patch also propagates positive
errors from both native next-result APIs; only their negative no-more-results
return is successful exhaustion. Uncertain protocol or transaction outcomes quarantine
the connection without replay or automatic reconnect.

MariaDB cancellation binds the original native connection ID to the server UID
observed on that connection and uses the winning native host/port/socket for
the control connection. Verify its server UID before issuing KILL QUERY; do not
retry cancellation against another failover candidate. Cancellation drains the
original protocol before reuse and does not roll back earlier transaction work.
Transaction observation/control and session release must not issue commands
while a worker owns the protocol. Shutdown refuses new sessions/executions,
cancels and joins workers, and retains their handles if they have not stopped.
It must not close a connection under a still-running worker.

Column metadata corrects Connector/Python 1.1.14's reversed length/max_length
entries before publishing declared and observed byte lengths. Native unsigned
flags, charset IDs, extended type identity and duplicate labels remain available.

MariaDB provider connection ownership
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MariaDB pools belong to individual provider instances, with local pool names
and a maximum of 64 physical connections. Pool reset/validation preferences
alone do not enable pooling. Compare the complete connection, credential and
pool configuration on every checkout using a private keyed digest. Retire an
old generation on configuration change; close idle connections and allow leased
connections to finish on their original native attachment before discarding
them. A returned lease cannot access a subsequently borrowed connection.

Use native MariaDB connections with provider-private lease accounting instead
of the connector's process-global named pool registry. On return request native
rollback, then native ``reset()`` when configured. A failed return/reset discards
the physical connection. Following a reset, checkout restores the original
database and autocommit defaults and reapplies the admitted initial command.
If an originally unselected database cannot be restored after a USE command,
discard that idle connection and open a fresh one. Validation interval is milliseconds since return;
zero validates every idle checkout with native ping. Idle failure permits a
fresh connection; no active operation may reconnect or replay. Reject enabled
automatic reconnect for these retained sessions instead of silently honoring
it inside an active transaction. Closing a provider retires its pools.

MySQL provider connection ownership
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MySQL pooling belongs to one provider instance. Connector/Python's process-wide
named-pool registry must not select another provider's endpoint, credentials or
TLS/session configuration. Pool reset preferences alone do not enable pooling;
an explicit positive pool size enables a bounded, lazily populated pool.
The pool name is local to that provider. Every checkout compares the complete
native connection configuration, including current credential values, using a
process-private digest. Changed configuration retires idle old connections;
outstanding old leases remain with their original session until release and
cannot enter the replacement pool. Never write credentials or their digests
into evidence, logs or public observations.

Only idle connections may be replaced after a failed non-reconnecting liveness
check. Never reconnect or replay a retained active session. Returning a lease
rolls back pending work, and applies native session reset when enabled. Failure
of rollback/reset closes the physical connection and does not make it reusable.
Closing a provider closes its idle connections; outstanding leases from a
retired pool close on return. Exhaustion is explicit; no connection is borrowed
from another pool. DNS SRV and failover remain native fresh-connection options.
MariaDB's pool and transaction semantics remain independently specified.

MySQL query value transport
~~~~~~~~~~~~~~~~~~~~~~~~~~

User query results retain the native text-protocol values before the Python
driver's date/time conversions. Native zero/incomplete dates are text, not SQL
NULL; TIME is a signed duration (potentially over 24 hours). Preserve native
fractional digits and the session's temporal interpretation. DECIMAL and
floating-point protocol text must not pass through browser Number conversion.
Integers beyond JavaScript's exact range are decimal strings. SQL NULL remains
JSON null. Binary strings/BLOBs, geometry and VECTOR retain exact bytes through
base64 envelopes; text BLOBs and JSON retain their text without parsing JSON
numbers into floats. BIT values retain their full unsigned magnitude.

Result metadata records native type codes, flags, charset/collation IDs and
nullability when reported by Connector/Python. Unique result keys preserve
duplicate labels separately from the original native labels. Select cell types
that do not reparse exact text as browser dates/numbers. Never infer precision,
scale or a base relation from sample values. Ordinary catalog readers continue
to use their native typed connector interface.

Named and positional query bindings use Connector/Python's native placeholders.
The MySQL language declares ``object-or-array`` parameter shape. Data Studio and
its query form accept both shapes without weakening object-only or array-only
providers. Use ``%(name)s`` for an object and ``%s`` for an ordered array.
Within either parameter container, an explicit ``encoding: base64`` envelope
binds binary bytes; ``encoding: decimal`` and ``encoding: integer`` envelopes
bind exact finite numbers from textual ``data``. Reject malformed envelopes,
nonfinite numbers and unsafe JSON integer magnitudes before native dispatch.
Plain temporal strings retain server SQL-mode validation, including zero dates;
no client rewrite changes that policy. MariaDB bindings are independent.
An explicitly empty MySQL ``sql_mode`` clears the session mode; it must not be
treated as an omitted option by the driver's post-connect truthiness check.
Apply it through the native session property before exposing the connection.

MySQL execution streams
~~~~~~~~~~~~~~~~~~~~~~~

The native MySQL endpoint exposes ``use_pure`` separately from other engines.
True selects Connector/Python's portable implementation; false explicitly
requires its installed C extension and must fail if unavailable. The form
defaults to true. A saved route without this field retains the connector's
native selection behavior. Qualification records the implementation actually
loaded, Python/OS architecture, connector and server revisions. TLS settings
remain native connector options, including certificate and hostname checking;
failed verification never retries with verification disabled.
MySQL alone also exposes native ``allow_local_infile`` (default false) and
``allow_local_infile_in_path``. The latter admits a client-side directory
through Connector/Python's native path checks; it is not a server path or a
MySQL Shell workspace. The provider never enables LOCAL loading implicitly.
Server ``local_infile`` policy still applies, and importing rows does not
implicitly request commit or rollback.
The MySQL 9.7 form excludes ``mysql_native_password``, removed from the server
in 9.0, without changing other MySQL-wire engine forms. An old route explicitly
selecting that plugin is rejected; it is not silently remapped to another
authentication method. Optional installed authentication plugins retain their
server, connector and platform prerequisites.
The ``mysql-native-9.7-v1`` connection capability set declares provider-private
pooling and active/idle/executing/unknown observations, and omits removed native
password authentication and unobserved isolation-level state. Shared wire
capability declarations for other engines remain independent.

A retained MySQL session has one native execution owner at a time. Execute
returns a provider token while a worker consumes the native protocol. Polling
delivers bounded pages in protocol order, with zero-based result-set index,
row offset, native column metadata, and an end-of-set marker. Include empty
sets and affected-row results, including a procedure's trailing OK response.
Completion means all native results have been consumed, not merely that the
first SELECT ended. A later native error preserves pages already delivered;
its terminal observation carries native error identity without SQL or secrets.
No error implies rollback or replay of the batch.

The provider queue holds at most two pages of 256 rows with a one-MiB target
per page. A single larger native row is delivered intact; Connector/Python
materializes that row, so this is not chunked BLOB transport. Backpressure
stops further fetching. The query form displays each delivered page and its
result-set identity; an empty terminal status must not replace the last grid.
Transaction control, another execution and session release cannot race the
worker. While it owns the protocol, transaction observation reports executing
without issuing another command on that connection.

Cancellation uses a separate authenticated connection pinned to the original
server UUID and physical endpoint, then requests native KILL QUERY for the
original connection ID. It never reconnects or replays the query connection.
Cancellation is a request, not proof of rollback or nonexecution of later
statements already sent in the same batch. The worker consumes remaining native
responses before releasing the session; cleanup failure quarantines it.
Provider shutdown cancels and joins workers before releasing connections; a
worker that cannot be stopped remains owned and shutdown reports failure.

MySQL retained transaction observations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Observe connection liveness without reconnecting before reporting native
transaction flags. A failed commit/rollback call is an unknown outcome, even
when the driver later reports an idle flag. Quarantine that retained session:
no later execution, finality request or pool return may reuse it. Closing it
releases the physical connection without claiming rollback or commit success.
After a decoded server SQL error, a failed non-reconnecting native ping also
quarantines the session. Client-side refusals, transport errors and conversion
failures do not establish a command boundary: quarantine without issuing a
ping or cursor cleanup command. In particular, LOCAL file rejection may leave
the server awaiting file packets; a new command would corrupt that exchange.
Ordinary SQL errors on a still-usable connection remain native
errors and do not imply automatic rollback. An explicit new session is separate
from resolution of the earlier outcome; do not retry user SQL automatically.

MySQL result charset ownership
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Text decoding follows each native column's reported collation/charset ID,
including ``character_set_results=NULL``. It does not assume that all result
columns use the connection's command encoding. MySQL latin1 uses its Windows
1252 mapping, including the five control-code positions. Unicode multibyte
results use their declared byte order. If the connector charset registry has
no matching client codec, preserve the exact bytes in a base64 envelope with
native charset and collation identity, and declare a JSON cell. Do not guess,
replace invalid characters or treat those bytes as UTF-8. The default UTF-8
result path lets the server perform conversion from its storage charsets.
Changing SQL character-set variables does not change the connector's command
encoder; connection character-set changes belong in the connection profile.


Firebird attachment metadata and ARRAY identifier encodings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Statement metadata names (field, relation, owner and alias) are decoded using
the admitted attachment encoding, including metadata obtained through native
metadata builders. The provider wraps only interfaces owned by that attachment;
it must not alter global driver classes or another connection. Native status is
checked before decoding, and invalid text is rejected without replacement.
The facade preserves native pointer identity, reference ownership and cleanup;
installation itself starts no transaction and prepares no SQL. Native plan text
uses the same attachment encoding.

ARRAY SDL relation and field names instead use UTF-8 metadata identifiers,
independently of the attachment character set. Catalog parameters and ordinary
values continue to use attachment conversion. Applying the attachment encoding
to SDL identifiers corrupts non-ASCII source names and is prohibited. Storage
character sets, attachment character sets and metadata identifiers are distinct
contracts. Qualification of a storage charset does not establish attachment
charset or alias support; those require separate native evidence.


Grid column keys are opaque record lookup keys, not SQL or HTML identifiers.
Preserve Unicode, punctuation and explicit whitespace in supplied keys; never
ASCII-sanitize them independently of their records. Repeated normalization must
preserve unique keys (including provider-disambiguated duplicate labels). The
display name remains separate. DOM identifiers and layout scope identifiers use
their own contracts and do not authorize rewriting record keys.


Firebird attachment charset observation and private codecs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Resolve the runtime attachment codec from native ``isc_info_att_charset``;
charset aliases and spelling are not Python codec names. Preserve the saved
route and native charset choice. Record the canonical native name on the owned
connection for catalog width lookups, and update its internal cursor before
provider SQL. Installation issues no SQL and changes no transaction boundary.
Unknown native IDs are explicit admission failures, never ASCII fallback.
``NONE`` retains its unconverted native semantics and driver locale encoding;
``OCTETS`` remains available for stored values but is not a native-admitted
attachment charset. Metadata and ordinary text use the observed codec while
SDL identifiers remain UTF-8.

All admitted attachment encodings require native conversion equivalence; a
similarly named Python codec is insufficient. Use provider-private codec names
for missing or differing mappings, including legacy Japanese, Chinese, Korean,
Greek, Ukrainian and Windows encodings, and immutable tables
derived from the admitted native engine. Keep decode and encode maps separate:
multiple byte sequences can decode alike while native encoding chooses a
specific sequence, and native aliases need not be decoder outputs. Incremental
text decoding retains incomplete multibyte sequences across chunks and rejects
incomplete final input. Do not add replacement characters for codec failures;
native mappings that explicitly produce U+FFFD are distinct from substitution.
Codec registration must not mutate firebird-driver's global charset map.
Table qualification records engine/runtime and derives every one-byte input
and every two-byte input for legacy multibyte encodings, with a separate BMP
encoding oracle. Retain native malformed/unrepresentable rejections separately
from infrastructure failures. Built-in codecs may remain only where equivalence
is established. GB18030 uses independently verified native corrections to the
Python mapping: qualify every Unicode scalar and all one/two-byte inputs and
four-byte grammar sequences. Preserve its native decoding aliases independently
of canonical encoding. Stream decoding must retain up to three incomplete bytes
and validate final input without changing native conversion semantics.
Character ARRAY length recovery must use the same native-equivalent codec for
the stored charset, independently of the attachment charset. A successful
native slice conversion must not subsequently fail because Python's similarly
named codec rejects a native byte sequence or counts its characters differently.

UNICODE_FSS is not ordinary UTF-8. Encode UTF-16 code units using the native
one-to-three-byte representation (six bytes for a supplementary scalar), and
decode native FSS sequences through their 16-bit code-unit semantics. Preserve
native-admitted unpaired units without replacement, join valid surrogate pairs
for application Unicode values, and retain incomplete sequences and trailing
high surrogates across stream chunks. Never send four-byte UTF-8 for a
supplementary FSS parameter: native conversion narrows it to an unrelated
16-bit value. Qualify this independently from UTF8 and the legacy codec tables.
Firebird 5.0.4's FSS input validator can reject the canonical surrogate-pair
representation with native malformed-string status, even though native output
conversion emits it. Keep the selected attachment and SQL/identifier encoding,
but explicitly use UTF8 message metadata for FSS text parameters/results and
UTF8 SDL descriptors for its character ARRAY payloads. Size those message and
slice buffers for UTF8. This uses the native per-message conversion interface;
it does not reconnect or change LC_CTYPE. SQL source literals still obey the
native FSS validator: preserve its rejection without lossy retry. The native
engine may also reject supplementary bound inputs despite explicit UTF8 message
metadata, because the prepared expression still uses FSS internally. Report
that native error rather than accepting a narrowed value. UTF8 attachments
support unrestricted Unicode SQL source and input. Successful FSS reads and
writes must preserve exact values; unsupported conversions fail explicitly.
The qualified Firebird 5.0.4 engine can fail transcoding supplementary text
BLOBs through FSS. Rebinding those output BLOBs can also invalidate their native
virtual IDs; retain their native output descriptor. Require strict UTF8
validation of FSS text BLOB results, including incremental streamed chunks, to
reject surrogate-containing native conversion output rather than publishing
potentially corrupt data. Ordinary BMP FSS bytes are UTF8-compatible. Do not
strip bytes, invent replacement text or retry the SQL. Qualify this
native limitation separately, with the same stored BLOB read exactly through
UTF8. SQL plans and identifier metadata still use attachment encoding, not the
negotiated data-message encoding.

:doc:`firebird_driver_development` documents the native platform runner.

Native platform driver handoff uses fresh-process tests against the platform's
actual client library. A portable qualification runner may create a uniquely
named disposable database in an explicitly selected test directory, exercise
provider creation/opening, metadata, typed values, streaming and transaction
visibility, and drop only the database it successfully created. Never overwrite
or attach an existing database as its fixture. Passwords come from a prompt or
an explicitly selected environment variable, never command-line arguments or
evidence. Record platform, driver/client versions, source hashes, completed
checks and cleanup separately. A failed check or unresolved cleanup prevents
PASS. This driver proof does not imply native UX, accessibility, OS-specific
authentication or release qualification.

Attachment parameter block text is independent of SQL attachment encoding.
With the native UTF8 filename/DPB flag, textual identity, role, credentials and
configuration are encoded as UTF-8. The native LC_CTYPE item still selects the
requested SQL attachment charset. Creation must preserve the separately chosen
database default charset. Use owned configurations and native builders, preserve
all admitted options and callbacks, and retain explicit failed-attach ownership;
never change global driver defaults to accommodate one attachment.


Database ATTACHED callbacks run after provider ownership registration and
attachment initialization. A callback failure follows failed-session quarantine
and release; it does not lose the handle or repeat the callback. If the Python
connection constructor fails after native attachment, retain that partial owner
until detach is confirmed, including when local transaction fields are absent.


PostgreSQL retained-session driver contract
-------------------------------------------

Provider sessions own a fresh connection identity and the exact manager which
created it, including delegated managers. Caller-supplied Query Tool identities
do not alias these sessions. Disable automatic reconnect on retained sessions.
Connection loss never authorizes replay of SQL or a transaction decision.

Only one execution may own a retained session. Completion and transaction
commands require an idle, usable session. Cancellation is a request whose
result is observed separately; a terminal operation cannot cancel later work.
Uncertain transaction decisions quarantine the session until explicit close.
A failed rollback during close must not prevent release; release failure must
retain ownership for a later cleanup attempt. Shutdown closes owned sessions
and may not merely drop their handles. Driver diagnostics exposed by this
contract contain error classes and SQLSTATE, not SQL, connection strings or
credential values. PostgreSQL remains transaction-finality authority.

The preserved pgAdmin Query Tool, native tools, connection configuration and
authentication remain PostgreSQL-owned surfaces. Their separate connection
identities must not be borrowed by retained provider sessions.

Provider execution uses a dedicated synchronous libpq connection owned by one
background worker, with at most two queued browser pages (256 rows or 1 MiB
per page; one larger value may exceed the byte target). Native libpq result
buffering is separate and is not claimed to be bounded. Every successful
result set has an ordinal, offset, final-page marker and command status.
Native text output and OIDs preserve numeric precision, temporal extremes,
arrays, composites, ranges, JSON, extension types and duplicate column names.
NULL remains NULL; text output is never parsed through JavaScript numbers.
Binary parameters use an explicit base64 envelope; decimal/integer envelopes
are exact. PostgreSQL SQL casts select engine-specific parameter types.
Server errors terminate the operation and retain native SQLSTATE. A script
which fails can have effects from earlier statements: no replay is implied.
COPY workflows remain on the existing PostgreSQL import/export and native
Query Tool surfaces; the generic query pane does not invent file paths.

A native PostgreSQL attachment remains owned if initialization raises after
libpq connects. Close the attachment before clearing its handle. If close
itself fails, retain the handle and its ownership flag for manager cleanup;
an initialization exception must not hide a live connection from release.

SQLite retained-session and backup driver contract
-------------------------------------------------

SQLite retains its native five storage classes, lock behavior and transaction
rules. Queries use one background worker per retained connection and bounded
browser pages (256 rows or 1 MiB target, two queued pages; one larger cell may
exceed the byte target). Native named and positional bindings are admitted.
Large signed 64-bit integers use decimal text at the browser boundary; BLOBs
use base64 with their byte length. SQLite does not gain a decimal storage type.
Column identity includes an ordinal because result labels may repeat and
SQLite result columns do not have one fixed storage class. Optional Python
type detection remains an explicit connector conversion, not an engine type.

One execution owns a session until observed or explicitly closed. Cancellation
calls SQLite interrupt and observes the actual native result and in_transaction
state; it does not promise that only the current statement, or the entire
transaction, was rolled back. SQLITE_BUSY at commit may leave the transaction
active and retryable by explicit user choice; do not automatically retry a
transaction decision. I/O or ownership uncertainty blocks session reuse until
close. Failed rollback does not bypass close; failed close retains ownership.
Single-statement execution does not silently invoke executescript, whose
native implicit-commit behavior differs from execute.

Online backup uses SQLite's backup API, verifies quick_check, and publishes a
completed staging file atomically. Failed backup preserves an existing backup.
Without overwrite authorization, publication must not replace any existing
file. Reject active-file aliases, including hard links; preserve native page
size and SQLite's consistent backup semantics for its supported journal modes.
Restore validates the source, uses an escaped read-only URI and the native
backup API into the selected live attachment. Neither operation is admitted
inside a retained transaction. Both have an explicit bounded deadline and
preserve failure diagnostics. SQLite's journal/WAL behavior remains its own;
ScratchBird's transaction design is not substituted for SQLite semantics.

DuckDB native driver contract
-----------------------------

DuckDB retains one native connection for transactions, SQL and metadata;
its cursor factory must not be used as a same-session cursor. Worker execution,
ordered bounded pages, exact Arrow values, native interruption, separate
decision/restart observations and cleanup ownership follow
:doc:`duckdb_driver_development`. Native COPY/import/export and attachments
retain DuckDB semantics; no unsupported server or savepoint features are added.

CockroachDB retained native driver contract
------------------------------------------

CockroachDB owns its transaction retries and ambiguous outcomes. The provider
uses psycopg transport mechanics with isolated retained sessions, savepoint-safe
metadata, configuration-specific pools, native cancellation and exact result
pages as specified in :doc:`cockroachdb_driver_development`. No automatic
transaction replay or reconnect is admitted. PostgreSQL wire compatibility
does not enable PostgreSQL-only administration features.

YugabyteDB YSQL retained native driver contract
----------------------------------------------

YSQL admits shared retained PG-wire mechanics while preserving its own
metadata, language, forms and distributed transaction authority. Its exact
contract and portable qualification requirements are specified in
:doc:`yugabytedb_ysql_driver_development`. YCQL remains a separate provider.

YugabyteDB YCQL retained native driver contract
----------------------------------------------

YCQL uses native prepared binary bindings, asynchronous operation ownership,
complete native paging, ordinal exact-value results and conservative uncertain
outcomes as specified in :doc:`yugabytedb_ycql_driver_development`. Cancellation
stops local delivery only; protocol v4 does not supply server query cancellation.
Native YCQL table transaction and conditional mutation semantics remain native.

TiDB retained native driver contract
------------------------------------

TiDB admits exact MySQL-wire values and retained operation mechanics without
inheriting MySQL Shell administration. Its process-identity checked cancellation,
conflict decisions, metadata isolation and pool behavior follow
:doc:`tidb_driver_development`. TiCDC credentials remain leased separately;
copying an administration request preserves its native session handle by
reference instead of attempting to copy a live socket.

Vitess retained driver
----------------------

See :doc:`vitess_driver_development` for retained VTGate execution ownership,
exact MySQL-wire values, uncertain-outcome quarantine, transport-abort
cancellation and physical lease discard. COM_RESET_CONNECTION alone is not
evidence of complete VTGate session isolation. Routing and distributed
transaction policy remain native Vitess decisions.

Dolt retained driver
--------------------

See :doc:`dolt_driver_development` for native SQL versus version-control
commit separation, exact streaming, branch-sensitive lease disposal and
unknown-outcome handling. No version-control mutation is implicit.

XTDB retained driver
--------------------

See :doc:`xtdb_driver_development` for bitemporal document values, native
transaction policy, asynchronous retained execution and unknown outcomes.

immudb retained driver
----------------------

See :doc:`immudb_driver_development` for native SQL/REST separation, exact BLOB
binding, independent metadata, retained ownership and uncertain decisions.

MongoDB, ClickHouse, InfluxDB and Neo4j retained drivers
-----------------------------------------------------

The default factories retain worker ownership and stream native results.
MongoDB and Neo4j keep writes on the explicit native transaction session;
ClickHouse and InfluxDB expose their native request semantics without SQL
transaction controls. Exact value envelopes and engine-native forms remain
provider-owned. See :doc:`mongodb_driver_development`,
:doc:`clickhouse_driver_development`, :doc:`influxdb_driver_development` and
:doc:`neo4j_driver_development` for formats, cancellation, cleanup and portable
native qualification gates.

Search and vector retained drivers
----------------------------------

Milvus uses owned gRPC sessions, exact vector values and native iterators.
OpenSearch preserves Query DSL top-K semantics and provides explicit scroll
scans, native REST and per-item bulk results. Its SQL plugin drains native
cursors; PPL retains native result limits without inventing pagination.
See :doc:`milvus_driver_development`, :doc:`opensearch_driver_development`
and :doc:`opensearch_sql_ppl_driver_development` for lifecycle, cancellation,
security and portable qualification contracts.
