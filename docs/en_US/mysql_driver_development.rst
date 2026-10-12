MySQL driver development and platform handoff
============================================

ScratchRobin targets MySQL 9.7.0 with ``mysql-connector-python==26.7.0``.
The full engine acceptance contract is ``mysql_functional_completion.rst``;
driver and shared-editor receipts alone do not establish full engine completion.

Native catalog exchange
-----------------------

MySQL catalog capture uses an independently owned connection and an explicit
registered database target. It verifies ``DATABASE()`` and exact server version,
captures native ``SHOW CREATE`` definitions and visible information-schema child
facts, and exports documentary DDN under ``scratchrobin.mysql.catalog@1``.
Identifiers use escaped backticks; catalog predicates use bound parameters.
Capture is bounded to 20,000 facts and 8 MiB, with streamed catalog rows.
Permission-denied sections remain explicit observations; other query failures
abort capture. Definitions withheld by the server remain unavailable, never
empty authoritative definitions. Catalog visibility is privilege-filtered and
DDL is not an atomic snapshot, so capture never asserts full coverage or backup
equivalence. Row data and account secrets are excluded from this metadata path.
Imported documentary DDN may be compared, but comparison grants no execution.

SQL history
-----------

The shared editor exposes optional persistent history for MySQL, scoped to the
authenticated application owner, server, registered database and ``mysql-sql``.
Capture defaults off. Retention is limited by days and record count. Explicitly
sensitive requests, credential URIs and authentication statements omit source;
parameters and results are never stored. Loading an entry only changes editor
text. A history-store failure adds a notice without blocking or retrying native
execution, and recorded request acceptance is not transaction finality.

Provider shutdown releases result backpressure and permits the worker to finish
an in-flight cancellation-identity read before attempting a native kill. If the
worker has not dispatched SQL, shutdown prevents dispatch. Cancellation failure
does not authorize concurrent socket reuse or destruction while that worker
still owns the protocol. Shutdown checks every execution and retains any
unfinished ownership for a subsequent cleanup attempt; it never asserts rollback
or replays a statement to establish an outcome.

Dedicated monitoring source
---------------------------

The MySQL collector owns its connection, uses native autocommit for bounded
read-only probes and never borrows a query session. Each sample verifies the
server UUID, exact version and selected database. Global status remains labelled
server-wide even on a database dashboard. Database storage figures from
``information_schema.TABLES`` are estimates, not filesystem usage. Activity and
replication groups are privilege-filtered and limited to 100 rows. Denied groups
are unavailable; connection failures invalidate the whole sample and retire the
attachment. Reconnection establishes a new source epoch and never replays user
work. Only a completed sample supplies heartbeat evidence. This source alone
does not establish host credential configuration or dashboard qualification.

MySQL collector delegation uses the existing sealed worker grant and
single-process ownership lock. The authenticated owner selects registration or
dedicated credentials at admission. Workers retain encrypted, lease-bounded
credentials and recheck persisted owner activity, endpoint verification,
provider/profile generation, routes, targets and credential references before
collection and viewing. A registration change requires stop/reconfiguration;
worker authorization must not depend on an interactive Flask login session.
Stopping revokes the grant before releasing its attachment. Engine/server
inventory remains owner-scoped and reports configured collectors, not a complete
discovered fleet. Multiworker scheduling is not admitted by this contract.

The MySQL monitoring policy form uses compact credential and numeric controls.
Registration credentials are the default; dedicated credentials are submitted
only on start and the password is cleared after either success or failure.
Heartbeat timeout is optional and must exceed the sampling interval by at least
five seconds. Target changes discard credentials and outstanding responses.
Dashboard viewers use the DDN presentation surface without policy or editing
controls. Only a fresh, completed observation for the selected scope supplies
current metric values; failed, stale and mismatched samples remain unavailable.
An action failure remains visible when subsequent background polling succeeds.

Engine and server dashboard contracts
-------------------------------------

The engine dashboard enumerates only the authenticated owner's native MySQL
registrations and registered database targets. It reads existing collector
observations without opening connections or starting collection. Each endpoint
and database retains its own status; server-global counters are not summed
across database collectors or registration aliases. Registration identity does
not prove physical-instance identity, and no complete discovered fleet is
asserted. Server dashboards and collector policies are accessible from their
server context, independently of database policies.
The passive fleet response includes only the latest identity/availability
observation per scope, not detailed native row groups or authentication data.
The standard engine publication displays at most 128 scopes and reduces this
limit further to fit 512 KiB, reporting omitted scopes explicitly. All registered
scopes remain selectable for their separate dashboards. Page selectors come
from generated compositions rather than untrusted native labels.

