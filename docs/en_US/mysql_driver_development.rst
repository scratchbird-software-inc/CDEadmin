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
server UUID/version and recorded native session context, caps the batch to 32
statements/1 MiB and returns per-statement native error codes. Unsupported
preparation remains unavailable; it is not relabelled successful validation.
Validation does not reserve the live schema or make a preview executable.

Reviewed single-table metadata application
------------------------------------------

A MySQL application review binds one new-table CREATE, existing-table ALTER or explicitly confirmed
DROP to the registration, database target, native server UUID, owner and exact
compiled statement digest. Ordered batches use the multi-table application
contract below and retain an independent outcome for every statement. Reviews
expire after five minutes. A durable receipt is
claimed as ``unknown_outcome`` before native access; a claimed token is never
redispatched, including after process restart. This application receipt stores
review/dispatch evidence, not database recovery or a substitute transaction log.

Execution uses an independently owned idle connection. Existing-table changes
use native WRITE table locking with a bounded lock wait. Under that lock, the executor rechecks native
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

Relational DDN native review handoff
----------------------------------

MySQL relational designs bind table/view native facts and field UIDs to the exact
endpoint, database target and object. An explicit handoff reconstructs baseline
and desired catalog DDN against a fresh native capture. Edited native definitions
follow the ordinary three-way preview/review path. Field datatype, nullability
and description edits on an existing native table update the corresponding exact
SHOW CREATE column clause, preserving other attributes, defaults, expressions,
indexes and options. Native and graphical edits to the same clause must agree.
Field omissions and view filtering never remove columns. New field identities
require the explicit graphical column admission below; renamed identities require
explicit graphical rename admission below; unsupported properties
are not silently treated as deployed changes. Native PREPARE remains required:
lexical clause editing is not a replacement grammar or deployment authority.

Native resource-group administration
------------------------------------

MySQL resource groups expose structured create, alter, explicit thread
assignment and drop operations. Creation selects native USER/SYSTEM type,
optional VCPU numbers/ranges, native thread priority and enabled state. Alteration
preserves omitted settings and exposes ENABLE/DISABLE with explicit FORCE.
Assignment requires one or more exact performance_schema thread IDs; it never
silently assigns an independent helper connection. Built-in groups cannot be
removed through these forms. Native RESOURCE_GROUP_ADMIN/RESOURCE_GROUP_USER,
platform support, CPU availability and operating-system scheduling privileges
remain authoritative; a native refusal is not reported as successful change.
FORCE may move assigned threads back to the native default group. These server
operations commit independently of an interactive user's transaction. MariaDB
must not inherit the MySQL resource-group syntax or controls.

Native server configuration and session control
----------------------------------------------

MySQL server navigation exposes native global variables, persisted values and
variable-source metadata from performance_schema. Separate operations use SET
GLOBAL, SET PERSIST, SET PERSIST_ONLY and RESET PERSIST for the selected exact
variable. Values are bound scalars or explicit DEFAULT; previews redact bound
values. Native privilege, dynamic/read-only/startup-only and persistence rules
remain authoritative. SET PERSIST changes current and restart configuration;
PERSIST_ONLY changes restart configuration without changing the current value.
RESET PERSIST removes only the selected persisted override. These forms do not
pretend a helper connection's session settings configure the user's SQL session.

Native session nodes retain separate process/connection IDs and thread IDs as
exact decimal strings. Query cancellation uses KILL QUERY; disconnect uses KILL
CONNECTION against the selected native process ID. Both require explicit target
confirmation. KILL has native transaction and disconnection effects; a cancelled
statement or broken connection must not be reported as a commit/rollback proof.
Only native server-visible sessions are discovered, with denied observations
reported by the existing catalog-coverage contract.

Exact numeric variable inputs may use JSON text with explicit INTEGER or DECIMAL
representation; the adapter uses bound text with native numeric casts, keeping
durable plans JSON-safe without JavaScript integer rounding. Automatic JSON scalars preserve their scalar type.
A numeric variable may reject a quoted text value rather than coerce it. Native
KILL QUERY acknowledgement means the interrupt was requested, not that every
statement produces an error: MySQL 9.7's SLEEP expression can return its native
interrupted value. The result and transaction state must remain native facts.

Native InnoDB storage lifecycle
------------------------------

