PostgreSQL driver development and platform qualification
=======================================================

ScratchRobin preserves pgAdmin's PostgreSQL administration, connection editor,
Query Tool, import/export, backup/restore and native utilities. Provider Data
Studio sessions use the same manager and credential leases, with their own
connection identities. Those sessions disable automatic reconnection and own
a synchronous psycopg connection; a worker executes SQL and publishes ordered
result pages. The preserved Query Tool retains its separate execution path.

The current admitted server profile is PostgreSQL 18.3. Approved psycopg
versions are 3.2.13 and 3.3.4. Install project requirements, the platform's libpq
runtime (or the admitted psycopg binary distribution) and PostgreSQL client
utilities matching the managed server for native backup/restore workflows.
The portable driver gate uses no Docker. Windows and macOS teams should run
it in a fresh Python process with their actual packaged client libraries.

Native values and transactions
-----------------------------

Results carry PostgreSQL's text representation, type OID, originating table
OID/attribute number and an ordinal column key. Duplicate column labels remain
visible. Exact numerics, large integers, temporal infinity, ranges, arrays,
composites, JSON and extension types do not pass through JavaScript numeric
conversion. SQL NULL remains null. ``bytea`` follows the server's text output
setting. Non-ASCII bytes from a SQL_ASCII connection use a base64 envelope
with their original byte length instead of replacement characters. Each page carries result-set index, row offset, end marker and native
command status. The queue holds at most two pages; a page targets 256 rows or
1 MiB. A single larger value can exceed that byte target. libpq itself buffers
native results; these page limits do not establish a server-memory limit.

Named ``%(name)s`` and positional ``%s`` bindings use psycopg. JSON parameters
may contain exact scalar envelopes with ``type`` and string ``value``:
``integer``, ``decimal`` or ``binary`` (base64). Use explicit SQL casts for
PostgreSQL-specific types. Native SQL placeholders never use string expansion.

A native error during multi-statement execution may prevent publication of
earlier buffered result sets. Earlier statements may nevertheless have effects;
the provider exposes the failure and never retries the script.

A session admits one execution until its terminal observation. Cancel sends
libpq's backend-key-bound request; it does not imply rollback or success.
PostgreSQL can leave a transaction aborted after cancellation or SQL errors;
use explicit rollback. Committing an aborted transaction can return the native
``ROLLBACK`` command status. A lost decision response quarantines the session;
close it and investigate the outcome before any deliberate retry. Closing
requests cancellation of active work, discards pending presentation pages and
waits for the worker. An unfinished worker or failed release remains owned
for a cleanup retry. Shutdown must not silently forget live connections.

Running the portable gate
-------------------------

Use an explicitly selected PostgreSQL 18.3 test server and an isolated qualification account. The current gate also
creates uniquely named operator classes/families and index/table access methods,
so its native administration section requires PostgreSQL superuser privileges.
Use a disposable qualification instance for that section. Store a route JSON outside the source repository::

    {
      "host": "localhost",
      "port": 5432,
      "user": "driver_qa",
      "database": "driver_qa",
      "connection_params": {
        "sslmode": "verify-full",
        "sslrootcert": "/absolute/path/to/test-ca.pem"
      }
    }

Run from the repository root; the password is prompted, never a command-line
argument::

    python tools/cdeadmin_postgresql_driver_platform_gate.py \
      --route /external/workarea/route.json \
      --evidence /external/workarea/new-postgresql-proof

``--password-env VARIABLE_NAME`` selects an existing process environment
variable for unattended testing. The evidence directory must be new and
outside the source tree. It contains an isolated application configuration,
source hashes, exact server/client versions and individual completed checks.
The gate exercises the real delegated application manager, exact values,
multiple results, bindings, native transaction decisions, cancellation, COPY
and manager release. A failure prevents a passing receipt.

``--reply-loss`` additionally requires an explicitly plaintext loopback test
route (``sslmode: disable``) and CREATE/DROP TABLE permission. A private fixture
withholds a decoded successful COMMIT response; an independent connection
verifies the committed effect and provider refusal to replay it. It creates
and removes one uniquely named table. Never use this option to weaken a TLS
route or against a production database.

Platform UX, accessibility, installer signing and OS-specific authentication
qualification remain with the platform teams. A Linux gate receipt is not
Windows or macOS execution evidence.

