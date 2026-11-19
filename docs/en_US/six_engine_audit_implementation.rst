Six-engine audit implementation: backend contract changes
=======================================================

This is an implementation overlay for the completed PostgreSQL, MySQL,
MariaDB, Firebird network/embedded, SQLite and DuckDB audits. It does not
replace their findings or establish six-engine completion. The final audit
queues contain 250 records, including qualification, platform/human acceptance,
post-beta and owner-deferred work. No UI presentation changes are included.

The current item-level status and verification receipts are retained in
``/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/``.
The immutable audit records and consolidated worklist remain in
``/home/dcalford/Sandbox/codex-work-area/cdeadmin-backend-audit/``.

Current shared-gate status
--------------------------

The owner confirmed application of the shared UI/schema repair. The earlier
18 descriptor errors and 63 shared family-render failures quoted in the batch
history below are resolved by that repair; they are historical qualification
results, not current outstanding failures. See descriptor_gate_repairs.rst and
the post-application ui-repair-applied-* receipts in the designated work area.
This correction does not close unrelated engine audit or human/platform work.

Existing administration transport
---------------------------------

Use the registered endpoint's authenticated ``NODE-server.cde_workspace_id``
route with the existing ``action`` and ``request`` envelope. Database operations
retain the explicit ``database_target_id``. The actions affected here are
``visual_admin_validate``, ``visual_admin_plan``, ``visual_admin_apply`` and
``visual_admin_rows``. Preserve the server-retained ``plan_id`` and
``plan_digest`` returned by planning; apply requires both and
``confirmed: true``. A native error or conflict requires inspection and a new
review rather than automatic replay. These changes add no alternative SQL
execution endpoint or client-side engine dispatcher.

SQLite: SQ-AUD-16
----------------

``table.create`` now admits the descriptor's boolean ``strict`` and
``without_rowid`` fields through the production field contract, including
false defaults. They survive facade validation, planning and native apply.
Existing native primary-key requirements for WITHOUT ROWID remain in force.
STRICT is gated using the descriptor's minimum version and the actual SQLite
module runtime; requesting it below 3.37.0 returns ``unsupported_version``.
The supported floor remains 3.35.0. No additional descriptor fields are
implicitly admitted by this change.

Qualification covers facade/native create on 3.35.0, 3.45.1 and 3.53.0,
and authenticated validate/plan/apply with independent native flags read-back
on the current reference runtime. Keep booleans typed; dropping either field
from a draft is not a workaround for failed validation.

DuckDB: DU-AUD-42
----------------

``visual_admin_rows`` continues returning
``cdeadmin.relational-row-page.v1``. Each row contains ``values`` and an opaque
``identity_token``. DuckDB values now use the same exact Arrow-backed output
codec as the Query Tool. For example TIMESTAMP_NS carries a temporal envelope
whose ``ticks`` is a decimal string; HUGEINT uses an exact decimal string.
Nested structures and tagged UNION values retain their existing exact output
representations. Do not narrow ticks to JavaScript Date or wide integers to
JavaScript Number. NULL UNION and a tagged member containing NULL are distinct.

An update passes ``draft.selector.identity_token`` and typed
``draft.changes`` to the existing table update operation. The token binds the
original native values privately on the server. The server reconstructs exact
native comparisons with bound scalar parameters; private binding trees and
DuckDB type objects are never public request fields. No client-supplied SQL
predicate or replacement original-value payload is accepted.

The reader uses the original connection, including a caller-owned transaction,
and restores its Arrow output setting. Reading does not commit pending work.
Native tests cover precision, unrelated update, rollback, a one-nanosecond
conflict, nested/container/opaque values, helper-name shadowing and single
observation of generated values. Authenticated JSON row/read-review-apply
qualification covers a 21-column native fixture. This is not full DU-AUD-42
acceptance across every type, delete and authenticated retained-session case.
DU-AUD-43's richer new-value input/inverse codecs remain outstanding; exact
output and private original binding do not implement those codecs.

MariaDB: scope, FLAGSET and server-DDN dependency
------------------------------------------------

For the existing ``system-variable.set_global`` operation, native
``VARIABLE_SCOPE=SESSION`` means global and session applicability; it is now
admitted alongside GLOBAL. SESSION ONLY, unknown and missing scope are refused.
Native read-only and bounds checks remain active. This does not add a session
assignment workflow or qualify every installed variable.

``draft.value_mode`` supports ``VALUE``, ``DEFAULT``, ``BITMASK`` and ``FLAGS``. FLAGSET
``VALUE`` accepts a string using actual native flag names from
``ENUM_VALUE_LIST``: comma-separated ``flag=on``, ``flag=off`` or
``flag=default``, and at most one bare ``default`` token. Empty string is the
native no-op. Unknown/duplicate flags, malformed assignments and non-string
values are refused. FLAGSET is not an ENUM/SET list of bare option names.
DEFAULT mode continues to compile native DEFAULT. BITMASK mode is restricted
to FLAGSET targets and reads ``draft.bitmask`` as canonical unsigned decimal
text (not a JSON number). It emits an unquoted native integer expression;
VALUE text such as ``"1"`` retains its textual meaning. The descriptor exposes
the separate bitmask text field only in BITMASK mode. The bound is derived
from the native option count including the final ``default`` entry, rather
than the number of named flags; unsupported/incomplete metadata is refused.
Current numeric admission supports 2 through 64 metadata entries; larger
numeric profiles remain unqualified.

FLAGS mode reads ``draft.flags`` as a list of ``{flag, state}`` rows, with
``state`` exactly ``on``, ``off`` or ``default``. Grid ``_id`` is ignored;
other extra row keys are refused. ``draft.reset_defaults`` is a boolean,
default false. When true, the native bare ``default`` token precedes the
selected assignments. Empty rows with false reset compile the native empty
string no-op. Unknown/duplicate flags and malformed rows are refused.
Only FLAGSET targets admit FLAGS or BITMASK. The descriptor exposes a flag
grid and reset checkbox in FLAGS mode. Names come from the target's native
``ENUM_VALUE_LIST``; the final ``default`` token is a reset choice, not a
flag row. Partial assignments preserve unselected flags through native SET,
rather than rebuilding an application's copy of the current mask.

An owned MariaDB 12.2.2 fixture qualified production validation/plan/apply and
independent GLOBAL read-back for sort_buffer_size, optimizer_switch and
optimizer_trace, plus native SESSION ONLY refusal. Numeric masks 0–3 on
optimizer_trace passed production apply and independent read-back; 4 is refused.
A separate native probe confirms quoted decimal text is refused by MariaDB.
Six descriptor-generated FLAGS drafts qualified native partial on/off,
reset-only, reset-plus-override, per-flag default and empty no-op, with exact
independent GLOBAL read-back and an existing session remaining unchanged.
The repeatable runner is ``tools/cdeadmin_mariadb_variables_qualification.py
--output <work-area>``. Broader restricted-role, authenticated HTTP,
original-session assignment and full FLAGSET qualification remain outstanding.

Server-DDN preview/application now imports the actual MariaDB provider from
``providers.mysql_family.provider``. The exact MariaDB registration, provider
instance and owner/permission guards are preserved. Existing server-DDN
preview, review, apply and receipt contracts are unchanged. The regression
checks dependency resolution and wrong-engine/provider refusal; authenticated
server-DDN lifecycle and native effect acceptance remain outstanding.

MariaDB: automatic completion and diagnostic preservation
--------------------------------------------------------

``source_complete`` / the native editor completion contribution no longer
runs catalog queries on the caller's MariaDB session. Opening a new session
captures server UID, effective authenticated account, native version and
connection ID before the handle is returned. Completion checks its managed
identity locally and opens a separate unpooled, non-reconnecting connection
using the registration's existing route and secret handling. The peer must
match the admitted server/account/version and have a different connection ID.
There is no fallback to the caller's connection if observation fails.

The existing ``editor_context`` response reports
``observation_source=private-native-peer``, ``original_session_commands_sent=0``,
``original_diagnostics_preserved=true`` and
``original_session_catalog_binding_validated=false``. ``complete`` is false:
this is committed-catalog observation, not the caller's current role, SQL mode,
charset, default schema, temporary objects or uncommitted DDL. Peer settings
are held under ``context.metadata_peer_context``; their source-context keys
are removed from ``context`` and
``context.original_session_context_observed=false``. A denied observation for
``retained-session-overlays`` records these limits. UI consumers must retain
that incomplete-coverage indication and must not relabel peer settings or
objects as current original-session observations. These symbols do not
provide mutation authority. Source-context overlays remain separate work.

Native peer failure yields a bounded source-free error and no source-session
metadata substitution. Peer release failure also refuses a successful result.
The source is neither pinged nor committed/rolled back for completion. A
changed native connection ID or unavailable opening identity refuses the
request; automatic source reconnect/replay is not introduced.

``tools/cdeadmin_mariadb_completion_qualification.py --output <work-area>``
qualifies the production provider callback on owned MariaDB 12.2.2. Native
warning 1365, error 1054 and a repeated warning remained unchanged across
completion; an existing savepoint and uncommitted InnoDB row survived, and an
independent connection continued to see no committed row. Unit tests cover
peer identity/account/version mismatch, connection/catalog/release failure,
changed source identity and source-handle alias refusal. Native restricted
accounts, interruption, authenticated HTTP and other supported runtimes
remain to be qualified; this is not full editor or engine completion.

MariaDB: SQL datatype completion
--------------------------------

The native editor now uses ``mysql_family/mariadb_types.py`` for SQL type
suggestions. The original dialect contract's grammar-production inventory is
retained as source evidence; productions and lexer symbols are no longer
interpreted as column-type spellings. The SQL profile includes integer and
numeric aliases, temporal types, character/binary types and their multiword
forms, LOB/JSON types, ENUM/SET, spatial types and VECTOR. UUID, INET4 and INET6
require an ACTIVE row in native ``information_schema.PLUGINS`` with
``PLUGIN_TYPE='DATA TYPE'``. NUMBER, VARCHAR2, RAW and CLOB additionally require
ORACLE in the observed SQL mode. A runtime outside the qualified 12.2.2 profile
returns an unavailable type-profile observation rather than borrowing its
suggestions. This does not change the engine's declared version policy.

Each type resource keeps its normal ``display_name`` / ``display_path`` and
has ``native_type_keyword=true``, including multiword spellings. Its
``native_type_syntax`` contains ``parameter_requirement`` (none, optional or
required), human-readable ``parameters``, a legal example column-type clause
in ``example_sql``, a semantic ``family``, an ``availability`` gate and
``semantics_authority=native-type-handler-and-sql-mode``. Parameter notation
is explanatory text, not SQL to execute. Examples do not replace native
validation of chosen dimensions, precision, lengths, members or modifiers;
column value codecs are a separate concern. Mode-sensitive type semantics
remain native, including REAL, DATE and Oracle BLOB.

The runtime also reports active ASSOCIATIVE_ARRAY and SYS_REFCURSOR plugins.
Their bare types are not column types: the native fixture refused both in
both modes. Their routine-local completion contexts remain unimplemented,
reported under ``native-routine-type-contexts``; neither is mislabeled as an
absent engine feature. Other unknown active type plugins are explicitly
recorded as unavailable under
``native-type-plugin-parameters`` and omitted until their parameter grammar
is qualified. Denied native plugin discovery omits plugin-dependent types
and keeps the observation incomplete while retaining known core suggestions.
The type observations describe the connection actually inspected. Automatic
completion still reports the independent peer's mode under
``context.metadata_peer_context`` and does not claim it is the caller's
current SQL mode. UI consumers must retain that source-context limitation.

``tools/cdeadmin_mariadb_types_qualification.py --output <work-area>``
qualified all 162 example clauses across default and Oracle modes using
native temporary-table creation and column-type read-back. It also checked
162 omitted-parameter acceptance/refusal decisions, the four default-mode
Oracle-alias refusals, four routine-type column refusals, and actual native
editor type resources. Routine-local completion, additional installed type
plugin grammars, native restricted-account/interruption tests,
authenticated HTTP and other runtime profiles remain outstanding.

MariaDB: installed-variable and function completion
---------------------------------------------------

Native editor metadata now discovers MariaDB variables from
``information_schema.SYSTEM_VARIABLES``, UDF registrations from ``mysql.func``
and ACTIVE FUNCTION plugins from ``information_schema.PLUGINS``. No MySQL
Performance Schema UDF query is substituted. Each section has an independent
native observation: ``native-variable-metadata``,
``native-loadable-functions`` and ``native-plugin-functions``. A native
permission refusal records its numeric code and makes coverage incomplete;
other permitted sections remain available. Transport/invalid-query failures
are refused rather than converted to an empty registry. Normal completion
uses the private authenticated peer described above and never invokes UDFs.

Variable resources use ``resource_kind=system-variable`` and a one-part native
name. ``native_variable`` contains ``scope``, ``data_type``, ``read_only``,
``minimum``, ``maximum``, ``block_size``, ``enum_value_list`` and
``metadata_origin=information_schema.SYSTEM_VARIABLES``. Native labels and
bounds are preserved. MariaDB SESSION means both global and session scope;
SESSION ONLY, including its space, is distinct from GLOBAL. Current/default
values and configuration paths are not selected or exposed; their observed
flags are false. This metadata does not authorize an assignment or replace
native read-only/type/value checks and retained operation review.

Both function registries produce ``resource_kind=function`` with a one-part
name and ``native_function`` provenance. UDFs report ``origin=mysql.func``,
``registration_observed=true``, their native return-type code/name and native
``kind`` (including aggregate), and ``scope=global-registration``. A registry
row alone does not prove the library loaded successfully, a usable signature
or callability. Those flags stay false, and
``native-loadable-function-execution-state`` is explicitly unavailable when
registrations exist. FUNCTION plugins report their ACTIVE native status,
``scope=global-plugin`` and ``origin=information_schema.PLUGINS``; signatures,
return types and invocation are not inferred. No shared-library paths or
source code are exposed. Discovery never executes third-party function code
to test it. Native resource observations refresh on each request, so removed
registrations and plugin variables are not held as permanent suggestions.

The UI group must extend the verified MySQL-only handling in
``web/pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion.js`` for MariaDB's
``system-variable`` resources and multiword ``native_type_keyword`` resources.
The current variable completion filter in ``editors/mysqlVariables.js`` uses
MySQL's ``SESSION_ONLY`` spelling; MariaDB's native scope labels must be
interpreted correctly without changing the backend facts. Registered UDFs,
ACTIVE plugins and stored routines need distinct provenance/availability
labels. ``native_type_syntax`` supplies type parameter hints. Preserve all
incomplete observations and do not present ``metadata_peer_context`` as the
caller's current SQL mode, schema or role. The current renderer defaults a
missing SQL mode to an empty mode; that is not a verified original-session
context. Context-dependent quoting/suggestions need an explicit unobserved
state. These are UI handoff requirements; frontend implementation has not
been changed or accepted by this backend work.

``tools/cdeadmin_mariadb_installed_completion_qualification.py --output
<work-area>`` builds a small task-owned UDF fixture, loads it only into an
owned MariaDB 12.2.2 container, independently invokes that fixture, and checks
registration removal. It checks added/removed native audit-plugin variables,
ACTIVE FUNCTION plugin facts and an actual restricted account's mysql.func
refusal with warning preservation. Native aggregate-UDF execution,
FUNCTION-plugin enable/disable/failure lifecycle, interruption, authenticated
HTTP and broader version/context qualification remain outstanding.

MySQL: engine STATUS, LOGS and MUTEX diagnostics
----------------------------------------------

The server operations ``show_engine_status``, ``show_engine_logs`` and
``show_engine_mutex`` are declared in MySQL's capabilities and operations
JSON and use the existing visual administration validate/review/apply path.
Each takes ``engine_scope`` (ENGINE or ALL, default ENGINE),
``private_data_confirmed`` (boolean true required) and ``confirmation`` (the
exact selected server display name). ENGINE additionally takes ``engine``
(the installed engine name, default InnoDB). ALL omits ``engine`` or supplies
an empty value; a conflicting individual name is refused. The backend removes
the single-engine default from ALL admission. Existing requests without
``engine_scope`` continue selecting ENGINE. The target is the observed native
server resource, including its UUID. No raw SQL is accepted. These are
administration-authorized private inspections. STATUS and MUTEX
require native PROCESS; LOGS requires native FILE. The native server checks
current effective privileges; application ownership does not grant them.

Review observes server UUID/version, authenticated/effective principal, active
roles and installed/enabled engine. ALL records a complete bounded native
engine inventory, including disabled states, and emits one native SHOW ENGINE
ALL statement. Execution rechecks those observations on
a dedicated connection, with pooling disabled and five-second connect/read/
write timeouts. It does not borrow a caller's transaction. The engine name is
quoted as an identifier and independently checked through bound native catalog
selection. A changed identity or unavailable engine requires a new review.

The apply response's ``provider_result.engine_diagnostic`` contains ``columns``
(Type, Name, Status), native text ``rows``, engine/execution identity and UTC
observation time. Treat this text as private content: it may include other
sessions' SQL, transaction details and host paths. The existing authenticated
route uses no-store responses. The UI group owns its presentation.

ENGINE output is bounded to 256 rows and 1 MiB of UTF-8 text; ALL output to
4096 rows and 8 MiB. Inspect
``complete``, ``truncated``, ``native_acknowledged`` and ``native_completion``.
Truncation reports ``unconfirmed-output-truncated`` rather than claiming a
native completion acknowledgement. A complete empty result means only
``native-no-rows-returned``; some native engine handlers provide no rows for
LOGS or MUTEX. It does not prove implemented handler support or an empty log.
``provider_result.connection_release`` reports cursor and connection cleanup
separately. A failed connection release leaves the handle owned by the client
for subsequent cleanup and does not erase an acknowledged native result.
Native failures retain error codes and dispatch/acknowledgement state without
including source text in the error message. No operation is automatically
replayed.

``tools/cdeadmin_mysql_engine_diagnostics_qualification.py`` runs the owned
native core or authenticated HTTP stage outside source. The core stage covers
both pure and C MySQL connector implementations, individual and ALL native statements,
missing-engine and restricted-account refusal, and connection cleanup. Run
``tools/reference_engine_demos/supplement_mysql_engine_diagnostics_contract.py``
with that completed core receipt to add the three exact-version dialect tasks;
the supplement refuses incomplete runs, failed cleanup and changed source
hashes. Refresh the immutable snapshot before the HTTP stage. Dialect task
coverage is deliberately mandatory; adding descriptors alone cannot activate
a generated SQL operation.

PostgreSQL: PG-AUDIT-FIELD-01
---------------------------

Existing-table column/constraint grids are explicitly refused during table
ALTER rather than ignored beside a successful comment or other change. This
covers ``columns``, ``primary_key``, ``foreign_key``, ``check_constraint``,
``unique_constraint`` and ``exclude_constraint``. Their table-form descriptors
now declare ``editable_after_create: false``. Table creation still uses them.
Route existing objects to their separate column/constraint provider nodes.
Refusal occurs before any compiled combined mutation can execute; the native
column/constraint capabilities are not removed.

Native catalog capture now reads ``toast_reloptions`` from the actual TOAST
relation. Table facts expose ``toast_autovacuum_enabled`` (t/f/x),
``toast_autovacuum``, ``toast_vacuum_settings`` and
``toast_options_observed``. Materialized-view facts read those same native
options. ALTER consumes ``toast_autovacuum_enabled`` and the
``vacuum_toast`` name/value rows, with native SET/RESET. A custom-options reset
requires observed TOAST state; refresh when it was not captured. Parent-table
and TOAST options remain distinct. Explicit parameter rows are honored even
when a custom-options checkbox is omitted. Schema/native validity and
privileges remain PostgreSQL's authority.

Owned PostgreSQL 18.3 qualification used production capture and compilation,
executed native SET/RESET, independently read the TOAST relation and verified
combined grid/comment refusals. Authenticated facade and supported-version
qualification remain outstanding. The separate generated-column, temporal
constraint and other PostgreSQL audit records remain open.

PostgreSQL: PG-AUDIT-IDENTITY-01, guarded table DROP
---------------------------------------------------

Ordinary and partitioned-table DROP now retains a server-observed identity in
``provider_payload.destructive_identity`` and exposes it in
``command_preview.native_target_identity``. This is server-retained review
state, not an additional client input. It contains the native database identity,
server address/port/postmaster start, available system identifier, current
principal/role, schema/table OIDs, exact names and the pg_class row generation.
Review uses an independently owned connection and retains no native table lock
while a person considers the plan.

Apply opens its existing independent administrative transaction, takes
``LOCK TABLE ONLY ... IN ACCESS EXCLUSIVE MODE NOWAIT``, and rechecks the
retained identity while holding that lock. The same transaction then executes
DROP and commits. Same-name replacements, moved/renamed objects, changed
catalog generations and changed native execution identities require a new
review. A busy native target returns a native lock refusal, without an
unguarded fallback or automatic retry. Exact quoted names, including whitespace,
remain exact. Old plans without this binding are refused.

The existing visual administration rejection contract reports the refusal as
known with ``unknown_outcome: false``, ``stage: provider_rejected`` and a
``rejection.message``. Native lock/permission refusals retain SQLSTATE; an
application identity conflict carries no invented native SQLSTATE. The UI must
show the refusal and refresh/new-review requirement. No new input field,
frontend engine branch or raw-SQL form is introduced.

Native LOCK has an important additional admission requirement. On PostgreSQL
18.3, any of MAINTAIN, UPDATE, DELETE or TRUNCATE permits this lock; native table
ownership supplies privileges, but schema ownership alone does not. The suite
proves that a schema-owner-only role can perform direct native DROP while this
guarded path refuses LOCK with 42501. That privilege-equivalence gap remains
open: do not call this full native DROP coverage, grant privileges automatically,
or fall back to unsafe name-based DROP. Other destructive object kinds and
supported-version/authenticated route qualification also remain outstanding.

``tools/cdeadmin_postgresql_drop_identity_qualification.py`` runs a uniquely
owned PostgreSQL 18.3 fixture, the real provider callbacks and competing native
transactions. Its current suite passes 22 checks, including 15 native cases:
ordinary/partitioned DROP, replacements before and after review, rename/move,
catalog drift, lock contention, lock retention through dispatch, unrelated
caller transactions, table-owner and schema-owner privilege cases, quoted names,
and a second cluster with genuinely matching database/schema/table OIDs. The
cross-cluster case allocates ordinary native objects to establish the collision;
it does not edit system catalogs or force OIDs. Both servers' cleanup is checked.
This is not HTTP or other-version qualification.

Firebird embedded: FB-EMB-database_statistics
---------------------------------------------

The embedded profile now surfaces ``database.database_statistics`` through the
shared Firebird typed form and the existing authenticated visual-admin route.
It remains a registered database-target operation. The local form title and
notes identify the ScratchRobin host and approved local file; it does not open
the network server-service workspace or request network credentials. Other
embedded Services operations remain excluded until implemented and qualified.

Inputs remain ``statistics_flags`` (native enum-name list), ``tables`` (shared
grid rows with an exact ``value`` table name) and optional ``role``. The normal
backend form codec produces native table-name lists. Runtime and filesystem
permissions are both required. The service attachment is forced to
``Providers=Engine13`` and literal local ``service_mgr``. Host/port/wire/auth
options and credential references are refused. A service request cannot select
a database different from its approved route. SQL compiler equivalence is
preserved: local service review/execution lives in the native query client,
not an alternative SQL compiler.

The existing preview's ``service_authentication_requested`` identifies
``attachment_mode: embedded``, ``execution_host: application-local`` and
``network_authentication: false``. Authorization remains a native action and
filesystem decision; a requested role is not proof of authorization. Apply
returns ``provider_result.driver_observation`` with the existing Firebird
service result schema, native output lines, output truncation and separate
service-handle/connection release fields. Local results also carry the execution
host, Engine13 provider and the reviewed file identity. Device/inode identifiers
are decimal strings. File replacement detected before apply is a known provider
rejection requiring refresh/new review, with no automatic replay.

Completion has precise limits. ``server_completed`` records the Services task
return/wait; ``native_utility_exit_code`` is null and
``native_utility_exit_code_observed`` is false. Do not interpret this as a
separately observed utility exit code. ``file_identity_race_fenced`` is false:
the pre-dispatch device/inode check does not close a replacement race during
dispatch. Native-failure/interruption, race fencing, broader flags and platform
acceptance remain open; this audit record is partially implemented.

