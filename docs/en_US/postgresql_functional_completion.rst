PostgreSQL functional completion
*******************************

Scope and layout direction
==========================

Owner direction, 2026-10-11: apply the Firebird completion standard to PostgreSQL,
preserving the complete native administration surface. Compare existing forms
before replacing them: PostgreSQL's tabbed property forms, privilege collections,
constraint editors, SQL preview and version-aware fields may provide better
layouts than the Firebird forms. Preserve those strengths and reuse them for
other engines where appropriate. Shared controls do not imply shared grammar,
transaction semantics, object hierarchies or capabilities.

Explicit table-data DDN capture
==============================

Metadata capture never reads application rows. A separate, explicit data-capture
action binds one selected native relation OID to the connected database and offers
sample or full-selection mode. Both use an independent read-only REPEATABLE READ
transaction, native SELECT privileges and row-security rules, a 1–6,000-row
budget, at most 256 columns, a 4 MiB encoded-value budget and an 8 MiB final DDN
workspace limit. Fetch at most 128 rows at a time through a server cursor. Each
fetch batch, including large individual values, requires native-driver buffering
before its byte budget can be checked.
The exported selection is complete only when the cursor confirms end-of-data;
exceeding the requested row budget produces an explicitly partial selection.
Byte/document budget failure returns no misleading partial document. Sampling
is a bounded prefix in native scan order, not random or ordered sampling.

Resolve the exact table, partitioned table, view or materialized-view OID, acquire
an ACCESS SHARE lock and revalidate that name-to-OID mapping before reading.
Do not substitute a same-named replacement. Preserve positional column metadata,
type OIDs, NULL and PostgreSQL text encodings without floating-point conversion.
Capture records its local ISO/YMD date style, postgres interval style, UTC
timezone, hexadecimal bytea output and extra_float_digits=3 settings, preserving
portable interpretation without changing any user attachment's settings.
Record endpoint/database/relation identity, observation time, selected mode,
limits, acquired row count, truncation, isolation and row-security scope in the
portable DDN source. Full means all rows visible to this authorized attachment
within that one relation selection; it is not a backup or an entire-server dump.
User transactions are never committed, rolled back or borrowed. Close the cursor
and complete/release the owned transaction before returning a successful result.
Exported documents are static data and do not authorize imported queries.

The existing PostgreSQL driver qualification is recorded in
``postgresql_driver_development.rst``. This checklist is additional required
work, not a claim that the full feature set has been qualified. The owner's
October 14/16 completion scope includes persistent monitoring history and the
ScratchBird history backend. PostgreSQL archive integration is wired; the
owner correction of October 16 defers ScratchBird history testing until explicitly
resumed. Windows/macOS qualification belongs to the platform teams. The additional
catalog, language and complete management-workflow acceptance requirements and
current gaps are recorded in :doc:`six_engine_completion`.

Acceptance obligations
======================

Native property validation evaluates conditional field visibility with the owning
schema as its callback context, including nested schemas and collection rows.
Hidden required fields must not block unrelated authentication or object forms;
visible fields retain their native validation. Table inspectors and editable
Properties dialogs must both open and save without losing this context.
Delayed initial or tab focus must never steal focus from a control the user has
selected. Cancel pending focus callbacks when tabs change or forms unmount;
skip disabled and read-only inputs when choosing an initial editing control.
Typing into Comment must not rename the object because a delayed callback moves
focus to Name.

Native advanced-object forms retain quoted and Unicode catalog identifiers.
Operator administration binds both operand types as well as schema and symbol;
prefix operators have no left operand. Preserve overloads. Creation exposes the
implementation function, optional commutator/negator, restriction/join estimators
and hash/merge flags. Alteration exposes owner, schema, comment and PostgreSQL 18
optimization options, without inventing operator rename or postfix operators.
Removing an estimator uses native NONE; hash/merge support cannot be unset by
ALTER. Drop defaults to RESTRICT and requires the exact symbol confirmation.
Inspect, review and execution use the existing owned native administration path.
Read-only inherited operator properties alone do not satisfy these obligations.
Native syntax authority is PostgreSQL 18 create_operator.sgml and
alter_operator.sgml in the reference source tree.

Aggregate administration preserves native signatures, including zero-input,
variadic and ordered-set aggregates. Creation accepts one bounded, qualified
native CREATE AGGREGATE definition, retaining the complete PostgreSQL option set
instead of reducing it to transition-function and state-type fields. OR REPLACE
requires a separate explicit replacement choice matching the definition.
Owned administration transactions set ``standard_conforming_strings=on`` locally
before executing parser-reviewed definitions, independent of connection defaults;
failure to establish that literal policy rolls back the owned operation.
Alteration provides native rename, owner, schema and comment actions; drop uses
the selected native signature and defaults to RESTRICT. Inspection uses the
selected catalog OID. Read-only inherited aggregate properties remain available.
Discovery retains PostgreSQL's fully qualified object/type identities for owned
administration connections; the Explorer's search path must not retarget a
captured overload when a separate connection executes its operation.
Administration target selectors display those native identities, including
schema and argument types, while selection remains bound to the resource ID.
Same-name overloads must not appear as indistinguishable choices.
Aggregate and operator Explorer objects and their collections expose native
administration links. An object link binds the connected database and native
OID plus object kind, resolves that exact object in the authorized workspace
catalog after refreshing its snapshot, and refuses missing targets; it never selects another same-name overload.
Collection creation starts with its exact schema name, preserving whitespace.
These user-object actions are not offered in system catalog branches.
The existing read-only property tabs remain available alongside administration.

Leading/trailing whitespace in an identifier is significant and is never trimmed;
destructive-action confirmation must match the exact native name.
Operator-class members carry separate operand types, function argument types and
optional ordering-family references; function signatures must not be discarded.
Empty operator or function lists are permitted when other members exist, as
PostgreSQL access methods have different requirements. Inspecting an operator
class or family binds its access method as well as schema/name. Native execution
remains PostgreSQL's authority for validating an access method's member semantics.
Compiler reference: https://www.postgresql.org/docs/18/sql-createopclass.html .

* PG-COMP-01: Preserve the native server/database/schema/object hierarchy and all
  existing PostgreSQL forms, including partitions, materialized views, extensions,
  foreign data wrappers, publications/subscriptions, event triggers, policies,
  roles, tablespaces, languages, types and full-text objects. Hide unavailable
  operations by server version and permissions; distinguish system objects.
* PG-COMP-02: Explorer authentication, SQL selection and disconnect agree. A
  selected database is bound by its server-scoped native OID. Do not use the
  maintenance database as a fallback when an explicit database is invalid,
  disconnected, dropped or inaccessible. Database selection does not mutate the
  server registration or other editors. Preserve independently owned sessions,
  drafts, cancellation, aborted transactions and uncertain outcomes.
* PG-COMP-03: Shared SQL editor with PostgreSQL syntax, native parameter binding,
  completion, script/file tools, history, result navigation, buffer row limit,
  autocommit checkbox and explicit commit/rollback. Preserve the existing Query
  Tool's richer native facilities until equivalent shared paths are qualified.
  Report timings with measurement scope; distinguish estimated EXPLAIN from
  executed EXPLAIN ANALYZE. Never execute statements just to obtain a plan without
  explicit authorization. Do not manufacture a plan from another execution.
* PG-COMP-04: Native object/database/server metadata search, dependency-aware
  metadata/data export, COPY/import, selected-row SQL, binary/large values and
  test-data recipes. Use PostgreSQL quoting/types and explicit transaction
  outcomes. Native pg_dump/pg_restore backups remain distinct from DDN export.
* PG-COMP-05: DDN discovery/display/design, native generation, semantic diff,
  review/apply and rediscovery at object/database/server scope, following
  ``ddn_database_roundtrip.rst``. Retain unsupported native details and report
  incompleteness rather than silently flattening them into a generic SQL model.
* PG-COMP-06: Display-only engine/server/database DDN dashboards using independent
  collector connections, configurable credentials/role, bounded samples, policy
  heartbeat and regularly completed read transactions. Preserve native metric
  scope and resets. Availability does not imply replication freshness. Dashboard
  editing belongs in the separate DDN editor. A pgAdmin polling chart alone does
  not qualify this collection/authorization contract.
* PG-COMP-07: Compact forms, stable form references, keyboard navigation,
  accessible labels, efficient checkbox/select choices and paged editable grids.
  Preserve good native layouts. Compare corresponding Firebird forms and record
  reusable improvements rather than mechanically replacing PostgreSQL forms.