Dashboard drafts and publications use the shared versioned project-asset store,
with engine/owner/endpoint/target identity in the asset key. Editing is a separate
authorized context action. Publication validates DDN and a finite MySQL metric
binding contract, strips sampled values, and uses expected publication versions.
Viewers reauthorize both definition and observations; unavailable bindings never
retain a previously sampled or draft-authored value. Native metric record keys
derive from source identity and field name rather than a row's current position.
Reordering or losing visibility to another row must not rebind a saved metric.

Retained trend views cover the bounded volatile window only. Counter rates use
exact decimal differences over positive monotonic sample intervals, within the
same collector epoch and server UUID. Missing/denied/failed probes, reconnects,
uptime decreases and counter resets break rate continuity. Database-scoped
collectors label global-status rates as server-wide. Chart conversion is
approximate; preserve exact values and explicit gaps beside the chart and
do not claim stale observations are current availability.
Settings and database storage observations follow the configured metadata
interval. Cached metadata retains its original observation time and reports its
age; status, activity, replication and heartbeat probes refresh each sample.
Connection failure discards the cache, and a new collector epoch refreshes it.
For a configured monitoring role, establish the dedicated transport without a
default database, activate the exact quoted role, then select the requested
database. This permits accounts whose database privileges derive from that
role without granting direct privileges or changing their default roles.
Native integer probe cells use exact decimal strings over JSON, including
connection identities and byte counts; browser numeric conversion must not
round a binding identity.

The backend team owns native driver correctness, backend operations and
functional forms. Windows and macOS teams own native UX refinement and platform
QA; driver defects discovered there return to this workstream. MariaDB has a
separate provider and is not substituted for MySQL.

Installation and driver selection
--------------------------------

Install the application requirements, regression requirements and
``tools/reference_engine_demos/requirements.txt`` into a platform-native Python
virtual environment. Python 3.12 is the current Linux qualification baseline.
Keep the pinned connector version. Do not copy a Linux environment or native
extension to Windows/macOS. The pure Python connector does not require a
separate ``libmysqlclient`` installation. Optional authentication mechanisms
retain their connector-specific dependencies and server configuration.

The MySQL connection form defaults ``use_pure`` to true. Disabling it explicitly
requires the connector's C extension for the Python version, architecture and
OS in use; an absent extension is an error. Routes saved without this field
retain Connector/Python's selection behavior. Qualify each implementation you
intend to deploy. The qualified Linux baseline currently uses pure Python;
C-extension and native Windows/macOS receipts must come from those environments.

TLS CA, client certificate/key, certificate verification, hostname verification,
TLS versions and cipher settings are native connector options. They refer to
files readable by the backend process, not the browser machine. Failed
verification is not retried with weaker settings. A control connection used for
query cancellation keeps the authentication and TLS requirements and verifies
the original server UUID before issuing KILL QUERY. Server permissions apply.
MySQL 9.7 excludes the removed ``mysql_native_password`` method from its form
and capability declaration; older routes explicitly choosing it are rejected.

Native behavior
---------------

Provider-private pools isolate endpoints and credential/configuration
generations. Merely selecting reset-on-return does not enable a pool. Pending
work is rolled back before an admitted return; a failed reset discards the
physical connection. No active operation reconnects or replays SQL implicitly.

Queries accept named objects or positional arrays. Exact integer/decimal and
binary envelopes are documented in the query form. Results preserve unsigned
64-bit integers, exact decimals, zero dates, signed extended TIME, JSON text,
Unicode, BLOB, geometry and VECTOR bytes. Duplicate labels receive unique
lookup names while retaining native labels. Catalog reads use their native
metadata path, separately from raw query decoding.
When ``character_set_results=NULL`` is used, each column's charset owns value
decoding. A charset with no matching Python codec is represented as exact
base64 bytes with native charset/collation identity, rather than guessed text.
For a text presentation across storage charsets, retain the default UTF-8
results or explicitly request MySQL's native conversion to UTF-8. Changing SQL
charset variables does not reconfigure the connector's command encoder; edit
the connection character set and open a new session for that purpose.