Tablespace discovery retains native InnoDB space type, state, allocation,
encryption and autoextension observations. General and undo tablespaces expose
native create, alter, rename where supported, and drop operations. File-per-table
and system spaces remain managed through their native owning table/server
contracts. General creation supports datafile, FILE_BLOCK_SIZE, AUTOEXTEND_SIZE,
encryption and ENGINE_ATTRIBUTE. Alteration supports encryption, autoextension,
engine attributes and the native undo ACTIVE/INACTIVE lifecycle. Undo spaces
cannot be renamed through a general-tablespace command. Native default undo
spaces cannot be removed through these controls.

Datafile paths and JSON engine attributes are bound values, escaped by the
selected native connection. Native FILE privilege, filesystem location rules,
keyring/encryption availability, page-size compatibility and engine restrictions
remain authoritative. An undo space must reach the native droppable state after
INACTIVE; sweep/purge work is not replaced by a timer or presumed completion.
Dropping a nonempty general space is a native refusal, not permission to remove
its tables. Tablespace DDL commits independently; DROP can remove native files.
NDB-only storage options are not admitted on the current InnoDB-qualified profile.

MySQL 9.7 general-tablespace ALTER and DROP omit ENGINE: the native command
handler rejects that clause in these contexts even though the grammar retains
its production. CREATE and the admitted undo commands use their own native
engine rules. Grammar inventory alone is not evidence of executable syntax.

Native per-object administration subsets hide mutations for system, default undo
and file-per-table spaces. Undo nodes omit rename; alter choices are filtered by
native space type. General-space ENCRYPTION alteration is offered only when an
active native component/plugin keyring was observed. Absence of an observation
is not proof that a privileged raw SQL command cannot work; it grants no form
capability. Native rediscovery and validation still govern each operation.

Native partition administration
-------------------------------

Partition nodes retain their exact database/table/partition identity and native
method, expression, ordinal, bound and storage observations. Their operations
address the owning table explicitly: analyze, check, optimize, rebuild, truncate,
drop and exchange with a named compatible nonpartitioned table. Exchange defaults
to WITH VALIDATION; WITHOUT VALIDATION requires explicit selection. Native engine
compatibility, partition method, privileges and row-placement checks remain
server authority. InnoDB does not offer a fictitious REPAIR operation.

Owning table forms add or reorganize native partition definitions, coalesce
HASH/KEY partitions, remove partitioning or set a native PARTITION BY clause.
Definitions and partition clauses are bounded single native fragments with
balanced lexical boundaries; the forms do not invent a common partition dialect.
Comments, statement separators and mode-dependent backslash escapes in these
fragment fields are refused; the engine-aware SQL editor supports complete native
scripts. Exact identifiers in structured fields are quoted separately. A native
DDL result is not a rollback promise: destructive operations may delete rows,
exchange moves ownership of data and partition DDL commits independently.

Per-partition capability filters hide RANGE/LIST-only drop/reorganization on
HASH/KEY nodes, and hide EXCHANGE on a table with native subpartitions. InnoDB
OPTIMIZE can report that it rebuilt/analyzed the table instead; the native result
messages are retained rather than relabeled as a partition-only optimization.

Native replication channels
---------------------------

MySQL channel forms use CHANGE REPLICATION SOURCE TO, START/STOP REPLICA,
RESET REPLICA and CHANGE REPLICATION FILTER, scoped with an explicitly bound
FOR CHANNEL value. The empty value identifies only the native default channel;
it never means all channels. Reserved Group Replication channels remain owned
by their native group lifecycle, not these asynchronous-replication forms.
Create and alter share the native change-source command and retain unspecified
settings. They never stop an active channel implicitly. Credentials have a
separate password field and are redacted from validation and command previews.

The advanced source-options object retains native option names and typed values:
source/network binding, retry/delay/heartbeat, log/GTID positioning, TLS paths,
verification, compression, failover, row-format and privilege-check settings.
Unknown options are refused. Exact large log positions use decimal strings.
Thread selection, source/relay-position or GTID stop conditions, and channel
filters are explicit controls. RESET optionally removes channel configuration;
its default preserves it. Native privileges, thread state and option combinations
remain authoritative. A start acknowledgement does not prove connected transport
or applied data; discovery exposes native receiver/applier status and error codes
without passwords. Native replication changes are independent of interactive
transaction rollback, and failures do not authorize automatic replay.