Retained replication slots and exported snapshots
-------------------------------------------------

The server continuity workspace includes a separate temporary replication
resource. It uses the saved registration's exact database, native principal and
an independently retained database replication connection. Ordinary SQL startup,
role substitution and the SQL slot catalog are not required. Resource and command
reviews bind the native identity, original backend, provider isolation scope and
adapter. Credentials are withheld from durable receipts.

Typed commands create native temporary physical/logical slots, select WAL
reservation, logical two-phase decoding and export/no-export snapshot modes,
and drop only slots acknowledged and still owned by that original backend.
Prior creation receipts cannot authorize deletion of a subsequently reused name.
Native plugin/permission/configuration errors remain native failures. An error
ends this owner rather than reconnecting or recreating its temporary state.

An exported snapshot requires that original connection and expires on its next
native command or termination. Status, reviews, acknowledgement pages and viewer
reloads send no native command. Another command requires explicit confirmation
to invalidate the current snapshot. Recent acknowledgements are bounded to 100;
complete command receipts have their own paging. Neither is a SQL slot catalog
or a current health check. Viewer close does not release the resource; confirmed
release and its configured lifetime do. Native command acknowledgement, local
connection close and independently observed server cleanup remain separate.
Uncertain commands never replay, including after a later storage failure.

``tools/cdeadmin_postgresql_replication_temporary_qualification.py --output``
exercises authenticated original-backend creation, snapshot import by an
independent observer after idle/status reads, provider/database isolation,
foreign-name protection, native errors, release and offline receipts. Optional
``--browser-binary`` and ``--driver-binary`` exercise the production controls and
retention across viewer reload. Evidence belongs outside source. Independent
application consumers are described below. Destination orchestration and
installed-plugin acceptance retain their own acceptance requirements.

The same retained resource can capture an acknowledged logical temporary slot
through native START_REPLICATION / COPY BOTH. Native plugin options and the
requested start LSN are reviewed with optional message, artifact-byte and
duration bounds. A bound can split a native transaction and does not establish
a complete WAL archive. Exact XLogData frames are stored as base64 JSONL records
in private storage; preview is bounded, download preserves every captured byte,
and stopped captures have explicit inspection and confirmed removal controls.

Flush feedback is disabled by default. When explicitly selected, feedback
advances only to data-start positions from frames already flushed and fsynced.
Server WAL-end hints never advance it, and the application apply position stays
zero. A locally sent feedback message does not establish a current server flush
checkpoint. Native completion requires both CommandComplete responses and the
final idle protocol boundary. It is saved before artifact publication, separately
from durable bytes, later publication failures and inspected partial captures.
The original backend remains usable after a successful bounded capture;
cancellation, native error or uncertain publication ends the owner. Neither a
capture nor its inspection automatically replays a stream or recreates a slot.

The native qualification also exercises original-backend streaming, default and
selected flush feedback, exact delivery/preview, byte bounds, cancellation and
publication failure. Its browser path captures and previews a temporary logical
stream after retaining a snapshot across reload. These receipts qualify their
recorded plugin and installation; installed output plugins need their own native
payload/language acceptance.

The pinned server can terminate a later START_REPLICATION immediately after an
earlier logical stream on the same backend. Its source resets the stream-end
flags in physical startup but not in logical startup. A clean native end is
recorded as ``native_stream_end`` with its actual frames and both native command
completions; it is never represented as a reached client bound or caught-up
checkpoint. ScratchRobin does not issue hidden physical commands, reconnect or
recreate a temporary slot to work around that native behavior. A continuously
retained first stream can use no local capture bounds under application policy.

Owned SNAPSHOT USE and initial relation COPY
--------------------------------------------

The same resource offers native SNAPSHOT USE. Its reviewed logical-slot command
starts an owned read-only repeatable-read transaction and creates the slot as
the first command inside that transaction. Native BEGIN acknowledgement is
journalled separately from slot creation. A failure between those commands never
claims slot creation or automatically repeats it. The original backend retains
the installed snapshot across local status reads and viewer changes.

An explicit native snapshot catalog operation lists relation identities with
bounded paging, exact schema filtering, native SELECT permission and row-security
facts. Explicit relation inspection records the native column identities,
declared types, modifiers and applicable flags. Declared domains remain distinct
from the base wire type and modifier used by native RowDescription. Inspection
runs as a cancellable command with its own deadline. COPY review and local status
send no native query. The backend retains the latest 100 inspected sources;
complete inspection receipts remain separately paged. Inspect an evicted source
again before reviewing its copy.

