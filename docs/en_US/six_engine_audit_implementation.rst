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