Reviewed creation checks native absence before dispatch and uses an ordinary
CREATE TABLE without IF NOT EXISTS, REPLACE or DROP. No client lock is claimed on
a nonexistent table. MySQL's native dictionary serializes the actual creation;
a concurrent creator can cause a native refusal. A pre-dispatch existing target
refuses application, while a lost acknowledgement after dispatch stays unknown
and the durable token is never replayed. The desired definition is fingerprinted
and recompiled from the same exact catalog representation. Successful creation
is independently rediscovered using SHOW CREATE TABLE. This does not authorize
unreviewed multi-object batches or infer atomic rollback across DDL statements.

Native encoding-aware metadata scripts
--------------------------------------

Stored routine, trigger, view and event creation contexts can use native client
encodings other than UTF-8. The SQL export adapter must preserve those contexts
and exact Unicode definitions. It uses a separate idle native connection for
charset/collation admission and MySQL CONVERT round trips; no imported DDL is
executed during export. Unknown client encodings, incompatible collations or
lossy conversion prevent download instead of replacing characters silently.

An export containing different native client encodings is a binary mysql-client
script. Each complete statement is encoded by MySQL in its admitted charset,
with explicit mysql-client \C charset commands and original SQL mode/collation.
The artifact retains byte size, SHA-256 and per-statement encoding facts. A UTF-8
preview is documentary and must not be saved as the executable mixed-encoding
file. Run the binary script in a fresh dedicated native mysql client; it is not
a generic driver script or an in-place interactive-session restoration contract.
Native delimiter selection avoids every encoded statement, and file generation
retains the existing 8 MiB bound and dependency ordering. This export grants no
execution authorization or DDL atomicity.

The mixed-encoding consumer uses ``mysql --binary-mode
--default-character-set=utf8mb4``. MySQL 9.7 disables long local commands by
default in batch mode; the admitted short ``\C`` charset command and DELIMITER
continue to work without enabling unrelated local commands. Consumer options
are retained in the artifact manifest and shown with the download.

Routine characteristics and index identity
------------------------------------------

MySQL routine ALTER forms change native SQL SECURITY, SQL data-access
characteristics and comments, retaining unspecified characteristics. Native
MySQL 9.7 ignores an empty ALTER comment; the adapter refuses an explicitly
empty comment rather than promising to clear it. A blank optional field leaves
the comment unchanged. They never replace a routine body or change its
signature or determinism: those are not MySQL ALTER characteristics. Native
privileges and routine-language restrictions remain authoritative. Comments are
bound values and are not included in generated command previews.

Secondary-index forms rename the exact database/table/index or set native
VISIBLE/INVISIBLE optimizer visibility. Invisible indexes remain maintained and
continue enforcing uniqueness; visibility is not deletion or constraint removal.
Primary keys have neither operation. Native implicit-primary-key restrictions
may also reject invisibility. These DDL actions commit independently; a lost
acknowledgement must not be automatically replayed. MariaDB retains its own
separate dialect and does not inherit these MySQL controls.

Persistent SQL request history
-------------------------------

The shared SQL editor offers opt-in source history per application owner,
registered MySQL server, explicit database target and native language profile.
Its configuration-store session is independent of native transactions. Retention
and record limits are bounded policy settings; history survives application
restart. Credentials, query parameter values and result rows are never captured.
Known authentication statements and credential-bearing MySQL URIs omit source;
the user can also mark any source sensitive. This detector is conservative, not
a guarantee that arbitrary SQL contains no confidential data. Capture is off by
default.

History reports host request/preparation observations, not commit finality.
Storage failures cannot block or replay native execution. Loading an entry
changes editor text only and never executes it. Clearing entries requires
confirmation and retains policy. Engine/target switches reset the visible
history state so one connection's entries are not displayed under another.

Database connection menu
-------------------------

The MySQL database context menu offers one Connect action that verifies the
selected registered database target. Connection registration/editing remains a
separate action. Disconnect explicitly names its server-wide effect: all
registered database routes and their active sessions for that endpoint are
released together. It is never labeled as disconnecting only one database.

Shared query toolbar and autocommit observation
-----------------------------------------------

MySQL uses the shared compact query frame, icon actions, connection selector,
language binding and bounded browser-buffer control. A single autocommit
checkbox replaces separate on/off buttons. Its state comes from the native
session observation, including a refresh after opening and terminal execution;
it is indeterminate when no reliable observation is available. Commit/rollback
are disabled while autocommit is on or unknown. An uncertain policy must be
refreshed before execution resumes; the UI never guesses transaction state.
Concurrent validation/execution share one session-opening request. Switching
languages or closing a workspace waits for that request and releases the same
owned session. These controls do not change MySQL DDL implicit-commit semantics.

