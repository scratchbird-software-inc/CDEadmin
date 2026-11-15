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