* PG-COMP-08: Qualify with a real supported PostgreSQL instance, independent
  transaction observers, at least two databases and two SQL sessions, native
  permission failures, disconnect/reconnect, cancellation and connection loss.
  Test native forms as well as provider adapters. Record exact DDN provenance.

The preserved-surface inventory and direct SQL smoke test are supporting
evidence only. They must not mark native UI operations passed or authorize engine
activation. Qualify each operation through the actual compiler, host ownership
and transaction path, and form interaction where applicable. Keep untested
operations explicitly unqualified; file existence is not behavioral evidence.

Database-bound shared workspace contract
=======================================

All native catalog kinds exposed in a database workspace must have the provider's
read-only inspector, including partitioned relations, window functions, policies,
full-text objects and default privileges. Inspector availability is separate from
mutation support. The workspace presents captured ``policy`` objects as
``row-policy`` to match the existing administration form; their catalog kind,
OID, resource ID and DDN representation remain unchanged. Reinspection must
resolve the same native identity, and a missing object must be reported as gone.

The shared PostgreSQL workspace identifies a selected database using
``postgresql-database:<oid>`` within the registered server endpoint. The backend
accepts only canonical positive PostgreSQL OIDs and resolves names through the
server's catalog. An explicit target requires an already connected Explorer
attachment. Server scope retains the explicitly configured initial database;
unknown targets never collapse to that scope. Target-specific cache/session
namespaces prevent cross-database result or metadata reuse. Registration forms
remain the existing native PostgreSQL forms; shared read-only descriptors do not
permit generic provider registration mutations.

While any shared PostgreSQL SQL session on the endpoint remains open, native
server/database disconnect and configuration replacement are refused. The user
must explicitly resolve work and close the query session first. This conservative
endpoint guard also protects sessions on other databases of that server; it does
not infer that cancellation, socket loss or attempted commit resolved a transaction.

When a restored server node is still checking its native connection status,
Explorer expansion waits for that check and its node reset to finish. A late
status response must not discard children fetched by an earlier expansion and
leave an empty, apparently expanded branch. Failed checks leave expansion
unfulfilled and report the error; they never authorize child discovery.

Independent monitoring source contract
======================================

The PostgreSQL source uses an independently opened psycopg attachment named
``ScratchRobin monitoring``. It never accepts an existing user connection. Each
sample executes a bounded, read-only transaction and ends it before publishing a
successful refresh. Optional metric groups use savepoints so a permission failure
does not poison other groups. Native SQLSTATE identifies unavailable groups; SQL
text, credentials and connection exception messages are not placed in samples.
Failure to end a transaction makes that sample unavailable. Failed connection
release remains owned and must be retried before reconnecting.

Initial native metric groups are database cumulative counters, activity excluding
the collector, lock waits, table maintenance estimates, replication state,
cluster I/O and relevant settings. Server scope reads per-database counters and
cluster groups; database scope limits activity, locks and relation statistics to
the selected database. Server statistics and database-local relation statistics
are labelled separately. Query text is not collected. Restricted statistics
visibility is explicit; null/redacted values are not converted to zeros.
Settings describe the collector connection and use the configured metadata
sampling interval, retaining their actual observation timestamp. Cached settings
are discarded on release/reconnect; a failed refresh is reported as unavailable.

Counter rates require consecutive samples from the same database, postmaster
start and statistics-reset epoch. Reconnect, failure, reset, decreasing counters
or missing counters break the rate baseline. Exact integral/decimal measurements
are serialized as strings, retaining SQL NULL. Table estimates are not row
counts; PostgreSQL buffer hits are not operating-system cache hits. All samples
are process-local, bounded by the monitoring runtime's lease and retention policy.
Collector availability and a fresh completed transaction do not imply replication
freshness. PostgreSQL metrics must use PostgreSQL dashboard bindings; Firebird
``MON$`` bindings are not reused.

Native semantics reference:
https://www.postgresql.org/docs/18/monitoring-stats.html

Monitoring delegation and presentation
======================================

The host selects the monitoring engine; a browser cannot supply a source factory.
Sealed credential grants bind that engine along with the owner, target, route,
generation, account and policy. PostgreSQL requires an explicit connection
database even for server-wide statistics. A database-scoped grant also binds the
native database OID and checks it on each completed refresh, so recreating a
database under the same name cannot silently resume the old collector.

DDN publications use fixed native metric bindings. Names and observations are
quoted data, never executable DDN identifiers or SQL. Only the latest fresh,
successfully completed, matching-scope sample can populate current measurements.
Stopped, failed, stale and incomplete observations do not retain earlier values
as current. Missing values remain unavailable; numeric zero and boolean false
remain valid observations. Counter rate values require an available baseline.
Each bounded group reports scope, visibility and truncation. Table tuple counts
are estimates; replication positions and intervals retain their native meaning.
No aggregate silently sums server-wide metrics across database collectors.

The source and DDN adapter are independently qualified components. Their presence
does not complete PG-COMP-06: host routes, credential configuration, policy UI,
engine inventory, publication editing and live browser qualification must also
be integrated and verified.

Host admission uses the authenticated owner's already connected native PostgreSQL
18.3 attachment only to resolve its database and capture encrypted credentials;
sampling never borrows that attachment. Both server and database context menus
provide separate monitoring settings and display-only DDN viewer destinations.
Current credentials and a dedicated username/password/optional role are supported.
The worker rechecks persisted ownership, active account, endpoint generation and
registration configuration before and after sampling. Registration changes revoke
access to old samples and require stop/reconfigure; browser disconnection alone
does not stop a separately admitted policy. The native database OID is rechecked
by the dedicated collector. Settings accept only PostgreSQL policy fields.

Password-authenticated libpq service registrations resolve the already connected
attachment's selected host, port, database and user at policy admission. Preserve
admitted effective TLS options, freeze that explicit route, and never pass the
service alias to a collector reconnect. Editing a service file does not retarget
an existing policy; stop and reconfigure it to admit a new route. Current native
libpq password material may be leased synchronously into the sealed grant when
the registration's encrypted password cache is empty. Never retain that password
in route metadata or samples. A dedicated account remains an alternative.

Direct registrations resolve certificate, private-key, root-certificate and
revocation-list paths through the same authorized storage resolver as the native
connection, synchronously at policy admission. The root-certificate sentinel
``system`` remains a libpq value. Workers receive the resolved paths and never
resolve request-relative storage paths in a background context. Effective service
paths are already resolved by libpq and must not be reinterpreted as uploaded
user files. Certificate contents remain file-backed, as with the native driver;
this path resolution does not claim certificate-content snapshotting.
An explicitly configured TLS private-key password is sealed in a separate
``tls_private_key_password`` lease. It never enters admitted route metadata or
samples. Dedicated database credentials do not replace the TLS key password.
The native display connection string masks both database and TLS key passwords,
including passwords supplied as connection parameters; masking must not change
the private connection string passed to libpq.
The worker decrypts it only for the native connection attempt, releases the
lease on success or failure and refuses unsupported secret kinds. Service
admission extracts this password from effective native parameters before
retaining the route; it never reopens the service file for credentials.

SSH monitoring owns a separate loopback-bound tunnel and PostgreSQL attachment.
Admission freezes the connected registration's SSH endpoint, username, remote
destination and observed server host key. Reconnect must match that host key;
it does not silently accept a changed peer. This pins the already connected peer,
not a claim that an unverified initial registration performed host-key checking.
The interactive manager retains the successfully used encrypted SSH credential
for its session, including an unsaved password or private-key passphrase. This
does not save the credential in the server registration; persistence still
requires the user's Save Password choice. Failed authentication does not replace
the retained credential. Monitoring configuration errors remain visible through
successful background polling until the user retries the action.
Password and private-key SSH authentication use separate sealed, purpose-bound
worker secret leases; a dedicated database account replaces only the database
credential. No ambient SSH agent, user SSH configuration or fallback key search
may supply another identity. Private-key contents are captured at admission,
never reread or written to a worker key file. Registration changes revoke the
grant; changing an external key file requires stop/reconfigure to capture it.
The collector preserves the original database hostname for TLS verification,
while connecting through its own loopback address and port. User disconnect does
not close this owned tunnel. Stop, failed attachment and reconnect cleanup release
the owned database attachment and tunnel; failed release remains unconfirmed.
SSH qualification includes both password and encrypted private-key authentication,
independent native attachment identity, interactive disconnect, failed-attachment
recovery, grant revocation, peer-key mismatch refusal and confirmed transport
release. Registration admission also rejects endpoint/authentication/key-path
changes until the interactive connection is re-established.
PostgreSQL samples provide the coordinator's scoped completion evidence:
``transaction_refresh.status=completed`` for a database policy and
``service_probe.status=completed`` for a server policy, only after the dedicated
read-only transaction commits and the sample is assembled. Partial metric
visibility does not invalidate a completed availability probe. Failed or
unconfirmed transactions never advance the heartbeat; a generic completion
boolean alone is not the coordinator's evidence contract.
Reusing a Kerberos login ticket for monitoring remains explicitly refused pending
separate credential-context and native qualification work. A Kerberos-authenticated
interactive registration may nevertheless select a dedicated monitoring
username/password. This independent attachment disables GSS encryption negotiation
and requires native password/MD5/SCRAM authentication, preserving its TLS policy.
It must never borrow an ambient Kerberos identity as a fallback. A server that
only admits GSS for that dedicated role refuses the attachment normally.
TLS/GSS options are preserved under
the collector's allowlist; unknown options are refused. Connection timeout must
be 1–30 seconds. Those unsupported admission paths remain qualification work,
not a claim of complete native transport parity. The application shares one
process-ownership lock across Firebird and PostgreSQL and releases it only after
both runtimes confirm attachment cleanup.