MySQL statement diagnostics retain native error number, SQLSTATE and message in
the shared result area, including requests that produce no row result. Client
dispatch timing covers execution through the first response and excludes result
fetching. It is shown separately from engine preparation/execution timings,
which remain unavailable unless independently observed. A JSON EXPLAIN or
EXPLAIN ANALYZE result is a requested plan; the UI must not relabel client timing
as engine timing or infer a plan for ordinary statements.

Native ordinary-view definition controls
---------------------------------------

MySQL ordinary-view CREATE and ALTER use the same compact structured form:
exact database/name, SELECT or WITH query, optional ordered output-column names,
ALGORITHM (UNDEFINED, MERGE or TEMPTABLE), SQL SECURITY (DEFINER or INVOKER),
optional exact definer user/host, and NONE/LOCAL/CASCADED check option. ALTER
requires the complete desired definition; omitted native clauses use MySQL's
native defaults and must not be described as preserving previous values.
CREATE remains distinct from replacement and must fail if the name exists.
Queries are single statements checked for lexical framing under both native
backslash modes; native MySQL owns grammar, privileges, dependencies,
updatability, algorithm warnings and check-option enforcement. Quoted identifiers
and account components must remain safe under ANSI_QUOTES/NO_BACKSLASH_ESCAPES.
Definition changes use native implicit-commit DDL, preserve grants according to
MySQL, and are never automatically retried after uncertain acknowledgement.

Native CHECK constraint enforcement
-----------------------------------

MySQL CHECK constraints expose their native ENFORCED state and a separate
ENFORCED/NOT ENFORCED operation under the exact database/table/constraint target.
Primary, unique and foreign-key constraints do not receive this operation.
Changing enforcement uses native ALTER TABLE and implicit commit semantics;
MySQL validates existing rows when enabling enforcement. A refusal leaves the
previous native state in force and is not evidence that enforcement changed.

Explicit graphical column additions
-----------------------------------

The MySQL relational viewer offers an unchecked "Include new graphical columns"
choice when preparing metadata review. Its explicit boolean is bound to the
selected database target and the original/edited DDN documents. Without it,
unknown field identities remain a reconciliation error. With it, up to 128 new
fields per existing user table may become ADD COLUMN clauses using their exact
unique names, required native datatype, boolean nullability and optional comment.
Existing native clauses, defaults, generated expressions and constraints remain
intact; a conflicting native definition blocks review. New fields cannot reuse
an existing column name through a different UID. Missing fields never delete
columns. Renames use the separate explicit admission below. This choice
only prepares the ordinary three-way preview; native PREPARE validation and
owner-bound reviewed application remain required before database mutation.

A pending relational handoff disables parent catalog previews and mutations until
the reviewed baseline/desired pair is installed or the handoff fails. A concurrent
preview must not invalidate a handoff or leave the catalog in a busy state.

Reviewed multi-table application receipts
----------------------------------------

A native-validated plan may contain 1 to 32 distinct user-table/ordinary-view/library/event CREATE/ALTER/DROP
operations, within 1 MiB of SQL and the existing 4 MiB review bound. Review seals
its displayed order, exact baseline/desired fingerprints, owner and database
binding. Application runs that order once, using the existing independently
owned native connection, absence/table-lock revalidation and rediscovery contract
for each statement. It does not promise atomic DDL or a hypothetical-schema
preflight; native PREPARE acceptance precedes execution, and native privileges,
dependencies and engine checks remain authoritative at execution time.

The host durably records each statement as uncertain before its native call and
records its returned outcome before advancing. It stops after a refusal, unknown
outcome or unverified rediscovery. Earlier committed effects remain committed;
remaining statements stay explicitly not dispatched. The receipt reports ordered
per-statement results, including partial commitment. Crash/restart and repeat
requests expose retained observations without redispatching any statement. The
owner must reconcile native state and prepare a fresh review for remaining work.


Native encoding during metadata deployment
------------------------------------------

Validation and application support native character-set-client and independent
collation-connection contexts. An owned UTF-8 connection asks MySQL to encode the
complete statement in the recorded client charset and round-trip it to UTF-8.
Loss or unsupported context refuses dispatch. ASCII-only charset/collation names
are required; native SET validates their availability. No Python encoding alias
is used to approximate MySQL's character maps.