The owned Engine13-only native qualification exercises header statistics,
a Unicode table filter, host/credential refusal, same-path replacement refusal,
independent original-data read-back and cleanup. No network server is started.
The reference runtime remains byte-identical. A separate filename probe records
that creation requested ``Trailing.fdb `` while native MON$DATABASE reported
``Trailing.fdb`` and the requested pathname was absent. Statistics refuses the
missing requested file; exact trailing-space creation/attachment semantics
remain unqualified rather than being silently treated as equivalent paths.

``tools/cdeadmin_firebird_local_statistics_qualification.py`` repeats that native
scope. The existing embedded contract gate was rerun against current source,
including attachment, transaction, monitoring, profiler and event observations;
its generated dialect/metrics receipts were refreshed. This does not transfer
network or cross-platform qualification. Authenticated HTTP evidence is retained
separately in the implementation work area.

Verification limits and retained work
-------------------------------------

The descriptor gate still fails on the same 18 baseline descriptor/schema/lint
errors. Its separately executed family tests pass with native-environment
skips. Do not report the full gate as passed. Source hashes, commands, native
versions, DDN revision and individual receipts are recorded in the work area.
The remaining MySQL and Firebird audit work is not completed by these changes.
No Windows/macOS or human presentation acceptance is claimed. ScratchBird
monitoring-history qualification remains deferred by owner direction.

Five-issue backend batch
------------------------

The following fixes were handled sequentially. Their qualification is scoped
below; this does not close the other engine, UI presentation or platform queues.

* ``MY-AUDIT-INVENTORY-GENERATOR``: the current source already contained the
  repaired Bison/dispatch reader. Verification against the read-only 9.7.0
  source independently matched all 168 native dispatch IDs, 144 statement
  alternatives and 79 SQL type spellings, including exact source locations.
  A new committed-category regression protects the separation of dispatch
  IDs, grammar alternatives and diagnostics and refuses the old prose ``Note``
  item. Historical 987-label totals are not product-completion denominators.
  Source packet admission remains structurally complete, not release-proven.
* ``MY-AUDIT-REGRESSION-COUNTS``: 31 tool entries are reconciled as 25
  engine-specific openers and six shared BI/design openers. The immutable audit
  baseline currently exposes 2581 graphical operation declarations; this
  implementation adds the three MySQL engine diagnostics and embedded Firebird
  statistics, giving 2585. Tests retain all fail-closed structural and native
  surface equality checks and now verify the exact per-profile counts too.
  Declaration counts do not qualify native product functionality.
* ``PG-AUDIT-COLLECTOR-01``: both registration admission and independent native
  attachment use the existing PostgreSQL support policy instead of equality
  to 180003. Samples record ``identity.server_version_num`` from the actual
  collector connection. The I/O source is versioned: PostgreSQL 15 reports the
  unavailable native view as unsupported; 16/17 collect their native columns
  with their native op_bytes unit and no invented byte counters; 18 retains
  read_bytes/write_bytes. The
  ``io.unavailable_columns`` list identifies absent byte fields on 16/17.
  The policy and native I/O column definitions were checked against the
  PostgreSQL versioning policy and versioned monitoring documentation:
  https://www.postgresql.org/support/versioning/,
  https://www.postgresql.org/docs/16/monitoring-stats.html and
  https://www.postgresql.org/docs/18/monitoring-stats.html.
  Unit admission/complete-sample tests exercise supported minor variants;
  actual native sampling is qualified on the owned 18.3 runtime. Other server
  binaries remain unrun rather than being called qualified. Kerberos,
  arbitrary installed metric sources and wider monitoring qualification are
  separately tracked.
* ``SQ-AUD-02``: generic file alteration now refuses ``synchronous`` before
  dispatch. The source-session facade action ``sqlite_connection_settings``
  accepts an owner-bound studio ``session_id`` and typed ``request``:
  ``{operation: inspect}``, ``{operation: review, value: OFF|NORMAL|FULL|EXTRA}``
  or ``{operation: set_connection_synchronous, value, expected_code, confirmed:
  true}``. Review returns canonical ``native_statement``, observed
  ``expected_code`` and ``ready_to_apply``. The mutation requires execute and
  administer permissions, an idle admitted original handle, no pending caller
  transaction, exact current code and explicit confirmation. It reads back the
  native effective value. Results state ``scope=original-connection-main``,
  ``file_persisted=false`` and ``future_connection_defaults_changed=false``;
  no caller commit/rollback is requested. Settings mutations conservatively
  invalidate retained review work revisions; inspect and review do not. Only
  the original main connection is
  admitted; attached-schema/default-policy management is not implied. The
  ``set_connection_synchronous@database`` descriptor supplies the typed fields
  for this session task; it must use this facade transport rather than the
  independent generic object-operation executor. The existing file property
  form explains this boundary. UI must bind the session, preserve review
  evidence and display native read-back, rather than label this a durable file
  setting. Three native runtimes (3.35.0, 3.45.1 and 3.53.0) qualify original,
  independent and newly opened handle isolation, stale/pending refusal and
  savepoint/data preservation. The corrected database.alter dialect task now
  includes only native file properties and carries fresh scoped evidence;
  historical receipts are not relabeled.
* ``DU-AUD-41``: index.create accepts an ordered ``terms`` grid of
  ``{kind: column|expression, value: text}``, optionally carrying grid ``_id``.
  Nonempty terms and legacy columns are mutually exclusive. The native
  ``SQLExpression`` parser admits one expression without evaluating it, then
  the provider generates one CREATE INDEX statement. Bounds are application
  policy: 64 terms, 65536 UTF-8 bytes per expression. The method contract admits
  the qualified core ART registration and no WITH options: the native ART
  creation binder does not implement those arbitrary options, so silently
  accepted options are refused by this adapter. Preview reports
  ``native_index_capabilities`` with admitted methods/options and explicitly
  does not claim to enumerate extension methods. Non-ART methods need their
  native extension adapter, tracked separately under installed-extension
  coverage; their absence is not an engine impossibility. Native tests qualify
  descriptor/facade review/apply, mixed ordered expressions and columns,
  unique-expression enforcement, missing-column refusal, parse-only planning,
  query correctness and preservation through the existing DDN index replay
  validator. Native index creation does not promise an optimizer index scan
  for an expression predicate. Full rebuild/dependency/extension-index and
  frontend presentation acceptance remain separate work.

SQLite native create controls: SQ-FORM-1/2/3/4/6 (SQ-AUD-17)
------------------------------------------------------------

Five existing decisions in ``sqlite-final-audit/ui-gap-decisions.json`` now
have backend implementations and typed descriptor contracts. SQ-AUD-17 remains
partially implemented: SQ-FORM-5 (reviewed table rebuild on alter) and SQ-FORM-7
(view replacement) are not closed by this batch. Human presentation acceptance
and Windows/macOS qualification remain with their owning teams.

All five use the existing visual administration validate/plan/confirmed-apply
transport described above. Native SQL previews remain part of review; preserve
plan identity and digest and never automatically replay a refused mutation.
The forms in ``ui_descriptors/sqlite/forms/`` are the authoritative UI hooks:

* SQ-FORM-1, ``index.form.json``: ``terms`` is an ordered grid of
  ``{kind: column|expression, value, collation?, order: ASC|DESC}`` and
  ``predicate`` is an optional native WHERE expression. Legacy ``columns``
  remains accepted; do not send both nonempty terms and columns. SQLite owns
  expression binding, determinism and native index eligibility. Quoted names
  are preserved, predicates/expressions are fenced against escaping their
  clause, and the native executor admits one complete statement. The native
  acceptance tests verify planner use, unique enforcement and inactive-row
  exclusion, rather than merely accepting generated SQL.
* SQ-FORM-2, ``table.form.json``: select ``variant: virtual`` and an installed
  ``module``. ``module_columns`` maps to backend ``columns``. Spatial modules
  receive their ordinary column names and ``auxiliary_columns``; geopoly uses
  its native column convention. Vocabulary modules use ``source_table`` and
  optional ``source_database``; FTS5 vocabulary adds ``vocabulary_mode``
  (row/col/instance). Dbstat uses optional ``source_database``.
  ``tokenizer_name`` plus ordered ``tokenizer_arguments`` apply to
  fts3tokenize and FTS constructors. Arguments require an explicit name.
  Constructor-only modules define their own columns: leave the grid empty.
  UNINDEXED in the column grid is FTS5-only; incompatible module options are
  refused. Module choices retain their installed-resource requirements;
  SQLite's runtime constructor is the authority for module/tokenizer presence.
  TEMP/attached and cross-database rules retain their existing retained-session
  requirements and native transaction/post-state checks.
* SQ-FORM-3, ``table.form.json``: select ``variant: fts`` and the FTS generation.
  ``prefix_lengths`` is an ordered number grid; ``notindexed_columns`` is
  FTS4's string grid. ``content_mode`` is INTERNAL (omit native content),
  EXTERNAL (requires ``content_table``), or CONTENTLESS (native empty content).
  The ``fts_`` controls map to native ``matchinfo``, ``compress``,
  ``uncompress``, ``order``, ``languageid``, ``content_rowid``, ``detail``,
  ``columnsize``, ``contentless_delete``, ``contentless_unindexed``,
  ``tokendata`` and ``locale``. Optional selects use DEFAULT to omit the native
  option, rather than forcing a false setting onto an older runtime. Native
  contentless-delete requires 3.43.0, tokendata 3.45.0, and locale and
  contentless-unindexed 3.47.0. Both typed controls and legacy native option
  maps pass the actual client runtime gate. Option-level descriptor version
  gates let the UI retain DEFAULT on older runtimes. Sources: SQLite's
  `3.43.0 release notes <https://sqlite.org/releaselog/3_43_0.html>`_,
  `3.45.0 release notes <https://sqlite.org/releaselog/3_45_0.html>`_, and
  `3.47.0 release notes <https://sqlite.org/releaselog/3_47_0.html>`_.
  External-content creation does not populate or synchronize its index;
  explicit rebuild/maintenance and synchronization remain separate reviewed
  operations. Custom tokenizers are native dependencies: built-in tokenizer
  tests do not qualify custom locale/tokendata tokenization implementations.
* SQ-FORM-4, ordinary ``table.form.json`` Columns grid: create-only column
  attributes are ``collation``, ``generated_storage`` (NONE/VIRTUAL/STORED),
  ``generated_expression``, ``autoincrement``, ``check_expression`` and
  ``not_null_conflict``, ``primary_key_conflict``, ``unique_conflict``
  (DEFAULT/ABORT/FAIL/IGNORE/REPLACE/ROLLBACK). AUTOINCREMENT requires exact
  INTEGER PRIMARY KEY. Generated columns reject DEFAULT, PRIMARY KEY and
  AUTOINCREMENT; a generated expression requires an explicit storage choice.
  Conflict policies require their corresponding active native constraint.
  Values/defaults, generated values, collation-sensitive uniqueness, CHECK,
  sequence non-reuse and native conflict transaction semantics are exercised
  on actual SQLite connections. Advanced attributes are not inferred from
  incomplete ``table_xinfo`` metadata, and editing them on an existing table
  still requires the separately tracked rebuild workflow.
* SQ-FORM-6, ``trigger.form.json``: ``when`` is an optional expression using
  native OLD/NEW references. Timing BEFORE/AFTER selects the table reference;
  INSTEAD OF selects a view reference (``view`` maps to backend ``table``).
  The event is exactly one INSERT, UPDATE or DELETE. The body remains native
  statements wrapped in BEGIN/END when needed. Native target/timing eligibility
  is enforced at execution; accepted bodies and conditions are not emulated.
  Removed inactive/position controls: SQLite has neither native capability.
  Native constructor failures may surface through the existing facade as
  unknown outcome; do not retry. Tests independently inspect the owned native
  catalog after refusal and verify no trigger or data mutation occurred.

The generic ``module_options`` map stays accepted for existing API clients but
is no longer a raw form editor. Typed/native-map conflicts are rejected rather
than silently overriding an explicit setting. UI initial module selection is
now explicit, so module-specific controls do not appear on an ordinary table
because of a hidden FTS default. Native read-back and full form presentation
remain separate concerns; these changes do not claim frontend acceptance.

Current native matrix and source hashes are recorded in
``sqlite-form-batch-native.json`` with per-version JUnit/log receipts for
3.35.0, 3.45.1 and the required 3.53.0 reference runtime. Unavailable features
are tested as explicit old-runtime refusals, not silently skipped.

SQLite original-connection native limits (scoped work under SQ-AUD-04)
--------------------------------------------------------------------

The next five implemented native management workflows are value/row byte length
(``SQLITE_LIMIT_LENGTH``), SQL source byte length (``SQLITE_LIMIT_SQL_LENGTH``),
column count (``SQLITE_LIMIT_COLUMN``), expression depth
(``SQLITE_LIMIT_EXPR_DEPTH``) and compound SELECT terms
(``SQLITE_LIMIT_COMPOUND_SELECT``), in that order. These are five concrete native
controls within SQ-AUD-04, not five closed top-level audit records. SQ-AUD-04
remains partial for other ``sqlite3_limit`` categories and ``sqlite3_db_config``
flags. No arbitrary integer native API dispatch is exposed.

UI/API hooks
~~~~~~~~~~~~

The existing authenticated workspace envelope admits action
``sqlite_connection_limits`` with ``database_target_id``, the public owner-bound
``session_id`` and a ``request`` object. The studio resolves that public session
to its private provider session; request-supplied private session or language
identities cannot replace it. The provider requires execute permission for
inspection and administer permission for review and mutation. It holds the
original provider lock and refuses busy, uncertain or closed connections.
No substitute connection is opened and no authorizer or preupdate/session hook
is replaced. The capability gate requires the interpreter's native
``getlimit``/``setlimit`` and the specific named constant. Missing APIs fail
closed, without SQL emulation or guessed defaults. All five APIs predate the
supported SQLite 3.35.0 floor; an unavailable interpreter binding is still an
explicit unavailable capability, regardless of SQLite version.

Each limit has an individual typed ``operations.json`` entry:
``set_connection_limit_length``, ``set_connection_limit_sql_length``,
``set_connection_limit_column``, ``set_connection_limit_expr_depth`` and
``set_connection_limit_compound_select``. These use the original-session task
transport, not generic independent-file visual administration. Their values
are integer controls, not raw SQL or unrestricted numeric native selectors.
The UI chooses the fixed ``limit`` from the entry's notes and sends:

* Inspect: ``{operation: inspect, limit: length}``, substituting the selected
  admitted limit name (length/sql_length/column/expr_depth/compound_select).
* Review: ``{operation: review, limit, value}``. This observes the current
  original-handle value and returns ``expected_value`` and
  ``requested_value`` without probing or temporarily changing any limit.
* Apply: ``{operation: set_connection_limit, limit, value, expected_value,
  confirmed: true}``. Both numeric fields are exact integers in 0..2147483647;
  booleans, floats, negative values, extra fields and unadmitted categories are
  refused. A changed original value refuses dispatch and requires fresh review.

Show ``before_value``, ``effective_value``, ``requested_value`` and ``outcome``.
Native compile-time hard caps may clamp a requested increase: ``native_adjusted``
is an observed result, not an assertion that the requested value took effect.
``applied`` means the native read-back equals the requested number. No hard cap
is discovered by temporarily raising the connection's limit. Native zero-value
semantics differ by category/build; do not label zero uniformly as unlimited or
as disabled. In particular a build with compile-time expression-depth zero has
no native runtime expression-depth restriction. Native already-prepared/cached
statements retain SQLite's own behaviour: this API does not promise retroactive
recompilation or replace existing statement machinery.

The change affects this original connection, including its applicable attached
schemas; it is neither a main-file property nor a default for future connections.
It is not transaction state: rollback does not restore limits. Pending data and
caller savepoints remain intact; ScratchRobin requests no commit or rollback.
A successful or attempted setter invalidates prior native-work revisions;
inspection and review do not. A missing postcondition returns unknown outcome,
never an applied receipt or automatic retry. Inspect before deciding what to do
next. Closing the original connection ends its limit state.

Native acceptance exercises each limit's real refusal of an oversized query,
value, result-column list, expression tree or compound SELECT. A separate native
connection keeps its previous defaults and accepts the same input; restoring
the original value restores acceptance on the source. Tests also cover native
hard-cap read-back, stale comparisons, invalid types/ranges, busy/closed and
permission refusal, pending savepoints, rollback persistence, untouched
SQLite authorizer callbacks, private session routing and unknown postconditions.
``sqlite-limit-batch-native.json`` records source hashes and the actual native
3.35.0, 3.45.1 and 3.53.0 runs. Human presentation and platform qualification are
separate; no frontend implementation or authenticated HTTP qualification is
claimed by these direct studio/workspace/native checks.

Native semantics follow SQLite's `runtime limit API
<https://www.sqlite.org/c3ref/limit.html>`_ and `limits documentation
<https://www.sqlite.org/limits.html>`_.

Qualification limits: the descriptor validator still reports the same 18
pre-existing errors. Lint counts before/after this limit batch are JSON controls
301/301, MUI imports 212/212, UI engine branches 113/113 and engine panels 113/113.
The current shared JavaScript suites report 94 passes and 63 family-render
failures. A read-only run against the immutable original audit snapshot reports
95 passes and 62 failures; the extra current case is the earlier DuckDB index
form, whose descriptor hash still matches its previous implementation receipt.
No frontend source or family forms were changed by the five-limit batch.
These shared-render qualification failures remain for the UI group; neither a
full descriptor gate pass nor human form acceptance is claimed. Per-case
receipts are ``limit-family-render.json`` and
``limit-baseline-family-render.json`` in the designated work area.

Next SQLite native limits: five additional controls under SQ-AUD-04
-----------------------------------------------------------------

Implemented in sequence: function argument count (SQLITE_LIMIT_FUNCTION_ARG),
attached database count (SQLITE_LIMIT_ATTACHED), LIKE/GLOB pattern byte length
(SQLITE_LIMIT_LIKE_PATTERN_LENGTH), largest SQL parameter slot number
(SQLITE_LIMIT_VARIABLE_NUMBER), and trigger execution depth
(SQLITE_LIMIT_TRIGGER_DEPTH). These add five original-connection native controls
to the existing five, not five closed top-level audit records. SQ-AUD-04 remains
partial for other limit categories and the broader sqlite3_db_config workflow.

The transport, original-handle ownership, permissions, interpreter capability
checks, native hard-cap read-back, compare-and-set, confirmation, no automatic
retry, and nontransactional connection-state semantics in the preceding section
apply unchanged. Each new control has its own typed operations.json entry:

* set_connection_limit_function_arg: request.limit=function_arg.
* set_connection_limit_attached: request.limit=attached.
* set_connection_limit_like_pattern_length: request.limit=like_pattern_length.
* set_connection_limit_variable_number: request.limit=variable_number.
* set_connection_limit_trigger_depth: request.limit=trigger_depth.

Use action sqlite_connection_limits and request.operation inspect/review or
set_connection_limit as documented above. Values and expected_value are bounded
exact integers; the native effective value is authoritative. These five native
categories predate SQLite's 3.35.0 support floor. Native defaults/hard caps vary
by version and build; do not hard-code them, including the function argument
default changed in SQLite 3.48.0. Interpreter bindings and the specific native
constant must still exist; their absence is an unavailable capability.

Native distinctions the UI must preserve:

* Function argument limits count the arguments of a function invocation.
  Native coalesce and vararg printf calls qualify the new control; this is
  not a policy that changes the definitions of existing functions.
* Lowering the attachment limit below the number already attached does not
  detach databases. Existing Unicode aliases and their data remain accessible;
  additional ATTACH requests are natively refused until capacity is restored.
  The limit is connection-wide, not a setting stored in an attached file.
* LIKE/GLOB pattern limits count native UTF-8 bytes. The GLOB test qualifies
  a two-character, four-byte pattern as too large for a three-byte setting;
  a two-byte ASCII pattern remains accepted.
* The variable-number limit bounds the highest parameter slot, not the number
  of repeated occurrences. ?2 may occur repeatedly with two bindings while ?3
  and a third distinct named parameter are refused at a setting of two.
* Trigger depth applies to native nested trigger execution, including different
  tables. A native recursion error can leave preceding statement/trigger writes
  pending: tests observe both the original-row insert and the first triggered
  insert still present. Never report that the error automatically rolled back
  those writes. The caller explicitly rolls back its chosen savepoint; earlier
  pending work and the outer savepoint remain intact. Restoring the limit then
  permits the same trigger chain. This adapter neither interprets a SQL error
  as commit/rollback nor silently settles the caller's transaction.

All five controls retain independent-connection defaults, native zero-value
read-back without guessed zero semantics, stale-value and hard-cap checks,
busy/closed and permission refusals, untouched authorizer callbacks and caller
savepoints, and original-session route/revision checks. Native 3.35.0, 3.45.1
and required reference 3.53.0 receipts are recorded separately in
sqlite-next-limit-batch-native.json and the corresponding per-version logs and
JUnit files. No frontend implementation or authenticated HTTP qualification is
claimed. Existing shared-render failures and descriptor-validator failures
remain separate from these backend/native checks.

Current batch verification: 80 tests pass on each native SQLite 3.35.0, 3.45.1
and 3.53.0 runtime; the wider backend suite passes 1,136 tests (65 skipped,
26 subtests passed). Runtime source IDs, compile options, actual native limit
defaults and library SHA-256 values accompany the native receipts. These
confirm function argument defaults of 127 on the two older tested builds and
1000 on the reference build, without baking those values into the adapter.
The ten admitted controls leave VDBE_OP and WORKER_THREADS unadmitted among the
categories exposed by the tested interpreter; db_config work remains separate.

The 18 descriptor-validator errors and all 63 shared JavaScript family-render
failures exactly match the previous batch's error/case sets. No new failures
were added. Lint counts before/after: JSON controls 301/301, MUI imports 212/212,
UI engine branches 113/113, engine panels 113/113. This is backend/native
qualification with explicit shared-render limitations, not a full UI gate pass.

Five original-connection PRAGMA controls under SQ-AUD-03
------------------------------------------------------

Implemented in order from the existing pragma-decisions audit: foreign_keys,
query_only, recursive_triggers, read_uncommitted and reverse_unordered_selects.
SQ-AUD-03 remains partially implemented for other native PRAGMAs and action
categories; this batch does not close five whole top-level audit records.

The authenticated workspace action is sqlite_connection_pragmas. Keep the public
owner-bound session_id and registered database_target_id in the envelope; send
request with operation inspect/review/set_connection_pragma and one fixed pragma
name from the five above. Inspect accepts only that name. Review additionally
accepts boolean value and returns native_statement, expected_value and
ready_to_apply. Apply additionally requires the exact boolean expected_value
and confirmed:true. Nonboolean aliases such as 0, 1 or ON are not this typed
transport. Each control has its own operations.json entry named
set_connection_pragma_<name>, with boolean value, expected_value and confirmed
controls. Display the actual review SQL through the native-task review flow;
do not send these operations to independent-file visual administration.

Execute permission is required for inspect, administer also for review/set.
The studio resolves public sessions to private native bindings and replaces
request-supplied session/language identities. Busy, uncertain and closed native
connections are refused; no replacement connection is opened. Review and inspect
do not advance the native work revision; a setter attempt does, invalidating
earlier retained-work reviews. The provider serializes observation, comparison,
native dispatch and read-back under the original client's lock.

Runtime/build admission is an actual native getter returning integer 0 or 1.
An unknown or omitted PRAGMA is unavailable, not a guessed false default. The
canonical names are whitelisted, with no raw SQL/action selector or numeric ABI
dispatch. Stale expected values refuse mutation. Native setter errors or a
missing/mismatched postcondition never return an applied receipt and never
trigger an automatic replay. Native getter/authorizer refusal before dispatch
is distinguished from an unconfirmed setter outcome. Existing native authorizer
ownership is retained; it can still deny the requested operation.

These are connection flags, not file properties or defaults for later
connections. Generic database alter refuses them rather than acknowledging a
setting on a disposable connection. No commit or rollback is requested; rolling
back caller data does not restore these flags. SQL outcomes after a flag change
remain the native engine's outcomes.

Native distinctions and acceptance:

* Foreign keys: actual violating inserts are refused when enabled and permitted
  when disabled. Setters are refused while the caller has an open transaction,
  avoiding SQLite's ignored in-transaction assignment; review reports not ready.
* Query-only: native writes return SQLITE_READONLY while existing pending rows
  remain readable. The flag can be cleared on the original connection so the
  caller can continue and explicitly roll back its own savepoint. It is not a
  replacement for filesystem permissions, an immutable route or native extension
  policies.
* Recursive triggers: a bounded same-trigger chain produces different native
  results with the switch off and on; recursion is not simulated by application
  callbacks. Existing prepared-statement and depth-limit semantics remain native.
* Read-uncommitted: native private-cache readers still do not see another
  connection's pending rows. A separately qualified pair of actual shared-cache
  connections demonstrates native lock refusal with the flag off, pending-row
  visibility with it on, and disappearance after the writer's rollback.
  No cache mode is silently changed or source connection reopened.
* Reverse unordered scans: a supported native table scan reverses on the tested
  plan while explicit ORDER BY stays authoritative. This is a diagnostic flag,
  not a guarantee that every possible SQLite query plan reverses.

The three-runtime matrix uses actual 3.35.0, 3.45.1 and required reference
3.53.0 binaries/libraries. It includes descriptor round trips, native effects,
connection isolation, stale/type/permission/busy/closed refusals, caller
savepoints, rollback persistence, authorizer refusal and fault-injected missing
getters/read-backs. sqlite-pragma-batch-native.json records scope, source hashes
and per-version receipts. Human presentation, authenticated HTTP acceptance and
native Windows/macOS qualification remain separate.