The PostgreSQL engine dashboard lists only the current owner's native PostgreSQL
registrations. Server registration inventory is distinct from configured volatile
database collectors and from the native database catalog. Viewing inventory never
starts a collector. Each server and database observation is reauthorized; revoked,
failed, stale or missing sources remain explicitly unavailable. Fleet output is
bounded to the latest sample per collector, with no credentials or SQL text.
Metrics from different scopes are not summed. Navigation selects a registered
server or an admitted database target; it does not change or start a policy.

Native query execution-policy acknowledgement
=============================================

The shared source editor loads and saves browser-local UTF-8 source files up to
1 MiB. Loading a file never executes SQL, interprets client include commands,
changes the selected connection or changes transaction policy. Invalid UTF-8 and
NUL are rejected. A read completing after a source edit, context change or
execution lock is discarded. Retained running or uncertain scripts cannot have
their source replaced by a file load. Source files may contain sensitive SQL or
data and are downloaded only by explicit user action.
The shared editor bounds and scrolls its resizable source pane independently of
the result tabs. Expanding source tools must not hide the result/engine-options
area outside a clipped workspace; small windows retain workspace scrolling.

Persistent shared-editor SQL history is opt-in and scoped by authenticated
application owner, registered server, native database OID, engine and language.
PostgreSQL SQL history does not use Firebird's numbered dialect namespace.
Policies retain 1–365 days and at most 1,000 records. Bound values and results are
never history payloads. Explicitly sensitive source, credential-bearing source
and source over 64 KiB are omitted with a reason. History records submission or
preparation observations, not commit or rollback. History-store failures must
never retry or suppress native execution. Reloading an entry only edits source;
clearing requires explicit confirmation and leaves the scope's policy intact.

The native PostgreSQL Query Tool exposes autocommit as a toolbar checkbox.
Commit and rollback buttons are disabled while it is checked. Policy changes
use the existing native Query Tool transaction endpoint, never generated SQL.
The checkbox updates only after a successful policy acknowledgement. Pending
or failed/uncertain policy requests block toolbar execution controls and their
shortcuts until an explicit
request for each unresolved policy is acknowledged; failures do not claim rollback or retry SQL.
Late responses for a replaced query-tool transaction cannot update its new
policy. Server-cursor state changes only after the same acknowledgement.

Published dashboard definitions
===============================

PostgreSQL dashboard drafts and publications are owner-scoped project assets in
an engine-specific namespace. Server and database definitions bind the registered
endpoint and database OID; access is reauthorized on every read/save/publication.
Saving a draft does not publish it. Publication requires optimistic source and
publication versions and server-side validation using the consumed DDN runtime.
The display-only viewer replaces recorded metric values with current admitted
observations; draft literals never stand in for live measurements.

Bindings must be stable across row ordering and inventory changes. Object-specific
bindings include native identity and name; disappeared or renamed objects become
unavailable rather than borrowing a different object's row. DDN layout editing
remains in a separate context-menu destination. Invalid or unavailable published
definitions produce an explicit error rather than silently reverting to another
layout. Persistent definitions are in scope; persistent monitoring history is not.

Generated dashboards retain all selected observations across compositions of at
most twelve panels, matching the consumed DDN runtime limit. A read-only page
selector exposes additional compositions without layout editing. Publications
retain their selected view and layout state; optional page navigation does not
modify the stored definition. Native object bindings remain stable across pages.

Monitoring admission recognizes both preserved legacy PostgreSQL registrations
and registrations using the installed native PostgreSQL provider/profile revision.
The endpoint must still belong to the active user. Other PostgreSQL-wire engines
and unqualified provider/profile revisions are not admitted through this source.
The registered endpoint's generation and configuration continue to fence grants;
using the provider-managed registration path does not bypass native version,
connection, credential or database-identity checks.

Delegated database selection
============================

A delegated worker selecting a native database OID must resolve that OID through
an independently owned, authenticated catalog attachment. Its registered initial
database is used only for this resolution; it must never become the execution
target when resolution fails. Release the catalog attachment before opening the
selected database, then verify its actual OID before accepting user statements.
A rename/drop/recreation between resolution and attachment must fail closed.
Each worker session owns its attachment and transaction independently, even when
several sessions select different databases of the same registered server.

Per-editor result buffering
===========================

The native PostgreSQL Query Tool provides an integer rows-per-fetch control for
1–100,000 rows. Changes are acknowledged by the session-owning backend and apply
to the next result page; they do not alter another editor or the user's saved
preference. Existing explicit range selection remains an explicit separate fetch
request. Changing a fetch setting does not commit, rollback, re-execute SQL or
restart an active result. A running statement cannot change this setting. Lost
acknowledgements use the same execution-policy uncertainty handling as autocommit.

Native catalog capture for DDN
=============================

PostgreSQL catalog discovery uses a separately owned attachment and one bounded
repeatable-read, read-only transaction. It verifies the selected database OID
inside that transaction and completes it before returning a capture. Each catalog
group has an explicit coverage observation; permission failures are isolated with
savepoints and are not empty successful groups. Object addresses retain catalog,
native OID and subobject identity. Native definitions, exact types, owner/ACL,
comments and dependency addresses remain engine-specific facts in DDN records.

Capture is documentary: imported SQL text is never executable authority. A hidden
view or absent record cannot request deletion. Credential-bearing catalogs/options
are omitted or redacted explicitly, including role password hashes, subscription
connection strings and foreign-server/user-mapping options. Row data and large
object contents require separate explicit export. Bounds fail the entire capture
instead of reporting truncated metadata as complete. Database captures are not
server-wide atomic snapshots. The adapter reports its catalog coverage and
exclusions; capture alone does not qualify native generation, diff or application.

Database capture includes casts, transforms, access methods, default privileges,
database-local subscription metadata and user-mapping identities. Subscription
connection strings and user-mapping options are never selected from the server;
select only their noncredential columns, allowing PostgreSQL's column privileges
to remain effective. Capture security labels by native object/subobject address
for the selected objects. Publication row filters retain deparsed native SQL.
Subscription relation states remain child facts and do not certify replication
freshness. Server-shared roles/tablespaces/settings and replication slots/origins
remain separately scoped export work.

Native catalog/addressing references:
https://www.postgresql.org/docs/18/catalogs.html and
https://www.postgresql.org/docs/18/functions-info.html.

Native workspace admission includes both legacy PostgreSQL registrations and the
exact installed native provider/profile revision. These use the connected native
manager's runtime verification and database OID, not a second unrelated generic
provider verification state. Unqualified revisions and other PostgreSQL-wire
engines are not promoted to native PostgreSQL. Database/route catalogs use the
same classification as SQL, DDN and monitoring admission.

Relational DDN projection
========================

PostgreSQL relational views use DDN's graph renderer. Table/view identity includes
endpoint, database OID and native catalog address; equal names in different
schemas or catalogs remain different objects. Column identity uses relation OID
and attribute number. Display exact native formatted types, arrays, column
comments and observed nullability without inventing fixed array bounds. Keep
partitioned tables, foreign tables and materialized views labelled as their
native kinds even when projected through DDN's table/view shapes.

Foreign-key edges retain the ordered source/reference attribute tuples and native
constraint identity. A referenced table outside the selection is reported as
outside scope, never replaced by a same-named table. Pagination retains complete
source and stable identities. Graph labels and layout are presentation; only a
separate admitted native review can generate or execute metadata changes.