Only statement preparation/dispatch uses those exact bytes under the captured
context. The connection returns to UTF-8 for identity, baseline and rediscovery
queries, preserving non-ASCII object names and Unicode result decoding. Native
SQL mode remains the captured mode. Context restoration does not imply rollback:
a success followed by restoration failure is still committed; lost replies remain
uncertain. The independently owned connection is retired after the operation.

Reviewed ordinary-view DDN deployment
-------------------------------------

Native ordinary views join table CREATE/ALTER/DROP in the same ordered receipt
contract. The adapter preserves native algorithm, exact definer, SQL security,
query, check option and recorded client/collation context. It accepts an exact
quoted SHOW CREATE VIEW target; CREATE never replaces an existing object. A reviewed view update
uses native CREATE OR REPLACE with the exact existing-target observation and baseline
check below; absence is refused. MySQL 9.7 PREPARE rejects ALTER VIEW with error
1295, so it is not falsely labelled validated. The displayed replacement
statement itself must pass native PREPARE. The query form retains native ALTER
VIEW as its separate operation. Explicit DROP requires the
exact view name confirmation. Materialized views require their separate adapter.

Existing views use a bounded native advisory lock keyed by database and view,
then exact SHOW CREATE definition and creation-context revalidation immediately
before dispatch. This serializes cooperating ScratchRobin DDN applications only;
ordinary SQL and other administrators need not honor it. MySQL rejects view
replacement under LOCK TABLES with error 1192, so no table-lock or atomic
compare-and-swap guarantee is claimed for view updates/removals. Review exposes
this concurrency warning and receipts record that external DDL was not fenced.
Concurrent external replacement in the observation/dispatch interval can be
overwritten or removed; use an exclusive DDL maintenance window when that must
be prevented. Permission or advisory-lock refusal stops before dispatch.

Views can depend on tables or other views; displayed order remains the sealed
execution order, and native PREPARE does not preflight a hypothetical schema
containing earlier changes. Observed creation-context or native-definition drift
requires a fresh review. Rediscovery reports native definitions; dependent
objects are not implicitly rewritten or recreated by the adapter.

Explicit native DDN column rename intent
----------------------------------------

An existing-table desired native definition may declare
``mysql_change.rename_columns`` as an exact old-name to new-name mapping, bounded
to 128 distinct pairs. Every source must be present only in the baseline and
every destination only in the desired definition. Names are 1–64 characters;
identity reuse, swaps into occupied names and implicit rename guessing are
refused. Unmapped disappearance still requires exact drop_columns intent.

Compilation uses native CHANGE COLUMN with the full desired column clause and
ordered placement, retaining defaults, generation, comments and native type
attributes. Desired indexes, constraints and generated expressions must carry
their explicitly intended native definitions; normal clause differences produce
the corresponding drop/add/modify operations within that single ALTER TABLE.
Native PREPARE, locked baseline revalidation, receipt admission, execution and
rediscovery remain required. Graphical label changes alone do not authorize this
operation; field UID and native-name reconciliation remain distinct.

Native server components
------------------------

MySQL components have their own server-level inventory branch, separate from
plugins. Discovery reads component_id, component_group_id and exact component_urn
from mysql.component; permission failures remain unavailable observations.
Install accepts 1–32 distinct exact URNs and optional ordered native SET entries
(scope GLOBAL or PERSIST, exact variable name and scalar literal value).
Uninstall targets the discovered exact URN with confirmation. A component is not
renamed or altered through plugin commands; dependent services, native library
availability, privileges and persistence remain MySQL's authority.

Compilation binds URNs and scalar values as parameters; variable identifiers are
bounded native names, including component-qualified names. The compact forms
expose install-time options separately from runtime global/persisted settings.
No component is downloaded or an absent native library silently substituted.
Successful install/remove is independently rediscovered; native implicit commits
and component lifecycle side effects are not represented as user rollbackable.
MariaDB does not inherit this MySQL-only component operation family.

Native Group Replication administration
---------------------------------------

An active native group_replication plugin admits a distinct server Group
Replication node, with observed members and member statistics. Its recovery and
applier channels remain inspect-only through asynchronous-channel controls.
The group node exposes START/STOP GROUP_REPLICATION; primary election; switching
single/multi-primary mode; communication protocol and write concurrency; and
member-action enable, disable and reset functions. Native membership, quorum,
permissions, action-state and argument checks remain authoritative. Unsupported
plugin state is not presented as an available group operation.