Reviewed relation COPY stays on this original snapshot transaction. Native locks,
current regclass identity and actual RowDescription bind the selected source
before bytes are captured. Plain/partitioned tables and views use native LOCK
TABLE. Materialized and foreign relations use a zero-row SELECT to obtain their
native AccessShareLock, with current identity checks before and after. This
preserves their native eligibility when LOCK TABLE itself rejects those kinds.
Native SELECT permissions, row security, view behavior and foreign-server
authentication remain authoritative. Foreign sources retain their own remote
snapshot semantics; a local decoding snapshot does not establish remote snapshot
synchronization.

The application streams exact native binary, text or CSV COPY output into private
artifacts. Typed COPY TO options expose delimiter, NULL marker, header, quote,
escape, FORCE_QUOTE and encoding. Native format/option refusal remains a native
failure. Receipts preserve the selected relation, type facts, format/options,
native row count and byte hash. Native command acknowledgement is saved before
artifact flush/publication. Bounded byte preview, exact download, explicit
stopped-file inspection and confirmed removal remain available after the original
backend ends. Inspecting bytes cannot promote an unknown native command outcome
or infer completeness without its recorded acknowledgement.

Explicit commit or rollback ends the owned read-only transaction. Temporary
slots remain session-owned under native rules; subsequent native streaming can
use the original slot/backend. A native error or uncertain command ends this
owner and releases its locks instead of reconnecting, recreating slots or
replaying COPY. Selected relation captures, database backup, destination loading,
logical application and production cutover retain their separate receipts.

The qualification command covers exact native values and domain identities,
binary/text/CSV roundtrips through independent native COPY imports, materialized
and postgres_fdw relations, native RLS/privilege refusal, explicit transaction
end and a same-backend post-snapshot logical stream. It also exercises the
BEGIN/creation boundary, reused relation names, publication failure, offline
inspection/removal and independently observed native COPY cancellation. Its
browser path creates the owned snapshot, inspects/copies a relation, verifies
the delivered bytes through an independent native import, ends the transaction
and streams on the original backend. Evidence qualifies the recorded installation
and selected scopes; destination orchestration/cutover and wider installed-plugin
acceptance remain open.

Independent exported-snapshot consumers
---------------------------------------

An active export offers a separate reviewed consumer resource. Its snapshot
reference is derived from the current original-owner receipt, bound to the
registration, exact database/principal, complete provider isolation scope and
adapter. Callers cannot submit arbitrary snapshot names or source metadata.
Review and start refuse an expired, changed or unavailable original export;
the worker rechecks it after opening its own connection and transport. It never
borrows the exporter's socket or SSH tunnel, and sends no command on that socket.

The new native database replication connection verifies the cluster and peer,
then observes the exporter's PID, database, principal, application identity,
backend type and start time. It begins a read-only repeatable-read transaction
and imports the acknowledged snapshot as the first command after BEGIN. Native
BEGIN, snapshot import, exporter verification and readiness are recorded
separately. The exporter identity and start time must still match after import.
Cancellation, native refusal or uncertain publication closes only this consumer;
its durable acknowledgements survive and an uncertain import never replays.

After verified import, this independent transaction retains its snapshot under
PostgreSQL's native rules even after the exporter ends or invalidates its export.
It offers the existing explicit relation catalog, inspection, locked native COPY,
private delivery and transaction-end controls. Its source slot remains owned by
the exporter: the consumer cannot stream or drop that slot. Relation privileges,
RLS, concurrent DDL and foreign-source snapshot limitations remain native.

The qualification command tests independent application import, concurrent
commits, exporter termination, exact binary delivery through a native COPY
import, explicit transaction end, source-slot refusal, expired review, native
42704 between BEGIN and import, and publication failure after native import.
Its browser path imports an independent consumer, returns to the exporter for
streaming/release, then copies and independently verifies the original rows from
the surviving consumer. This scope uses the same registration and authenticated
REPLICATION principal. Cross-registration consumers and consumers admitted as
ordinary SQL users without REPLICATION remain implementation gaps. Destination
loading/application/cutover and other installed plugins remain separately open.