Non-executing SQL grammar and script framing
===========================================

PostgreSQL source tools use the pinned pglast/libpg_query PostgreSQL 18 parser.
Report the embedded parser's exact revision separately from the connected server
revision. Grammar acceptance is offline syntax evidence, not server permission,
catalog resolution, execution success or validation of quoted procedural bodies.
The supported server remains 18.3; the embedded parser is 18.6. Their patch
versions are not interchangeable qualification claims. Older 8.1–8.4 wheels use
18.4, so downgrading does not establish an 18.3 parser. Retain the qualified 8.5
pin and its constraint-printer fixes; upstream release history is
https://pglast.readthedocs.io/en/v8/changes.html . Reject NUL and oversized
sources, bound statement count, and retain Unicode character offsets.

Read the selected session's actual standard_conforming_strings setting without
executing SQL. Only the parser's standard-string mode is admitted. Use native
statement boundaries for SQL BEGIN ATOMIC bodies and dollar quotes. Refuse
embedded COPY streams and scripts that change parsing settings. Recheck the
session setting before each retained statement, stopping before submission when
it no longer matches. Parsing never creates a savepoint, runs EXPLAIN, commits,
rolls back or reconnects a lost attachment. Missing/incompatible parser packages
produce an unavailable validation result, not lexical success masquerading as
grammar acceptance. Other PostgreSQL-wire engines retain their own adapters.

Parser API reference: https://pglast.readthedocs.io/en/v8/parser.html.
The new runtime dependency must be included by DEB/RPM packagers through the
root requirements file; this record is not a claim that packagers were notified
or that their packages have been qualified.
The parser is available under the current Python 3.14-or-later product minimum.
The earlier Python 3.9 fallback is no longer a supported runtime path.
The dependency's GPL-3.0-or-later license and bundled PostgreSQL/libpg_query
notices must accompany redistribution; the application's existing license text
does not replace dependency notices.

Retained monitoring observations
===============================

Server and database viewers provide read-only retained-window projections of
their authorized in-process samples. Select a native database OID and metric;
never combine same-named databases or turn a hidden/missing group into zero.
Keep exact numeric strings beside approximate DDN point charts. Failure,
incomplete transactions, missing identity/time, reset baselines and values outside
the chart's numeric range remain explicit gaps. Do not interpolate across samples
or reconnect/reset epochs. Label the collection state, age and eviction count;
past points never certify present availability. Fleet views navigate to each
owned source rather than sum independent clocks or unrelated databases.
Counter normalization accepts exact nonnegative bigint values or canonical bigint
text returned by the host's global driver loaders. Floats, booleans, malformed
text, missing values and out-of-range counters break the rate baseline; converting
through floating point is prohibited.

Provider-native administration transactions
===========================================

Structured PostgreSQL administration actions use their own attachment and native
transaction, including read-only inspection. Recompile the retained structured
plan and verify its statement before dispatch. Verify the selected database OID
inside the owned transaction. Never execute administrative DDL on the Explorer's
attachment or commit a query editor's pending changes. Report commit observation
separately from connection cleanup. A lost commit reply remains unknown, with no
automatic resubmission; cleanup failure does not erase an observed commit.

PostgreSQL DDN semantic planning
===============================

Planning receives separate baseline and desired DDN documents and captures a
fresh live catalog on an independent connection. All three bind the same engine,
endpoint and database OID. Object omission is never deletion intent. Preserve
unmodified live fields; report conflicting edits, missing native objects and
unsupported changes as blockers rather than returning a deployable partial plan.
Use live native object identity, never an imported SQL identity, for generated
commands. Labels and layout remain presentation only.

The planner admits native object-comment edits and the qualified relation/column
renames, column nullability/default changes and explicit creation drafts
described below. Planning uses the full authorized live database catalog even
when the displayed document is a selected branch. PostgreSQL supplies the
quoted identity including routine signatures and index access methods. Desired
comments are quoted literal data and may explicitly be SQL NULL. Other metadata
changes remain visible blockers until their native generation adapters are
qualified. A preview is not an application receipt: durable review, apply and
post-commit rediscovery are separate obligations and remain required.

Shared registration navigation
------------------------------

Shared-server presentation must retain its engine identity and verification
metadata when constructing a detached per-user view. Per-user credentials and
connection settings remain isolated from the owner's persisted registration;
listing shared servers must not require lazy-loading a detached relationship.

Database-level advanced objects
-------------------------------

Access methods expose create, inspect and drop, with an explicit INDEX or TABLE
method type and a catalog-qualified handler. They have database scope and no
schema or ALTER operation. Transforms expose create (including explicit replace),
inspect and drop, identified by the exact data type and language, not a synthetic
object name. FROM SQL and TO SQL functions retain their argument signatures; at
least one direction is required. PostgreSQL validates handler signatures,
privileges and language/type support. These actions use the same independently
owned, reviewed native administration transaction as other advanced objects.
Drop requires exact identity confirmation and explicit dependency-cascade choice.
Reference: PostgreSQL 18 CREATE ACCESS METHOD and CREATE TRANSFORM grammar.

Operator-family alteration also supports explicit member addition and removal.
Added members preserve operator operand types and function signatures. Removed
members are selected by member kind, strategy/support number and operand type
pair, never by display name alone. Rename, owner and schema changes remain
separate actions. PostgreSQL validates dependencies and index-method semantics.