START may supply an exact native recovery user, sensitive password and default
authentication plugin. Credentials remain bound values and are not discovery
facts. Configuration and persisted variables use the existing native variable
forms. Starting never silently bootstraps a new group, forces membership,
installs a plugin or alters recovery channels. Explicit native bootstrap is a
separate operator-controlled variable action; operators must clear it according
to MySQL's lifecycle. Group operations are independent administration with
native distributed effects, not rollbackable user transactions.

Forms require exact member UUIDs and bounded native integer/version arguments.
Protocol/write-concurrency observations use native read functions only when a
member is ONLINE. Member action reset remains available while the plugin is
installed, the group is stopped and super_read_only is OFF; native MySQL decides
applicability. Reset does not silently change that server setting.
Qualification uses an isolated real group, preserves returned observations and
removes its own servers/network. Single-node refusal tests do not establish
multi-member election, mode-change or replicated-data correctness.

Stored libraries and loadable functions
---------------------------------------

Stored libraries are database-scoped native objects, separate from routines and
server loadable functions. MySQL 9.7 supplies CREATE LIBRARY (JAVASCRIPT, optional
IF NOT EXISTS/comment, text or exact binary source), ALTER LIBRARY COMMENT, SHOW
CREATE LIBRARY and DROP LIBRARY. Forms do not invent body/language replacement
through ALTER. Native runtime availability and execution of imported code remain
server decisions. Discovery preserves LIBRARIES facts, SHOW CREATE and native SQL mode.
SHOW CREATE LIBRARY does not expose original client charset/collation; decoded
Unicode definitions are explicitly exported under UTF8mb4, with that limitation
recorded rather than claiming preservation of hidden character context. Binary
bodies retain the native hexadecimal representation. DDN native exports retain libraries and ROUTINE_LIBRARIES
edges, ordering captured dependencies or reporting external prerequisites.

Loadable functions have server scope and distinct scalar/aggregate selection,
STRING/REAL/INTEGER/DECIMAL return types and exact native SONAME. CREATE and DROP
use their native statements on an independently owned connection verified to
have no default database; stored-routine ALTER is unavailable. Borrowed user
sessions are refused. This prevents a stale DROP FUNCTION from falling back to
a same-name database stored routine when the global registration has vanished. Discovery reads
persistent mysql.func and runtime performance_schema.user_defined_functions,
keeping their native registration origins distinct. A runtime function installed
by a component/plugin is inspect-only through this branch and is removed through
its owning lifecycle. No native library is downloaded, fabricated or silently
substituted. A successful registration does not prove the library's own runtime
services are configured; ordinary SQL exposes native execution diagnostics.

The reference 9.7 source also parses masking policy statements, but its community
runtime requires an unavailable object-policy component to implement policy DDL.
Grammar presence alone must not expose a working masking-policy administration
feature or claim successful policy deployment. Native SQL diagnostics remain
available; support for an admitted policy component needs its exact native
catalog/operation contract and qualification rather than a placeholder.

Reviewed DDN library deployment
-------------------------------

Catalog DDN libraries support exact-target CREATE, COMMENT-only ALTER and
explicit name-confirmed DROP through the durable review/apply pipeline. Native
PREPARE validates the complete statement without execution. Body, language or
creation-context replacement through ALTER is refused; it is not silently
implemented as DROP/CREATE. Existing targets use an advisory lock and fresh
SHOW CREATE/SQL-mode comparison. External DDL is not fenced, so a guaranteed
exclusive change requires an operator-controlled DDL maintenance window.
Native acknowledgements, uncertain outcomes, restart and non-replay follow the
same per-operation durable receipt rules as table/view deployment.

Reviewed DDN events and time zones
----------------------------------

Event metadata preserves native SHOW CREATE EVENT SQL mode, client charset,
connection/database collation and event time zone. Native SQL export sets and
restores the event time zone explicitly; an absent time-zone observation blocks
event export rather than reinterpreting schedule timestamps in the caller's zone.
Reviewed CREATE/ALTER/DROP uses the exact event identity, complete native
schedule/body/definer and recorded session context. No replacement or rename is
inferred. Native PREPARE validates without scheduling or running an event.
Advisory locks serialize cooperating applications and fresh SHOW CREATE/context
checks refuse observed drift; external DDL and scheduler activity remain unfenced.
An event may execute, expire or remove itself according to native scheduling.
A success acknowledgement remains committed even if later rediscovery cannot
find the event; an uncertain outcome is never automatically retried.