Execution runs asynchronously. Polling delivers every native result set,
including procedure and affected-row responses, in bounded pages. A page has
its own set index, row offset and end-of-set marker. Later failures do not erase
earlier pages or implicitly roll back earlier work. Queue bounds are two pages,
256 rows and a one-MiB target per page; a larger single row remains intact and
is materialized by the connector. This is not a streaming BLOB API. Query result
history shows recent pages, not an assertion that the last grid is the whole
batch or a whole-result export.

Cancellation requests KILL QUERY through a separate verified connection. The
worker consumes native responses before the session can be reused. Cancellation
does not undo previously executed statements or prove transaction finality.
Failed COMMIT/ROLLBACK replies and unusable connections quarantine the retained
session as unknown, including when the server actually committed. Closing an
unknown session does not claim successful rollback. Do not retry user mutations
to resolve an unknown outcome.

LOAD DATA LOCAL INFILE is disabled by default. Its MySQL-only controls can
admit a directory through ``allow_local_infile_in_path`` while keeping
unrestricted loading disabled. These are client-side paths and native connector
checks. Server ``local_infile`` policy must also permit loading. Imports retain
native transaction behavior; the provider does not commit on the user's behalf.

Portable qualification
----------------------

Use a dedicated MySQL 9.7.0 test server and test principal with permission to
create and drop disposable schemas/tables/procedures and cancel its own queries.
The runner creates random owned schemas and removes them. It does not install a
server, invoke Docker, alter accounts or global configuration, or touch an
existing database. Do not supply a database or password in the route file::

    {
      "host": "mysql-test.example",
      "port": 3306,
      "user": "scratchrobin_test",
      "use_pure": true,
      "ssl_ca": "/absolute/path/to/test-ca.pem",
      "ssl_verify_cert": true,
      "ssl_verify_identity": true,
      "connection_timeout": 10
    }

Use native Windows paths in Windows route JSON, with JSON backslash escaping.
On macOS/Linux, from the repository root::

    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_driver_platform_gate \
      --route /path/to/route.json --evidence /path/to/new-evidence-directory