Service monitoring preserves effective native TCP keepalive settings (including
the host driver's keepalive defaults), certificate mode and selected host address
when freezing the route. These settings must not turn a valid current connection
into an unavailable monitoring policy. The collector still owns an independent
attachment, transaction cadence and policy heartbeat.

Database-scoped provider resource pages
--------------------------------------

A provider workspace bound to an explicit PostgreSQL database returns that
database's native catalog objects, rather than repeating the server's database
list. Capture uses its own completed read transaction and verifies the database
OID. Cached resource identities retain their catalog/OID and native parentage.
Inspection resolves the same catalog identity in a fresh authorized capture;
disappeared objects cannot fall back to another database or an object name.
The inherited Explorer remains responsible for its existing richer native forms.

The connected database context menu opens PostgreSQL advanced-object forms.
Access-method, transform, conversion, operator, aggregate, operator-class and operator-family forms
reuse their native navigation form references across actions. SQL source
diagnostics uses SR-F-001383. Actions display only their applicable fields;
operator-family member changes do not request an unrelated new owner/name.

Advanced-object type fields accept native multiword type spellings as well as
qualified/quoted catalog names. Multiword syntax is parsed as one isolated native
TypeName and rendered from that node; expressions, additional SELECT clauses and
additional statements are refused. Native type resolution remains server-owned.

DDN explicit object creation previews
------------------------------------

A desired catalog may add a user object using a new ``postgresql:new:<UUID>``
resource identity and a ``native.create`` object. Its ``kind``, exact name and
schema must match the row. Creation is explicit; a missing live row, copied OID,
view omission or imported SQL definition is never implicit creation/deletion.
The initial creation adapters cover schemas, enum types, sequences and ordinary
permanent/unlogged tables with typed columns, nullability and primary/unique
keys. Unsupported fields are blockers, not silently discarded options.

Index drafts use the containing relation's schema, an exact ``table`` name,
ordered ``keys`` (each has either ``column`` or ``expression``), optional
``method``, boolean ``unique``, ``include`` columns, boolean ``nulls_distinct``,
``predicate`` and ``tablespace``. Keys may specify ``order`` (ASC/DESC),
``nulls`` (FIRST/LAST), and schema/name objects for ``collation`` and
``opclass``. Expressions use the native AST renderer. An index on a newly
created table or materialized view requires its explicit resource dependency.
Indexes share PostgreSQL's relation namespace and cannot specify a different
schema from their relation. Native PostgreSQL validates method capabilities,
expression immutability and column/type compatibility before commit.
Index ``storage_parameters`` and key ``opclass_parameters`` accept nonempty
maps of at most 64 exact parameter names to booleans, integers or bounded text
values (4096 UTF-8 bytes). Operator-class parameters require an explicit qualified
operator class. Identifiers and values are quoted independently; PostgreSQL
validates method-specific names, ranges and compatibility in the owned application
transaction. Render parameter maps in canonical name order so durable review
serialization cannot change the approved execution digest. Unknown or invalid
native parameters fail the complete batch rather
than being dropped. Native rediscovery retains the resulting index definition and
options. Concurrent builds remain blocked in this transactional DDN adapter;
they require an independently owned nontransactional operation. Application
retains the same creation-batch admission in new or OID-bound existing user
schemas and native identity rediscovery.

Type drafts may use ``type_kind`` ENUM (the default), COMPOSITE or RANGE.
ENUM carries ``labels``. COMPOSITE carries ordered ``attributes`` with exact
``name``, ``data_type`` and optional schema/name ``collation``; composite types
occupy both relation and type namespaces. RANGE carries ``subtype`` and optional
schema/name ``subtype_opclass``, ``collation`` and ``subtype_diff`` references.
PostgreSQL generates the associated array/multirange identities. Dependencies
on other new types must be declared. Base/shell types, canonical functions
requiring shell construction and custom multirange naming require separate
adapters and are rejected, not approximated. Native definition and use must be
qualified together with the same durable application/rediscovery path.

The create object contains ``depends_on`` (exact desired/live resource IDs),
``name`` and, except for schemas, ``schema``. Table ``columns`` contain ``name``,
``data_type`` and optional boolean ``nullable``; table ``keys`` contain ``kind``
(``PRIMARY KEY`` or ``UNIQUE``), ``name`` and ordered ``columns``. Enum
``labels`` preserve case, whitespace and order. Sequence numeric properties
remain exact signed integers, with PostgreSQL validating type-specific bounds.
The planner orders new schemas before contained objects and honors explicit
creation dependencies. Unknown dependencies, cycles and existing native name
collisions block the plan. Preview itself does not write; only the narrowly
admitted plans described under reviewed native application can be prepared and
applied. A raw SQL fixture alone is not proof of production application support.

Column comment previews retain the relation OID and positive native attribute
number. Explicit comments, boolean ``attnotnull``, qualified ``attname`` and
``default_expression`` edits on existing ordinary table columns are admitted. Removing/reordering identity fields or other column
metadata edits require their owning adapter. Nullability changes use ALTER TABLE
ONLY under the relation lock, retain the exact attribute number/name, reject
inherited columns and compare baseline/desired/live values before dispatch.
PostgreSQL validates existing rows, identity and key constraints; failed validation
rolls back the whole reviewed batch. Converged nullability is not reapplied. Preserve
unmodified live column properties and block independent comment conflicts,
renames and disappeared columns. Generated COLUMN identities use the fresh
relation identity and quoted native attribute name.

Table creation drafts also admit one of ``default`` (native expression),
``generated`` (expression and STORED/VIRTUAL storage), or ``identity``
(ALWAYS/BY DEFAULT) per column. Expressions must parse as a single expression;
SQL statement or SELECT-clause injection is rejected. PostgreSQL owns semantic
and volatility validation. Identity columns cannot explicitly request nullable.
Named CHECK keys carry an expression; FOREIGN KEY keys carry ordered local and
referenced columns, referenced schema/table, optional MATCH SIMPLE/FULL and
ON UPDATE/DELETE actions. Key deferrability is explicit and defaults to immediate
nondeferrable. Duplicate names, mismatched column counts and incompatible options
block generation. References to other new tables must declare their draft IDs
in depends_on; cyclic creation dependencies remain blocked pending a separate
post-creation constraint phase. No unsupported option is silently dropped.

Domain creation drafts retain the exact base type, optional default expression,
boolean nullability and named CHECK expressions. View and materialized-view
drafts contain an explicit single SELECT query and optional ordered output
column names. Ordinary views additionally support explicit security_barrier,
security_invoker and LOCAL/CASCADED check options. Materialized views support
explicit with_data (default false for design previews); view-only options are
rejected. Query text is parsed as one SELECT and rendered from its AST; multiple
statements and SELECT INTO are refused. Native PostgreSQL still owns name,
privilege, expression and materialization semantics. Relation/type namespace
collisions include the composite types created for views and materialized views.

Relational design handoff
-------------------------

The PostgreSQL relational viewer has a separate DDN edit action. Keeping that
draft sends the original and authored relational workspaces to the server,
which reads them with the paired public DDN parser and captures a fresh catalog.
Exact endpoint/database/resource UIDs must match. Native facts become separate
baseline and desired catalog documents for the same three-way preview pipeline;
layout, labels and hidden objects never imply metadata edits or deletion.
New unbound graphical identities require explicit native creation drafts instead
of guessed names or OIDs. Native facts are edited through the DDN document;
ordinary diagram labels are presentation only. PostgreSQL field ``nullable``
and ``description`` edits map to their exact native attribute identity. Missing
properties are presentation omissions, not deletion intent; an explicit empty
description clears a comment. Conflicting graphical/native edits and unbound
field identities are rejected. Datatype edits map to ``formatted_type`` and the
native type migration admission described below. Handoff itself executes no SQL.

Reviewed native application admission
------------------------------------

Relation application admits COMMENT edits on ordinary tables, partitioned
tables, views and their existing columns, plus the qualified ordinary-column
nullability/default/type changes and explicit relation/column renames described in
this contract. Each operation must retain
an exact native relation OID, schema and relation name. Other preview adapters
remain nonapplicable until their own concurrency contracts are qualified.

Preparing a review recaptures live metadata, matches the displayed execution
fingerprint and stores an expiring, owner/endpoint/database/route-bound receipt.
Application requires explicit confirmation of that receipt. A durable uncertain
state is written before native dispatch; duplicate delivery, reconnect or process
restart never redispatches a claimed receipt. Receipt storage is application
review evidence, not database transaction recovery authority.

Execution opens an independent native attachment and read/write transaction,
locks every target relation in deterministic identity order with a bounded lock
wait, then recaptures and replans within that same transaction. An identity,
comment or guard change aborts before any mutation. Native commit acknowledgement
and rollback acknowledgement are distinct. Losing the COMMIT reply preserves
unknown outcome even if cleanup succeeds. Fresh post-commit rediscovery reports
whether reviewed properties are visible, without erasing an observed commit if
rediscovery fails. The user editor's transaction is never borrowed or committed.

The creation admission also permits supported creation drafts alongside
admitted relation alterations. Creation drafts may target new schemas or exactly captured existing user schemas. Every declared
dependency must belong to that creation plan or be an explicitly guarded existing
partition parent. Cyclic graphs remain invalid. Existing
schemas require an OID and native-metadata fingerprint in every contained
creation operation. Fresh preflight must match both. Before commit, each created
object must reference that exact namespace OID; a same-name replacement schema
is never an acceptable destination. The fresh
preflight must still find each requested name available in its native namespace;
native CREATE uniqueness,
permissions and transactional DDL provide the final arbitration if another
session wins the name after preflight. A failed batch rolls back as a unit.
References in authored expressions are explicit PostgreSQL name resolution,
not a promise that an external routine/type was pinned by an omitted dependency.
Capture the created native OIDs and metadata fingerprints within the owned
transaction before commit. Rediscovery checks those exact native identities and
properties after commit; same-name replacement is never accepted as success.
Lost commit replies retain uncertainty and the receipt is never replayed.

Rollback of these batches refers to their transactional native DDL. Authored
expressions retain PostgreSQL's native semantics, including nontransactional
sequence advances or external effects of invoked functions; the adapter does not
promise rollback of those external effects. Created OIDs recorded before commit
are observations of the owned transaction, not proof of commit when its reply is
lost.

Server metadata bundles
-----------------------

A server metadata inventory uses a separate, regularly completed read-only
transaction and records native database OIDs, connectability, roles, role
memberships, tablespaces, replication slots/origins and database/role-setting
identities. Password hashes and setting/foreign-connection credentials never
enter the export. Redacted properties and unavailable sections are explicit.
Database captures are selected by native OID, resolved afresh through the owning
registration, and attached independently without relying on an explorer cache.
A capture bundle contains individually bound DDN workspaces and per-database
failures. It is not a cross-database consistent backup or an atomic server-wide
migration. Each database's review and native transaction remain separate.
The inventory is bounded at 1,000 databases and a capture batch at 32 explicitly
selected database OIDs; larger selections must be split rather than silently
truncated. No database is substituted when the selected OID is unavailable.

Each selected attachment must match the inventory's observed server address,
port, postmaster-start epoch and native version. A restart or retargeted service
is reported as unavailable instead of combining that attachment with the old
server inventory. This is an operational instance check, not a cryptographic
server identity or a guarantee of one cross-database transaction snapshot.

Owned catalog and application transactions set standard_conforming_strings=on
locally so parsed drafts and deparsed native definitions share one literal
interpretation. This does not change a user's query connection or persisted
server configuration. A native ROLLBACK command acknowledgement in response to
commit is recorded as observed rollback, not as uncertain commit.

PostgreSQL test-data recipe generation
-------------------------------------

Recipes use ``scratchrobin.postgresql.test-data@1``, an explicit endpoint/database
``scope``, a uint32 seed and up to
32 tables identified by exact native resource IDs. Each table supplies a row
count and a mapping of native column names to constant, default, sequential,
random-integer, choice/file or generated-parent sources. The total is bounded
at 5000 rows, recipe input at 4 MiB and generated SQL at 1 MiB (the shared SQL
file tool's bound). Ordinary rows are grouped into multi-row INSERTs per table;
default-only rows use per-table INSERT CTEs, keeping scripts within the shared
editor's statement limit. Values preserve exact text and
explicit integer/decimal/binary envelopes; approximate JSON numbers are rejected.
Generation uses current native column metadata and rejects generated columns,
always-generated identities, duplicate tables and unknown columns. Referenced
new parent values must be generated explicitly; cycles are blockers. A saved
recipe is portable only when its native identities are reconciled explicitly.

Generation produces a reviewable SQL script, not an executed transaction. Scripts
contain no implicit transaction controls: the existing shared Query Tool owns
execution, autocommit, commit, rollback and uncertain outcomes. Recipe and SQL
files may contain data and are saved only at the user's request. Source choices
and copied file values never become SQL expressions. A ``returned`` source names
an exact selected parent table/column and uses its native INSERT RETURNING value,
including identity/default/generated values. Such recipes compile into one
data-modifying WITH statement with one INSERT per requested row; dependency
subqueries consume the specific parent row's returned value. Parent rows cycle
in recipe order when counts differ. Only referenced columns are returned; other
inserts return a constant. A parent suppressed by a trigger returns no value and
therefore supplies SQL NULL, subject to the child's native constraints. Native
RLS, privileges, triggers and nontransactional sequence advances still apply.
The result reports actual inserted rows, which can differ from requested rows
when triggers suppress inserts. Cycles remain rejected.

An ``existing`` source names a captured user table/column and a nonempty
``order_by`` list of exact column names. A shared materialized sample per table
reads at most 200 rows in the execution statement's snapshot, under the executing
user's SELECT privileges and RLS. All references to that table must agree on
ordering; columns from the same sampled row stay aligned for composite keys.
Rows cycle by requested row position. Empty samples supply NULL, not invented
values; native constraints decide whether that is acceptable. Order ties are
not deterministic, and samples can change between executions. Use a unique
ordering key when repeatable row choice is required. Sampling occurs only when
the user executes the generated script, never during preview. These recipes also
use the single data-modifying WITH path and do not observe rows inserted by that
same statement as existing data. Unsupported source kinds are rejected explicitly.

Shared editor autocommit contract
---------------------------------

The PostgreSQL shared editor exposes an acknowledged autocommit checkbox.
``autocommit_on`` and ``autocommit_off`` set the native connection policy; they
do not issue COMMIT or ROLLBACK. A policy change requires an idle native
transaction, no executing statement and a known connection. Pending and failed
transactions must first be explicitly committed or rolled back. Reaffirming an
already observed policy does not alter transaction state. Unknown policy must
be refreshed before further execution; commit/rollback controls are disabled
when autocommit is enabled or its state is unknown. A new connection starts
with the native driver default, observed before its first execution.

Native DDN column renames
-------------------------

An explicit ``attname`` edit on an existing ordinary table column retains its
relation OID and attribute number. Rename applies only to non-inherited columns
on tables without descendants; partitions and recursive changes require their
own adapter. Missing fields never imply a rename or deletion. The native name
must fit PostgreSQL's 63-byte identifier limit without truncation. The reviewed
plan locks the table, rechecks its current identity and refuses independent name
changes or destination-name collisions. A converged rename is not replayed.
When combined with comment, default or nullability edits, subsequent statements use the
new name within the same transaction. Native dependencies remain PostgreSQL's
responsibility, and a failed statement rolls back the complete reviewed batch.

DDN routine creation drafts
---------------------------

New function/procedure/window-function/aggregate drafts carry one complete
PostgreSQL ``definition`` and
explicit schema/name/dependencies. The parser must identify exactly one CREATE
FUNCTION, CREATE PROCEDURE or modern CREATE AGGREGATE of the declared kind
and exact qualified name;
OR REPLACE is not creation intent. Native bodies, language, argument modes,
defaults and routine attributes are preserved in the reviewed SQL. PostgreSQL
validates language, privilege and dependency semantics during application.
Overloads in a new-schema batch are distinguished by their input signatures;
OUT-only parameters are excluded from signatures; aggregate input/direct
arguments retain native signature order. Window declarations must match the
window-function kind. Legacy BASETYPE aggregate syntax is not admitted.
Post-creation discovery resolves those signatures to native pg_proc OIDs on the
executing connection. Existing same-name routines require a separate change
adapter rather than implicit replacement. No routine body is invoked to qualify
creation; any later invocation is a separately authorized execution.

Aggregate child capture converts regproc ownership columns explicitly to OIDs;
routine display names never substitute for native parent identities.

Concurrent shared-editor requests reuse one pending session-opening promise,
including initial native-policy observation. A second request cannot bypass
that observation or create an orphan attachment. Closing or changing language
accounts for the pending opener before releasing the owned session.

Shared PostgreSQL completion uses the preserved native completion provider on
the editor's owned session. Requests carry the full source and exact prefix to
the cursor, bounded to 1 MiB, and never dispatch source for execution. Completion
does not commit or roll back user work. Active execution/uncertain-session guards
still apply; obsolete replies cannot replace suggestions after a source, cursor,
connection or language change. Browser suggestion lists are bounded to 1,000
items without claiming that every visible catalog object was loaded.

Completion template selection uses the owned connection manager, including
delegated/provider registrations; it must not resolve a different legacy manager
by numeric server ID or borrow its version or credentials.

Routine completion accepts both driver-decoded arrays and native PostgreSQL
array text, preserving quoted argument names/types containing commas. Routine
defaults remain expression text and are split with the PostgreSQL parser, so
commas inside literals, arrays and function calls do not create extra arguments.

Completion quotes both explicit schema names and search-path entries as native
SQL literals, including apostrophes and backslashes, without changing session
string-literal settings or resolving transaction outcomes.

The shared PostgreSQL editor supports reviewed selection, current-statement and
from-cursor preparation. Statement boundaries come from the pinned native SQL
parser on the owned session; dollar-quoted bodies and literal semicolons are
not split by client heuristics. Editor UTF-16 positions are translated to parser
character offsets. Empty selections and invalid source are refused. Preparation
never executes SQL. One statement uses the ordinary parameterized Run path;
multiple statements first create a retained script preview and require the
separate Run/resume action. Changes to source or connection invalidate pending
preparation replies. Transaction statements are preserved, never injected.

Buffered query results can be exported as a portable DDN workspace through the
same owner/endpoint-authorized, policy-redacted result export path. This is an
explicit static selection of already retrieved rows, never an implicit query,
whole-table dump, provider continuation fetch or database backup. Provenance
records result/execution identities, exact column metadata, stored/exported row
counts, sampling, export-policy limits and whether provider continuation remains.
Each positional row retains its exact provider JSON values in a documented
``x_record.values_json`` property; display cells are JSON literals so NULL and
the string "null" remain distinct. Duplicate column names retain separate
ordinal fields. Large integer, decimal, temporal and binary envelopes are not
coerced through JavaScript numbers. At most 100 rows are shown per view, within
the paired DDN runtime's 128-element live-view limit, with
64 workspace files, 2,000,000 UTF-16 units per file and 8 MiB total; exceeding a
bound refuses the export rather than returning an unmarked partial document.
The provider admits this application export format independently of native SQL
features. It does not complete full-table snapshot/archive or DDN data import.

Reviewed relation renames
------------------------

DDN native metadata may explicitly change ``catalog_row.relname`` for an
ordinary, non-inherited table or view. The catalog/OID identity and schema stay
fixed; desired display name/path may follow the new name, but changing a label
alone never renames SQL. Rename plans cannot combine additional edits on that
same object in one draft. Existing independent live metadata is preserved;
independent renames, occupied destinations, system objects, inherited/partitioned
tables, missing identities and overlength names block admission. PostgreSQL
ACCESS EXCLUSIVE locking, fresh preflight, durable outcome receipts and native
rediscovery apply. Dependencies continue to reference the original object OID.
A converged rename is observed without redispatch. Native failure rolls back
the entire reviewed batch; a lost commit reply remains an unknown outcome.

DDN creation drafts also admit fully qualified native definitions for collations,
conversions and text-search configurations, dictionaries, parsers and templates.
The single parsed CREATE statement must match the declared kind, schema and
name; replacement, IF NOT EXISTS and extra statements are refused. Complete
native options and callback signatures remain in the definition rather than
being flattened into generic fields. Native namespace collisions, declared
creation dependencies, schema-OID guards, reviewed application and rediscovered
catalog identities use the existing creation contract. Native permissions and
callback/type compatibility are checked by PostgreSQL; drafting is not execution.

Native column defaults
----------------------

Column capture includes ``default_expression`` from PostgreSQL's deparser,
including explicit null when no default exists. A reviewed DDN edit can set one
native expression or explicitly drop the default on an ordinary table column.
Generated/identity/inherited columns and tables with inheritance descendants are
not admitted by this adapter. Omitting the property never means DROP DEFAULT.
Expressions are parsed as one expression, then rendered into ALTER COLUMN; they
cannot append statements. Defaults affect subsequent inserts, not existing rows.
Concurrent default edits require renewed review unless already converged.
The existing locked preflight, whole-batch rollback and durable outcome rules
apply, including combinations with admitted column renames/nullability/comments.
PostgreSQL may canonicalize expressions; rediscovery records whether the observed
deparsed text matches the reviewed expression. A confirmed commit remains a
confirmed commit when textual canonicalization prevents a match; it is never
silently replayed or described as rolled back.

Retained scripts have no parameter-binding contract. The shared editor and host
refuse nonempty bindings (or malformed binding values) before preparing a script;
only an empty object/array is admitted. A prepared script cannot be run while
nonempty bindings are displayed. Parameter controls are disabled during active
execution. Single-statement preparation retains the usual native binding path.

Declarative partition creation
-----------------------------

DDN admits a complete native CREATE TABLE definition for a partitioned table or
partition, including RANGE/LIST/HASH bounds, DEFAULT partitions and subpartition
keys. The parser must identify one permanent CREATE TABLE with the exact schema
and name; the declared kind distinguishes a partitioned parent/subparent from an
ordinary leaf. IF NOT EXISTS, temporary/unlogged persistence and legacy INHERITS
are refused by this adapter. A partition must name its parent with an explicit
schema and declare its exact parent dependency. A new parent is created earlier
in the same batch. An existing parent requires a captured native OID and metadata
fingerprint, an ACCESS EXCLUSIVE lock before fresh preflight, and verification of
the created child's inheritance link to that exact OID before commit. Concurrent
parent rename/replacement or metadata change invalidates review. Existing DEFAULT
partition data/bounds remain subject to native validation; failure rolls back
the new partition. ATTACH/DETACH of existing tables is a separate migration. PostgreSQL owns partition-key/bound/constraint validation,
routing and row-type semantics; generated statements are never split or
reconstructed from generic partition fields. Native OID rediscovery, atomic
batch rollback, schema guards and unknown-commit handling remain mandatory.


Completion search-path updates preserve raw native names; SQL-identifier quoting
is applied only to displayed candidates, and schema predicates use native SQL
literal encoding. Embedded apostrophes, backslashes and double quotes must not
change the schema selected by completion or execute additional SQL.


Native column type migration
----------------------------

An explicit change to a captured column's ``formatted_type`` (including the
DDN graphical ``datatype`` property) requests ALTER COLUMN TYPE. The adapter
preserves relation OID/attribute number and takes the existing relation lock.
Only ordinary, non-inherited, non-generated, non-identity table columns without
partition descendants are admitted. PostgreSQL validates assignment casts,
constraints, defaults, privileges and dependent objects. No USING expression or
CASCADE is inferred; failed conversions roll back the whole reviewed batch.
The type reference is parsed as a native type, never interpolated as arbitrary
SQL. Concurrent changes to the original native type identity or modifiers
invalidate review. Alias normalization may require fresh rediscovery/review;
confirmed commits are never replayed merely because rendered type text differs.


Mixed native migration batches
------------------------------

Supported creations and admitted existing-relation alterations may share one
reviewed transaction. All existing targets are locked before fresh preflight;
creations run in their explicit dependency order, followed by the reviewed
alterations. The preview exposes that exact order. There is no inferred
cross-operation reordering to satisfy authored expressions or names. Every
operation must independently satisfy its creation or alteration admission.
Created identities are captured after all statements, before commit. Post-commit
rediscovery checks both created OIDs/fingerprints and altered properties; it
never reports success after checking only one side of a mixed batch. A native
failure rolls back transactional DDL on both sides, subject to the documented
native limits on sequence advances and external function effects.


Native transform qualification
------------------------------

Transform form qualification must use compatible native conversion functions and
actually invoke the transform in its procedural language. A CREATE/DROP using
unrelated internal functions is not evidence of conversion support. The optional
Linux qualification fixture uses PostgreSQL 18.3-matched PL/Python and its shipped
jsonb conversion callbacks, creates an owned schema, verifies both conversion
directions with nested JSON/null/Unicode values, and exercises provider
create/inspect/drop independently of Explorer transactions. It refuses to replace
an existing jsonb/plpython3u transform. Optional language packages are fixture
prerequisites, not mandatory dependencies for ordinary PostgreSQL connections.


Existing routine overloads
-------------------------

An existing routine name does not occupy every signature in PostgreSQL's routine
namespace. Creation previews may add an overload beside captured functions,
procedures or aggregates of the same name. Native CREATE, without OR REPLACE or
IF NOT EXISTS, arbitrates exact resolved input-signature collisions, including
type aliases. A duplicate signature fails and rolls back its transaction; it
must never modify the existing routine. Rediscovery resolves each newly created
signature to its exact native OID. The preview still rejects repeated identical
draft signatures within a batch.


Explicit relation deletion intent
---------------------------------

Removing an object from a DDN view or desired catalog is never deletion intent.
For a captured ordinary table or view, ``native.drop: true`` explicitly requests
DROP RESTRICT while preserving all other baseline native facts. It is reviewed
and confirmed through the same owner-bound receipt as other mutations. Changes
to the relation since that baseline require a fresh review. System relations,
inheritance and partitions are excluded from this admission. The exact original
OID is locked and revalidated before dispatch; if it is already absent, the
operation is converged and a same-named replacement is never dropped. Native
dependent-object failures roll back the batch. No CASCADE or dependency deletion
is inferred; the preview states the actual statement order. After commit,
rediscovery verifies absence of the original OID, not merely absence of its name.


Table-owned definition creation
--------------------------------

Trigger, rewrite-rule and row-security-policy DDN creation drafts contain their
complete native definition, exact name/schema/table and an explicit dependency
on the captured or newly created ordinary table. One correctly typed CREATE
statement is required; replacement is not admitted. Existing tables require an
OID/fingerprint guard and the same bounded exclusive lock used for mutations.
Names are unique per native table, not across the schema. Before commit,
rediscovery binds the new catalog object's ownership column to the exact table
OID and that table's reviewed namespace. Native trigger timing/events/function
arguments, rule actions, policy roles/command/permissiveness and expressions
remain intact. PostgreSQL validates dependencies and permissions. Creating a
policy does not implicitly enable row-level security. Table inheritance,
partition propagation and existing-object replacement require separate adapters.

Captured user triggers, rewrite rules and row-security policies also admit
explicit ``native.drop: true`` and comment changes on ordinary owning tables.
Deletion retains all other baseline facts and emits DROP ... ON ... RESTRICT;
it never infers deletion from a filtered view. Resolve ownership by the native
table OID and lock that exact table before revalidating the child identity and
review fingerprint. Persisted reviews retain both the changed child and owning
table metadata so receipt reload cannot discard that authority. Same-named
objects on other tables are independent. System
objects, constraint-owned triggers, view return rules, inherited and partitioned
owners are excluded. A missing original child OID is converged, even if a new
child now uses its name; the replacement must survive. Native permission and
dependency failures roll back the batch. Dropping a policy leaves the table's
row-security enablement unchanged. Rediscovery verifies the original child OID
is absent after a confirmed commit.

An explicit change to the native ``tgname``, ``rulename`` or ``polname`` field
requests a rename on the same ordinary owning table. Emit the corresponding
ALTER ... ON ... RENAME TO statement under that table's lock, preserving the
child OID and all definitions, expressions, roles and timing. Other changes in
the desired native object are reviewed separately. Bind the owner by OID, check
name collisions only within that table and reject independent renames. A prior
successful rename converges without replay; unrelated live properties are
preserved and enter the fresh review fingerprint.

DDN trigger and rule activation
-------------------------------

An explicit edit of a captured ordinary user table trigger's ``tgenabled`` or
rule's ``ev_enabled`` selects PostgreSQL's native ``O`` (origin/local), ``D``
(disabled), ``R`` (replica) or ``A`` (always) state. Generate a single named
``ALTER TABLE ONLY ... ENABLE [REPLICA|ALWAYS] TRIGGER|RULE`` or ``DISABLE``
statement. Never widen the operation to ALL/USER or inherited tables. Internal
and constraint-owned triggers, view return rules and partition/inheritance
targets remain outside this adapter.

Bind the original child OID, catalog, parent OID and exact names. Reject mixed
desired edits and concurrent changes to its other native facts; activating an
independently changed definition requires another review. A live activation
state different from both baseline and desired is a conflict; an already matching
state converges without replay. Apply through the existing durable review path,
locking and revalidating the captured parent before mutation, and rediscover
the resulting native state after acknowledged commit. Qualification must verify
ordinary and replica-session effects as well as catalog flags.

DDN table row-security switches
------------------------------

Explicit boolean changes to an ordinary user table's ``relrowsecurity`` and
``relforcerowsecurity`` produce named ``ALTER TABLE ONLY`` ENABLE/DISABLE and
FORCE/NO FORCE ROW LEVEL SECURITY statements. Preserve the same table OID, exact
name, schema and other native facts. Reject mixed desired edits, unreviewed live
table changes, missing/replaced identities, non-boolean values and inheritance
or partition targets. A flag already at its desired value converges without
replay; apply other requested flags atomically through the durable review and
parent-lock path. These switches do not create, remove or rewrite policies or
grants. Native policy and role behavior remains authoritative, including owner
bypass without FORCE and PostgreSQL's superuser/BYPASSRLS exceptions. Verify
ordinary-role and owner visibility, persisted flags and rediscovery after commit.


Explicit DDN column removal
---------------------------

A captured ordinary user-table attribute may request removal by adding only
``drop: true`` to that attribute in ``native.children.pg_attribute``. Removing
an attribute from the document, changing its ``attnum`` or omitting it from a
view never implies removal. Review displays ``ALTER TABLE ONLY ... DROP COLUMN
... RESTRICT`` and the exact parent OID/attribute number. The application holds
its parent table's native access-exclusive lock, rechecks the complete captured
attribute and executes within its independently owned review transaction.
Inherited/partitioned tables and inherited attributes require separate adapters.
Native RESTRICT dependency rules apply, including PostgreSQL's own removal of
local column-owned objects; dependent views cannot be silently cascaded away.
A changed or renamed attribute requires a new review. An already absent native
attribute converges only when no replacement uses its old name. Rediscovery
confirms removal, and failed dependencies roll back the entire application.


Explicit DDN column addition
---------------------------

An existing ordinary user table may carry a nonempty ``native.add_columns``
array (at most 1600 entries), each containing a fresh canonical
``postgresql:new:<UUID>`` ``resource_id`` and a ``definition`` using the same
name/type/nullability/default/generated/identity fields as table creation.
These are draft identities, never fabricated attribute numbers. Column order
is the array order. Addition must be reviewed separately from other edits to
that table; existing names, repeated draft IDs and inheritance/partition scope
are rejected. Baseline and current parent metadata must agree at review/apply.

Application locks the captured parent OID, revalidates the approved plan, runs
``ALTER TABLE ONLY ... ADD COLUMN`` in its owned transaction and captures each
new native ``attnum`` before commit. Native PostgreSQL validates types, defaults,
generation expressions and existing-row nullability. Failure rolls back all
additions. Receipts map draft IDs to parent-OID/attribute-number identities and
post-commit rediscovery verifies the captured attribute metadata. A column with
the same name is not evidence that this draft was previously applied. A consumed
receipt is never rerun; uncertain commit outcomes retain the existing no-replay
contract. Defaults and generated values must be checked against actual data.


Relational DDN new-field reconciliation
--------------------------------------

A new field under a captured PostgreSQL table may explicitly identify creation
with UID ``<captured-parent-uid>:new:<canonical-UUID>``. Its label supplies the
exact new column name, ``datatype`` the native type and optional ``nullable``
the native nullability. The handoff converts it to the parent's ``add_columns``
draft without assigning an OID or attribute number. The parent UID retains the
endpoint/database binding. Existing field labels remain presentation labels;
changing or removing their UID is not a rename/drop shortcut. New-field
properties outside this admitted set, including comments and array presentation
shapes, require native draft editing and are refused rather than ignored.
A graphical creation and an explicit native creation for the same draft must
agree exactly. Read-only handoff still requires normal live preview, durable
review and confirmation before any database operation.

Shared editor execution observations
-----------------------------------

The PostgreSQL shared editor reports client dispatch duration measured around
psycopg execute, including protocol transfer and native result buffering. It is
not server execution or preparation time; those remain unavailable when the
protocol supplies no separate measurement. Browser paging waits are excluded.
Observations belong to the current execution and survive its final empty poll.
Native SQL diagnostics include severity, SQLSTATE, primary message, detail, hint
and statement position, displayed as text in the owning editor. Non-server
exceptions must not expose connection credentials. Explain output appears only
for an explicitly requested plan, and is cleared by a subsequent ordinary run.
Ordinary execution never silently runs EXPLAIN ANALYZE to collect a plan.

PostgreSQL Explain actions use FORMAT JSON. Explain Analyze is explicitly
labelled as executing the statement; its changes follow the session's native
transaction/autocommit policy. Plan requests retain parameter bindings and must
parse to exactly one native ExplainStmt after psycopg client adaptation. Batch
plan requests are refused before dispatch. Parser/session-mode admission matches
the qualified source validator. No implicit rollback is added to Analyze.

The scoped dialect contract ``postgresql.shared-explain.18.3.v1`` admits only
these two Explain templates, not a complete PostgreSQL dialect inventory.
Evidence: PostgreSQL 18.3 ``doc/src/sgml/ref/explain.sgml`` SHA-256
``43bc7ee2b009e7d57455f56b5dd8a1e5ca27dec2c7cb6ba9dbb9e44382232a78``;
native estimated/analyzed parameterized JSON-plan and transactional INSERT
qualification is retained in ``shared-editor-native-plan.log`` in the owner's
temporary evidence area. The qualified parser remains pglast 8.5 / PostgreSQL
18.6 and does not imply a server revision change.
Retained temporary replication-slot resources
---------------------------------------------

The continuity workspace can open an independently owned SQL backend for
temporary physical and logical slots. Native create/copy, physical WAL
reservation, logical output-plugin/two-phase settings, advancement and removal
use that same backend. Paged inventory includes only its temporary slots;
permanent slots and temporary slots owned by another backend cannot be selected
for mutation through this resource. Plugin names are checked in the database's
encoding before PostgreSQL's name cast can silently truncate them.

Resource and command reviews have separate confirmation and receipts. A durable
owner-process channel supports requests admitted by other application workers.
Native dispatch/return, later slot observation, local connection close and
independent backend/slot cleanup remain separate facts. Duplicate requests do
not redispatch a completed or uncertain command. Closing a viewer or selecting
another database does not release the resource; explicit release or its reviewed
lifetime closes the backend. WAL may be retained until PostgreSQL removes slots.

Native SQL errors can remove every temporary slot on the resource's backend.
Cancellation observers stop before later SQL/cleanup observations. Existing
interactive query connections, pending SQL and savepoints stay separate. Native
checks cover temporary create/copy/advance/drop, UTF-8/LATIN1 name widths, lost
acknowledgement, native-error cleanup and asynchronous connection-close cleanup.
Cross-process requests and cancellation of waiting logical initialization are
qualified without settling a separate user transaction. Authenticated API and
browser checks verify native slot lifetime, inventory, confirmation/scope
refusals and later independent cleanup.

Temporary logical text/binary peek/get now runs on this same retained backend.
Ordered plugin options, exact WAL positions and native transaction thresholds
are reviewed before dispatch. Text and base64 binary records stream to private
JSONL artifacts; the native acknowledgement is saved before file publication.
A failed publication cannot undo consumption, and recovery inspects captured
bytes without replaying the command or promoting an uncertain command outcome.

Owned artifacts have bounded previews, streamed browser downloads, independent
checksum inspection and confirmed removal with retained receipts. Inspection
and removal serialize across application workers. Artifacts remain accessible
after resource release. Native text and binary output is compared against
independent permanent slots, including large integer identities, Unicode and
binary payloads; authenticated API and browser checks cover these controls.
Replication-protocol streams and the wider product matrix remain open. History
testing remains deferred and Windows/macOS qualification remains with the
platform teams.