Complete native event forms
---------------------------

MySQL event forms expose schedule, completion, ENABLE/DISABLE/DISABLE ON REPLICA,
body, comment/explicit comment clearing, exact optional definer and event time
zone. ALTER selectors default to UNCHANGED; changing a comment must not reset
status, schedule, body or completion. CREATE supports IF NOT EXISTS. RENAME uses
ALTER EVENT RENAME TO with an exact optional destination database, and DROP
uses the discovered database/name. Native definer and scheduler rules remain
authoritative; omitted DEFINER follows MySQL's own ALTER behavior.
Administration owns an independent connection and refuses a borrowed transaction.
An explicit time zone is set with a bound session value before native DDL.
Discovery retains complete visible EVENTS facts and SHOW CREATE/context.

Explicit graphical column renames
---------------------------------

The unchecked "Include graphical column renames" choice admits changed column
labels only with the original exact field UID. New names cannot rebind existing
native columns, and omissions never imply deletion. Up to 128 renames per table
are translated into explicit mysql_change.rename_columns for ordinary reviewed
CHANGE COLUMN deployment. Native defaults, literal text, index/constraint names
and table options are preserved. Quoted column references in generated/default
expressions, index lists, checks and foreign-key source lists are reconciled;
self-referencing targets are updated while other-table targets remain unchanged.
Simultaneous native-source and graphical rename edits require separate native
reconciliation. Native PREPARE and reviewed durable application remain required.
Changes MySQL propagates into other tables require fresh capture/review of those
tables; a later batch baseline conflict is never bypassed or automatically retried.

Unadmitted design intent must remain visible
-------------------------------------------

The relational handoff compares native relationship endpoints, identities,
kind/enforcement and exact decoded facts. Changed or newly authored relationships
require explicit native foreign-key design admission below, or reconciliation
in the owning table definition; they must not be silently ignored or represented as deployed.
Pure diagram label/layout changes remain presentation. Rebinding diagram aliases
without changing native endpoints is presentation as well. Database-root native
definition/removal changes are blocked with a native-administration requirement
until a database deployment adapter is admitted; skipping the root is not success.

Foreign-key dependencies during locked application
-------------------------------------------------

An altered existing table locks its exact quoted source with WRITE and the
distinct parent tables referenced by baseline/desired foreign-key clauses with
READ, in deterministic order. Self references do not duplicate the owner lock.
This preserves the existing table-lock baseline contract while admitting native
foreign-key changes that need parent tables opened under LOCK TABLES. Malformed
or ambiguous parent identities refuse dispatch. Native privilege, parent index,
column compatibility and existing-data checks remain authoritative. All locks
are released before retiring the independently owned application connection.

Native MySQL 9.7 can reject DROP/ADD of a same-name foreign key within one ALTER
with duplicate-constraint error 1826, even after PREPARE acceptance. Review
therefore requires an explicit new constraint name or separately reviewed native
DROP and ADD, with the intermediate unconstrained state visible. It never
disables foreign-key checking or silently splits one reviewed statement. Column
renames whose only FK difference is the corresponding native column references
retain their FK identity and use MySQL's automatic reference propagation.

Explicit relational foreign-key design intent
--------------------------------------------

The unchecked "Include foreign key design changes" choice admits native ref
relationships with database enforcement, exact visible source/target tables and
bounded unique UIDs. The relationship x_record.native_json carries an exact JSON
object with format scratchrobin.mysql.foreign-key@1; action create or replace;
name; ordered columns and referenced_columns; and optional native on_delete and
on_update rules. Existing relationships retain their original native UID/facts
while specifying replacement intent. Removal instead requires action drop and
confirmation equal to the exact original constraint name. Missing relationships
are selection omissions, never drops. Alias/label/layout changes remain display.

The handoff adds/replaces/removes the exact owning table FOREIGN KEY clause,
rejecting identity collisions, ambiguous original facts and conflicting native
edits. It then uses normal native PREPARE, reviewed receipts, parent locks and
rediscovery. Same-name replacement retains the native restriction above; users
choose a new name or separate reviewed DROP/ADD. Parent/source columns, types,
indexes, privileges and existing data are validated by native MySQL. Selecting
this option does not execute or relax any native constraints.