On Windows PowerShell, from the repository root::

    $env:PYTHONPATH = "web"
    python -B -m tools.cdeadmin_mysql_driver_platform_gate `
      --route C:\test\route.json --evidence C:\test\new-evidence-directory

The password is prompted without echo and supplied through the provider secret
lease. Use ``--no-password`` only for an explicitly passwordless test account.
The evidence destination must be new. Receipts include platform, architecture,
Python/connector/server versions, actual connection class, TLS version, source
hashes, completed scopes and redacted failures. A failure must not be called a
pass. Retain failure artifacts and send driver defects back to the backend team.
Repeat with ``use_pure: false`` when qualifying an installed C extension.

The platform gate exercises exact values, transaction visibility, killed
sessions, multiple native results, later-statement errors, paging and native
cancellation. It does not weaken a supplied TLS route to inject plaintext
faults. Separate uniquely owned Docker fixtures provide reproducible pool,
TLS rejection, local-file policy and lost-COMMIT-reply checks::

    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_connection_ownership_gate --evidence /new/pool-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_execution_gate --evidence /new/execution-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_tls_gate --evidence /new/tls-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_local_infile_gate --evidence /new/import-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_connection_modes_gate --evidence /new/connection-modes-proof

The TLS fixture additionally requires OpenSSL. Those fixture runners use
loopback ephemeral ports and remove only their own containers and volumes.
No Windows/macOS execution, receiving-team acceptance, enterprise identity
provider deployment, or complete management-console UX acceptance is inferred
from Linux driver receipts.

Shared SQL query form
---------------------

MySQL query entry points use the global SQL workspace and its PostgreSQL-based
frame, compact native-action toolbar, source pane, result navigation and
Data Output/Explain/Messages/Engine options panels. Connection labels include
MySQL and retain endpoint/database identity. Firebird dialect, profiler,
DECFLOAT and streaming controls do not appear in a MySQL session.

Plan buttons keep their provider-native MySQL names: JSON EXPLAIN and execution
plan (EXPLAIN ANALYZE). The latter executes the source statement. Parameters
retain Connector/Python positional/named shapes and exact-value envelopes.
The MySQL options panel displays the last explicitly requested session-state,
autocommit and in-transaction observations, including unknown/unobserved states;
it does not infer finality. The shared toolbar changes autocommit only through
the provider-owned action and displays the acknowledged native value. It explains
implicit DDL commits, nontransactional-table limits and native script binding.
Multi-result paging, cancellation and transaction callbacks remain provider-owned.

MySQL shared transaction controls
--------------------------------

The shared editor exposes an autocommit checkbox when the MySQL provider admits
both policy actions. Opening the retained SQL session observes its native policy
before execution. Commit and rollback are disabled while autocommit is enabled
or its value is unknown. A failed policy request invalidates the checkbox until
an explicit transaction-state refresh succeeds; the UI never assumes success.

The provider serializes policy changes with execution. Changing autocommit while
a native transaction is active is refused: the user must explicitly commit or
roll back first. An unchanged setting is an idempotent observation. A failed SET
or uncertain acknowledgement quarantines the connection without reconnect or
replay. MySQL DDL implicit commits and nontransactional table behavior are not
changed. These actions are not added to MariaDB or MySQL-wire engines by analogy.

Completed MySQL statements refresh the checkbox's observation on the same idle
connection, so explicit SET autocommit SQL is reflected. Failed observation
blocks further execution until refresh succeeds. Query messages expose bounded
native server error text with errno/SQLSTATE, but not local connector exception
text. Client dispatch timing covers cursor.execute only: it includes transport
and the first native response, not subsequent result fetching, browser waits,
or isolated server execution/preparation time.

DDN to native metadata export
-----------------------------

A MySQL catalog DDN document can produce a downloadable native metadata script
without executing it. Only native MySQL catalog modules and exact recorded
endpoint/database identities are admitted. Imported definitions are user input;
export does not certify their grammar or authorize their execution. A selected
view does not limit the metadata model or imply object removal.

Preserve each complete SHOW CREATE definition, including routine/trigger/event
bodies, definers, table options and generated expressions. Capture its native
creation context (SQL mode, client character set and connection collation).
Restore those session settings around the export. Use a collision-free MySQL
client DELIMITER directive rather than splitting routine bodies at semicolons.
Emit database selection explicitly. The script never disables foreign-key
checking, drops objects, or creates missing users/grants implicitly.

Order captured tables by their foreign-key dependencies, views by visible
VIEW_TABLE_USAGE, and triggers after their owning tables. Missing prerequisites
remain explicit. Cycles, ambiguous identities, unavailable definitions/context,
system objects, denied dependency observations and incompatible server identity
block a runnable script. Observational capture is not a transactionally atomic
DDL snapshot, and native script export is distinct from reviewed diff/apply.
The response carries source and statement digests, native prerequisites,
blockers and permission/consistency warnings; it never reports deployment.

Catalog SET-valued cells (including native routine SQL-mode facts) use explicit
sorted ``{set:[...]}`` JSON representations. Empty SET, null and empty text remain
separate; arbitrary Python sets are not serialized as lossy strings. Native
creation-context text supplied by SHOW CREATE remains its own recorded value.

The native ``mysql`` client's delimiter is limited to 15 bytes. Generated tokens
respect that limit and are absent from every emitted definition. The initial
UTF-8 script adapter admits utf8mb4 and representable utf8mb3 creation contexts;
other stored client encodings remain an explicit blocker, without silently
converting their creation semantics. Native replay may canonicalize equivalent
SHOW CREATE text (for example, make a column CHARACTER SET explicit); qualify
exact type/default/generated/comment/collation facts and retain this difference.

The shared session contribution contract admits native ``autocommit_on`` and
``autocommit_off`` alongside begin/commit/rollback. Admission does not advertise
an action for an engine: the selected provider's declared action set remains
controlling. MySQL's advertised actions must pass host contribution validation
before an explorer workspace can bootstrap.

Saved relational designs
------------------------

MySQL relational captures open in the same sister-project DDN designer used by
Firebird. Editing a diagram never executes SQL. Native baseline and authored
workspace are stored together in immutable revisions of an owner-scoped project
asset. MySQL and Firebird use different project namespaces and baseline keys;
endpoint/database/kind scopes and optimistic asset versions must match before
saving. Reading an older revision returns its historical design and baseline
alongside the current reference for a subsequent compare-and-swap save.

Use the registered native MySQL database context for every read/save; ownership,
engine and route/database checks occur before asset access. The designer can
save/download manual layouts and native facts, then merge a newer capture using
the existing DDN three-way merge tools. A saved diagram is an authored asset,
not permission to apply metadata. Database-switch responses cannot replace the
new target's design, and empty visual selections never request deletion.

Selected relation data to DDN
-----------------------------

Data inclusion is explicit and separate from metadata capture. Select one exact
native user table/view identity in an owned registered database, sample/full
mode and a 1–6,000 row budget. Capture on an independent native attachment with
REPEATABLE READ, READ ONLY and WITH CONSISTENT SNAPSHOT, bounded execution/lock
waits, 4 MiB of acquired JSON and at most 8 MiB of generated DDN. The owner must
have both data-read and execute permission. Refresh and close that transaction
before returning the download; never reuse an interactive session or its work.

Observe database/server/version and relation kind before selecting. Native
column definitions accompany positional values encoded by the same exact
MySQL codec as the SQL editor, preserving unsigned integers, decimals, temporal
text, JSON, character encodings and opaque/binary values. Row order is native
and unspecified. A sample discloses whether more rows were observed; full mode
exceeding its budget fails without a partial download. Denied or failed reads
never become empty results. Only a successful rollback/attachment cleanup
permits success.

InnoDB table capture uses the native consistent snapshot. Nontransactional
tables and views are explicitly labelled with their weaker consistency; the
read-only transaction does not make MyISAM or unknown view dependencies
transactional. No cross-database snapshot, metadata fence, restorable backup or
historical retention is implied. Static DDN table views carry acquisition
provenance and page bounds through the shared engine-independent result adapter.

Server-wide DDN discovery
-------------------------

Server inventory is independently acquired and owner-scoped. Capture native
identity, visible databases, account identity/policy flags, role edges, default
roles, visible global grants, plugins/components, built-in character metadata,
storage engines and tablespaces using explicit credential-free projections.
Never read authentication strings, password hashes, arbitrary configuration
values or replication-secret stores. Each section records visibility or native
permission refusal; a denied catalog is not empty or fully covered. Accounts
without visible role edges are not heuristically classified as roles.

Bound inventory to 20,000 facts and 8 MiB. Optional database expansion accepts at
most 32 distinct owned registered database target IDs; each uses its own existing
native metadata capture and must report the inventory's server UUID. Return
separate database DDN workspaces with their own baselines/diagrams. These reads
are observational and independent, not a global schema/data snapshot, cluster
backup or automatic migration. Unregistered visible databases require explicit
registration before database expansion. Engine-specific native version and
owner/route checks apply to every scope.

Native role membership and default activation
---------------------------------------------

MySQL role membership has dedicated grant/revoke forms. The target role uses
its native user/host pair; the recipient user and host are separate fields, so
names containing ``@``, quotes or backticks remain unambiguous. Grant optionally
includes ``WITH ADMIN OPTION``. Revoke removes membership; MySQL 9.7 does not
admit MariaDB's ``REVOKE ADMIN OPTION FOR`` syntax, so no such choice is shown.

Default activation is a separate native ``SET DEFAULT ROLE ... TO`` operation.
The mode is selected role, ALL granted roles or NONE. It replaces the recipient's
existing default set and requires explicit confirmation. It does not grant
membership and does not alter an existing attachment's active roles. Native
permissions and role-edge validation remain MySQL's authority. These account
administration statements can implicitly commit; they run through the existing
reviewed native-operation path, never inside the user's pending query work.
Unassigned locked accounts are not guessed to be roles during discovery.

Cyclic foreign-key metadata export
----------------------------------

Native table exports create all table bodies before adding their foreign keys.
The adapter separates only named, catalog-matched foreign-key clauses from the
captured SHOW CREATE table body, respecting nested expressions, quoted values,
SQL-mode escaping and comments. Every separated clause must match the captured
KEY_COLUMN_USAGE constraint identity exactly. An ambiguous or incomplete match
blocks script generation. Self references, composite keys and cycles therefore
use the same staged path; foreign-key checking is never disabled. External
referenced tables remain explicit prerequisites. Views and trigger/routine
bodies retain their native dependency/context handling. This is metadata export,
not an authorization to replay imported DDN or an atomic migration.

Native test-data generation
---------------------------

An owner selects a registered MySQL database and explicitly loads visible user
tables into a bounded recipe. Recipe generation runs on the server and performs
no SQL writes or data sampling. The recipe binds endpoint/database identities,
seed, exact native table IDs and column names. Sources include constants,
native defaults, exact sequential/random integers, bounded choice/file arrays,
references to explicitly generated parent columns, captured AUTO_INCREMENT
parent values and existing-row scalar selections with an explicit unique order.
Generated columns accept defaults only. Native types, constraints, privileges,
triggers, transaction and autocommit behavior remain MySQL's authority.

The output is a reviewable SQL script for the shared Query Tool. It inserts one
row at a time, captures AUTO_INCREMENT values immediately with LAST_INSERT_ID,
and never invents INSERT RETURNING support or toggles foreign-key checks. Parent
references use generated row positions; empty existing selections yield NULL.
Existing selections execute only when the user runs the script and can change
between statements, especially under autocommit. The generator does not claim
that MyISAM writes, sequence allocation or trigger effects are rollback-safe.
Limits: 32 tables, 1000 rows per table, 5000 total rows, 4 MiB recipe and 1 MiB
script. Recipes and downloaded scripts may include user data. SQL text literals
use explicit UTF-8 hexadecimal conversion, independent of SQL-mode escaping.

Native DDN change-review admission
---------------------------------

A native MySQL change review compares baseline, desired and freshly captured
live catalog models for the same authenticated endpoint, registered database
and server UUID. Comparison uses schema definitions and stored creation context,
not volatile statistics. A missing desired row is a filtered selection, never
removal intent. Explicit removals must carry the adapter's target-name
confirmation. Conflicting live edits block the affected operation. Imported
SQL remains input: lexical clause separation is not native grammar validation.

Table alteration previews preserve native SHOW CREATE clauses, including native
types, expressions, defaults, comments, indexes and constraints. Column removal
requires an explicit ``mysql_change.drop_columns`` list; table removal requires
``mysql_change.action = drop`` and exact name confirmation. New tables must have
an exact native target identity and a CREATE TABLE definition. Unsupported or
ambiguous native clauses block the affected operation without guessing SQL.
Native PREPARE validation, reviewed receipt admission, locked revalidation,
explicit apply and post-application rediscovery are separate required stages.
Until those stages pass, a semantic preview cannot be dispatched as a migration.

The table preview's explicit validation stage uses native MySQL PREPARE on an
independent idle connection, then DEALLOCATE without EXECUTE. It verifies the
server UUID/version and recorded UTF-8 session context, caps the batch to 32
statements/1 MiB and returns per-statement native error codes. Unsupported
preparation remains unavailable; it is not relabelled successful validation.
Validation does not reserve the live schema or make a preview executable.

Reviewed single-table metadata application
------------------------------------------

A MySQL application review binds one existing-table ALTER or explicitly confirmed
DROP to the registration, database target, native server UUID, owner and exact
compiled statement digest. Creation and multi-object batches require separately
admitted adapters. Reviews expire after five minutes. A durable receipt is
claimed as ``unknown_outcome`` before native access; a claimed token is never
redispatched, including after process restart. This application receipt stores
review/dispatch evidence, not database recovery or a substitute transaction log.

Execution uses an independently owned idle connection and native WRITE table
locking with a bounded lock wait. Under that lock, the executor rechecks native
server/database identity, SQL mode, quoted SHOW CREATE and the exact baseline
schema fingerprint before sending one DDL statement. Native DDL commits
implicitly: neither a user transaction nor receipt storage makes it rollbackable.
The executor retains the table lock through rediscovery. A received DDL success
acknowledgement means ``committed`` even when rediscovery subsequently fails;
``rediscovery_verified`` is then false. Failure after dispatch with uncertain
native outcome remains ``unknown_outcome``. Pre-dispatch failures are explicitly
``not_dispatched``. Exact schema differences found by rediscovery are reported;
canonicalized SHOW CREATE is not assumed textually identical to desired DDN.

Server UUID plus database/table name and observed definition are the native
identity contract. MySQL does not expose a permanent database/table UUID here;
an identical drop/recreate incarnation cannot be distinguished by these facts.
Table locking fences concurrent operations during revalidation and execution,
not the earlier documentary capture. Permission errors and lock timeouts are
not an empty catalog. Cleanup always retires the independent connection.