Native behaviour references: SQLite's PRAGMA documentation
(https://sqlite.org/pragma.html) and shared-cache locking documentation
(https://sqlite.org/sharedcache.html). Existing native limitations are retained.

Current PRAGMA batch qualification: 66 tests pass on each native SQLite 3.35.0,
3.45.1 and 3.53.0 runtime. The broader regression suite passes 1,177 tests
(65 skipped, plus 26 passing subtests), make ui-descriptors-check passes
142 tests (66 skipped), and all 160 selected JavaScript checks pass. The
descriptor validator reports zero errors. JSON controls remain 301, MUI imports
212, UI engine branches 111 and engine panels 113; none of these counts grew.
SQ-AUD-03 stays partial, with its other PRAGMA/action categories explicitly open.

Second set of five PRAGMA controls under SQ-AUD-03
------------------------------------------------

Implemented sequentially from the existing audited decisions: automatic_index,
ignore_check_constraints, trusted_schema, legacy_alter_table and
cell_size_check. Together with the preceding set, ten audited native connection
flags have typed management. SQ-AUD-03 still remains partial for the other
native PRAGMAs and action categories.

All five use the existing sqlite_connection_pragmas workspace action, original
public session and registered database target envelope, and inspect/review/
set_connection_pragma request operations. The fixed request.pragma values are
the five names above. Individual operation descriptors are
set_connection_pragma_<name>, with boolean value, observed expected_value and
confirmed:true. Review returns the exact native_statement without preparing or
executing that setter. Show it in native-task review; these operations are not
independent-file visual-admin assignments.

The same existing guards apply: execute/administer permissions, private session
binding, idle/uncertain/closed connection checks, serialized native observation
and compare-and-set, actual 0/1 runtime getter/build admission and read-back,
explicit missing/denied/unknown outcomes, and no automatic retry. These flags
predate the supported 3.35.0 floor. Prepared-statement invalidation and native
behaviour remain SQLite's; application callbacks do not emulate the features.
Values are connection state, not file properties, future defaults or transaction
state. Database alter rejects them before normalizing mixed file/connection
changes, so another requested file setting is not silently applied on its own.

Native distinctions and acceptance:

* automatic_index changes the planner's ability to build transient indexes.
  The native join-plan test observes an automatic index when enabled, its
  absence when disabled, and identical native query results. This is not a
  persistent CREATE INDEX or an index-advisor workflow.
* ignore_check_constraints permits native writes which otherwise violate CHECK.
  Turning it off does not delete or repair already-invalid rows; later violating
  writes are refused. Tests retain the caller transaction until its explicit
  rollback. This does not disable foreign-key, UNIQUE or NOT NULL constraints.
* trusted_schema controls trust in schema-origin execution. A native view using
  an application-defined deterministic function is accepted with trust enabled
  and refused with trust disabled; direct invocation remains allowed. Native
  innocuous/direct-only classifications remain authoritative, not guessed from
  a function name. Turning trust back on restores the tested view's use.
* legacy_alter_table changes native rename propagation. The modern-mode test
  observes a view being rebound to a renamed table; legacy mode leaves the
  reference pointing at the previous name and the native view fails to bind.
  Changing the flag alone does not repair that view. The owned fixture is
  repaired explicitly by renaming the table back under the appropriate native
  mode. Native foreign-key/version interactions are not replaced with a generic
  rename policy.
* cell_size_check enables additional native checks on pages read by SQLite.
  Native valid-page reads and corruption refusal are tested against a separate
  owned copy with a malformed table-leaf cell pointer. The original fixture's
  bytes and data are verified unchanged. The check does not repair the file,
  certify an entire database, or replace integrity_check; the test does not
  claim that disabling checks makes the damaged page valid.

Each new flag also participates in the original-session per-handle/default
isolation, stale-value, savepoint/rollback persistence and mixed-file refusal
matrix. Native evidence is recorded in sqlite-second-pragma-batch-native.json,
with source hashes and separate version receipts for SQLite 3.35.0, 3.45.1 and
reference 3.53.0. Human presentation, authenticated HTTP acceptance and native
Windows/macOS qualification remain separate.

The corruption fixture follows the native format's table-leaf header and
cell-pointer layout documented at https://sqlite.org/fileformat.html; behaviour
is qualified natively, not inferred from a header or catalog name. Native flag
semantics are documented at https://sqlite.org/pragma.html.

Current second-PRAGMA qualification: all 96 tests pass on each native SQLite
3.35.0, 3.45.1 and 3.53.0 runtime. The wider regression suite passes 1,207 tests
(65 skipped, plus 26 passing subtests), make ui-descriptors-check passes
147 tests (66 skipped), and all 32 selected operation/descriptor JavaScript
checks pass. Descriptor validation reports zero errors. Lint counts remain
JSON controls 301/301, MUI imports 212/212, UI engine branches 111/111 and engine
panels 113/113. This batch remains uncommitted; other SQ-AUD-03 work stays open.

SQLite remaining native limits and numeric connection controls
-------------------------------------------------------------

Five further audited subfeatures are implemented: VDBE_OP, WORKER_THREADS,
busy_timeout, wal_autocheckpoint and analysis_limit. SQ-AUD-03 and SQ-AUD-04
remain partial parent records; this does not close five top-level audit records.
All twelve interpreter-exposed sqlite3_limit categories now have typed controls;
broader sqlite3_db_config and other PRAGMA workflows remain outstanding.

UI handoff: database operations set_connection_limit_vdbe_op and
set_connection_limit_worker_threads use the existing sqlite_connection_limits
original-session transport, with integer value, integer expected_value and
confirmed=true. Native getlimit/setlimit readback determines applied versus
clamped results. The opcode budget can cause native SQLITE_NOMEM (Python
MemoryError) during preparation. Recovery uses the same handle's native limit
API, without preparing SQL. Worker threads is a budget; native compile-time
limits may clamp it and no worker creation is promised.

Database operations set_connection_pragma_busy_timeout,
set_connection_pragma_wal_autocheckpoint and
set_connection_pragma_analysis_limit use sqlite_connection_pragmas, with integer
value and expected_value in 0..2147483647 and confirmed=true. Inspect and review
observe the bound original session; setters compare that observation and read
back native state. Busy timeout is milliseconds (zero disables waiting), WAL
autocheckpoint is pages (zero disables automatic checkpoints), and analysis
limit is approximate rows per index (zero requests unrestricted analysis).
Setters neither enable WAL nor execute ANALYZE or manually checkpoint.

Busy timeout replaces the native busy-handler policy; WAL autocheckpoint
replaces the native WAL hook. Their forms require a separate
replace_callback_confirmed=true acknowledgement. The prior callback identity
is unobservable through these PRAGMAs, and restoring its previous numeric value
does not restore an unknown application callback. Result fields report
callback_policy, previous_callback_identity=unobservable,
callback_replacement_requested and callback_restoration_claimed=false.

These are per-handle settings with execute/administer authorization and the
existing private-session, idle/uncertain/closed and serialized dispatch guards.
They preserve caller transactions, are not restored by rollback and do not
change peer handles, file settings or future connection defaults. Missing native
getters mean not_dispatched; refused or mismatching post-dispatch observations
mean unknown_outcome, with no automatic retry or success claim. Generic database
alter rejects both direct and mixed file/connection settings before dispatch.

Native tests demonstrate opcode preparation failure and no-SQL recovery, worker
budget readback and sort correctness, actual SQLITE_BUSY waiting, automatic
checkpoint progress into the main file after committed WAL writes, and reduced
ANALYZE work with sampling. Uncheckpointed WAL content is not described as
uncommitted. Receipts: sqlite-tuning-batch-native.json and separate native
3.35.0, 3.45.1 and 3.53.0 XML reports in the designated work area. Human form,
authenticated HTTP and Windows/macOS acceptance remain separate; ScratchBird
history qualification remains deferred by owner direction.

Opcode recovery evidence above uses a direct native execution on the retained
handle. Managed query execution treats Python MemoryError without a native error
code as uncertain: its existing close/reconnect requirement remains authoritative
and is not bypassed by these controls. Do not promise in-place recovery through
the Query Tool after it has blocked that session. Native timeout granularity
also depends on the SQLite build; the lock-wait fixture uses 1100 milliseconds
so older builds with second-granularity sleep support are exercised honestly.

Current five-control qualification: 192 tests pass on each native SQLite
3.35.0, 3.45.1 and 3.53.0 runtime. The wider backend suite passes 1,248 tests
(65 skipped, plus 26 passing subtests); make ui-descriptors-check passes
152 tests (66 skipped). All 32 selected JavaScript operation/descriptor checks
pass and descriptor validation has zero errors. Lint counts are unchanged:
JSON controls 301/301, MUI imports 212/212, UI engine branches 111/111 and engine
panels 113/113. Changes remain uncommitted.

Seven partial-record implementation stream
------------------------------------------

The next requested scope is the seven original records PG-AUDIT-IDENTITY-01,
MA-AUDIT-FLAGSET, MA-AUDIT-TYPE-COMPLETION, FB-EMB-database_statistics,
SQ-AUD-03, SQ-AUD-04 and SQ-AUD-17. This section records the new backend
contracts; it does not declare the seven records finished or replace their
remaining acceptance requirements.

PostgreSQL schema-owner DROP admission
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing ordinary/partitioned-table identity guard now admits a schema
owner who has native DROP authority but no table LOCK privilege. When the
native UPDATE/DELETE/TRUNCATE privilege check permits LOCK, the existing
ACCESS EXCLUSIVE NOWAIT route remains. Otherwise the transaction creates and
drops a uniquely named zero-column guard view in the owned schema. Native
CREATE VIEW retains an AccessShareLock on the exact referenced table, even
after guard-view cleanup. The code then revalidates the full retained
server/principal/database/schema/table generation and dispatches DROP in the
same transaction. DROP upgrades the retained lock with lock_timeout=1ms on
that route. Busy/stale/native privilege failures never fall back to an
unguarded DROP. No table data is read or privileges granted.

The review warning discloses guard DDL: native event triggers can observe its
CREATE/DROP VIEW. Native 18.3 tests cover schema-owner execution, no leftover
guard view, and a competing native DROP blocked after guard cleanup. Existing
cross-cluster OID collision, replacement, namespace movement and table-owner
checks remain. Other destructive object families and additional runtime/HTTP
qualification remain separate outstanding scope.

MariaDB session FLAGSET and explicit source-context hooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Database-variable operations set_session_optimizer_switch_flags and
set_session_optimizer_trace_flags declare task mariadb_session_flagsets with
fixed variable=optimizer_switch or optimizer_trace. These operate on the
bound original Data Studio session, not a disposable connection. Every
inspect/review/set_session_flags request requires
diagnostics_change_confirmed=true: explicit native observation changes the
session's diagnostic and row-count state. Passive completion retains its
zero-original-command policy.

Review/set use value_mode=VALUE/FLAGS/BITMASK/DEFAULT, the existing typed flag
rows and reset_defaults, or exact decimal bitmask text as applicable. Setter
requires exact string expected_value from review and confirmed=true. Native
SYSTEM_VARIABLES must expose a writable SESSION/SESSION ONLY FLAGSET and its
actual option metadata. Numeric masks retain the native 64-bit bound; an
oversized option inventory is refused for numeric mode rather than truncated.
Textual flag assignment is not truncated to a fabricated bit position.

Successful set returns outcome=native_acknowledged_with_readback and expanded
native before_value/effective_value, not an echo of partial/default input.
Native warnings are captured before readback as bounded level/code records;
warning text is not published. No global/default change, commit, rollback,
reconnect or automatic retry is requested. An unconfirmed setter/readback
blocks source-session reuse. The Data Studio hook returns accepted=false,
outcome=unknown_outcome, effective_value_observed=false and
close_session_required=true; it does not return an applied result.

Routine-local SQL type declarations now have a separate
context.routine_type_candidates contract. SYS_REFCURSOR has Oracle and
non-Oracle declaration examples; ASSOCIATIVE_ARRAY supplies an Oracle TYPE
... IS TABLE OF ... INDEX BY ... declaration, never an invented column type
named ASSOCIATIVE_ARRAY. Native active-plugin and qualified-version gates
apply. Each template declares required_sql_mode, scope, completion_text and
example_sql. Ordinary column types retain their separate parameter profiles.

Operation refresh_editor_context declares task mariadb_editor_context with
operation=refresh_completion and diagnostics_change_confirmed=true. It reads
one fixed original-session context query, validates the admitted native
identity, and applies its observed database, SQL mode, role and character-set
context to a separately owned catalog peer. Source inspection and peer capture
are serialized against source commands. Returned editor_context exposes the
observed original context and routine-template available flags for that mode.
It does not claim to observe temporary objects or uncommitted schema on the
peer. The snapshot is not a guarantee after later source commands; the UI must
invalidate source-context hints then. Do not silently substitute this explicit
refresh for passive autocomplete or replay a lost request.

Unavailable source inspection returns accepted=false,
outcome=context_refresh_unavailable, close_session_required=true and unknown
sent/diagnostic-preservation observations (original_session_commands_attempted=1). A failure
on the private peer after successful inspection reports one source command,
original_diagnostics_preserved=false and close_session_required=false. Original work
is never committed or rolled back by the refresh.

Embedded Firebird statistics target fencing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Linux statistics now hold an open descriptor and a verified private hardlink
to the reviewed inode until native service completion and release. The
hardlink is created in a private directory beside the approved database and
verified against the reviewed device/inode after creation. A replacement
between open and link is refused. The native service reads the stable alias,
not a later same-name replacement. This alias is used only for read-only
statistics, never as an alternative SQL database attachment or lock alias.
The approved directory must permit temporary directory/hardlink creation;
failure is a known pre-dispatch refusal. Alias cleanup runs on errors too.

Native Linux qualification unlinks the original pathname and creates a
same-name database during actual dispatch; statistics still report the
original table. Descriptor symlinks were experimentally insufficient because
native canonicalization can lose the deleted target; they are not the
implemented fence. Non-Linux behaviour is preserved and its receipt explicitly
keeps file_identity_race_fenced=false pending the platform teams' adapter and
qualification. This is not a cross-platform completion claim.

Seven current native statistics sections are exercised individually.
DB_LOG is omitted and rejected before service attachment: it is an obsolete
log-page option from Firebird1.0/1.5, not a Firebird5 capability. Native5.0.4
rejected the attempted legacy service option with codes335544562/335545037.
The current owning reference is
https://firebirdsql.org/file/documentation/html/en/firebirddocs/gstat/firebird-gstat.html.
Service completion, service release and utility exit-code observation remain
distinct; no utility exit code is invented from returned text.

SQLite typed configuration, getter inspection and object designs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Task sqlite_connection_config operates on the bound original query handle
with inspect/review/set_connection_config and a fixed named config. Sixteen
interpreter-bound boolean sqlite3_db_config controls have individual database
operation entries. Fields are boolean value/expected_value and confirmed=true.
Enabling reset_database, writable_schema or enable_load_extension additionally
requires dangerous_change_confirmed=true. RESET_DATABASE immediately changes
native database interpretation and arms a later VACUUM to erase its contents;
this setter never executes VACUUM. Native getter/setter availability and exact
readback are required; no unrestricted numeric db_config call is admitted.
Permissions, source-idle/uncertain/closed checks, hook ownership and the native
work revision use the existing original-session route. Settings are not
transaction rollback state. Non-boolean/unbound native configuration APIs are
not claimed by these sixteen controls.

SQ-AUD-03 now has twenty typed original-session PRAGMA controls: seventeen
booleans and the three numeric controls described above. The seven additional
booleans are full_column_names, short_column_names, count_changes,
empty_result_callbacks, fullfsync, checkpoint_fullfsync and defer_foreign_keys.
The last resets on full COMMIT/ROLLBACK; failed COMMIT can retain both the flag
and pending writes. Legacy callback flags do not promise a Python DB-API
callback, and full-sync flags do not prove platform/filesystem/hardware
barriers. Native tests observe column naming, affected-row result sets and
actual deferred-FK failure/reset behaviour.

Task sqlite_connection_pragmas also exposes pragma_inspection_capabilities and
inspect_pragma_value (pragma, schema, object_name where required). The former
lists declared getter signatures and separate non-getter workflows, without
claiming runtime availability. The latter validates the original attachment,
checks native pragma_list presence and returns at most1000 rows/4MiB with
columns, exact values, native_storage_classes and a truncated flag. Empty
metadata is neither a setting default nor proof of object existence. Getter
presence is not mutation admission: management_declared/management_transport
only identify a separate implemented workflow. Heap/directory observations
require administer. Checkpoint, optimize, shrink and integrity actions are
never silently run as getters. Further mutable settings/actions remain open.

Operations table.rebuild and view.replace declare
sqlite_schema_object_design. Requests carry database_target_id, exact baseline
DDN, resource_id, operation=rebuild/replace and typed fields from the descriptor.
A rebuild takes the complete desired column grid and preserves table-level
constraints, native table modes, indexes and triggers. View replacement takes
a native SELECT/WITH query and optional column_names grid; it retains INSTEAD
OF triggers. Generation reproduces schema only in an empty private prototype,
returns desired DDN and explicit rebuild identities, and leaves the file and
original sessions unchanged. It excludes temp/attached targets and virtual
rebuilds; their existing dedicated workflows are not relabelled.

The UI then calls sqlite_schema_plan, displays its complete SQL/dependencies,
passes the unchanged execution_sha256 to sqlite_schema_review, and applies
only review_id/review_digest/confirmed through sqlite_schema_apply. Existing
one-use receipts, exact file identity, three-way conflicts, atomic rollback,
row conversion and independent rediscovery remain mandatory. Removed columns
or changed affinity can lose/convert values and require the actual plan warning.
A view is drop/recreate under review, never an invented ALTER VIEW.

Table rebuild previews now validate derived view column facts against a native
empty desired schema. Affinity changes may change projections without changing
a view's SQL. Forged/stale projection facts block review; atomic apply checks
the final native projections before commit. Pre3.37 runtimes use native empty
module-constructor authorizer events to classify storage and native
index_info(table-name) to observe WITHOUT ROWID; source-name suffix guesses
are not used. An unreproducible schema remains explicitly unobserved. The
index_info behaviour is documented at https://sqlite.org/pragma.html#pragma_index_info.

Additional original-session and process policy contracts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The typed PRAGMA route additionally admits ten schema/pager settings:
cache_size, cache_spill, max_page_count, default_cache_size, schema_version,
journal_size_limit, mmap_size, secure_delete, locking_mode and temp_store.
Each has its own operation descriptor and typed value, native getter, expected
value comparison and native readback. journal_size_limit/mmap_size use canonical
signed-64-bit decimal text, avoiding JavaScript integer rounding. Enum choices
are explicit. A native clamp/ignored request returns native_adjusted; configured
state never proves allocated bytes, physical erasure or lock ownership.

Schema identifiers must be attached to the original session. temp_store has
connection scope and rejects a schema argument. Changing it requires no open
caller transaction, explicit TEMP-object deletion confirmation, and a one-use
review_id bound to the server-owned native work revision. Review returns at
most500 TEMP object name previews of256 characters, with truncation flags;
the deletion scope is all TEMP objects, not only the displayed previews.
Native compile-time TEMP_STORE options are returned separately from the
configured policy. schema_version additionally requires explicit direct-header
confirmation. default_cache_size/schema_version header persistence follows
native transaction state; no setter receipt claims a durable commit. In
particular, rolling back default_cache_size's header change need not restore
its connection-cache change. Native defensive schema_version protection differs
across versions: SQLite added that protection in3.40.0; the minimum3.35.0
runtime does not have it. Reference:
https://sqlite.org/releaselog/3_40_0.html.

Setter-only case_sensitive_like has no native getter. Review never evaluates
unknown application callbacks and returns before_value=null with an explicit
unobserved flag. Apply requires a one-use review_id, the unchanged server-owned
native work revision, explicit value, confirmed=true and
replace_callback_confirmed=true. Native ASCII LIKE/GLOB probes establish only
the resulting policy. Unknown readback consumes the review; callbacks are
never restored or replayed automatically, and rollback does not restore them.
Schema expressions involving LIKE may need REINDEX under the intended policy.

sqlite_connection_maintenance reviews fixed REINDEX, ANALYZE and
PRAGMA shrink_memory recipes on the original connection. It creates an existing
retained native-script plan; the UI uses that plan's advance/poll/discard
contract. Review suppresses prepare-time PRAGMA effects and never runs the
action. Advance refuses intervening original native work before its first
statement. One native execution remains caller-transaction-owned; no byte
reclamation amount, implicit commit or automatic resubmission is promised.

soft_heap_limit/hard_heap_limit are explicitly process/loaded-runtime policies,
not connection-local controls, despite the historical sqlite_connection_pragmas
transport name. Separate operation descriptors require exact decimal-text
bytes and process_wide_change_confirmed=true. Hard-limit changes additionally
require irreversible_lowering_confirmed=true: native SQL can only lower a
hard limit, and a small limit can prevent SQL/cleanup until process restart.
The response observes both soft/hard limits before and after, including native
adjustment, and does not claim an OS memory cap, peer isolation or rollback
restoration. Application-managed policy writes serialize, but unrelated native
changes are not claimed to be excluded. Tests change these limits only inside
disposable owned worker processes.

Direct native virtual-table creation now repeats the FTS-option version gate
against the actual dispatch connection before starting its DDL transaction.
The driver/planning gate remains in place; direct administration calls cannot
bypass it. Older runtimes refuse unsupported options without creating a table.

The authenticated inherited PostgreSQL driver exposed an additional row-format
integration defect in DROP review: its DictCursor.fetchone returns tuples even
when a caller supplies dict_row. The identity guard now constructs a public
psycopg Cursor with its own explicit dict/tuple row contract, rather than
inheriting that cursor factory. A native regression uses the actual inherited
DictCursor; this does not substitute a mock driver for the integration boundary.

Native configuration and parent-identity follow-up (2026-11-15)
============================================================

This section supersedes the earlier implementation descriptions for the seven
partially implemented records. Qualification is recorded separately in the
current work-area ledger; this text is an API handoff, not a cross-platform
acceptance certificate. No frontend presentation was implemented here.

PostgreSQL parent namespace continuity
-------------------------------------

``PG-AUDIT-IDENTITY-01`` binds ordinary and partitioned table DROP to the
observed cluster/server startup, effective/authenticated principal, database,
namespace OID, relation OID and catalog generation. Apply rejects an already
stale observation before temporary guard DDL. It retains both native
``pg_namespace`` and ``pg_class`` tuple locks through the final observation,
DROP and commit. This includes older server minors whose schema rename does not
respect namespace object locks. A relation lock alone is insufficient.

A database superuser can take the tuple lock directly. Other native table/schema
owners require the fixed SQL helper
``pg_catalog.scratchrobin_lock_drop_namespace_v1(oid,oid,text)`` in that database.
The database operation ``install-drop-namespace-guard`` installs it through the
normal provider plan/apply workflow, requiring the exact draft confirmation
``INSTALL DROP NAMESPACE GUARD`` and native superuser authority. It performs
CREATE only, never replaces an existing function, and does not grant catalog
update privileges. The SECURITY DEFINER helper checks the invoking session or
SET ROLE identity against native table/schema ownership. Apply verifies its
body, signature, native SQL language, return type, volatility, strictness,
search path, superuser ownership and execute privilege before invocation.
Missing, altered or inaccessible helpers cause refusal and a new-review message;
installation is never automatic. The reviewed installation explicitly grants
PUBLIC EXECUTE on this ownership-restricted helper. An existing name collision requires inspection
rather than automatic replacement.

The namespace catalog-row lock also prevents a concurrent schema rename from redirecting the
name-based DROP after final identity validation. Native table/schema owners can DROP even without table ACLs or schema CREATE
rights. Where native table ACLs allow, apply additionally locks the relation
before dispatch. Otherwise native DROP acquires its own relation lock under a
1ms timeout while retained catalog-row locks prevent competing rename/drop
from committing a replacement. No temporary guard-view DDL, namespace CREATE
right or table ACL grant is needed. Busy targets are refused rather than retried.
These table
contracts do not certify unrelated destructive object families.

SQLite configuration component and contracts
-------------------------------------------

``SQ-AUD-04`` now provides the complete 24-signature configuration vocabulary in
the reference SQLite 3.53.0 header: sixteen interpreter-bound booleans, five
additional booleans, MAINDBNAME, LOOKASIDE and FP_DIGITS. Native limit controls
remain the twelve individually typed operations documented earlier. Actual
runtime/build admission applies on every supported version; a declaration in a
new header is not evidence that an older runtime implements that opcode.

The public-API component in ``tools/native/sqlite_config`` captures a database
only during its driver's staged original native open. It does not read private
CPython connection layouts, accept pointers/opcode numbers from API clients,
replace source SQL callbacks, reconnect, or reopen an existing query session.
The module and interpreter must use the same native SQLite library instance.
Each operation validates the original connection's live public owner. Retained
MAINDBNAME strings remain allocated until native close; the handle permits at
most 32 alias changes, stated as an application resource budget. Lookaside uses
the native allocator, requires no slots in use, and has a disclosed 16 MiB
application allocation budget. Native SQLITE_BUSY is a refusal; statements are
not silently finalized to make a setter succeed. Slot geometry has no native
getter: requested geometry must never be labelled an observed current value.

Use ``sqlite_connection_config`` with ``capabilities`` to obtain the typed
vocabulary and actual availability distinctions without sending original SQL.
The descriptor operation is ``configuration_capabilities``. Additional setter
operation IDs are ``set_connection_config_`` plus ``stmt_scanstatus``,
``reverse_scanorder``, ``enable_attach_create``, ``enable_attach_write``,
``enable_comments``, ``main_dbname``, ``lookaside`` and ``fp_digits``. Transport
operations remain ``inspect``, ``review`` and ``set_connection_config``.
Booleans and FP_DIGITS use exact typed current-value comparisons. MAINDBNAME
and LOOKASIDE require a one-use ``review_id`` bound to the server-owned original
work revision, plus their explicit effect acknowledgements. The descriptors
specify every draft field. Report native readback/adjustment and refusal as
returned; an unconfirmed setter outcome requires closing the original session,
with no automatic replay or rollback-restoration claim.

Linux developers install with ``bash tools/development/dev.sh sqlite-config``.
This performs the DDN refresh, builds an isolated source capture, probes an
actual target-interpreter connection and records source/core/interpreter/ABI and
binary provenance. ``SCRATCHROBIN_NATIVE_CONFIG_WORK`` selects disposable build
storage and ``SCRATCHROBIN_NATIVE_CONFIG_PREFIX`` selects the installation
library directory. Existing unknown or changed installations are preserved;
select a fresh prefix after stopping applications. An identical, hash-verified
installation is reusable. ``CDEADMIN_SQLITE_CONFIG_LIBRARY`` selects an explicit
component; otherwise the interpreter's lib/bin/DLLs directories are searched.
Windows/macOS asset integration exists but native qualification remains owned
by those platform teams.

SQLite PRAGMA and startup workflows
----------------------------------

``SQ-AUD-03`` additionally surfaces seven DEBUG flags: ``sql_trace``,
``vdbe_listing``, ``vdbe_trace``, ``vdbe_addoptrace``, ``vdbe_debug``,
``vdbe_eqp`` and ``parser_trace``. Each has its own
``set_connection_pragma_<name>`` descriptor on the original-session
``sqlite_connection_pragmas`` transport. Admission requires both the actual
DEBUG compile option and native pragma-list entry. Enabling requires
``sensitive_output_confirmed=true`` because native host diagnostics may contain
SQL and values. The native ``vdbe_debug`` flag changes multiple VDBE flags;
rollback does not restore them. No source callback is replaced or restored.

``lock_proxy_file`` has its own typed descriptor and original-session transport.
Admission requires actual ``ENABLE_LOCKING_STYLE=1`` and native pragma-list
presence. ``schema`` must identify an attached file inside registered filesystem
authority. Review selects ``AUTO`` (native ``:auto:``) or ``PATH`` and records
current native value, original work revision and a one-use review identity.
Apply requires ``native_locking_change_confirmed``, exact reviewed state and no
caller transaction. The getter can acquire a native VFS conch lock; do not label
it a physically inert observation. Return the actual native path, including
native automatic-path results. Native proxy mode generally cannot be disabled,
so no invented OFF operation is offered. Linux release builds refuse this
unavailable workflow; macOS qualification belongs to the platform team. An
unconfirmed native setter requires closing the source session.

``temp_store_directory`` and ``data_store_directory`` are process-global native
settings. A live setter would be unsafe even with one application thread if
another SQLite connection exists. Their typed descriptors therefore publish a
future host-startup policy through ``sqlite_connection_pragmas``; they never
execute a live global setter. ``inspect`` distinguishes configured policy and
revision from current-process startup revision, native name availability and
``restart_required``. Review requires native component/name availability,
registered filesystem authority, original work revision and a trusted
application-host Administrator principal. The server overwrites caller-supplied
host-authorization fields. ``value_mode`` is ``DEFAULT`` or ``DIRECTORY``;
DIRECTORY is bound to canonical directory/root device and inode identities.
Apply consumes ``review_id``, compares ``expected_policy_revision`` and requires
``confirmed`` and ``process_startup_change_confirmed``. Publication is locked,
durable and bounded. Unknown publication is a distinct configuration outcome:
inspect the store and obtain a new review rather than retrying automatically.
No live transaction/TEMP state is finalized or destroyed.

The accepted policy is ``DATA_DIR/sqlite-startup-policy.json``, overridable by
absolute ``CDEADMIN_SQLITE_STARTUP_POLICY``. Canonical startup applies it before
importing SQLite or opening application databases. The native component checks
that exactly one OS thread exists and SQLite accepts a pre-initialization
configuration query, then opens its sole private bootstrap database. Both native
PRAGMA names are checked before any requested write, each native value is read
back, the bootstrap database closes, and a separate interpreter probe verifies
the same native library instance. Failure aborts startup and writes
``<policy>.receipt.json``; it never silently falls back to unsafe live mutation.
The original failure is retained without an in-process retry. No physical
VFS temporary-file placement is inferred from a successful setting.

For startup recovery, run ``tools/sqlite_startup_policy.py inspect --policy
/absolute/policy.json`` as the application OS identity. The explicit ``clear``
action requires both ``--expected-revision`` from that inspection and
``--confirm-clear``. It clears future overrides under the same publication lock,
without importing SQLite, changing a running process or restarting the host.

``activate_extensions`` is the sole licensed-extension PRAGMA in the pinned
reference inventory. Source inspection of the hash-pinned public 3.53.0
amalgamation found only the guarded CEROD declaration and activation call, not
its implementation. SQLite's CEROD distribution documentation requires separate
licensed source appended to the amalgamation. CEROD activation therefore remains
a post-beta native dependency under the owner source-scope rule; no application
emulation or community execution support is claimed. The inspection capability
response records that dependency separately from beta workflows.

Five PostgreSQL backend audit closures (2026-11-15)
=================================================

This batch implements, in order, ``PG-AUDIT-GENERATED-01``,
``PG-AUDIT-STATS-01``, ``PG-AUDIT-ACL-01``,
``PG-AUDIT-DEFAULTACL-01`` and ``PG-AUDIT-CHECKPOINT-01``. The current
work-area ledger records exact executed checks and versions. These feature
closures do not close the separate cross-family retained-administration,
version-matrix, platform or human presentation records. Descriptor ``draft``
status for the new operation dialogs denotes outstanding presentation/family
acceptance, not stub backend code. UI implementation remains with the UI team.

Generated columns
-----------------

Column facts now retain ``generated_kind`` (native ``s`` or ``v``) and exact
``genexpr`` separately from ``defval``. Capture reads the generated expression
from ``pg_attrdef``; the provider column node supplies both facts for form
initialization. Column ``create``/``alter`` have individual typed operation
entries; the table creation grid also has ``generated_kind``. Creation defaults
to stored for compatibility. Virtual creation requires PostgreSQL 18. The
kind is fixed on an existing column; an in-place stored/virtual conversion is
refused rather than relabelled.

On column alter, ``generated_action`` is ``KEEP``, ``SET`` or ``DROP``. SET
requires a nonempty expression, PostgreSQL 17 for stored columns and 18 for
virtual columns. DROP is stored-only (13+) and preserves existing values while
removing future generation. Explicit KEEP with a changed expression is refused;
a legacy API draft containing a changed ``genexpr`` without the new action
emits SET instead of silently ignoring it beside another change. Ordinary
columns cannot acquire generation in place. Every emitted feature carries its
minimum native server version, checked on the actual private connection at
review and again at apply. Client-supplied version assertions are not used.
SET can rewrite stored values and remove their statistics; no implicit ANALYZE
is performed. Native DDL transactions, errors and rediscovery remain authoritative.

Extended statistics
-------------------

``extended-statistics`` now has provider-native ``create``, ``alter``, ``drop``
and ``inspect`` dialogs. Creation takes ``schema``, ``name``, ``table_schema``,
``table`` and an ``elements`` grid of ``kind=column|expression`` plus ``value``.
``kinds`` is a distinct grid containing ``ndistinct``, ``dependencies`` or
``mcv``. A single element must be an expression with no multivariate kinds.
Expression statistics require native 14+. The application limits a request to
32 elements; PostgreSQL still enforces its own dimensional/eligibility limits.
Virtual generated operands are native refusals, not a claimed statistics feature.

``target`` is an integer from -1 to 10000; -1 resets the target. Inspect returns
the native value, including PostgreSQL 18's NULL for a reset/default target.
Alter supports target, owner, name, schema and comment; operands and kinds
require reviewed drop/create. Compound alters perform ownership transfer last.
Inspect uses the exact native OID and returns source relation OID, owner OID,
keys, kinds and native definition; it does not expose collected data values.
Drop requires the exact statistics name and has explicit CASCADE intent.

The existing DDN native catalog already captured this kind. New
``postgresql:new:<uuid>`` creation drafts now accept the same typed operands
and kinds, with explicit source relation dependencies. The retained
capture/plan/review/apply path guards/revalidates dependencies and checks the
rediscovered statistics OID, source relation OID and statistics namespace before
commit. Schema namespace collision checks remain separate from source-table
identity; statistics names are schema-scoped, not table-scoped. This adds native
DDN creation, not an ANALYZE or statistics-data import service. Ordinary
administration retains its existing review lifecycle; the separately recorded
cross-family retained-administration audit is not waived by these tests.

Parameter ACLs
--------------

``parameter-acl`` is a server-level operation resource with ``grant``, ``revoke``
and ``inspect`` dialogs. Native PostgreSQL 15+ is required at review and apply.
The target is the native parameter name; a supplied draft parameter must agree
with a selected native target. A group invocation may explicitly supply
``parameter`` without an existing ACL row. Typed ``privileges`` rows select SET
and/or ALTER SYSTEM; typed ``roles`` rows select exact role names or PUBLIC.
Grant supports ``with_grant``; revoke supports ``grant_option_only`` and
explicit ``cascade`` (otherwise RESTRICT). Illegal combinations are refused.
This grants parameter authority and never assigns a configuration value.

Server inventory reads ``pg_parameter_acl`` OIDs, names and ACLs without
configuration values. Inspect and mutation readback return native explicit
ACL entries with grantor/grantee OIDs, privilege and grantability, plus native
current-principal SET/ALTER SYSTEM privilege observations. A missing explicit
ACL row does not prove effective access or denial. Native grant warnings and
role inheritance can affect effective rights: a successful command is not
presented as evidence that every requested direct grant was newly installed.
Application administer/execute permission does not replace native grant authority.
The retained transaction performs readback before COMMIT and releases its own
attachment. No automatic replay is introduced.

Default privileges
------------------

``default-privileges`` has dedicated selected-database ``grant``, ``revoke`` and
``inspect`` operations, preserving the existing schema/database family grids.
The new selectors cover TABLES, SEQUENCES, FUNCTIONS/ROUTINES, TYPES, SCHEMAS and
LARGE OBJECTS. Large-object defaults require native 18+; explicit MAINTAIN
requires 17+. The selected database OID is mandatory, so the adapter cannot
silently apply a database template in a maintenance database.

``owner_mode`` selects CURRENT_ROLE (empty ``owners`` grid) or NAMED_ROLES
(explicit owner ``role`` rows). ``owner_kind`` selects the native FOR ROLE or
FOR USER synonym. ``scope`` selects GLOBAL (empty ``schemas`` grid) or SCHEMAS
(explicit ``schema`` rows). SCHEMAS and LARGE OBJECTS reject IN SCHEMA. These
are explicit operation selectors, not guesses from a selected ACL row's label.
Typed ``privileges`` must match the object family, or contain ALL alone;
``grantees`` identifies native role names or PUBLIC. Grant supports grant
option; revoke supports grant-option-only and CASCADE/RESTRICT. Inspect and
precommit mutation readback preserve native default-ACL OIDs, owner and schema
OIDs, object-family code, ACLs and structured explicit grants.

Defaults affect future objects created for those owners; membership does not
merge every role's default templates, and existing object ACLs are unchanged.
An absent template row leaves native built-in defaults in effect, including
native PUBLIC defaults where applicable. It never means all access is denied.
Native role membership/authority and schema restrictions remain engine enforced;
revocation is not implemented as an application rewrite of existing object ACLs.

Standalone checkpoint
---------------------

Server ``checkpoint`` has its own typed descriptor, review and explicit
confirmation. Review binds the native server address/port/startup, database,
effective/authenticated principal names and OIDs, active role, and optional
native system identifier. Apply reobserves the same peer and refuses a changed
binding before dispatch. The command uses a private autocommit connection;
caller transactions and savepoints are neither committed nor rolled back.
Native superuser or native checkpoint-role authority is still required.

``wait_timeout_ms`` is an integer from 1 to 600000, default 30000, applied as a
native statement timeout on this private connection. The command must return
the actual native ``CHECKPOINT`` tag. ``transaction_outcome`` is explicitly
``not_applicable``. ``checkpoint_receipt`` records native completion/peer,
nontransactional scope, wait bound and connection-release outcome separately.
It does not claim independent physical durability or that SQL rollback undoes
a checkpoint. Known native permission/transaction-block refusals remain known
refusals. Cancellation, timeout, acknowledgement loss or an unrecognized command
tag after dispatch are unknown effects: native checkpoint work can continue
after the caller stops waiting. Do not replay automatically. This is a bounded
synchronous operation; no progress stream or manual cancellation endpoint is
advertised. Qualification includes actual native CHECKPOINT plus injected lost
acknowledgement/cancellation responses after completion; those injections do
not claim that a physical network outage was induced.

Native syntax/eligibility references: PostgreSQL documentation for
`ALTER TABLE <https://www.postgresql.org/docs/18/sql-altertable.html>`_,
`CREATE STATISTICS <https://www.postgresql.org/docs/18/sql-createstatistics.html>`_,
`GRANT <https://www.postgresql.org/docs/15/sql-grant.html>`_, and
`ALTER DEFAULT PRIVILEGES <https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html>`_.
All native checks in this batch use owned PostgreSQL 18.3 fixtures. Native
qualification of other supported majors and Windows/macOS remains separate.
No ScratchBird history tests were run.

Parameter-name qualification additionally covers native ASCII case folding,
legacy GUC aliases (including the version-dependent SSL alias) and qualified
custom names longer than one SQL identifier. Readback reports the canonical
native ACL name without reading configuration values. Each qualified name
component is quoted independently. The inherited UI-schema-ID guard explicitly
recognizes ``generated_kind`` as a provider-native field; it is not sent to an
inherited pgAdmin template.

The descriptor/lint boundary has no new UI implementation: JSON controls remain
301, MUI imports 212, engine branches 111, engine panels 113, and context-menu
engine branches 14 (before and after). The combined native/validation suite and
affected PostgreSQL consumers are recorded separately from human form and
platform acceptance in the work-area receipts.

Four SQLite original-session descriptor contracts (2026-11-15)
------------------------------------------------------------

Backend scope closes SQ-DESC-01, SQ-DESC-03, SQ-DESC-04 and SQ-DESC-05.
The native implementations already existed; this change supplies 24 typed
operation descriptors and a callable descriptor-to-task adapter, rather than
substituting registered-file operations for original-connection authority.
SQ-DESC-02 (native session/changeset controls) remains separate. No frontend
components, family skeletons, descriptor schemas or legacy editor controls
are changed. The UI team still owns shared task routing and human presentation.
``draft`` here records that presentation boundary, not a stub native adapter.

Transport and admission
~~~~~~~~~~~~~~~~~~~~~~~

Use the existing authenticated ``NODE-server.cde_workspace_id`` POST endpoint
(the registration's ``/cde_workspace`` URL), with ``action`` equal to
``sqlite_editor_operation``. All responses retain its ``Cache-Control:
no-store`` and existing success/data or error envelope. The registered server,
owned ``database_target_id`` and ``session_id`` stay outside the dialog draft.
The adapter forwards only these identities; client provider IDs, native file
paths, native helper paths, permissions and arbitrary transport names are
never accepted as operation fields. A different engine registration refuses.

Fetch the machine-readable contract without opening a native connection::

    {"action": "sqlite_editor_operation",
     "database_target_id": "<owned target>",
     "request": {"operation_id": "describe"}}

The result format is ``scratchrobin.sqlite.editor-operations@1``. Each row
contains the full standard engine operation descriptor, fixed task transport
and native operation, permissions, native admission, outcome keys, scope and
``original_session_required``. Fields also appear in SQLite's ordinary
``ui_descriptors/operations.json`` bundle. This contract is intentionally a
backend task adapter: do not send these IDs through independent-file provider
plan/apply. An original query session must already be open for every operation
except the archive operations below. Existing provider/studio isolation,
permissions, serialization, busy/uncertain checks and native helper admission
are applied again by the native task. No metadata declaration grants access.

Submit a typed dialog draft, for example::

    {"action": "sqlite_editor_operation",
     "database_target_id": "<owned target>", "session_id": "<original session>",
     "request": {"operation_id": "editor_array_create",
                 "draft": {"type": "int64",
                           "values": [{"encoding": "scalar",
                                       "value": "9007199254740993"}]}}}

Unknown fields, wrong primitive types (including booleans in integer fields),
unknown choices and incomplete required grids refuse before native dispatch.
Native bounds, authorization and capabilities remain authoritative. Mutating
SQL workflows show their actual native preview on the canonical SQL tab; C API
workflows have no SQL and must not display invented SQL. Extension initialization,
array allocations and hook state have no SQL-transaction rollback guarantee.
No workflow automatically reconnects or replays an uncertain native action.

SQ-DESC-01: approved extension loader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_extension_`` prefix provides these exact operations and drafts:

* ``inventory``: no fields; returns approved public identities/digests,
  ``loader_available``, execution host and current module/function/collation
  observations. Operator filesystem paths are excluded.
* ``review``: required ``extension_id`` from that approved inventory; returns
  ``review_id``, state, approved public library identity, verified byte count,
  execution host, native version and irreversible/dependency scope.
* ``load``: required ``review_id`` and boolean ``confirmed=true``; verifies
  unchanged operator approval and exact staged bytes, then initializes the
  library on the original handle. Returns state, native additions when
  observable and ``loader_cleanup_confirmed``.
* ``receipt``: required ``review_id``; reads the original connection's stored
  review, including an unknown-outcome receipt. It cannot revive a closed session.

All require ``execute``; review/load additionally require ``administer`` and
``filesystem``. Loading requires CPython's native loader and db_config APIs,
operator approval and no pending transaction. SQL ``load_extension()`` stays
disabled. There is no unload, cancellation or progress API. Reusing a completed
review returns its receipt without another native initialization. Partial native
initialization or uncertain cleanup blocks reuse and requires closing the
connection. Native dependencies resolve on the application host, and their
side effects may outlive it. Closing releases staged files and local receipts;
it does not promise to reverse initialization.

SQ-DESC-03: native typed arrays
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_array_`` prefix provides:

* ``inventory``: integer ``offset=0`` and ``limit=25`` (native maximum 100);
  returns page/total/more, types, actual helper availability, initialized
  context, operator memory policy and native program identity.
* ``create``: required ``type`` (``int32``, ``int64``, ``double``, ``text`` or
  ``blob``) and ordered ``values`` grid. Each row has ``encoding`` and ``value``.
  ``scalar`` uses a string (canonical decimal integers, float64 text or literal
  Unicode); ``base64`` represents BLOB or raw TEXT bytes; ``null`` is allowed
  only for TEXT/BLOB and has no value. Raw TEXT receives the native TEXT storage
  class. Invalid base64, integer overflow, incompatible representations and
  embedded-zero TEXT refuse through the existing native value codec.
* ``status``: required ``array_id``; returns allocation and binding facts.
* ``close``: required ``array_id`` and ``confirmed=true``; releases its native
  memory and makes those bindings unusable.

Only ``execute`` is required. Native creation requires the matching CARRAY
helper and SQLite instance, runtime at least 3.53.0, and the operator's connection
memory budget. Inventory reports absence without claiming native availability.
Bind the returned ``array.binding`` (``encoding=carray``, opaque ``data``) as
an ordinary query parameter; never interpolate it into SQL. Integer values,
allocation sizes and identities preserve exact native representation. Arrays
are connection-local, not catalog objects; close/release does not commit pending
work. There is no job/progress/cancel API or automatic recreation after close.

SQ-DESC-04: standalone preupdate diagnostics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_preupdate_`` prefix provides:

* ``inventory``: no fields; reports installed/runtime helper availability,
  active native captures and current status without taking hook ownership.
* ``start``: integer ``max_events=1000`` (1..2147483647), exact positive decimal
  text ``max_json_bytes="16777216"`` (maximum 2147483647).
* ``status``: no fields; returns the current native observation controller.
* ``events``: required ``run_id``, canonical decimal ``after_sequence="0"``
  (maximum 9223372036854775807), integer ``limit=25`` (1..100).
* ``stop``: required ``run_id``; disables collection and keeps observations.
* ``clear``: required ``run_id`` and ``confirmed=true``; discards observations
  and returns a new run generation, invalidating previous paging identities.

``execute`` is always required; everything except inventory also requires
``administer``. The matching helper/runtime (at least 3.45.1), native hook
ownership and capture compatibility are checked. Status includes enabled state,
retained/observed/dropped counts and native result codes; paging includes exact
sequence strings and typed native cells, with base64 for binary/unrepresentable
TEXT bytes. Buffers are bounded; never imply a complete history after loss.
These before-change observations include rolled-back changes and do not prove
commit. Schema, virtual/system-table changes are outside hook coverage; rowid
fields have the native undefined cases documented in every descriptor. Clearing
or stopping does not settle a transaction. There is no asynchronous job or
cancel endpoint; stop is explicit hook control, not rollback.

SQ-DESC-05: original-session DDN generation, apply and receipts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_schema_`` prefix provides:

* ``capture``: no fields; calls original-session ``source_catalog`` with
  ``include_system=false`` and returns resources plus ``document.snapshot``
  (or an explicit export warning if DDN bounds are exceeded). Main, TEMP and
  attached namespaces retain original-session provenance. This never calls
  the separate registered-file catalog path.
* ``columns``: required baseline DDN text, original table ``resource_id`` and
  ordered ``columns`` grid (native maximum 32). Controls cover name,
  ``data_type``, nullable, default/CHECK expressions, collation, generated
  expression/storage, reference table/column/update/delete/MATCH/deferrability/
  initial timing, and named NOT NULL/default/generated/CHECK/collation/reference
  constraints. Flat controls map to the existing typed native nested contract;
  incomplete generated/reference/named definitions refuse. Only an empty native
  prototype is modified during design generation.
* ``alter``: required baseline DDN and ordered ``alterations`` grid (native
  maximum 16). Each row identifies the original table, action and applicable
  column/name/expression/conflict operands. Actions are ``rename-table``,
  ``rename-column``, ``drop-column``, ``drop-constraint``, ``drop-not-null``,
  ``set-not-null`` and ``add-check``. Runtime-specific native syntax and exact
  constraint-name lookup remain gated by the existing compiler/probe. Unrelated
  nonempty operands refuse; blank optional grid cells are omitted.
* ``preview``: required baseline/desired DDN text, optional string-list
  ``deletions`` and ordered ``alterations`` grid. Returns native stages and
  ``execution_sha256``. Missing view-filter objects never imply deletion.
* ``review``: same fields, plus required preview ``execution_sha256``; returns
  a durable ``review_id``, ``review_digest``, expiry and exact original-context
  binding. A changed preview must be reviewed again.
* ``start``: required review ID/digest and ``confirmed=true``. Starts the native
  worker once; poll its archive receipt. Native rediscovery must match desired
  DDN before acknowledgement. An owned savepoint contains these stages;
  success is ``applied_pending_caller_transaction``, with
  ``commit_dispatched=false``. It does not commit caller work. Changed source
  context refuses; known failure/cancellation reports its savepoint result;
  unknown outcomes retain uncertainty. Show worker state, completed statements,
  native acknowledgement, rediscovery and native-session release separately.

The ``editor_schema_receipt_`` prefix provides archive ``list`` (offset/limit,
maximum 100), ``receipt`` (review ID), ``cancel`` (review ID) and ``remove``
(review ID and ``confirmed=true``). It requires an owned registered target and
``administer``, but no live session. Reads report ``archived_read_only=true``
and ``native_sql_requested=false``. Cancellation interrupts only an active
owned worker; read its final outcome rather than claiming immediate rollback.
Unresolved native dispatch receipts cannot be removed. Saved receipts contain
no authority to reconnect, replay or settle the original caller transaction.
After original-session closure or application restart, archive inspection
remains available while native start authority does not.

Qualification boundary
~~~~~~~~~~~~~~~~~~~~~~

Native descriptor-draft tests and the authenticated HTTP qualification use owned
Linux SQLite 3.53.0 fixtures, matching array/preupdate/session helpers and a
compiled clean-room extension fixture. They verify native effects and refusals,
exact integer binding, before-change versus commit semantics, original-context
DDL review/apply/rediscovery, caller rollback and archive access after close.
The affected native regression suites, descriptor validator/lint and shared
family render checks are retained in the assigned work area. Native helper
availability remains per-runtime; version metadata alone never establishes
availability. Human UI presentation and Windows/macOS acceptance remain external.

Five DuckDB original-session descriptor contracts (2026-11-15)
------------------------------------------------------------

Backend scope closes DU-AUD-22, DU-AUD-23, DU-AUD-24, DU-AUD-25 and
DU-AUD-26 in that order. The existing native attachment, extension, database-copy,
secret and receipt implementations are retained. Twenty-five typed engine
operation descriptors and a callable descriptor-to-task adapter now carry their
missing field contracts. This does not close the separate broader object-form
parity, remote/foreign attachment, extension-transport qualification, runtime
configuration or native outcome-matrix items. Shared UI routing and human
presentation remain with the UI group; no renderer, family skeleton, descriptor
schema or legacy editor panel is changed. Descriptor ``draft`` status records
that presentation boundary rather than an absent native backend.

Common transport
~~~~~~~~~~~~~~~~

Use the existing authenticated server workspace POST endpoint
(``NODE-server.cde_workspace_id``), action ``duckdb_editor_operation``. The
existing success/data or error envelope and ``Cache-Control: no-store`` remain.
Both the owned registration and its nonempty registered ``database_target_id``
are mandatory. All live operations require the exact original ``session_id``
outside the dialog draft. The adapter never opens a substitute SQL session,
accepts a client route/native handle, or dispatches a client-supplied transport.

Discover the machine-readable backend contract without native SQL::

    {"action": "duckdb_editor_operation",
     "database_target_id": "<owned target>",
     "request": {"operation_id": "describe"}}

The response format is ``scratchrobin.duckdb.editor-operations@1``. Its rows
include the standard engine descriptor, native task/operation, any fixed native
action, permissions, admission, outcome keys, scope and whether the original
session is required. Secret tasks identify their existing common administration
transports, with authoritative session-catalog preflight for removal. Release
identifies the existing close-session transport. These mappings are backend
implementation details: the shared task host submits the typed operation draft
to this adapter, not to independent-file provider plan/apply::

    {"action": "duckdb_editor_operation", "database_target_id": "<owned target>",
     "session_id": "<original session>",
     "request": {"operation_id": "editor_copy_review",
                 "draft": {"source_catalog": "source",
                           "destination_catalog": "destination", "mode": "ALL"}}}

Unknown fields, invalid choices and wrong primitive types refuse before native
dispatch. Native permission, path, version, storage, transaction and capability
admission remain authoritative and are checked again by the existing task.
Descriptors have only typed controls/grids; the native preview or common plan
belongs on the canonical SQL tab. Protected values stay private to the native
review/plan. Never fabricate a successful readback, commit, rollback, progress,
cancellation or replay from a saved receipt.

DU-AUD-22: attachment and storage controls
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_attachment_`` operations are:

* ``inventory``: no fields; returns native ``catalogs`` and ``original_catalog``
  with exact alias/OID/path, access, storage options, encryption and cipher.
* ``review_attach``: required ``alias`` and absolute registered-root ``path``
  (or explicitly authorized ``:memory:``); ``read_only=true``,
  ``conflict=ERROR|IGNORE|REPLACE`` (default ERROR),
  ``create_if_missing=false``. Optional ``block_size`` and ``row_group_size``
  are exact unsigned-64-bit decimal strings, and ``storage_version`` is native
  version text. ``compress_mode=NATIVE|ENABLED|DISABLED`` omits the option or
  sends the explicit native Boolean, admitted only for memory attachments.
  ``key_mode=NONE|SUPPLIED`` distinguishes omission from a supplied
  ``encryption_key`` password control; ``encryption_cipher=NATIVE|GCM|CTR``
  omits the cipher or selects it explicitly. Unselected but populated encryption
  controls refuse. Native open/create rules remain decisive: these options do
  not rewrite an existing store.
* ``review_detach``: required ``alias`` and ``if_exists=false``. The original
  registered catalog and native system/temp aliases cannot be detached.
* ``apply``: required review ID/digest, ``confirmation`` equal to the reviewed
  native alias, and ``confirmed=true``.
* ``receipt``: required ``review_id``; reads the original-session receipt,
  including terminal/uncertain states without native redispatch.
* ``discard``: required review ID/digest; discards unused review authority and
  releases a bound private key without creating or deleting a database file.

All require ``execute``. Review/apply/discard additionally require resource
``administer`` and ``filesystem``. Reviews bind exact original namespace and
file facts; apply checks them again. Keys remain private, bind for at most the
existing five-minute review window, and are released after dispatch, discard,
expiry or original-session close. Public native SQL uses a bound placeholder;
public digests are not derived from key bytes. Native acknowledgement and
rediscovery are separate. Native alias reuse after DETACH can require an
explicit caller transaction decision. Instance-visible attachments, created
files, detached aliases and registered automatic attachments have their existing
native lifetime semantics; rollback is not a file cleanup/reattach promise.

DU-AUD-23: extension controls
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_extension_`` operations are:

* ``inventory``: no fields; returns native installed/loaded/source/version facts,
  current runtime/home/extension-directory context and native admission settings.
* ``review_install``: required ``extension_name``; ``source_kind=NAME|FILE|URL``
  (default NAME), optional ``source``, Boolean ``force=false``,
  ``repository_kind=DEFAULT|ALIAS|URL|DIRECTORY`` (default DEFAULT), optional
  repository, native extension version and ``expected_http_secret`` name.
* ``review_load``: required extension name, ``source_kind=NAME|FILE`` and optional
  source. It has no FORCE, repository, version or remote URL option.
* ``apply``: required review ID/digest, exact extension-name ``confirmation`` and
  ``confirmed=true``.
* ``receipt``: required review ID; separates native dispatch/acknowledgement,
  last installed inventory and rediscovery availability.

All require ``execute`` and resource ``data_read``; review/apply additionally
require resource ``administer`` and ``filesystem``. The current native adapter
requires DuckDB 1.5.2 and binds original-session inventory, settings and source
identity. Files/directories stay under the registered root; file/URL sources
supply their own native artifact version rather than accepting repository/version
modifiers. Public HTTP(S) URLs exclude inline credentials, query and fragment.
``expected_http_secret`` names an existing native identity selected by
``which_secret`` for the exact download URL: it never supplies credential values
or establishes successful authentication. Native HTTP credential use requires
separate ``secret_read`` authority and actual httpfs availability. Installed
capability/admission observations are not replacement source availability proofs.

Installation/loading is synchronous; no progress or cancellation endpoint is
advertised. Native filesystem/process effects are not rolled back with a database
transaction. Terminal receipts are returned without replay; unknown outcomes
block reuse according to the native adapter. Existing ``update_extensions``
descriptors/native workflows remain separate. This batch positively qualifies isolated INSTALL of the existing signed httpfs
artifact (native version 13e18b3) from an approved-root file, native signature
admission, and LOAD of httpfs and built-in JSON. Source/repository/version/FORCE/
HTTP-identity controls are additionally checked through the native compiler and
refusal tests. It does not claim a successful remote INSTALL, native HTTPS
transport or TLS/authentication matrix; DU-AUD-33 remains open.

DU-AUD-24: native database copy and encryption
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_copy_`` operations are:

* ``inventory``: no fields; current attached catalogs and native storage facts.
* ``review``: required ``source_catalog`` and ``destination_catalog`` with
  ``mode=ALL|SCHEMA|DATA`` (default ALL). Distinct native catalogs, writable
  destination, registered filesystem/memory authority and native eligibility
  are required. Review itself uses a worker that reads native metadata and
  row aggregates within the existing budgets; poll its receipt.
* ``apply``: required review ID/digest, exact destination-catalog confirmation
  and ``confirmed=true``. ALL runs native SCHEMA then DATA as separate stages;
  DATA appends to native existing destination objects.
* ``receipt``: required review ID. Show ``phase``, active table, native steps,
  dispatch/acknowledgement, original storage facts, storage observation,
  rediscovery and session-reuse state. Wait for ``phase=finished`` before
  considering the worker released.
* ``cancel``: required review ID; requests interruption of an active worker.
  Read the final receipt; a request is not a completed rollback.
* ``discard``: required review ID/digest; discards unused reviewed authority,
  not destination files or acknowledged native effects.

All require ``execute`` and resource ``data_read``. Review/apply/cancel/discard
also require resource ``administer``, resource ``data_write`` and ``filesystem``.
A durable dispatch observation is required before native mutation. The native
one-writable-database-per-transaction limit, conflicts, partial stages,
cancellation and uncertain results are preserved; no implicit commit/rollback
or fallback is introduced. Row-bag aggregate and object/storage postconditions
are exactly the existing native checks, not a cryptographic equality claim.

Encryption, decryption and key changes use a separately attached destination
configured through the attachment contract, then native copy, explicit caller
commit/detach and independent reopening with the intended key/cipher. There is
no native in-place REKEY field or automatic replacement/cutover. Qualification
copies real objects/data into an encrypted destination and independently reopens
it. Native CTR reopening requires an explicit CTR cipher; omitting it is a
qualified native refusal, not a reason to change cipher or weaken admission.
Retiring a source remains a separately reviewed owner decision.

An isolated reference-runtime configuration initially has a read-only crypto
module. Encrypted writes require loading its native writable crypto provider
(httpfs here). Authenticated qualification records the actual pre-load refusal,
explicit caller rollback, signed-file INSTALL/LOAD and successful encrypted
creation/copy afterwards. It never enables ``force_mbedtls_unsafe``. The UI
handoff must show this dependency and use the extension inventory/workflow;
a cipher name alone does not prove native write capability.

DU-AUD-25: original-session secret fields
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_secret_`` operations are:

* ``inventory``: no fields; native public secret resources, with storage and
  persistence included in their distinct resource identities. It never reads
  native credential strings. Public native type/provider/storage/scope metadata
  can be present; do not equate that metadata with a secret value.
* ``review_create``: optional ``name=""`` (native default name),
  ``secret_type=HTTP`` (or empty with an explicit TYPE expression),
  ``persistence_mode=TEMPORARY|PERSISTENT|DEFAULT`` (default TEMPORARY), optional
  native storage name, and ``on_conflict=ERROR|IF NOT EXISTS|OR REPLACE``.
  ``property_nodes`` is an ordered typed grid: node ID, parent ID, property/map
  key, kind TEXT/INTEGER/DOUBLE/BOOLEAN/NULL/LIST/MAP, private scalar value and
  typed TRUE/FALSE choice. Root keys name native properties; LIST children have
  no keys; MAP children have exact string keys. Scalars, exact decimal integers,
  finite doubles, Booleans, NULLs and nested containers remain distinct.
  There is no raw JSON control. Node identities/parents/keys, cycles, unreachable
  nodes and depth/node budgets are checked; the existing native byte budget and
  SQL parser remain authoritative. Literal text is never inferred to be SQL.
  ``property_expressions`` is a separate ordered property-name/private-expression
  grid. Expressions are parsed without execution during review and evaluated
  only by the explicitly applied native statement, including original variables.
  Names are distinct across constants/expressions under native admission.
* ``review_drop``: required observed secret ``resource_id`` and exact secret-name
  confirmation. The backend reacquires that resource from the original native
  session and plans ``DROP SECRET ... FROM <observed storage>``; it never trusts
  a client-supplied storage/native record.
* ``apply``: common ``plan_id``, ``plan_digest`` and ``confirmed=true`` on the
  exact original session and registered target.
* ``receipts``: no fields; reads/filter the existing common operation receipt
  list for secret operations in the authorized endpoint/target scope. It is not
  the attachment/extension/copy archive described below.

The existing common administration pipeline checks native secret operation
permissions, retained session, verified runtime and one-use plan again. A native
TYPE expression with an explicit name is now admitted through the legacy
validation field as well as the native compiler; absence of both literal type
and TYPE expression still refuses. Private constants/expressions use the native
form's existing sensitive fields, so public previews/receipts omit them. The
native public metadata required for scope/storage identity remains observable.
Native expression functions can contact external systems at apply; a parse does
not establish execution authority or safety. Persistent native storage writes
and removals can survive database rollback. Native execution errors may abort
the caller transaction; the adapter never requests rollback. Identical native
public-metadata replacement cannot be detected and is not claimed fenced.

DU-AUD-26: receipt paging, finality and original-session release
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``editor_receipt_`` operations are:

* ``list``: integer ``offset=0``, ``limit=25`` (1..100); returns archived pages,
  total/more, family, last persisted observations and original-session state.
* ``get``: required ``review_id``; full authorized archived observation, including
  ``archived_read_only=true``, ``live_session_observed=false``,
  ``outcome_observation`` and ``transaction_finality_inferred=false``. An old
  applying/unknown state does not imply a completed native result.
* ``release``: required ``confirmed=true`` and the live original session ID;
  delegates to the existing common close-session path. Active workers must
  finish or be cancelled explicitly. Native close discards uncommitted database
  work, but cannot reverse persistent file/secret effects or unload process code.
  Show native close separately from durable ``receipt_release_recorded``;
  release failure/unconfirmed recording stays explicit.

Archive get/list require ``execute`` and ``data_read`` on the owned target;
``session_id`` is optional and no native connection/SQL is opened for the read.
The archive is owner/endpoint/registered-target bound. Original-session release
requires actual live authority; persisted receipts never reconstruct it.
Read-only archive reconstruction after close/restart is supported by the existing
store; no apply/retry/remove action is invented on this archive. Private keys and
native credential values remain excluded from persisted operation receipts.

Qualification scope
~~~~~~~~~~~~~~~~~~~

Verification uses owned Linux DuckDB 1.5.2 file/memory fixtures, the real typed
descriptor-to-task adapter, retained provider/common administration paths and
authenticated desktop HTTP. It includes encrypted creation/copy/independent
reopening, original transaction/TEMP state, native JSON loading, private secret
constant/expression and duplicate-storage workflows, and archived reads after
release with native-connect-forbidden regression checks. Shared descriptor/lint
and operation/family render checks are retained in the designated work area.
No frontend implementation, other-runtime/platform completion, remote-extension
transport success, ScratchBird history qualification or full-product completion
is inferred from these scoped results.

MariaDB native diagnostics, live plans, shutdown and binlog events; DuckDB alias (2026-11-15)
==========================================================================================

This batch implements ``MA-AUDIT-ENGINE-DIAGNOSTICS``,
``MA-AUDIT-OTHER-SESSION-PLANS``, ``MA-AUDIT-NATIVE-SHUTDOWN``,
``MA-AUDIT-BINLOG-EVENTS`` and ``DU-AUD-04``. These are scoped backend
and descriptor contracts. Form presentation, shared UI task routing and
Windows/macOS acceptance remain with their owners; other audit items remain
open. MariaDB qualification uses the pinned native 12.2.2 interface and the
patched 1.1.14 connector; DuckDB qualification uses native 1.5.2. No
ScratchBird monitoring-history qualification is performed.

MariaDB common native operation hooks
------------------------------------

The MariaDB dialect inventory retains its existing 88 qualified tasks and adds
six native server tasks (94 total), backed by successful native compiler
statements and acknowledgements. This is generated-task coverage, not product
completion. ``tools/cdeadmin_mariadb_server_management_qualification.py``
qualifies the added tasks and actual owned-process exit; it is included in
``tools/cdeadmin_mariadb_tasks_gate.py``.

The common ``visual_admin_catalog``, ``visual_admin_validate``,
``visual_admin_plan`` and retained ``visual_admin_apply`` routes expose six
server operations. Use the observed server resource, not an invented MySQL
identity: ordinary discovery provides ``server:MariaDB`` with display name/path
``MariaDB`` and native ``server_uid``; native server exchange provides
``mariadb-server:[server_uid,"server"]`` with its own observed display name/path.
The server UID is MariaDB's native value, not a UUID. Database target,
registration/credential and operation authorization remain enforced by the
common workspace/visual-administration facade. These operations require native
network connections independent of an editor session; a supplied original
``session_id`` is refused. Backend-owned SQL is compiled from typed fields;
there is no arbitrary SQL or client credential field.

All six operations require exact server-name ``confirmation``. Review binds
native server UID, version, authenticated/effective principals, active role and
SQL mode. Apply repeats those observations on a new dedicated connection.
Pooling options are removed. Connect/read/write timeouts are five seconds;
there is no automatic reconnect/replay. Native privilege enforcement is still
authoritative. The UI must distinguish common control-operation state from
``provider_result`` native observations and must retire submitted one-use plans.

* ``inspect_engine_status``, ``inspect_engine_logs``,
  ``inspect_engine_mutex``: ``engine_scope`` is ``ENGINE`` or ``ALL``;
  ``engine`` is required only for ENGINE and omitted/empty for ALL;
  ``private_data_confirmed`` must be true. Native installed/support state is
  reviewed and rechecked. SQL is one native ``SHOW ENGINE ...`` statement,
  including ALL. STATUS/MUTEX require PROCESS; LOGS requires FILE. Native
  denial codes differ: PROCESS is 1227/42000, FILE is 1045/28000 on the qualified
  runtime. The backend preserves native error number/SQLSTATE; do not label
  every 1045 as a connection-authentication failure.
* ``inspect_live_explain``, ``inspect_live_analyze``:
  ``connection_id`` is exact positive unsigned 64-bit decimal **text**;
  ``output_format`` is TABULAR or JSON; ``private_data_confirmed`` must be true.
  The backend issues native SHOW EXPLAIN/ANALYZE, never executes an ANALYZE
  statement in the target session. PROCESS is needed for another user's
  sessions; the native own-user exception is supported and qualified. An
  invisible/missing active query is reported as unavailable or not visible,
  never as proof that it does not exist.
* ``shutdown_server``: ``service_disruption_confirmed`` must be true. The
  native SHUTDOWN privilege is required. Review expires after 60 seconds;
  native uptime progression is rechecked with two-second granularity tolerance.
  This is an observation fence, not an atomic process-generation reservation.
  The backend issues only SHUTDOWN, without host service manipulation or
  restart. Embedded shutdown is unsupported. Interrupted/lost responses are
  unconfirmed and never replayed.

Successful engine diagnostics return ``provider_result.engine_diagnostic``:
``columns`` (Type, Name, Status), ordered ``rows``, ``complete``, ``truncated``,
row/UTF-8 byte limits and returned bytes, actual engine inventory,
``execution_identity``, timestamp, ``private_content``, ``native_dispatched``,
``native_acknowledged`` and ``native_completion``. ENGINE is bounded to
256 rows/1 MiB, ALL to 4096 rows/8 MiB. Truncated output is not a complete
acknowledgement; an empty native result does not prove that a handler is implemented.
Do not parse native output into invented capabilities. Private SQL, paths and
transaction details can be present; do not persist it to monitoring history.

Live plans return ``provider_result.live_plan`` with native column names and
ordered typed cells, query identity, execution identity and the same independent
acknowledgement/completeness observations. Large integers are decimal strings,
decimals/floats preserve their exact driver representation, binary values use
base64 envelopes. Native JSON output stays native JSON text. Identity binds
PROCESSLIST ID, USER, HOST, DB, COMMAND and native QUERY_ID without collecting
INFO/INFO_BINARY. Review/apply compare it before dispatch and after a complete
read; changed-query output is withheld. The checks are not an atomic query
reservation. At 256 rows/1 MiB, unread partial output is discarded and its rows
withheld because the post-read identity cannot be verified. A native SHOW
request can wait up to 30 seconds: a five-second client timeout does not prove
server cancellation. Native refusal/not-explainable errors are not simulated
with a fresh EXPLAIN against copied SQL.

Shutdown returns ``provider_result.shutdown`` with ``native_completion``
``shutdown-request-acknowledged``, ``native_acknowledged``,
``process_exit=not-observed``, ``host_service_control=false`` and
``restart_requested=false``. Native OK acknowledges the request; it does not
prove the operating-system process stopped. Qualification separately observes
the owned Docker process exit/code/OOM state. Do not display an unreachable
socket as confirmed process exit or report other clients' transaction finality.

All successful responses separately return ``connection_release`` with cursor
and connection cleanup facts; transaction-decision/retry flags remain false.
Native exceptions retain errno, SQLSTATE, dispatch/acknowledgement and cleanup
on the provider exception. The common HTTP failure receipt conservatively
reports its existing unknown-outcome state and native status codes; it does
not expose all provider exception attributes or private SQL. UI callers must
not infer cleanup or rollback from that HTTP error, nor retry its retired plan.

Lossless native binary-log discovery
-----------------------------------

The ordinary MariaDB catalog reader now uses
``mysql_family.mariadb_binlog_events.read``. It requires the rebuilt pinned
connector's checked-fetch and ``cdeadmin_lossless_text`` cursor support.
No SET NAMES/character_set_results mutation, replacement-character decoding or
silent fallback occurs. The opt-in flag is restored in ``finally``. Without
that opt-in, actual UTF-8 decoding failures propagate as UnicodeDecodeError
from fetchone/fetchmany/fetchall rather than SystemError or end-of-results.
Native binary fields keep bytes; valid UTF-8 remains text.

Each binary-log-event retains native log/position/type/server/end-position
facts. ``info`` is text or a base64/data/byte_length envelope;
``info_representation`` distinguishes native UTF-8 text, native binary and
undecodable native UTF-8 bytes. ``info_native_field`` retains the driver field
metadata. Do not render an envelope as a hex/text guess. Event resource IDs
and ``navigator_parent_resource_id`` remain under the observed binary log.
Each log's ``event_observation`` separately reports complete/truncated/limit
(200), retry and charset-change facts. The reader requests 201 rows to detect
truncation. Query/native-permission failures remain catalog failure
observations, never a fabricated empty complete section. This is bounded
catalog observation, not complete binary-log archival/replay. Rebuild the
connector with ``tools/cdeadmin_build_mariadb_driver.py`` and the reviewed
patch; its source and wheel provenance are retained with qualification.

DuckDB original-session SET ALIAS hook
-------------------------------------

``editor_attachment_review_rename`` is an additional typed descriptor in the
existing ``duckdb_editor_operation`` contract. It maps to fixed transport
``duckdb_attachments`` with ``operation=review`` and draft
``{action: rename, alias, new_alias, dependent_sql_confirmed}``.
Both aliases are exact text and acknowledgement must be true. Existing
``editor_attachment_apply``/``receipt``/``discard`` routes and exact old-alias
confirmation/review ID/digest remain in use. The existing execute, administer
and registered-filesystem permissions and original retained session lock apply.
The registered original catalog and internal catalogs cannot be renamed;
foreign attachment types and existing destination aliases are refused. Native
alias comparison folds ASCII only, preserving non-ASCII distinctions.

The backend compiles native ``ALTER DATABASE old SET ALIAS TO new``; it never
renames a physical file. Review/apply fence original route/catalog identity,
full attached namespace, file identity, current native transaction ID, observed
catalog definitions and native dependency rows. Catalog capture is bounded to
20,000 resources/dependencies and 8 MiB. A transaction, metadata, dependency,
namespace or file change refuses the one-use review before dispatch. The
public ``alias_review`` includes descendant identities, stored SQL source
hashes and native dependency observations without exporting source text.
Native dependency tables cannot enumerate every external/dynamic SQL reference.

Native alias changes survive rollback. Stored SQL is not rewritten, so old
references may fail; some views remain executable. These are native effects,
not guarantees inferred from SQL text. ``dependent_sql_confirmed`` explicitly
acknowledges that limitation. Successful receipts expose ``new_alias``,
``invalidate_resource_ids`` and ``refreshed_descendant_identities`` for the UI
team to invalidate the complete old subtree and reload its new identities.
They also report ``physical_file_renamed=false``,
``stored_sql_rewritten=false``, ``alias_restored_by_rollback=false``, native
acknowledgement and separate rediscovery verification. A completed/uncertain
receipt is read without redispatch. Only the caller commits/rolls back its
pending database work; that decision cannot restore the old alias. Design
bindings referring to old catalog identities are marked ``suspect`` in the
authoritative ``designs.db`` binding table, scoped by engine, endpoint and
database target, including bindings through stable resource-identity UUIDs.
The native dispatch-receipt publisher records this notice before executing
SET ALIAS; failure to record the notice prevents native dispatch. Native
refusal or uncertainty can therefore leave bindings conservatively suspect
until confirmed. A UUIDv7 ``catalog_binding_notice`` runtime row deduplicates
the native review ID durably; receipt reads, replay and process recreation
cannot undo a later explicit binding confirmation. This notice does not create
or alter DDN design versions or silently reassign target references.
``binding_notice`` reports its recorded ID and affected-binding count. The UI
uses the existing explicit binding-confirmation workflow to choose the desired
new reference; native acknowledgement, binding notice and rediscovery remain
separate observations. Anonymous volumes owned by the shutdown qualification
fixture are recorded and their deletion is verified along with container exit.

MariaDB recovery, caches, replication resets and sequence options
================================================================

This backend increment addresses ``MA-AUDIT-XA-RECOVERY``,
``MA-AUDIT-KEY-CACHE``, ``MA-AUDIT-ALL-CHANNELS`` and
``MA-AUDIT-SEQUENCE-FIELDS``. Its native reference is MariaDB 12.2.2 on
Linux; human presentation and Windows/macOS qualification remain separate.
Native acknowledgement, handler success, postcondition observation and cleanup
are separate receipt facts. None establishes an atomic external-writer fence.

The fourteen new server operations are declared in MariaDB's
``operations.json`` and served by the existing visual-administration
validate/plan/apply routes. Submit the exact observed server resource and typed
draft; preserve the returned plan ID/digest and native identity/observation.
Apply the retained plan once with confirmation. The shared facade retires a
submitted plan after failure or uncertainty; never reconstruct it for replay.
These operations own independent, unpooled connections and refuse a borrowed
query session. They never commit or roll back the caller's pending work.

* ``inspect_prepared_xa`` uses native ``XA RECOVER FORMAT=RAW``. Binary global
  and branch identifiers are uppercase hexadecimal strings with explicit byte
  lengths; never decode them as text. ``commit_prepared_xa`` and
  ``rollback_prepared_xa`` require ``gtrid_hex``, ``bqual_hex`` (possibly empty),
  canonical decimal-text ``format_id``, the exact server ``confirmation`` and
  an external coordinator ``decision_reference``. Native SQL admits format IDs
  0 through 2147483647; recovery can observe externally supplied IDs beyond
  that range, which this native SQL interface cannot resolve. The decision
  reference records the instruction, not proof of a global distributed commit
  decision. Review/apply rechecks branch presence and native execution identity;
  it cannot prove an XID has not been reused. Show ``xa_observation`` and
  separate connection-release/native error facts. A still-associated prepared
  transaction may be refused by native resolution from another connection.
* ``inspect_key_caches`` reads native ``information_schema.KEY_CACHES``,
  including configured names, segments and runtime counters;
  ``inspect_key_cache`` reads a selected prefix's six exact decimal-text values.
  ``configure_key_cache`` selects one of ``key_buffer_size``,
  ``key_cache_block_size``, ``key_cache_division_limit``,
  ``key_cache_age_threshold``, ``key_cache_file_hash_size`` and
  ``key_cache_segments``, with ``value_mode=VALUE`` plus unsigned decimal-text
  ``value``, or explicit native ``DEFAULT``. ``release_key_cache`` sets a named
  buffer to zero; default-cache release is refused. These are runtime settings,
  not server-configuration persistence or cache-content proof.
* ``assign_index_cache`` and ``preload_index_cache`` accept a typed ``tables``
  grid of database/table identities (at most 32), optional ``index_selection``
  rows with zero-based ``table_index`` and exact ``index_name``, and either
  exact ``partitions`` or ``all_partitions`` for a single table. Preload alone
  accepts per-table ``ignore_leaves``. Assignment selects ``cache_name``;
  preload deliberately has no cache selector because native LOAD uses the
  existing native assignment. Both compile one native batch statement, rather
  than an application execution loop. Only visible MyISAM base tables qualify.
  Show native handler rows and warnings: command acknowledgement alone does
  not mean every table returned status OK. Native definitions/indexes/partitions
  are rechecked, without pretending their hashes establish object generations.
* ``start_all_replicas`` and ``stop_all_replicas`` compile native START/STOP ALL
  SLAVES with ``threads=ALL|IO_THREAD|SQL_THREAD``. They do not loop through
  named channels. Before/after topology excludes passwords and mutable health
  counters; acknowledgement does not prove healthy or caught-up replication.
  ``reset_default_replica`` explicitly addresses the empty native connection
  name, independent of default_master_connection, and optionally removes its
  configuration with ``remove_configuration`` plus
  ``configuration_loss_confirmed``. Named-channel reset remains separate.
* ``reset_binary_logs`` issues RESET MASTER, optionally TO an exact positive
  decimal-text ``next_log_number`` through 2147483647. Require
  ``history_loss_confirmed`` and typed server confirmation. Show irreversible
  replica/backup history loss before apply; native gtid_slave_pos is not reset
  by this operation. ``reset_query_cache`` issues native RESET QUERY CACHE.
  These global effects cannot be rolled back or automatically retried.

Cache and replication/reset results use ``management_observation`` with
``before``, ``after``, native result columns/rows, bounded native warnings,
``native_acknowledged`` and separate ``native_reported_success``. Review
identity/topology changes refuse mutation before dispatch; observation budgets
refuse incomplete results instead of manufacturing complete empty lists.

Sequence create/alter now have explicit typed operation descriptors and the
shared sequence-family form. All integer values use exact decimal text so an
unsigned BIGINT bound survives JSON/JavaScript transport. ``integer_type``
selects TINYINT, SMALLINT, MEDIUMINT, INT or BIGINT; ``unsigned`` requires an
explicit type. Native ALTER AS must be reviewed separately from other sequence
options, as MariaDB forbids combining them in one ALTER; the compiler refuses
that combination instead of silently splitting independently committed changes.
Start, increment, cache and cycle intent remain native options;
``minimum_mode``/``maximum_mode`` select PRESERVE, VALUE or NATIVE. NATIVE emits
NO MINVALUE/NO MAXVALUE, rather than a guessed numerical default. Cycle intent
is PRESERVE/CYCLE/NOCYCLE. Alter can select one exact ``restart`` or
``restart_initial``, requiring the sequence's exact name as ``confirmation``.
Native limits, clamping and impossible bound combinations remain native
admission decisions. In the reference runtime, ALTER AS BIGINT UNSIGNED followed
by NO MAXVALUE reads back 9223372036854775806; creating an unsigned BIGINT with
an explicit bound supports 18446744073709551614. Do not infer a reset bound
from SHOW CREATE's type spelling or emulate a different default: show the native
readback. No NEXTVAL is used for discovery or verification. DDN
``mariadb_change`` sequence alters use the same option compiler while retaining
the unchanged native definition/context precondition; old minvalue/maxvalue
intent keys remain accepted there. Native DDL has independent commit effects.

SQLite capture and artifact descriptor handoff
=============================================

``SQ-DESC-02`` supplies typed descriptors for the existing native capture and
artifact backend. This does not replace it with stubs or implement a new UI.
The existing ``sqlite_editor_operation`` describe contract now includes:

* ``editor_capture_*``: inventory, open, attach, status, configure,
  object_config, diff, table_filter and close on the original retained handle.
  Explicit ALL modes map table/pattern selection to native null; exact mode
  requires a name/pattern. PRESERVE/ON/OFF switches avoid silently changing
  unspecified enable/indirect state. Native object configuration must precede
  attaching the first table. Closing requires confirmation and discards
  unexported capture state, not pending caller SQL.
* ``editor_export_*``: review the selected retained capture and native
  changeset/patchset format, then start/list/status/cancel/files/reconcile/remove
  the owned durable export. The original session identity is supplied by the
  envelope at review. No replacement database connection is substituted.
* ``editor_apply_*``: catalog, sources, review, start, list, status, cancel,
  files, reconcile, remove_artifact, conflict and decide. Review carries an
  owned source target/job/path/kind and typed options; independent file apply
  has its own transaction and commit receipts. Conflict policy has a separate
  choice per native kind; replacement is offered only for DATA/CONFLICT.
  Interactive decisions carry the exact callback challenge, bounded native
  choice and remember-kind Boolean, never arbitrary JSON or SQL.
* ``editor_transform_*``: catalog, schemas, sources, review and the same
  durable job controls. A typed ordered input grid identifies native
  capture/upload/transform/diff/rebase artifacts; no application-host file path
  is accepted. Native invert/concat/merge/rebase, optional schema basis and
  automatic/changeset/patchset output preserve their native compatibility rules.
* ``editor_inspection_*``: catalog, separate review_page/review_cell/
  review_extract forms, start/list/status/cancel/files/result/reconcile/removal.
  Exact decimal text preserves record/byte offsets. Each mode sends only its
  native operands; bounded previews never claim to validate an unvisited suffix
  or turn byte values into guessed text.
* ``editor_diff_*``: catalog/tables and review/start/list/status/cancel/files/
  reconcile/removal. A disposable native capture compares exact attached source
  and destination tables on the original retained handle, preserving existing
  captures, pending SQL and savepoints. It does not apply the resulting file.
* ``editor_upload_*``: catalog, create, checksum-bounded chunk, seal and durable
  job controls. File lengths/offsets remain decimal text. Native iterator
  validation and SHA-256 receipts precede eligibility as an apply/transform input.
* ``editor_delivery_*``: export/apply/transform/inspection/diff/upload and
  conflict_value typed binary delivery. The adapter returns ``binary_delivery``
  with a fixed existing workspace form action and bounded payload. POST that
  action and JSON-encoded payload as form data to the same authenticated
  workspace URL; never send file bytes through the JSON task response. The
  existing binary route independently checks owner, endpoint, target, receipt,
  exact artifact path/hash and conflict challenge/side/column. Delivery is
  limited to 4096 UTF-8 payload bytes and accepts no host filesystem path.

The 79 added SQLite operations use fixed transports in
``sqlite_capture_descriptors.py``; the combined editor contract contains 103
operations including the previous retained schema/receipt, preupdate, array and
extension tasks. All require an owned registered database target; original
session actions also require its live session. Native job managers retain
ownership, permission, runtime-helper, exact source identity and review-digest
checks. No client-supplied transport, native pointer, opcode or callback code is
accepted. A separate ``no_deadline`` choice maps to native null only where
operator runtime policy permits it. Start requires exact job ID, review digest
and confirmation. Completed/uncertain job receipts never imply replay authority.
Display native stage/result/worker-release facts and explicit commit-returned
receipts; cancellation, exported changes and verified files do not establish
that the original transaction committed. Schema/source compatibility and native
helper availability remain per-operation admission checks, not descriptor-only
completion claims. Frontend form integration and human/platform acceptance
remain with their owning teams.

PostgreSQL native application-host utilities
==========================================

Five backend utility workflows are supplied for the PostgreSQL 18 native-tool
interface: ``PG-AUDIT-UTILITY-PG_CONTROLDATA``,
``PG-AUDIT-UTILITY-PG_WALSUMMARY``, ``PG-AUDIT-UTILITY-PGTESTTIMING``,
``PG-AUDIT-UTILITY-PGTESTFSYNC`` and ``PG-AUDIT-UTILITY-PG_CHECKSUMS``.
They are application-host tools, independent of a connected SQL session and
of the registered server's network location. They do not start, stop or
implicitly modify the registered remote server. Tool major-version admission
is explicit; other native major versions and platform qualification must not
be inferred from this interface's Linux receipts. This work leaves the
PostgreSQL provider-tree migration and inherited SQL/tool behavior intact.

Operator admission and paths
----------------------------

The application operator configures
``CDEADMIN_POSTGRESQL_HOST_BINARY_PATH`` (otherwise the continuity tool
directory is used), ``CDEADMIN_POSTGRESQL_HOST_TOOL_ROOT`` (durable job files)
and ``CDEADMIN_POSTGRESQL_HOST_TOOL_MANIFEST`` (an absolute manifest filename).
The manifest's format is ``scratchrobin.postgresql.host-tools@1``. Its
``grants`` array contains exactly one matching ``endpoint_id`` for admission;
that row may contain ``clusters``, ``summary_files`` and ``benchmark_roots``.
Each entry has a bounded stable ``id`` and an exact absolute ``path``. Cluster
entries may additionally declare ``tablespaces`` as exact native ``oid`` /
absolute ``path`` pairs. Browser drafts never supply host paths or executables.
A minimal operator grant has this shape::

    {
      "format": "scratchrobin.postgresql.host-tools@1",
      "grants": [{
        "endpoint_id": "<registered endpoint UUID>",
        "clusters": [{"id": "offline_main", "path": "/operator/offline/main"}],
        "summary_files": [{"id": "summary_1", "path": "/operator/summary.native"}],
        "benchmark_roots": [{"id": "scratch_disk", "path": "/operator/scratch"}]
      }]
    }

Admission requires an owned native PostgreSQL registration, ScratchRobin
``backup_admin`` permission, and independently computed application-host
Administrator authority. The HTTP handler derives that authority from the
current authenticated user and server mode; it is not a draft Boolean. These
requirements do not replace OS permissions: tools run as the application's
native OS identity, which must already have access to the granted offline
files. No implicit elevation, remote-shell command, replacement database
connection, inherited PGDATA or client executable path is used.

Manifest identity, selected native files, native tool version/hash, execution
hostname/platform/OS identity and exact options are bound into the server-owned
review. Replacing input files or changing grants/paths/runtime/configuration
requires a fresh review. A cluster version marker must match the admitted
native tool major. Unexpected symbolic links, nonregular inputs and oversized
observations are refused. Checksum scan roots also refuse hard-linked files;
external tablespaces require explicit matching OID/path grants. Job storage
cannot be placed inside the selected database cluster. Snapshots and managed
resource leases do not establish an atomic fence against unrelated native
writers, external starts or other application instances using another store.

Typed task transport and outcomes
---------------------------------

These five ``host_pg_*`` entries in PostgreSQL ``operations.json`` are task
forms, not generic visual-admin SQL commands. Database-scoped workspace URLs
and database-target envelopes are refused: these host/whole-cluster operations
are admitted only from the server workspace. Use the owned server workspace
HTTP endpoint with ``action=postgresql_host_tools`` and ``request`` containing:

* ``stage=describe``: obtain the typed descriptor inventory, fixed stage names,
  permissions, host scope and no-retry contract.
* ``stage=catalog``: obtain only the endpoint-granted cluster, summary-file and
  scratch-root identities, manifest SHA-256 and actual installed native-tool
  availability/version/build hash. Missing tools are unavailable, not empty
  successful results. A granted file's accessibility remains review admission.
* ``stage=review``, ``operation_id`` and ``draft``: submit one descriptor's
  typed fields. The backend returns an opaque ``job_id`` and ``review_digest``,
  native program/host/source observations, expiry and consequences.
* ``stage=start`` with that ``job_id``, ``review_digest`` and ``confirmed=true``:
  claim exactly one native dispatch. No draft, SQL, argv or path is accepted at
  this stage. Repeated submission returns the existing receipt and never
  repeats the process.
* ``stage=status`` or ``cancel`` with ``job_id``; ``stage=list`` with bounded
  ``offset``/``limit``: read owned durable receipts or request cancellation.
  Revoking a manifest grant does not prevent reading/cancelling an existing
  receipt; it prevents newly admitted native execution.
* ``stage=reconcile`` with ``job_id``: after the worker stops, independently
  inspect the original durable native process reference and release its managed
  lease/owned temporary input only after confirmed termination. Reconciliation
  never changes an uncertain native operation into success and never replays it.

The worker records native dispatch admission before invocation. A durable
resource lease remains after an unknown process outcome, preventing another
managed invocation on that resource until reconciliation. Independently
confirmed termination is monotonic even when cancellation races the worker's
exception write. The native process guardian also protects parent-process
loss. Receipts distinguish native return code, native success, bounded report
completeness, process termination, temporary-file cleanup and lease release.
Terminal states include ``completed``, ``partial`` (native success with incomplete report,
verification or cleanup), ``failed``, ``cancelled``, ``not_dispatched`` and ``unknown``.
Native return code zero does not establish application-data correctness.
Cancellation/timeout or a missing acknowledgement never proves rollback.
All five workflows report no borrowed SQL session or caller commit/rollback.

Each stdout/stderr stream is bounded to 1 MiB, with separate truncation flags;
the native process remains supervised while output is drained. The native
supervisor timeout is 1--3600 seconds and does not purport to bound every
filesystem metadata preflight. Progress and the original native process
reference remain in the durable receipt. Native tool/manifest/source observations
are rechecked at start and immediately before dispatch, under the managed
resource lease. A submitted uncertain job remains retired even if later
readback shows the requested effect.

Individual native operations
----------------------------

``host_pg_controldata`` accepts ``cluster_id``, exact cluster-ID
``confirmation`` and ``timeout_seconds``. It invokes native pg_controldata
against the granted cluster, returning the raw report and string-valued
``control_fields``. Large system identifiers remain exact strings. Inspection
is read-only; a report is not an atomic live-cluster snapshot or a health /
recovery certificate. It can inspect a locally available cluster without
connecting to the registered network server.

``host_pg_walsummary`` accepts a typed string grid ``summary_ids`` (1--100
ordered distinct identities), ``individual``, ``quiet``,
``confirmation="WAL summaries"`` and timeout. Every file is regular,
SHA-256-bound and copied into a private owned snapshot before the one native
pg_walsummary invocation. Input limits are 64 MiB per file / 256 MiB aggregate.
Native format errors remain failed native receipts, separate from stale-input
refusal. Quiet mode is passed to the native tool without rewriting its output:
the qualified runtime still prints relation-limit records in quiet mode, even
though block lists are suppressed. Do not infer empty output from the switch.
Parsed files do not prove producer identity or association with a remote
registered server. Temporary snapshots are removed only after safe cleanup.

``host_pg_test_timing`` accepts ``duration_seconds`` (1--60), timeout and exact
application-host hostname confirmation. It runs the native timing loop and
returns its report, histogram and native execution identity. It measures this
application host, not database-server timer overhead. There is no SQL or
engine transaction in this workflow.

``host_pg_test_fsync`` selects an operator-granted ``scratch_id``,
``seconds_per_test`` (1--60), timeout and exact application-host hostname.
The backend creates a fresh private subdirectory and native test filename in
that granted filesystem; existing files are never selected as the native
output. Native seconds per test is not the total duration: the utility runs
multiple native test families. The report describes the recorded host and
scratch filesystem only. Confirmed process termination precedes temporary-file
cleanup; uncertain native I/O leaves the owned scratch and lease for explicit
reconciliation. Cleanup checks the recorded directory identity and job marker
and cannot remove a replacement directory.

``host_pg_checksums`` accepts exact ``cluster_id``/confirmation,
``mode=CHECK|ENABLE|DISABLE``, optional canonical decimal-text ``filenode``
(CHECK only, native range 0--2147483647), ``progress``, ``verbose``, ``sync``,
``sync_method=fsync|syncfs`` and timeout. syncfs is admitted only on the qualified
Linux host interface; it can synchronize the containing filesystem, not only
one cluster file. ``offline_quiescence_confirmed`` is mandatory for every mode;
ENABLE/DISABLE additionally require ``checksum_change_confirmed``. Disabling
sync for a mutation requires ``unsafe_no_sync_confirmed``. The backend never
silently stops a server or discards a postmaster PID file.

The selected cluster must have no postmaster.pid and native control-data state
``shut down`` or ``shut down in recovery``. Control identity plus bounded file /
directory metadata fingerprints across native global/base/table-space scan
roots are checked again before dispatch. External table-space links must match
explicit grants and the native catalog-version directory. Every admitted scan
file must be regular and unshared; the observation budget is 100000 entries.
These metadata checks supplement the native utility's own CRC, page-size,
control-version, shutdown and checksum-state admission; they are not a
content hash of all database data or an external-writer lock.

The receipt separately reports checksum mutation intent, raw native scan/result
output, native control-data readback and no rollback availability. Filenode
selection does not prove that a relation exists: native success after scanning
zero files is not a table-integrity certificate. ENABLE can write many pages
before changing the control flag; an error or lost acknowledgement may leave
partial changes even if that flag is unchanged. Preserve an unknown outcome,
keep external starts/writers inhibited, reconcile the process and inspect native
state before deciding what to do next. Reopening and independently reading an
owned cluster, rather than a flag alone, qualifies the recorded positive cases.
Human UI integration/presentation and Windows/macOS acceptance remain separate.

Firebird embedded local administration: ten native service adapters
------------------------------------------------------------------

The following original audit gaps now have explicit local-only adapters:
``FB-EMB-set_access_mode``, ``FB-EMB-set_page_cache_size``,
``FB-EMB-set_sweep_interval``, ``FB-EMB-set_space_reservation``,
``FB-EMB-set_write_mode``, ``FB-EMB-set_sql_dialect``,
``FB-EMB-set_replica_mode``, ``FB-EMB-remove_linger``,
``FB-EMB-sweep_database`` and ``FB-EMB-validate_database``.
They extend the previously qualified ``database_statistics`` adapter; they do
not enable the remaining network-only Services operations on embedded routes.

Use the existing authenticated server workspace ``visual_admin_catalog``,
``visual_admin_validate``, ``visual_admin_plan`` and ``visual_admin_apply``
actions. Select the discovered database resource on a verified
``firebird-embedded`` registration. The shared Firebird operation descriptors
and typed fields are reused; the embedded catalog removes ``server_service``
workspace scope and labels these tasks local. Do not route them through a
network Services credential form or accept a filesystem filename from a
separate client field. The provider route owns the approved absolute filename
and filesystem root. The provider requires ``embedded_runtime`` and
``filesystem``; the common operation requires ``administer`` and its declared
``maintenance_admin`` grant. Native Firebird authorization remains decisive.
No network password, credential reference, wire configuration or remote host
is acquired or accepted by the local Services adapter.

.. list-table:: Typed local selections and native observation scope
   :header-rows: 1

   * - Operation
     - Draft fields (optional ``role`` on each)
     - Native behavior and qualification
   * - ``set_access_mode``
     - ``mode``: ``READ_ONLY`` or ``READ_WRITE``
     - Native property setter; independently reopened ``DB_READ_ONLY``.
   * - ``set_page_cache_size``
     - Required integer ``page_buffers``, 0..2147483647
     - Native stored cache setting; reopened ``SET_PAGE_BUFFERS``. Do not
       equate this with a live attachment's actual cache allocation.
   * - ``set_sweep_interval``
     - Required integer ``sweep_interval``, 0..2147483647
     - Native interval setter; reopened ``SWEEP_INTERVAL``.
   * - ``set_space_reservation``
     - ``mode``: ``USE_FULL`` or ``RESERVE``
     - Native header reservation setting; reopened ``NO_RESERVE``.
   * - ``set_write_mode``
     - ``mode``: ``ASYNC`` or ``SYNC``
     - Native write-mode setter; reopened ``FORCED_WRITES``. No claim that
       application acknowledgement proves hardware durability.
   * - ``set_sql_dialect``
     - ``sql_dialect``: exact string ``1`` or ``3``
     - Native database dialect setter; reopened ``DB_SQL_DIALECT``. Changing
       this property does not convert existing stored objects or data types.
   * - ``set_replica_mode``
     - ``mode``: ``NONE``, ``READ_ONLY`` or ``READ_WRITE``
     - Native replica property; reopened ``REPLICA_MODE``. This operation
       does not provision a replication topology or configure its transport.
   * - ``remove_linger``
     - No fields other than optional ``role``
     - Native ``no_linger`` acknowledgement for current runtime linger.
       Persistent ``RDB$DATABASE.RDB$LINGER`` is preserved. There is no native
       runtime getter: display effect-unobserved, not a fabricated zero or
       promise that peer locks have been released. The shared presentation
       descriptor retains its ``draft`` status for that observation limit;
       the embedded backend adapter is implemented and natively acknowledged.
   * - ``sweep_database``
     - Optional ``parallel_workers``, integer 1..128
     - Native sweep, including the native Firebird 5 parallel-worker request.
       A pending original SQL transaction remained pending and invisible to
       independent attachments; the service never commits it for the caller.
   * - ``validate_database``
     - Optional ``include_table``, ``exclude_table``, ``include_index``,
       ``exclude_index``; optional integer ``lock_timeout``, -1..86400
     - Native online validation, preserving bounded output and its truncation
       flag. A completed call is not a declaration that every database page
       was checked when filters were supplied. It performs no repair action.

For short header operations on a database without LINGER, active physical
backup or auxiliary files, the Linux adapter pins the reviewed device/inode
with an application-created private hardlink for the native action and
service release. A native maintenance attachment checks these conditions,
using the operation's SQL role and suppressing database triggers. Managed SQL
attachment admission for that inode is held until the private alias is released.
Long sweep/validation tasks, unavailable SQL attachments and filename-sensitive
database states use the canonical filename with a retained file descriptor and
identity recheck instead. Those results report
``file_identity_race_fenced=false``: a filesystem administrator can replace a
filename after its final check. This scope does not promise protection from
concurrent changes made outside ScratchRobin. Canonical handling preserves
native default delta filenames and prevents LINGER retaining a deleted alias.
Engine13
uses native file identity for database locks. Native qualification verifies
that a service through this alias preserves an original-path SQL transaction,
and that replacing the public filename immediately before dispatch changes
only the pinned original, leaving the replacement database unchanged. The
alias is removed on normal and interrupted paths. These are administration
aliases, not backup copies; no user-selectable alias path is accepted.
Windows/macOS mutations are refused until their file-pinning adapters are
qualified. Read-only statistics retains its separately documented platform
behavior. No other platform or Firebird version was qualified by this batch.

Review retains exact typed options, local target identity and application-local
execution scope. Submit only the returned plan ID/digest and confirmation to
Apply. Common retained plans are consumed once, including failed or uncertain
submissions. Native dispatch does not reconnect/replay, commit or roll back an
unrelated editor transaction. The adapter reports ``native_provider=Engine13``,
``execution_host=application-local``, ``network_authentication=false``,
``reviewed_file_identity``, ``file_identity_race_fenced`` and separate
``service_release`` flags. These Services calls have no native CLI process exit
code; ``native_utility_exit_code_observed`` remains false. Native output,
acknowledgement, post-state observation and cleanup are distinct evidence.
A missing response after native dispatch remains unknown, even when a later
independent property read observes the requested value. Retire the review;
never automatically retry it. Refresh the property inspector after a confirmed
setter response, and show the backend operation record on uncertain responses.

``tools/cdeadmin_firebird_local_administration_qualification.py`` qualifies the
ten adapters sequentially on owned Engine13-only Firebird 5.0.4 fixtures, using
an isolated writable runtime capture, immutable input-runtime fingerprint,
Unicode database filenames and the shared review/apply facade. The original
network SQL/compiler proof is not transferred into a claim of embedded native
service qualification. The separate embedded contract gate refreshes attachment,
SQL-equivalence and monitoring evidence against the current source bindings.
Human form acceptance and Windows/macOS qualification remain external;
ScratchBird history qualification remains owner-deferred and is not run.

Embedded availability: shutdown and recovery
------------------------------------------

The embedded database catalog surfaces ``shutdown_database`` and
``bring_online`` through the shared Firebird descriptors. They use the local
Engine13 Services attachment, never a remote server or network credential.
Shutdown accepts ``mode`` (MULTI, SINGLE, FULL), ``method`` (FORCED,
DENY_ATTACHMENTS, DENY_TRANSACTIONS), integer ``shutdown_timeout`` (0..32767),
optional ``role`` and the descriptor's textual ``confirmation`` attention field.
Bring-online accepts ``mode`` (NORMAL, MULTI, SINGLE) and optional ``role``.
The shared Apply request still requires confirmation of the retained review.

Both operations retain ``workspace_scope=server_service`` so the generic
workspace builds a target from an authorized registered database without SQL.
For embedded registrations this scope describes workspace discovery, not a
network transport. The UI requests the workspace with ``database_target_id``
and ``focused_operation_id=bring_online`` (or ``shutdown_database``); the
returned target has ``extensions.cdeadmin.service_scope_only=true``. Pass that
target to the existing ``visual_admin_validate`` and ``visual_admin_plan``
actions, then submit the returned plan ID/digest to ``visual_admin_apply``.
This path remains reachable after FULL shutdown rejects ordinary SQL. Server
authorization and stored route configuration remain authoritative.

Show the native availability warning, including forced attachment termination,
pending-work loss and the need to inspect state after any native failure.
SINGLE/FULL shutdown during physical backup is refused by the engine; the
application never silently ends backup or retries shutdown. Successful
service acknowledgement, independent observed shutdown mode and released
service handles are separate evidence. Failed dispatched calls remain unknown
and consume their review. Responses use ``Cache-Control: no-store``.

The local availability qualifier covers all nine shutdown mode/method pairs,
FULL SQL refusal and read-only header observation, online transitions, pending
transactions, native physical-backup refusal, valid MULTI shutdown during backup
and persistent LINGER filename behavior on owned Linux Engine13 5.0.4 fixtures.
Other versions, human form acceptance and native Windows/macOS qualification
are not established by that evidence.

Firebird native target review and stale-plan refusal (FB-AUD-01)
--------------------------------------------------------------

The generic Firebird client now retains an internal native target binding for
mutations of existing database/catalog objects. It combines the native database
GUID and file ID with each selected catalog record's DB_KEY and native record
transaction number; child columns and packaged routines also bind their parent.
A DB_KEY alone is not treated as a permanent identity. Numbered shadows bind
all of their native RDB$FILES records. The implementation selects fixed native
catalogs and binds object names as parameters; it never derives SQL catalogs or
identifiers from client-supplied guard fields.

Existing ``visual_admin_plan`` and ``visual_admin_apply`` hooks are retained.
The preview adds ``native_target_revalidation_required=true``. The complete
binding remains in the server-owned one-use plan, not an editable form field
or an Apply argument. Apply rechecks the binding on the executing connection.
An absent/replaced/changed target returns the existing HTTP 409
``PROVIDER_OPERATION_REJECTED`` receipt, with stage ``provider_rejected``,
``unknown_outcome=false`` and an explicit refresh/review message. Refresh the
native catalog and request a new review; do not retry the consumed plan or
silently select another object with the same name. A native response failure
after dispatch retains the existing conservative unknown-outcome/no-retry
receipt and numeric native diagnostics.

Owned metadata operations use an independent SNAPSHOT transaction with native
autocommit disabled. Borrowed sessions must already provide a compatible native
SNAPSHOT transaction without endpoint autocommit; the backend never commits,
rolls back, reconnects or changes the isolation of a caller transaction merely
to satisfy a metadata precondition. An incompatible borrowed transaction is
refused before mutation. Offer an explicitly reviewed independent operation
rather than silently moving a user's work to a different connection. Successful
borrowed DDL still uses the native task savepoint and remains caller-owned.
The database-drop driver API also checks the reviewed database identity on the
actual attachment it will drop, and retains failed release ownership when
cleanup cannot be confirmed.

``tools/cdeadmin_firebird_metadata_guard_qualification.py`` uses an isolated
Firebird 5.0.4 runtime, disposable database files and its own loopback network
listener. It exercises embedded and network native review/apply, same-name table
replacement before Apply, replacement after the preflight read, unchanged-target
DROP, all 21 catalog identity selectors, packaged routine parents, pending caller
DML with transactional DDL/rollback, raced and fresh table grants, and replaced
and fresh native database drops. Declared external-function/filter fixtures
qualify catalog record identity only; their library callbacks are not loaded or
claimed as functional native plugins.

This correction does not close the full FB-AUD-01 investigation by itself.
The native table DROP and recorded table-grant races are covered; the remaining
mutation variants still require their native race matrix. A SNAPSHOT catalog
read is not a universal lock on unrelated catalog writes. User administration
and global authentication mappings act through external/security-database
interfaces, so this catalog binding is not represented as their native identity
protocol. DDN schema application retains its separate review/precondition path.
Full task completion must retain these limits rather than extrapolate from the
successful table/drop or selector checks. Human form acceptance and other
platform qualification remain external.

Embedded copied-database fixup
-----------------------------

``database.fixup_database`` is surfaced for the embedded profile through the
shared Firebird operation descriptor. It accepts ``fixup_flags`` (empty or
``["SEQUENCE"]``), optional ``role`` and textual ``confirmation``. Select the
registered offline copied database through the attachment-free workspace using
``focused_operation_id=fixup_database`` and its ``database_target_id``. The
normal validate/plan/apply actions bind the approved filesystem route and inode.
No SQL attachment is opened to the copy before native NFIX. The Linux raw-file
adapter holds a private inode alias and blocks new managed SQL attachments for
that inode until native completion and service release.

This operation requires an offline filesystem copy made during native backup
mode. It does not copy a running database, shut down another server or secure
exclusive access against external processes. The descriptor's offline warning
must remain visible. Native NFIX resets the GUID/replication identity by default;
SEQUENCE requests preservation. ``restore_policy_requested`` describes the
request, not an independently observed replication counter. The owned Linux
5.0.4 qualifier directly observes default GUID reset and SEQUENCE GUID
preservation, data retention, one-use reviews and native refusal on a normal
primary. Nonzero replication-counter qualification remains in the replication
acceptance work. A native failure is unknown, consumes the review and is never
retried automatically. A successful response does not qualify the copied
application's recovery beyond the checks actually performed.

Persistent private Firebird test-data recipes (FB-AUD-08)
------------------------------------------------------

The test-data tool descriptor publishes ``recipe_read_action=firebird_recipe_read``
and ``recipe_save_action=firebird_recipe_save``. These workspace actions accept
an explicit registered ``database_target_id`` for Firebird network or embedded.
Read accepts optional ``recipe_id`` (default ``default``, 1..64 ASCII letters,
digits, dots, underscores or hyphens, starting with a letter/digit) and optional
positive integer ``version``. A missing current recipe returns version zero and
``recipe=null``. Read returns the server-owned ``scope``; include it unchanged
inside a saved ``scratchrobin.firebird.test-data@1`` recipe. Existing file recipes
can add this scope before requesting persistence; do not relabel another format.

Save accepts ``recipe_id``, integer ``expected_version`` (zero for first save)
and ``recipe``. The recipe has exactly ``format``, ``scope``, uint32 ``seed`` and
``tables``. It retains the existing Firebird generator sources: default,
constant, sequential, random-integer, choice, file, existing and generated.
Bounds are 1 MiB UTF8 JSON, 1..32 tables, 1..1000 rows per table, 5000 total rows,
1..1000 choice/file values, and 32 nested value levels. Keep fractional and large
numeric values as exact strings or native typed envelopes; only NULL percentages
admit fractional JSON numbers. Save checks native user-table/column references
and insertability without staging rows. Generated references must resolve to
explicit generated columns with acyclic dependencies. Existing sample values
and foreign-key validity must be checked again by the native preview/staging
workflow; a saved draft is not a certificate of current type/FK validity.

Revisions use the existing transactional project-asset repository in the local
configuration database. Storage keys include owner, engine, endpoint, database
target and recipe name. Revisions are immutable and historical reads do not
advance the current revision. A stale expected version returns HTTP409 with
``info=FIREBIRD_RECIPE_CONFLICT``; refresh before saving again. Other recipe
refusals return ``FIREBIRD_RECIPE_REFUSED`` and never echo stored sample values.
All responses are ``Cache-Control: no-store``. Do not replay an uncertain save;
read the current revision to reconcile it.

Results include ``version``, ``current_version``, ``scope``, ``recipe``,
``executed=false``, ``requires_native_preview``, ``contains_user_values`` and
``source_control_eligible=false``. Recipes are private; grants to a different
project do not share this store. Secret-bearing content is refused, and file,
choice or constant values remain potentially sensitive personal test data.
Show that review requirement when loading. Save/load never executes generated
SQL, opens a test-data transaction, commits an editor transaction or changes the
existing file import/export workflow. Native row staging and explicit
commit/rollback continue through the existing dedicated Firebird data session.

Managed Firebird database user trace (FB-AUD-02, partial)
------------------------------------------------------

The database tool descriptor declares ``database.firebird.trace`` with
``tab=firebird-trace``, ``workspace_action=firebird_trace`` and
``describe_action=describe``. The UI group owns that tool's presentation.
Backend requests use the authenticated workspace endpoint with an explicit
registered ``database_target_id`` in both the outer workspace payload and
its ``request``. Every call rechecks ``administer`` on the resource and
``maintenance_admin`` on the endpoint, plus the provider's transport authority.
The engine remains authoritative for native trace privileges.

The request's ``action`` selects:

* ``describe``: returns ``scratchrobin.firebird.trace-api@1`` with typed native
  option fields, bounds, defaults and zero-value meanings. Booleans cover the
  database trace events, plans, counters, BLR and DYN; UInt32 fields cover the
  connection filter, duration and native text/argument limits. SQL and GDS-code
  filters are bounded strings. No file-output or service-audit settings are
  admitted by this database-scoped workflow.
* ``review`` with ``operation=start``: accepts optional ``name`` (128 UTF8
  bytes) and ``options``. The backend observes the native filename, engine
  version, database GUID and native file ID through an independent read-only
  SNAPSHOT attachment; it does not borrow the editor transaction. Embedded
  Linux also compares the approved filesystem inode against the attachment
  identity to reject stale native filename-cache matches. Only Firebird 5.0.4
  is admitted by this new configuration profile. The retained payload includes
  read-only ``native_configuration`` for the operation dialog's SQL/native-plan
  tab. Apply refuses a review if the current renderer would produce different
  native configuration; this is a Services plan, not an executable SQL script.
* ``review`` with ``operation=suspend|resume|stop|release|forget``: accepts an
  opaque managed ``trace_id``. It never accepts an arbitrary native session ID.
  These controls do not need a new SQL attachment, so cleanup remains available
  when the database stops admitting SQL connections.
* ``apply``: accepts only the returned ``review_id``, ``review_digest`` and
  ``confirmed=true``. Reviews expire after 300 seconds. A cross-process file
  lock protects the durable claim before native dispatch. Reusing a review
  returns its existing receipt and never executes it again. A native target
  identity change before start is a known rejection without trace dispatch.
* ``get``: reads an owned review/action receipt by ``review_id``.
* ``list``: lists this owner's managed traces for this endpoint/target. For
  live handles it separately observes the native trace session's presence and
  flags. It does not list or control external native sessions.
* ``poll``: accepts ``trace_id``, optional nonnegative ``after`` sequence
  (default zero) and integer ``limit`` (1..200, default 200). Returned lines
  have ``sequence``, ``text`` and ``truncated``; ``next_sequence`` advances the
  cursor, while ``delivery_gap`` and ``dropped_lines`` expose overwritten data.

The renderer disables database and service defaults, then enables an escaped
SIMILAR TO pattern for the observed server-native filename and the verified
registration attachment selector. Firebird passes an attachment alias to its
trace plugin even when MON$DATABASE reports a physical filename. The selected
registration alias is therefore included only after its connection supplied the
reviewed native GUID/file identity. Unlisted aliases of the same file are not
guessed or captured automatically; alias case variants are not automatically
expanded. This is native filename/alias scope, not a permanent inode lock: an
external administrator can later reassign a filename or alias. Configuration macros, double
quotes and control characters are refused rather than rendered ambiguously.
Braces are escaped independently for the native configuration grammar.

Defaults enable connection and initialization events, with SQL/BLR/DYN lengths
256, argument length 64, argument count 8 and duration threshold zero. Native
length/count zero means unlimited, not disabled; the backend preserves that
meaning. All integer options accept the native UInt32 range. Statement,
routine, trigger, plan, error, warning, context, BLR/DYN or filter capture
requires ``capture_sensitive=true`` in the reviewed options. Captured SQL,
arguments and diagnostics can contain sensitive values; no masking guarantee
is made. Output is private to the authorized owner/target and never published,
exported to Git or stored as SQL/monitoring history by this workflow.

A private client owns separate reader and control Services connections; driver
authentication buffers are discarded after attachment and no reconnect occurs.
The live worker drains timed native output independently of UI polls. Each
stream retains at most 2000 lines and 1 MiB, clips a single line to 32768 UTF8
bytes, and stops after 120 seconds without a poll or 3600 seconds total. There
are at most 16 active traces, four per owner and 32 retained live/finished
records per process. ``forget`` explicitly discards a finished stream only
when its owned handles were released. Failed release stays owned and admits
an explicitly reviewed ``release`` retry; it never replays start or a native
control to repair an audit write.

Native acknowledgement, observed output, plugin diagnostics, native stop/end
and handle release are distinct fields. ``capture_success_inferred`` stays
false: native start can return an ID before a plugin reports configuration
errors. The worker detects native plugin diagnostic headers and requests stop.
``native_started``, ``native_stop_acknowledged``, ``native_end_observed`` and
``cleanup_confirmed`` report only their respective observations. Unknown
native outcomes remain unknown. The action receipt's ``submitted`` state is
not a claim of successful native capture; inspect its ``outcome`` and poll.

Only review/settings and lifecycle metadata are written to the private
``firebird-trace-operations.json`` beside the operation store. Captured text
never enters that journal. A maximum of 1000 action receipts is retained;
only expired, never-dispatched reviews are pruned automatically. A missing
live handle can return an authorized durable session receipt with
``live_handle_available=false`` and ``output_available=false``. An unconfirmed
session after process loss is ``unknown_after_process_loss``, never restarted
or stopped automatically by recycling its native ID. All workspace responses
use ``Cache-Control: no-store``. Credentials, permission or endpoint-generation
changes invalidate the live binding; a caller that cannot renew the lease
cannot keep collection running through polls.

The owning audit item remains open for service/server tracing, system-audit
configuration, externally created trace-session administration, restricted
native-account/network failure qualification and the full native option/event
matrix. Human UI and native Windows/macOS acceptance remain external.
ScratchBird history qualification remains deferred and is not run here.

Embedded shadow activation recovery
-----------------------------------

The embedded provider exposes ``activate_shadow`` through the shared Firebird
operation descriptor. Its required fields are ``shadow_filename``, exact-path
``confirmation`` and ``original_isolated=true``; ``role`` is optional. The
original registered database and its parent directory may be unavailable.
Open the attachment-free workspace with ``focused_operation_id=activate_shadow``
and the existing ``database_target_id``, then use the normal visual administration
validate, plan and one-use confirmed apply actions. No SQL connection to the
original or recovery file is required before native activation.

The recovery filename must be canonical, existing and inside the approved
filesystem root. Symlinks, a hardlink to an existing primary, mismatched compiled
targets and replacement of the reviewed inode are refused. Apply retains a file
handle and rechecks its identity, but passes the canonical filename to Firebird:
``file_identity_race_fenced=false`` explicitly records that an external process
can still race that pathname. The isolation checkbox is an operator assertion,
not proof of exclusive access. The existing destructive recovery warning remains
part of review. Do not run the recovered database alongside its original.

The native service reads the header without SQL and requires a complete primary
header identifying an active shadow before activation. Results preserve native
header verification, service completion and handle-release observations. A lost
native outcome is not safe to replay. Recovery does not retarget the saved
registration automatically; the UI must present the actual recovery filename
and let the user explicitly update the registration separately.

Owned Linux Firebird 5.0.4 qualification covers LINGER 0 and 1, missing originals,
retained data, canonical MON$DATABASE_NAME and default backup delta handling,
ordinary-primary refusal and replacement before apply. It does not establish
external-process exclusivity, older-version support, native Windows/macOS
qualification or human form acceptance.

Embedded repair and ODS upgrade
------------------------------

``repair_database`` and ``upgrade_database`` use the local Engine13 Services
adapter and the shared Firebird operation forms. Open their attachment-free
workspace using ``focused_operation_id`` and the selected registered
``database_target_id``. The workspace supplies the database target resource
for the ordinary visual administration validate, review and confirmed one-use
apply actions. A failed SQL connection is not required to open these forms.

Repair takes ``repair_action``, optional ``repair_modifiers``, ICU-only
``parallel_workers``, ``no_linger`` and an optional task ``role``. The provider
preserves all shared native validation: mend implies full validation; modifiers
do not remove preset flags; ICU workers are requested, not observed; and zero
omits the native worker DPB setting. The dedicated ODS upgrade takes only the
optional role. The embedded filesystem/runtime authority remains required, and
neither workflow acquires network credentials.

Before dispatch, the provider releases its own idle catalog connections for
the selected file. It refuses to close a catalog handle with an active or
unconfirmed transaction; a failed detach remains owned for explicit cleanup.
Other database caches, borrowed metadata handles and user sessions are not
released. Native exclusive-access errors therefore remain possible and must
be presented as returned, rather than forcing other attachments closed.

Both tasks retain and recheck the reviewed file identity and pass its canonical
filename to Firebird without an SQL preflight. Results explicitly report
``file_identity_race_fenced=false``. This does not establish exclusive access
against external processes or disconnect existing attachments. Retain the shared
repair warnings: mend can discard damaged records, native success does not
establish recovery, and errors can follow partial changes. Preserve a recoverable
backup and independently inspect the native state before deciding what to do.

Owned Linux Firebird 5.0.4 qualification observes all seven repair actions,
including actual unavailable-manual-shadow cleanup and real ODS 13.0 to 13.1
upgrades through both upgrade entry points. The legacy fixture was created by
an isolated official Firebird 4.0.5 runtime; its row, primary key and text survive
upgrade. Validation/mend presets on healthy fixtures retain data; ICU worker
dispatch does not prove a stale ICU index needed rebuilding. A truncated copy
produces a native failure with unknown outcome and blocked replay. In the
missing-shadow case Firebird removes the catalog entry and permits SQL again,
yet its Services status retains the original file-open error. The backend keeps
that error and unknown outcome; subsequent inspection proves recovery separately.
The qualification also covers a replaced inode before dispatch and loss of an
actual completed native response. Arbitrary corruption recovery, older engine
versions, other native platforms and human form acceptance are not certified.

Embedded logical backup
-----------------------

``backup_logical`` is an application-local Engine13 Services operation. Its
shared typed Firebird form retains single-file and ordered split-volume
selection, byte capacities, native backup flags, include/skip patterns,
parallel workers, statistics, verbose settings, key-holder/crypt plugin
settings and task role. Embedded form labels identify the ScratchRobin host.
The embedded manifest declares ``backup_admin``; review and apply still require
the caller's grant, in addition to filesystem and embedded-runtime authority.

Open ``focused_operation_id=backup_logical`` with the selected registered
``database_target_id`` to obtain the attachment-free database target. Submit
the ordinary visual validate, plan and confirmed one-use apply requests. The
single-file ``split_backup=false`` default is honoured by backend conditional
field validation even when omitted by the caller. Explicit controlling values
override defaults. The preview includes ``local_backup_outputs`` in native
volume order, with exact filenames, capacities and reviewed parent identities.
The same list is retained in ``impact.backup_output_files`` on the operation
receipt, including after a native failure, so operation lookup can recover the
reviewed paths without inferring them from file existence.

All destinations must be canonical absolute filenames inside the approved
filesystem root, with existing parent directories. Existing outputs, aliases
and source-database paths are refused. Apply rechecks the reviewed source and
output directory identities, opens each approved parent by descriptor, and
reserves output files with exclusive creation and mode 0600. No existing file
is overwritten. Linux Engine13 writes through process-local descriptor aliases
to those reserved inodes, so a same-name replacement cannot redirect writes.
The source database keeps its canonical native filename and its existing
``file_identity_race_fenced=false`` result; output-inode pinning is a separate
observation and does not establish source-file exclusivity.
Online backup does not hold managed SQL admission for its duration; new query
connections remain possible, and existing caller transactions are preserved.

``driver_observation.local_backup_outputs`` reports the requested filename,
reserved device/inode identity, observed bytes, native descriptor alias and
``requested_path_still_names_output`` for each volume. Descriptor aliases are
diagnostics only: they expire when apply releases its handles and must not be
used as restore paths or download links. The aggregate
``outputs_at_reviewed_paths`` is false if a requested name or its parent was
replaced. Native ``server_completed`` and service-handle release remain separate
observations. ``restore_verified`` stays false: production backup does not
restore the file merely to infer that it is usable. The UI should retain the
reviewed destination list and inspect these fields before presenting completion.

Files are visible during the operation. An exception, interruption, failed
reservation after an earlier volume, or lost native response can leave partial
files at the reviewed destinations. They are retained for explicit inspection;
the backend does not automatically delete or replay them. File existence or
nonzero size does not mean a valid backup. A failure before any output reservation
can be a known pre-dispatch rejection; once files were created, it must not be
reported as ``nothing_changed``. A native failure keeps the normal unknown-outcome
receipt and its one-use review is retired. Installed native encryption plugins
remain real dependencies; absent plugins produce native errors.

Owned Linux Firebird 5.0.4 qualification independently restores full,
metadata-only, ZIP, Unicode-filtered and split-volume outputs, checking schema,
data and binary blobs. It verifies permission refusal, existing-output refusal,
replacement during dispatch, retained partial output on native plugin failure,
a lost completed response and preservation of a caller's pending transaction.
Those restore calls are qualification controls; product restore is qualified
separately below. Other native platforms, older versions, installed
encryption-plugin interoperability and human form acceptance remain separate.

FB-Q07: native EDS process-pool qualification
------------------------------------------

Current-source Linux Firebird 5.0.4 qualification exercises the original-session
EDS pool API in network and embedded modes, including actual pooled external
connections. A second attachment observes the same native process ID, pool size
and lifetime. Native minimum/maximum size and SECOND, MINUTE and HOUR lifetime
boundaries are read back, rather than inferred from generated SQL. A restricted
network principal is refused until its exact native system privilege is granted.

The checks retain a pending caller transaction and savepoint across pool
administration, verify settings outside rollback, observe idle expiry, and verify
that CLEAR ALL removes active pool tracking without cancelling its external
transaction. CLEAR database remains refused because native 5.0.4 does not
implement it. Native settings are process-local; archived receipts do not imply
that they survive an engine restart.

Authenticated API checks cover original-session control, URL/target scope
conflicts, foreign receipt scopes, explicit retention confirmation and archive
reads after session closure without resolving a SQL workspace. A separate fresh
Python process reads both receipt scopes after the owned native server has
stopped; the receipts explicitly remain archived observations, without a live
native connection, replay authority or inferred transaction finality. Unit checks
also cover expired reviews, adapter/process/role/session changes, durable claims,
lost responses, failed persistence, cancellation and cleanup failures. Browser
appearance and native Windows/macOS acceptance remain with their owning teams.

Embedded logical restore
------------------------

``restore_logical`` uses the local Engine13 Services adapter and shared typed
Firebird restore form. The embedded manifest grants the workflow capability
``restore_admin``; the caller must hold that permission as well as embedded
runtime, filesystem and administration authority. The attachment-free workspace
uses ``focused_operation_id=restore_logical``. Its registered original database
may be unavailable: restore does not open it or its destination as a SQL
preflight. Service-manager attachment alone does not create a database.

The form retains ordered backup volumes, single/multiple native database files
and page allocations, create/replacement selection, restore flags, page size,
buffers, access and replica modes, include/skip filters, workers, statistics,
verbose settings, installed crypt/key-holder options and task role. All selected
paths are canonical absolute application-host filenames inside the endpoint's
approved root. Input volumes must be distinct, nonempty regular-file inodes.
Secondary destination files must be new. Replacing a primary database requires
``replace_existing=true`` and ``confirmation`` equal to the exact
``restore_database`` filename, in addition to confirmed one-use apply. Native
active attachments are not forced closed.

Preview and ``impact.restore_files`` retain input SHA-256 digests and file
identities, destination identities or expected absence, parent identities and
ordered page allocations. Apply rechecks those values and hashes each pinned
input before dispatch. Backup inputs are read through held Linux descriptor
aliases; filenames cannot redirect those handles. Native database filenames stay
canonical so stored multi-file metadata remains correct. Output filenames are
rechecked but explicitly report no OS rename fence or external exclusive-access
guarantee. No operation automatically retries or deletes partial database files.

``driver_observation.local_restore_files`` reports input-inode pinning, reviewed
digests, whether names still identify their inputs, whether input metadata stayed
unchanged, and the observed destination file identities. A rename can change
ctime even when the pinned input bytes remain intact; that uncertainty is kept.
``data_readback_verified`` remains false in production. The native service result
and handle-release observations are separate from later data inspection.
Native errors or lost responses remain unknown, with reviewed paths available
through operation lookup. Existing idle catalog handles for the selected target
are released without closing user sessions or rolling back their transactions.

``provider_result.restored_database_target`` identifies the primary file and
reports ``registration_changed=false``. The existing registration stays selected.
After inspecting a known completed restore, the UI can use the existing
``database_target_attach`` action with ``database`` and ``display_name`` to
verify/register that file, subject to the normal active-handle rules. Registration
follow-up is separate from native restore and must never cause it to be replayed.

Native restore replica mode is encoded as a one-byte SPB field. Firebird 5.0.4's
clumplet schema rejects the installed driver's four-byte encoding before restore;
the provider uses its corrected action-first native writer whenever a replica
mode is selected. This correction applies to network and embedded execution.
The existing UTF-8 plugin-name path uses the same writer and preserves every
ordered file/page pairing.

Owned Engine13 qualification verifies full, metadata-only, Unicode-filtered,
read-only/replica, split-input, multiple-database-file and explicit replacement
restores with independent native row, BLOB and property readback. Stale targets,
pinned-input filename replacement, corrupt backups, lost completed responses and
pending caller transactions are also exercised. Authenticated API checks verify
the readonly replica properties and retained row, no-store responses, one-use
apply, known stale-target refusal and durable unknown-outcome path lookup.
Other native versions/platforms, installed crypt-provider interoperability and
human UI acceptance remain separately recorded.

Embedded physical backup
------------------------

``backup_physical`` uses the application-local Engine13 Services adapter and
shared typed Firebird ``nbackup`` form. Open its attachment-free workspace via
``focused_operation_id=backup_physical`` and the selected registered
``database_target_id``; review and apply require ``backup_admin`` alongside
embedded-runtime, filesystem and administration authority, with no network
credential acquisition.

The form admits canonical ``backup_file``, ``backup_level`` (0..2147483647 or
omitted when ``database_guid`` is supplied), ``database_guid``,
``direct_io_mode`` (``NATIVE``, ``ON`` or ``OFF``), ``backup_flags``
(``NO_TRIGGERS``), ``clean_history`` with ``history_keep_unit`` (``ROWS`` or
``DAYS``) and ``history_keep_value``, and optional SQL ``role``. Unlike
``gbak``, native Firebird 5.0.4 ``nbackup`` opens its output file with
``O_CREAT | O_EXCL`` (rejecting pre-opened ``/proc/self/fd`` aliases natively
with ``337117230``) and records the exact backup filename in
``RDB$BACKUP_HISTORY``. ``local_physical_backup.py`` therefore validates that
the destination is an unused canonical filename inside the approved filesystem
root, pins and rechecks the approved parent directory via
``O_DIRECTORY | O_NOFOLLOW``, verifies destination absence immediately before
dispatch, relies on native ``O_EXCL`` against raced file creation, and preserves
the canonical path for ``RDB$BACKUP_HISTORY``.

Preview and ``impact.backup_output_files`` retain the reviewed output path and
parent directory identity, including after native failures or lost responses.
``driver_observation.local_physical_backup_outputs`` reports the observed
regular-file identity, byte size, ``requested_path_names_regular_file``,
``parent_identity_unchanged``, ``output_inode_pinned=false``,
``native_exclusive_create=true``, ``rename_race_fenced=false`` and
``restore_verified=false``. Online physical backup does not hold managed SQL
admission during execution; concurrent managed SQL reads remain admitted and
caller pending transactions remain untouched.

Embedded physical restore
-------------------------

``restore_physical`` uses the application-local Engine13 Services adapter and
shared typed Firebird ``nrestore`` form. Open its attachment-free workspace via
``focused_operation_id=restore_physical``; its registered original database may
be absent or unavailable, and neither the original nor the destination is opened
as a SQL preflight. Review and apply require ``restore_admin`` alongside
embedded-runtime, filesystem and administration authority.

The form admits ordered ``backup_files``, canonical ``restore_database``,
``restore_flags`` (``IN_PLACE``, ``SEQUENCE``), optional SQL ``role`` and
conditional ``confirmation``. Firebird 5.0.4 ``nrestore`` does not implement
direct I/O overrides, so ``direct_io_mode`` remains excluded from the
``restore_physical`` form contract. Every input in ``backup_files`` must be a
distinct, nonempty regular-file inode inside the approved filesystem root;
preview and ``impact.restore_files`` record SHA-256 digests, file metadata and
destination parent identities. Apply rechecks those identities and hashes and
passes Linux ``/proc/self/fd`` handles to Engine13 ``nrestore``, preventing
filename replacement during dispatch from redirecting backup reads.

In ``NEW_DATABASE`` mode (default), ``restore_database`` must not exist; native
``nrestore`` resets the database GUID and replication sequence by default unless
``SEQUENCE`` is selected. In ``IN_PLACE`` mode, ``restore_database`` must be an
existing approved offline database file (distinct from all backup inputs) with
``confirmation`` equal to the exact canonical ``restore_database`` filename;
ScratchRobin releases its own idle catalog handles for that target before
planning and apply without forcing active user sessions closed. Native
``IN_PLACE`` applies ordered increments, leaves ``MON$READ_ONLY=1``, resets the
database GUID unless ``SEQUENCE`` is also selected, and rejects duplicate
increment replay natively with ``337117247``. ``provider_result.restored_database_target``
reports ``registration_changed=false`` without retargeting existing registrations.

Owned Linux Engine13 5.0.4 qualification (``tools/cdeadmin_firebird_local_physical_qualification.py``)
exercises 13 native scenarios and 3 authenticated HTTP workflow groups:
concurrent SQL during online Level 0 backup, ``backup_admin`` and
``restore_admin`` permission denials, Level 1 and ``database_guid`` incremental
backups, ``clean_history`` row retention followed by native missing-base refusal
(``337117235``), read-only source backup refusal (``335544765``), stale output
and stale destination pre-dispatch refusals, lost completed backup response,
``NEW_DATABASE`` default GUID reset and ``SEQUENCE`` GUID preservation with
independent row and binary BLOB readback, ``IN_PLACE`` standby replay and
duplicate increment refusal (``337117247``), pinned-input filename replacement
during dispatch, corrupt backup unknown-outcome durable path lookup
(``337117250``), caller SNAPSHOT transaction preservation, ``no-store`` headers
and one-use plan retirement. Native Windows/macOS and human UI acceptance remain
separately tracked.

FB-AUD-09: embedded/local external ISQL host contract
-----------------------------------------------------

``firebird_isql_context`` and ``runtime/src/js/firebirdIsql.js`` now define an
explicit same-host local-file contract for ``firebird-embedded`` registrations
alongside the existing network TCP contract, and ``database.firebird.isql`` in
``ui_descriptors/firebird/tools.json`` is enabled for both network and embedded
routes.

For ``firebird-native``, the response retains ``dsn``, ``user``, ``role``,
``charset`` and ``sql_dialect`` (1 or 3), requiring a launch-only password in
the desktop launcher. For ``firebird-embedded`` on Linux, the server validates
the registered route through ``admit_service_route`` and ``file_identity``
(enforcing canonical containment inside ``filesystem_root``, regular-file
existence and absence of network credential references), releases its own idle
catalog handles for that target so SuperServer-mode Engine13 file locks are not
held by idle metadata caches, and returns ``attachment_mode="embedded"``,
``database``, ``filesystem_root``, ``native_provider="Engine13"``,
``password_required=false`` and ``same_host_authority`` containing ``platform``,
``boot_id`` (``/proc/sys/kernel/random/boot_id``), ``hostname``,
``database_identity`` (``device``, ``inode``) and ``firebird_lock_directory``.
Client-supplied file paths are never accepted by ``firebird_isql_context``.

Before spawning Konsole or xterm, the desktop launcher verifies that its local
Linux ``boot_id`` matches ``same_host_authority.boot_id`` (refusing remote
desktop clients connected to a different ScratchRobin server host), rechecks
``filesystem_root`` and ``database`` ``realpath`` and ``(device, inode)``
identity, verifies that the selected Firebird 5 ``isql`` runtime includes
``plugins/libEngine13.so``, refuses any ``password`` on embedded launches,
strips ``ISC_*`` variables, stages an isolated ``Providers = Engine13`` runtime
configuration sharing ``firebird_lock_directory`` when present, and reports
``execution_host="same-host-local-desktop"``, ``native_connection_confirmed=false``
and ``transaction_outcome="owned-by-isql"`` (terminal spawn alone does not claim
native attachment success, particularly if another exclusive SuperServer-mode
process currently holds the file).

UI handoff for ``web/pgadmin/static/js/Dialogs/FirebirdIsql.jsx``: when
``connection.attachment_mode === 'embedded'``, display ``connection.database``
(read-only, labeled as the approved local database filename on this host) in
place of ``connection.dsn``, omit or disable the password input because
``connection.password_required === false``, and allow launching without a
password. Owned Linux 5.0.4 qualification
(``tools/cdeadmin_firebird_embedded_isql_qualification.py``) verifies
authenticated HTTP context issuance, actual Engine13 5.0.4 ``isql`` attachment
(``MON$REMOTE_PROTOCOL`` null) and committed row readback, stripped ``ISC_PASSWORD``,
cross-host ``boot_id`` refusal and replaced-inode refusal. Windows/macOS host
launchers and UI presentation acceptance remain with their owning teams.

FB-AUD-10: native fb_lock_print diagnostic utility
--------------------------------------------------

``web/pgadmin/cdeadmin/providers/firebird/lock_print.py``,
``web/pgadmin/cdeadmin/workspace/firebird_lock_print_actions.py`` and the
authenticated workspace action ``firebird_lock_print`` (surfaced in
``ui_descriptors/firebird/tools.json`` as ``database.firebird.lock_print``)
provide a reviewed, one-use, structured diagnostic adapter around Firebird
5.0.4 ``fb_lock_print``.

``describe`` returns ``scratchrobin.firebird.lock-print-api@1`` with
``published_as_default_metric=false`` and ``supported_platforms=["linux"]``.
Access requires endpoint ownership plus ``administer`` and
``maintenance_admin`` permissions; lock-table dumps are never published into
default ``MON$`` monitoring metrics or persisted as raw text in the operation
store. ``firebird-embedded`` routes validate canonical ``filesystem_root``
containment and file ``(device, inode)`` identity directly; ``firebird-native``
routes require an explicit operator grant in
``CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST``
(``scratchrobin.firebird.host-tools@1``) binding ``endpoint_id``,
``firebird_runtime_root``, ``firebird_lock_directory`` and allowed canonical
database paths on the application host, refusing remote TCP servers without a
local shared-memory grant.

``normalize_options`` validates snapshot flags (``owners``, ``locks``,
``requests``, ``history``, ``waiting_only``, ``pending_only``,
``consistent_mutex``, ``series``) and interactive counter sampling
(``interactive_seconds``, ``interactive_interval``, ``interactive_counters``
subset of ``aotw``), enforcing native CLI dependencies (``-r`` and ``-w``
require ``-o``; ``-s`` requires ``-l``; ``-n`` requires ``-o`` or ``-l``;
interactive sampling is mutually exclusive with snapshot flags) and bounded
``timeout_seconds`` (1..60). ``execute_lock_print`` revalidates ``boot_id``,
database ``(device, inode)`` and ``fb_lock_print`` binary SHA-256 before
spawning a process group without a shell or ``ISC_*`` credentials, kills the
process group with ``SIGKILL`` on timeout, and parses ``LOCK_HEADER BLOCK``,
``OWNER BLOCK`` (including ``waits_on_offsets`` and ``is_waiting``),
``LOCK BLOCK``, ``REQUEST BLOCK``, unmapped idle lock-table state
(``unmapped_no_active_attachments``) and interactive counter samples/averages.
Raw ``AST``/``argument`` pointer addresses are always redacted, and raw lock
``Key`` values are redacted unless ``include_raw_lock_keys=true``,
``sensitive_lock_data_confirmed=true`` and ``confirmation`` matches the exact
database filename.

Owned Linux Firebird 5.0.4 qualification
(``tools/cdeadmin_firebird_lock_print_qualification.py``) verifies unmapped
idle lock-table detection, real cross-process Classic Engine13 lock-waiter
contention (observing the blocked ``isql`` PID and redacted lock keys),
interactive counter sampling, unauthenticated refusal, remote-TCP refusal
versus same-host grant-manifest admission, stale-inode pre-dispatch refusal,
one-use review retirement, ``no-store`` headers and absence of raw lock output
on disk. Native Windows/macOS availability and UI presentation acceptance
remain with their owning teams.

FB-AUD-01: stale destructive and mutation target-identity guard
---------------------------------------------------------------

``web/pgadmin/cdeadmin/providers/firebird/metadata_guard.py`` now covers every
mutable Firebird resource kind in ``FirebirdProvider`` across both
``firebird-native`` and ``firebird-embedded``:

* All 21 ``RDB$`` catalog object kinds bind ``(database_guid, database_file_id,
  RDB$DB_KEY, RDB$RECORD_VERSION)`` plus parent relation/package record identity
  inside a verified ``SNAPSHOT`` transaction before DDL or ``drop_database``
  dispatch, including package header and body operations (``replace_body``,
  ``drop_body``).
* Inspected ``privilege`` rows from ``RDB$USER_PRIVILEGES`` bind their exact
  matching ``RDB$USER_PRIVILEGES`` ``(RDB$DB_KEY, RDB$RECORD_VERSION)`` set,
  and collection-level object ``grant``/``revoke`` plans bind the target
  ``RDB$`` object record.
* Security-database virtual projections (``user`` via
  ``SEC$USERS``/``SEC$USER_ATTRIBUTES`` and ``global-authentication-mapping``
  via ``SEC$GLOBAL_AUTH_MAPPING``) bind a SHA-256 digest of the non-secret
  projected state without storing plaintext PII or tag values in plan payloads,
  marking ``record_version_available=false`` explicitly because ``SEC$``
  virtual views do not expose ``RDB$RECORD_VERSION`` or password hashes.
* ``create_or_alter`` requests targeting a newly entered name distinct from an
  inspected row skip stale-target binding on the unrelated row.

Owned Linux Firebird 5.0.4 qualification
(``tools/cdeadmin_firebird_metadata_guard_qualification.py``) verifies
same-name table replacement (``RDB$RELATION_ID`` mismatch), post-preflight
concurrent DDL conflict conservatism (``unknown_outcome=true``, no replay),
all 21 ``RDB$`` catalog selectors and packaged routines, package body
replacement, inspected and collection-scoped privilege target replacement,
``SEC$USERS`` and ``SEC$GLOBAL_AUTH_MAPPING`` pre-dispatch refusal, database
replacement refusal, borrowed ``SNAPSHOT`` pending-DML preservation, and
authenticated HTTP ``409 PROVIDER_OPERATION_REJECTED`` pre-dispatch conflict
handling with retired-plan replay refusal.

FB-AUD-02: native trace service, external session and system-audit lifecycle
----------------------------------------------------------------------------

``web/pgadmin/cdeadmin/providers/firebird/trace_config.py``,
``trace_sessions.py``, ``workspace/firebird_trace_actions.py`` and
``workspace/service.py`` (``firebird_trace``, surfaced in
``ui_descriptors/firebird/tools.json`` as ``database.firebird.trace`` and
``endpoint.firebird.trace``) now support the complete Firebird 5.0.4 native
trace lifecycle:

* **Database-scoped user trace** (``start``) and **engine-instance service
  trace** (``start_services`` with ``supported_scopes`` covering ``database``,
  ``services`` and ``database_and_services``), requiring explicit
  ``service_scope_confirmed=true`` for service-wide observation and
  ``capture_sensitive=true`` before enabling SQL, plans, arguments, service
  queries, error/warning text or filters.
* **External native trace-session inventory and reviewed controls**:
  ``list_native`` queries ``Server.trace.sessions`` to report active native
  sessions visible to the current Firebird service account, distinguishing
  workspace-managed streams (``managed_by_workspace=true``) and system-audit
  sessions (``system_audit=true``). Reviewed one-use ``suspend_external``,
  ``resume_external`` and ``stop_external`` operations bind
  ``(native_session_id, name, user, started_at)`` to reject numeric session-ID
  reuse before dispatch and refuse stopping workspace-managed or system-audit
  sessions through external controls.
* **System-audit trace configuration and bounded tail inspection**:
  ``render_system_audit`` validates ``AuditTraceConfigFile`` database and
  service rules (enforcing canonical ``log_filename`` containment inside an
  admitted host directory, ``max_log_size`` bounds, and rejecting macros,
  quotes, control characters and sed backreferences), while ``read_audit_log``
  reads bounded, clipped tail lines without persisting captured SQL in the
  operation journal.

Owned Linux Firebird 5.0.4 qualification
(``tools/cdeadmin_firebird_trace_qualification.py`` and
``tools/cdeadmin_firebird_trace_network_qualification.py``) verifies
authenticated Engine13 HTTP database and service-scope trace streams, external
session ``list_native``/``suspend_external``/``resume_external``/``stop_external``
and stale-ID rejection, encrypted loopback TCP alias resolution, restricted
user cross-session isolation and foreign-stop refusal, live
``AuditTraceConfigFile`` database and service audit log capture and audit-stop
refusal, mid-trace credential revocation, listener transport loss conservative
outcomes without automatic retry, and caller SQL transaction preservation.
Native Windows/macOS and UI presentation acceptance remain with their owning
teams.
