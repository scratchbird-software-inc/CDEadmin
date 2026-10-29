.. _ui_unification_status:

UI unification status
=====================

Tracker for :doc:`ui_unified_design`. Updated by whoever moves a form, operation
or panel; counts are produced by ``python3 tools/validate_ui_descriptors.py --counts``
(``make ui-descriptors-check``). This page records progress; it never certifies
acceptance on its own.

Owner-approved shared dashboard integration (2026-10-26): MySQL and Firebird
endpoint/database openers declare their existing DDN viewer in ``tools.json``.
The shared dashboard pane consumes this metadata without engine branches or
interactive SQL-session gating. Collector policy and layout editing remain
separate; object-family form acceptance is unchanged. See design Decision18.

Phase status
------------

.. list-table::
   :header-rows: 1
   :widths: 8 40 14 38

   * - Phase
     - Package
     - Status
     - Gate evidence
   * - 0
     - Freeze and inventory
     - in progress
     - This page; baseline counts below; panel disposition in design section 6.11
   * - 1
     - Foundations: schemas, family skeletons, validator, lint rules
     - done
     - ``ui_descriptors/schema``, ``ui_descriptors/families`` (10), validator in ``make check``; ESLint import boundary covers ``cdeadmin_ui/objects`` and the tree glue; family render harness in ``regression/javascript/families``
   * - 2
     - Shell: tree, object editor, operation dialog, menu model
     - in progress
     - ``cdeadmin_ui/objects``: ObjectEditor (canonical tabs, SQL tab = provider plan), OperationDialog, FieldControl, RecordGrid, KeyValueEditor, menu model; descriptor service ``/cdeadmin/api/ui/descriptors``; tree activation opens the family editor when the engine declares one (legacy workspace fallback). Second increment: ``options.json`` per engine feeds selects and reference pickers (dialect lists + catalog lists from the endpoint's resources); descriptor entries (Edit, Create, tier 2/3 operations in the OperationDialog) merged into the tree context menu with legacy duplicates retired; Statistics / Dependencies / Indexes / Triggers tabs read the inspected resource. Third increment: Data tab opens the provider row grid; variant switches are ``ui_only`` and default from the kind; record pre-fill primitives (dotted keys, derive/filter/pluck/pattern rules, ``record_children`` for inventories that list columns as separate resources). Fourth increment: the in-panel Resource Explorer (flat object tree, filter, breadcrumb, context menu) is gone; the Resources tab hands off to the Object Explorer tree and keeps only catalog refresh/paging. Remaining: PostgreSQL routing
   * - 3
     - Engine descriptors (Firebird, MySQL, MariaDB, DuckDB, SQLite)
     - in progress
     - Firebird 10/10, MariaDB 8/8, DuckDB 8/8, SQLite 6/6 forms ``complete`` by live round trip (server forms through the registration contract, ``tools/tests/test_ui_descriptor_server_forms.py``). MySQL: owned by the MySQL stream. PostgreSQL: drafts pass the ui.js schema-id gate; 5 large-object tier 2/3 operations ``complete`` on PostgreSQL 16.15 (not 18.3); routing is phase 5. Family table below
   * - 4
     - Operations, panels, menus
     - in progress
     - ``tools.json`` per engine declares the tool/dashboard/registration openers; ``context_menu.py`` appends them through ``declared_tool_actions`` instead of ``engine_id`` branches (Firebird, DuckDB, SQLite migrated with a 480-scenario output snapshot unchanged; MySQL/MariaDB branches left to the MySQL stream). SQLite and DuckDB database operations (17) are ``complete`` by dialog-draft round trips (``tools/tests/test_ui_descriptor_operations_{sqlite,duckdb}.py``) and their legacy menu task lists are deleted; the tree serves them from ``operations.json`` through the OperationDialog, which now resolves database-node targets and sends typed confirmations as the draft's ``confirmation``. Branch count gated: 35 -> 14 (``engine_branches_in_context_menu``). Panel count below
   * - 5
     - PostgreSQL convergence, beta acceptance
     - not started
     - 

Family descriptor status per engine
-----------------------------------

Values are the ``status`` of ``ui_descriptors/<engine>/forms/<family>.form.json`` with field count (f) and
recorded gaps (g): ``pending`` (skeleton only), ``draft`` (fields listed), ``complete`` (round trip verified
on the tested version). ``n/a`` = family omitted with a reason in ``omitted_families.json``.

.. list-table::
   :header-rows: 1

   * - Family
     - PostgreSQL
     - MySQL
     - MariaDB
     - Firebird
     - DuckDB
     - SQLite
   * - Table
     - draft (54f, 6g)
     - draft (33f, 9g)
     - complete (7f, 5g)
     - complete (11f, 1g)
     - complete (7f, 2g)
     - complete (11f, 5g)
   * - View
     - draft (27f, 2g)
     - draft (8f, 3g)
     - complete (3f, 2g)
     - complete (2f, 1g)
     - complete (5f, 0g)
     - complete (3f, 1g)
   * - Index
     - draft (24f, 2g)
     - draft (14f, 4g)
     - complete (5f, 2g)
     - complete (10f, 0g)
     - complete (5f, 0g)
     - complete (5f, 1g)
   * - Routine
     - draft (57f, 4g)
     - draft (15f, 3g)
     - complete (10f, 2g)
     - complete (9f, 0g)
     - complete (7f, 0g)
     - n/a
   * - Trigger
     - draft (30f, 3g)
     - draft (11f, 1g)
     - complete (6f, 2g)
     - complete (7f, 0g)
     - n/a
     - complete (8f, 1g)
   * - Sequence
     - draft (19f, 0g)
     - n/a
     - complete (8f, 0g)
     - complete (7f, 0g)
     - complete (7f, 1g)
     - n/a
   * - Type
     - draft (47f, 4g)
     - n/a
     - n/a
     - complete (7f, 0g)
     - complete (5f, 0g)
     - n/a
   * - Role
     - draft (18f, 2g)
     - draft (4f, 1g)
     - complete (22f, 2g)
     - complete (10f, 1g)
     - n/a
     - n/a
   * - Database
     - draft (33f, 2g)
     - complete (6f, 1g)
     - complete (6f, 0g)
     - complete (11f, 0g)
     - complete (2f, 3g)
     - complete (9f, 0g)
   * - Server
     - draft (46f, 5g)
     - draft (41f, 4g)
     - complete (38f, 0g)
     - complete (53f, 0g)
     - complete (10f, 0g)
     - complete (17f, 0g)

Baseline lint counts (2026-10-25)
---------------------------------

Reported by the validator. Each should only go down; the phase that retires a
count sets its maximum to zero in the enforcement file.

.. list-table::
   :header-rows: 1
   :widths: 50 15 35

   * - Count
     - Baseline
     - Retired by
   * - ``json`` controls in provider form code
     - 305
     - Phase 3 (per engine)
   * - Direct ``@mui`` imports in UI code
     - 244
     - Phase 2 (shell) and 4 (panels)
   * - Engine-literal branches in UI code
     - 111
     - Phase 2 and 4
   * - Hand-written engine panels in ``static/js/Dialogs``
     - 113
     - Phase 4 (target: tool panels only, about 70)
   * - ``ProviderWorkspaceContent.jsx`` lines
     - 8528 (8230 after the in-panel Resource Explorer was removed, 2026-10-25;
       6543 after ``SemanticModelWorkspace`` was retired, 2026-10-28)
     - Phase 5 (deleted)
   * - ``relational_admin.py`` lines
     - 8942
     - Phase 3 (``_form()`` and ``catalog()`` patching removed)

Change log
----------

Firebird diagram physical edits to reviewed plan (2026-10-29)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Stream B3/B4 for Firebird: the relations diagram now publishes the physical-schema
vocabulary (indexes with unique/descending/inactive/COMPUTED BY/partial, PRIMARY KEY,
UNIQUE, CHECK, FOREIGN KEY with ON DELETE/ON UPDATE and constraint-backing indexes),
and edits to it flow through the hand-off into the existing reviewed plan and the
owned-transaction applier. Explicit-mapping renames are carried only for columns;
table, index and constraint renames return "not carried" with the Firebird 5.0 reason;
drops need ``drop`` plus the exact name and are flagged destructive. A replayed review
of an index or constraint creation now converges instead of blocking as "added outside
the baseline" (other objects keep that blocker). Code:
``workspace/firebird_physical.py``, ``firebird_lifecycle_plan.py``,
``firebird_schema_plan.py``, ``firebird_relational_review.py``. Live tests:
``tools/tests/test_firebird_physical_roundtrip.py`` (36 tests, Firebird 5.0.3.1683,
forward, edit, reverse, plan, apply, re-inspect, converged re-plan); gate scenario
``physical`` in ``tools/cdeadmin_firebird_ddn_exchange_gate.py``. Matrix per kind in
:doc:`ddn_physical_schema_vocabulary`.

BI signed embedding (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Stream C4 embedding: a dashboard or question shown in an iframe on another site
to people without an account, through a short-lived HS256 token the embedding
site signs (Metabase-style). Off by default (``CDEADMIN_BI_EMBED_ENABLED``),
server mode only. Embeds run with the owner's delegated credentials (the alert
delegation machinery, BI-embed resolver id and AAD) under a distinct
``embedding`` principal; locked parameters and claims are inside the signature
and claims feed the semantic row policies; the cache key and result ownership
include the principal. Raw SQL is refused unless a server setting and
``assert_raw_sql_allowed`` allow it (never with claims). Unauthenticated
blueprint ``/cdeadmin/embed/`` with uniform 404s, ``frame-ancestors`` from the
embed's origins, no cookies, no CORS, per-IP and per-embed rate limits, row
caps and counts-only statistics. Migration ``cde_bi_embeds_v1``
(``cde_bi_embed``, ``_key``, ``_delegation``, ``_credential``, ``_jti``,
``_stat``); ``SCHEMA_VERSION`` not bumped. New actions ``bi_embed_*`` (catalog,
list, get, create, update, enable, disable, rotate, retire_key, revoke, delete,
mint, preview, check_token, stats). BI UI: Embed dialog on question and
dashboard pages. Tests: ``tools/tests/test_cdeadmin_bi_embedding.py``; Jest
``embeds`` and ``EmbedDialog`` specs on fixtures generated from the real
backend. See :doc:`bi_embedding` (threat model, residual risks, decisions).

BI alerts and subscriptions (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Stream C4 threshold alerts: alerts on saved questions (row count or column
aggregate against a number or the previous evaluation, results exist or empty;
edge triggered by default, optional every-evaluation, re-arm, mute with expiry)
and scheduled question or dashboard subscriptions (CSV, XLSX, PDF, SVG under the
export policy). They run on the existing report scheduler with the owner's
encrypted delegated credentials (BI-specific resolver id and AAD) and pause with
a recorded reason when the owner loses view access. Channels: in-app
notifications, report_delivery SMTP and S3, and a signed webhook (HMAC-SHA256,
host allow-list, DNS resolution with IP pinning, no redirects). Migration
``cde_bi_alerts_v1`` (``cde_bi_alert``, ``_delegation``, ``_credential``,
``_occurrence``, ``_event``, ``cde_bi_notification``); ``SCHEMA_VERSION`` not
bumped. New actions: ``bi_alert_*`` (catalog, schedule_preview, list, get,
create, update, delete, test, run_now, mute, unmute, rearm, pause, resume,
history) and ``bi_notification_list`` / ``bi_notification_read``. BI UI: Alerts
and Subscriptions section on question and dashboard pages with condition
builder, schedule picker with next-run preview, channel and recipient picker,
test evaluate, history and mute. Tests:
``tools/tests/test_cdeadmin_bi_alerts.py`` (fake clock); Jest ``alerts`` and
``AlertsPanel`` specs on fixtures generated from the real backend. See
:doc:`bi_alerts` (security model and residual risks).

Semantic-model workspace retired (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Stream C5: ``SemanticModelWorkspace`` and its private helpers
(``portableId``, ``emptySemanticModel``, ``semanticCrossFilter``,
``SemanticChartView``) are deleted from ``ProviderWorkspaceContent.jsx``. The
``semantic`` tab mounts the BI module's Models view
(``cdeadmin_ui/modules/bi/models/``, surface ``bi.models``), a descriptor and
``FieldControl``/``RecordGrid`` driven editor with revisions, compare, status
transitions, lineage, diagnostics and a cellset grid; raw JSON is only the
Advanced JSON tab. Embedded visualizations and dashboards migrate to saved
questions and BI dashboards through ``semantic_model_migrate`` (dry run by
default, idempotent, model unchanged); reports and schedules stay in the model,
run through ``report_scheduler`` and are read-only in the view. Capability map,
dropped capabilities, the subscription TODO and owner decisions are in
:doc:`bi_models_view`. No shared schema, family renderer or MySQL descriptor was
edited. Counts from ``python3 tools/validate_ui_descriptors.py --counts``,
before/after: JSON controls 297/297, MUI imports 244/244, engine-literal UI
branches 111/111, engine panels in Dialogs 113/113, context-menu branches
14/14, ``ProviderWorkspaceContent.jsx`` lines 8230/6543. The MUI count is a
count of import statements, and every ``@mui`` import the deleted component used
is still used by other panels in the file, so it does not move. The maxima in
``tools/ui_lint_maximums.json`` are left as they are.

BI sharing and permissions (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Stream C4 permissions: grants (view, edit, manage) for users or pgAdmin roles on
collections, saved questions and dashboards, per endpoint, with inheritance down
the collection tree and per-item overrides (``cde_bi_permissions_v1``:
``cde_bi_grant``, ``cde_bi_access_override``, ``cde_bi_audit``, revision
``actor_user_id``; ``SCHEMA_VERSION`` not bumped). Every ``bi_*`` entry point
goes through ``BIAccess.require``; no grants means owner-only as before. Shared
questions run with the runner's credentials and row policies, raw SQL is
redacted below edit, dashboard cards without question access answer
``no_access``. New actions: ``bi_access_get``, ``bi_grant_*``,
``bi_access_inherit``, ``bi_transfer_owner``, ``bi_shared_with_me``,
``bi_principal_search``, ``bi_audit_list``. BI UI: Share dialog, Shared with me
root, permission-aware controls, read-only banner, redacted-SQL notice, "No
access" card. Tests: ``tools/tests/test_cdeadmin_bi_permissions.py``; Jest
``sharing``, ``ShareDialog`` and ``SharedTool`` specs on fixtures generated from
the real backend. See :doc:`bi_permissions` (residual risks included).

PostgreSQL maintenance actions (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The provider now plans and applies VACUUM, ANALYZE, REINDEX (table, index,
schema, database), CLUSTER, table TRUNCATE and REFRESH MATERIALIZED VIEW
(``providers/postgresql/maintenance.py``; ``compile_native_admin`` routes by
operation, so the other table/index/view actions stay ``legacy-preserved``).
Identifiers are always double-quoted from catalog identity and every option is
allow-listed with strict types (VACUUM FULL/FREEZE/ANALYZE/VERBOSE/PARALLEL n,
ANALYZE VERBOSE/SKIP_LOCKED, REINDEX CONCURRENTLY/VERBOSE, CLUSTER USING,
TRUNCATE RESTART IDENTITY/CASCADE with the typed table name, REFRESH
CONCURRENTLY/WITH [NO] DATA). VACUUM, REINDEX SCHEMA/DATABASE and any REINDEX
CONCURRENTLY are refused by PostgreSQL inside a transaction block, so the plan
marks them ``autocommit`` and ``apply_admin_operation`` runs them without
BEGIN/COMMIT (the connection must be idle and in autocommit); the plan warns
that they cannot be rolled back. Every apply returns a ``maintenance_receipt``
(action, object, options, executed statement, transaction mode). CLUSTER and
REINDEX SCHEMA/DATABASE require plan confirmation. ``operations.json`` goes
from 5 to 14 operations (generated by ``tools/draft_postgresql_operations.py``),
all ``complete`` by live round trip in
``tools/tests/test_ui_descriptor_operations_postgresql.py`` (effects observed:
relfilenode rewrites, statistics, clustered heap order, identity restart,
materialized-view contents). Evidence is **PostgreSQL 16.15, not 18.3**; the
18.3 qualification stays open. Not covered: CLUSTER from the index node
(needs the owning table in the native identity), VACUUM/ANALYZE column lists,
REINDEX TABLESPACE, and the rename / set schema / owner / grant actions.

PostgreSQL tier 2/3 operations (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``postgresql/operations.json`` goes from 0 to 5 operations (generated by
``tools/draft_postgresql_operations.py``): large-object ``read``, ``write``,
``truncate`` (typed OID), ``import-server-file`` and ``export-server-file``
(typed destination path). All 5 are ``complete``: each dialog draft passes
provider validate, plan and apply (with the confirmation gate) against a live
server and the effect is observed (``tools/tests/test_ui_descriptor_operations_postgresql.py``,
``CDEADMIN_ROUNDTRIP_POSTGRESQL``). Evidence is **PostgreSQL 16.15, not 18.3**:
the capability profile pins 18.3 and this container has 16, so the 18.3
qualification stays open. The ``large-object`` kind was added to
``capabilities.json`` (``engine_object``, tier-1 create/alter/drop/grant/revoke
listed, no editor until the Engine-object skeleton, Decision 15). The 30
recorded provider gaps and the ten ``draft`` forms are unchanged.

Not drafted, by finding: the provider exposes no validate/plan/apply for
VACUUM, ANALYZE, REINDEX, CLUSTER, table TRUNCATE, REFRESH MATERIALIZED VIEW,
or rename / set schema / owner / grant on tables, indexes, sequences, roles and
databases. These are ``legacy-preserved`` (``compile_native_admin`` refuses
them as owned by the preserved pgAdmin UI), so a descriptor would promise a
dialog nothing can plan. Each is a provider ask: a native compiler per action,
then a descriptor and a round trip. The provider's other non-lifecycle forms
(operator-family add/drop members, operator optimization options) are ``alter``
actions behind an ``action`` discriminator; descriptor ``operation_id`` is sent
verbatim, so they need a design decision (separate operation ids mapped to
``alter`` or a fixed hidden ``action``) before they can be drafted. PostgreSQL
shell routing remains phase 5. Descriptor counts: operations 0 -> 5, kinds
23 -> 24.

Server editor wired into the tree (2026-10-28; legacy retired, unverified)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

"Register server" (endpoint intent) and "Edit endpoint" open the descriptor
Server editor (``ServerRegistrationHost``) for engines whose ``server`` form is
``complete`` (MariaDB, Firebird, DuckDB, SQLite). ``ObjectEditor`` gained a
``directApply`` mode (no plan, Preview SQL hidden) because registration is not
DDL; the host posts ``toBackendDraft`` plus ``cde_profile_id``,
``cde_registration_intent`` and ``cde_verify_now`` to the servers API and feeds
the tree through the same ``tree:add`` / ``tree:update`` events as the legacy
dialog. ``create_database`` and ``register_existing`` intents, PostgreSQL,
MySQL and any engine without a complete form keep the legacy dialog (fallback
on any bundle error). Not yet exercised in a running browser; the Jest specs
cover payloads and the edit-only-changed rule. ``confirm``-type operations that
carry a typed ``confirmation`` field (Firebird limbo and shadow tasks) were
checked: the field is an ordinary required field and reaches the draft.

Owner decision 2026-10-28: the legacy dialog is retired for these four engines
without a browser test (fallback commented out, errors reported instead). Risk,
trace and restore steps: :ref:`ui_server_editor_retirement`.

Firebird and MariaDB operation round trips (2026-10-28)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tier 2/3 operations driven through their dialog drafts against live servers
(``tools/tests/test_ui_descriptor_operations_{firebird,mariadb}.py``): Firebird
33 of 35 ``complete`` (Firebird 5.0.3), MariaDB 29 of 35 (MariaDB 10.11). Left
``draft`` with the reason in each operation's ``notes``: Firebird
``remove_linger`` (no observable effect) and ``upgrade_database`` (no older-ODS
database); MariaDB logical backup/restore and the upgrade check (provider pins
the 12.2.2 tool release) and partition/table exchange (provider always emits
``WITH|WITHOUT VALIDATION``, rejected by 10.11). Note: the 5.0.3 server refuses
gfix-class Services API tasks over TCP with Srp256 (auth block over 255 bytes);
those 13 operations were exercised through the local Services route and
observed over TCP. Descriptor fixes: string lists are typed grids, hidden-field
defaults removed, typed-name/confirmation fields aligned with the provider.
Provider fixes (additive): firebird-driver ``keyholder`` spelling, grid
``{value: x}`` unwrapping for Firebird and MariaDB string lists, MariaDB
``DROP PACKAGE BODY`` ``sql_mode``.

MariaDB program objects and the Server family (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MariaDB trigger and routine forms are ``complete``: the MariaDB inventory now
reports trigger timing/events/position/body, routine body/parameters/returns
and event schedule/preserve/enabled/body (``mariadb_catalog.program_object_natives``,
additive), so a re-opened object shows its definition; ``active``/``position``
are hidden on the MariaDB trigger form because the compiler emits neither, and
OUT/INOUT parameter modes are recorded as a backend ask. The Server family is
``complete`` for MariaDB, Firebird (network live; embedded by contract mapping),
DuckDB and SQLite: ``tools/draft_server_descriptors.py`` now emits the
servers-API keys (``backend_field_id`` = ``cde_route_<id>`` / ``cde_secret_<id>``
/ ``db`` ...), the generic registration fields (database or file, connect now,
comment, colours, tags) and typed controls for the former JSON fields (attached
databases grid, DuckDB configuration key/value); the round trip is draft ->
servers-API payload -> persisted route through ``provider_route_options`` ->
live identity -> edit pre-fill through ``provider_route_form_values``. Provider
fix found by it: the MariaDB ``ssl_verify_cert`` registration default forced
TLS on routes with SSL off. Shell rule change: in alter mode an unchanged field
stays out of the ALTER set whether or not it is required (the target names the
object); both twins and their tests agree. PostgreSQL server/family forms stay
``draft`` (phase 5, open decision 1).

Firebird, MariaDB, SQLite and DuckDB round trips (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Live engines were stood up for acceptance (Firebird 5.0.3 from the GitHub
release tarball, MariaDB 10.11 and PostgreSQL 16 from apt). Firebird
table/view/index/trigger/sequence/type/routine/role/database and MariaDB
table/view/index/sequence/role/database are ``complete``: each form was driven
through its own fields -> provider plan -> apply -> re-inspect, and the
re-opened object pre-fills every tab the inventory can supply
(``tools/tests/test_ui_descriptor_roundtrip_{firebird,mariadb}.py``, skipped
without ``CDEADMIN_ROUNDTRIP_*``). SQLite and DuckDB database forms joined
their suites. Backend additions for pre-fill, all additive: Firebird domain
``type_editor``/``type_sql``, routine parameter ``type_sql`` + function
parameter modes, trigger ``trigger_timing``/``trigger_events``. MariaDB
trigger and routine stay ``draft`` because the mysql_family inventory reports
no body or parameters (recorded under ``gaps`` as a backend ask). PostgreSQL
forms gained a schema-id gate against the pgAdmin ``*.ui.js`` sources and stay
``draft`` until phase 5 (open decision 1). ``make ui-descriptors-check`` now
runs the descriptor pytest suites.

MySQL audit and native user-key work (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The MySQL capability seed has been reconciled against its complete administration
catalog and read-only profile kinds. Unsupported seeded server/replication DDL
entries were removed; missing kinds and operations were added. Closed masking
and execution-runtime limits remain explicit. The table family stays ``draft``:
every retained create binding reaches the actual compiler; ignored properties,
incorrect constraint discriminators and value-shape mismatches were corrected or
recorded under ``gaps``. Details are in ``ui_descriptors/mysql/README.md``.
The MySQL-specific legacy table field branch and field factory were deleted.

Five user-key operation descriptors now accompany their backend implementation,
with typed fields and Security menu placement. Stable form-reference allocation
remains with the front-end registry owner.
They are ``draft`` and remain **unsurfaced by the unified shell** pending the
front-end stream's shared operation-dialog/family-render acceptance; native/API
qualification is not a substitute for that gate. Protected key retrieval/export
is Decision 10. No shared schema, family skeleton, renderer or family-render test
was changed by the backend stream.

Current lint counts for this change: JSON controls **305 → 304**, direct MUI
imports **244 → 244**, engine-literal UI branches **111 → 111**, engine panels
**113 → 113**. The tracked family statuses have not advanced to ``complete``.

* 2026-10-25 (phase 3, review pass): ``tools/review_ui_descriptors.py`` applies the canonical shapes to the
  generated drafts (constraint grid split into Primary key / Unique / Foreign keys / Check bound to
  ``constraints[kind=...]``, trigger events as a multiselect, table/parent reference pickers, string-list grids,
  column-grid ``record_key`` pre-fill, SQLite virtual/FTS variants, DuckDB replace acknowledgements).
  ``tools/ui_descriptor_roundtrip.py`` is the Python twin of the shell's draft mapping; in-process round trips
  (create, re-inspect, alter via the Columns grid diff) pass for SQLite table/view/index/trigger and DuckDB
  table/view/index/sequence/type/routine, which are now ``complete`` (verified on SQLite 3.53.1 and DuckDB 2.0.0;
  the pinned 3.53.0 / 1.5.2 qualification stays with the platform teams). Provider fix: SQLite triggers wrap the
  body in BEGIN ... END and admit one event. Firebird, MariaDB and PostgreSQL drafts are reviewed structurally
  but stay ``draft``: no engine is reachable from this environment for their round trips.
* 2026-10-25 (phase 2, second increment): per-engine ``options.json`` (schema + validator check that every
  ``option_values_path`` has a source); host builds the option context from the bundle and one resource page;
  tree context menu gains Edit / Create / descriptor operations from the cached bundle (``familyEditorContextActions``),
  legacy entries for the same operation id retired; Statistics, Dependencies, Indexes and Triggers tabs read the
  inspected resource. 91 family-suite tests green; lint counts unchanged.
* 2026-10-25 (phase 2, first increment): descriptor service and bundle endpoint; shared ObjectEditor /
  OperationDialog / FieldControl / RecordGrid / KeyValueEditor in ``cdeadmin_ui/objects`` (primitives only,
  zero engine branches); tree activation of a provider resource opens the family editor when the bundle
  declares one; family render gate (61 engine x family cases) and descriptor logic tests green; ESLint
  boundary extended. Lint counts unchanged: 304 / 244 / 111 / 113.
* 2026-10-25 (later): drafted descriptors for the five non-MySQL engines from the live provider contracts
  (``tools/dump_provider_forms.py`` + ``tools/draft_ui_descriptors.py``), Server family from
  ``form_contracts.py`` (``tools/draft_server_descriptors.py``), PostgreSQL families from the legacy
  ``*.ui.js`` schemas (``tools/draft_postgresql_descriptors.py``), Firebird virtual tree layout in
  ``navigator.json``; tier 2/3 operations per engine: PostgreSQL 0, MySQL 5, MariaDB 35, Firebird 35, DuckDB 8, SQLite 17.
  Recorded provider gaps: PostgreSQL 30, MySQL 8, MariaDB 14, Firebird 6, DuckDB 9, SQLite 12. ``mysql/`` untouched; its stream can run the same tools.
* 2026-10-25: design adopted; descriptor schemas, ten family skeletons, engine
  stubs for the six beta engines, MySQL table worked example and the validator
  added. All other forms ``pending``.

MySQL View descriptor migration (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The View family moves from ``pending`` to ``draft``. Every declared create/alter
field reaches the real provider compiler; the duplicate native view field
factory and `_form()` branch were removed. Scalar output aliases and privilege
diffs remain explicit Decision 9 gaps. MySQL's absence of triggers on views is
recorded under ``omitted_tabs``. Shared render acceptance remains pending; no
family is promoted to ``complete``. Lint counts: JSON controls **304 → 303**, MUI
imports **244 → 244**, engine-literal UI branches **111 → 111**, panels
**113 → 113**. Shared skeletons, schemas, shell and family render tests were not
changed.

MySQL Index and Routine migrations (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Index is draft with14fields/4gaps. Native ordered expressions, prefixes,
FULLTEXT/SPATIAL/HASH, visibility and online clauses are qualified through both
connectors and authenticated plan/apply. Primary engine-attribute hooks are
excluded from beta controls: the audited Community source has no implementing
primary engine, and release InnoDB/MyISAM/MEMORY reject them.

Routine is draft with48fields/8gaps across Procedure, Function and Scheduled
variants. Each capability routes directly to its variant descriptor. Native
procedure OUT/INOUT modes and create characteristics have typed backend inputs;
functions retain their native input-only parameter contract. Create and alter
characteristic defaults are separate, so comment-only edits preserve native
security/data-access or event schedule/status/completion. Legacy routine-change
and event field factories and dispatch branches were removed. A typed event
rename operation accompanies the existing backend action. Decision9 gaps and
post-beta non-SQL runtime dependencies remain explicit; no implicit body
replacement is introduced. Lint counts before/after: JSON303/303, MUI244/244,
engine branches111/111, panels113/113. Shared render and round-trip acceptance
remain pending; no family is marked complete.

MySQL Trigger migration (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trigger moves to draft (11fields/1gap). Native timing, single event, definer,
IF NOT EXISTS and relative ordering are typed; unsupported active/position
controls are absent. Ordering is on Engine; Options is omitted because native
row triggers have no deferrability/transition-table options. Native pure/C and
authenticated plan/apply qualify row effects, ordering and drop, while shared
rendering/round-trip acceptance remains pending. There was no MySQL-specific
legacy trigger field factory to delete; the frozen generic branch remains for
other engines. Lint counts before/after: JSON303/303, MUI244/244, engine
branches111/111, panels113/113.

MySQL User and Role variants (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

User is draft (36fields/3gaps); Role is draft (4fields/1gap). Native MySQL9.7
pure/C and authenticated plan/apply qualify plugins, password and TLS policies,
resource limits, default roles, real GPL socket second/third factors and exact
account rename/drop. Native registration hooks are not proof of an available
registration plugin. Generated passwords and protected key results remain
Decision10; family membership/privilege dispatch remains Decision9.

The privilege variant is now draft (15fields/1gap); all three Role variants have typed inputs.
Named-account role aliases expose native membership actions without inventing
persisted CREATE ROLE origin. All accounts remain visible under Users for policy
editing. Initial role grants have separately acknowledged native statements; a
later grant failure does not undo creation. The legacy MySQL role field factory
and create-role dispatch were removed. Shared rendering/round trips remain
pending. Lint before/after: JSON303/303, MUI244/244, branches111/111, panels113/113.

MySQL native privilege inputs (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The privilege variant moves to draft with15fields/1gap. Dedicated Security
operations declare typed grantees, column privileges, native dynamic names,
proxy accounts, global GRANT AS role modes and REVOKE options. Native MySQL9.7
pure/C and authenticated plan/apply qualify real permission effects and denials,
partial revokes, native warnings/errors, changed-state refusal and no replay
after observation loss. The runtime partial_revokes policy is bound to review.
The old MySQL-specific privilege scope field branch was deleted; the generic
factory remains for other engines. Family diff dispatch remains Decision9.
Shared rendering/round trips remain pending. Lint before/after: JSON303/303,
MUI244/244, branches111/111, panels113/113.

MySQL user-key result scope ruling (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Decision10 is resolved for user keys: the owner selected metadata-only for beta.
Type/byte-length inspection and the five existing native Security operations
remain in scope; raw-key retrieval/export is owner-excluded from the current
beta, not an implementation blocker or closed-source Enterprise deferral.
Public plans/receipts contain no key material and no download control is added.
Protected generated-password delivery remains a separate gap. Descriptor draft
and shared rendering/round-trip statuses are unchanged. Lint before/after:
JSON303/303, MUI244/244, branches111/111, panels113/113.

MySQL Database and Server descriptors (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Database moves from pending to complete for its declared fields (6fields/1gap). The existing endpoint and
visual-admin input contracts load the same descriptor fields; legacy MySQL
create/alter/drop field tuples were removed. Native SHOW CREATE DATABASE now
supplies read-only state and full definition; an unavailable observation stays
unavailable. Record projections map native encryption YES/NO to the provider's
Y/N inputs. Native MySQL9.7 pure/C and authenticated plan/apply qualify create,
prefill, alter, read-only enforcement, data preservation and drop. The unchanged shared family-render suite and the native descriptor/draft
round trip qualify these fields; human presentation and platform acceptance
remain separately owned. Security diff dispatch remains Decision9.

Server moves from pending to draft (41fields/4gaps), audited against the expanded
registration profile and its existing input validation. Failover targets, TLS
lists and connection attributes use typed grids/multiselect/keyvalue controls.
Optional closed-server authentication dependencies remain post beta. Nested
failover credentials/pools and absent application metadata bindings are explicit
gaps. No MySQL-specific legacy server form factory existed; the shared profile
builder remains a backend input contract for other connectors. Registration is
not server DDL: Decision11 records the shared registration-action dispatch that
must land before this Server form counts as surfaced. No shared host, schema or
family-render test was changed. Lint before/after: JSON303/303, MUI244/244,
engine branches111/111, panels113/113, context-menu branches14/14.

The startup route assertion now includes the two authenticated descriptor GET
routes introduced by the shared shell (1413 to1415). This updates the expected
API surface, not a resource allowance: source/bundle byte limits, the8-second
startup limit and240000KiB RSS limit are unchanged.

MySQL server maintenance and navigation descriptors (2026-10-25)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Operations now declare42 entries (29 added): page tracking, query rewrite rules,
server shutdown/restart, prepared XA recovery, instance maintenance and SDI
import, named MyISAM cache lifecycle and table cache assignment/preload.
The seven legacy native-module form factories and their dispatches are deleted;
the existing catalog/input adapter derives fields solely from descriptor data.
All29 native field sets and defaults are preserved; unsigned64-bit values and
binary XA identities stay text, and three former JSON lists become scalar-list
grids. The seven native modules' remaining ASTs are unchanged.

All42 entries remain draft. Decision12 records the shared operation dialog's
missing declared draft projection; the three scalar-list operations are
explicitly unsurfaced until it lands. Backend projection/admission and native
pure/C plus authenticated cache workflows are separate from dialog acceptance.
No shared schema, renderer or family-render tests were changed.

Navigator now declares all33 actual catalog kinds,16 folders, semantic icons,
system grouping and table/view child kinds. The declared layout is draft and
unsurfaced pending the shared tree consumer (Decision13). No extra MariaDB-only
kinds were inferred. Group9/native inventory and generated-password delivery
remain open. Lint before/after: JSON303/301, MUI244/244, engine branches111/111,
panels113/113, context-menu branches14/14.

MySQL partition, CHECK and Group Replication operations (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Operations now declare65 entries (23 added): eleven partition/table maintenance
actions, CHECK enforcement, ten Group Replication actions and privilege
inspection. All remain draft. Native partition drop retains its Tier1 lifecycle
classification and its existing confirmation-only input contract; it is not
duplicated as a maintenance operation. The Group Replication and CHECK form
factories/dispatches are deleted. The partition factory retains only that
unmigrated drop contract; every migrated partition field comes from descriptor
data. Existing catalog titles delegate to those same input contracts, without
new engine branches or handwritten fields.

Partition definitions use the existing bounded native SQL grammar; a separate
statement or unrelated ALTER action is rejected. Reorganize uses a scalar-list
grid. Hidden COUNT/DEFINITIONS fields require shared draft projection
(Decision12); family Partitions-grid dispatch stays Decision9. Those workflows
remain explicitly unsurfaced. Native projected-input qualifications cover
partition data effects, CHECK refusal/enforcement, both connectors and
authenticated APIs; the three-member group harness covers all ten group
actions. They do not establish actual dialog acceptance.

Capabilities retain identical parsed content, including all33 kinds, operation
IDs and tiers; only nested JSON layout was compacted. The backend adapter now
preserves declared prefill paths as the existing ``initial_value_path`` contract.
No shared schema, renderer or family-render test changed. Lint before/after:
JSON301/300, MUI244/244, engine branches111/111, panels113/113, context-menu
branches14/14. Twenty-two beta tier2/3 entries still lack descriptors; two
closed-source masking entries remain separately post beta. Group9 is open.

MySQL configuration and channel operation descriptors (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Operations now declare76 entries (11 added): global/persisted variable changes,
persisted-value reset, query/connection termination, resource-group assignment
and four asynchronous channel actions. The server-operation form factory and
dispatch are deleted. Channel create/alter and resource-group lifecycle forms
remain outside this operation cutover; their migrated action branches are
removed rather than duplicated.

Variable inputs use Text, Boolean, safe integer, exact integer, exact decimal
and floating-point controls. Native scalar bindings and existing numeric CASTs
are preserved. Input-dependent backend contracts receive private draft context;
they retain AUTO and encoded mapping compatibility without a raw JSON UI
control. An existing defect is fixed: scalar JSON input previously reached an
object/array-only validator and was rejected. The explicit backend-only scalar
admission mode now accepts the native scalar contract. DEFAULT/NULL skip ignored
values. Native compiler checks still reject unsupported types and ranges.

Channel controls declare every native UNTIL family and seven filter families.
Typed database/table and rewrite records now compile to the same native SQL as
the existing pair-array API. Empty selected filter lists clear only those
filters; unselected filters are preserved. Thread IDs and positions remain
exact decimal text. Projected inputs are qualified independently from actual
dialog acceptance. All11 entries stay draft/unsurfaced pending shared operation
projection (Decision12); no shared renderer, schema or family-render test changed.

Existing family/options JSON was reindented with identical parsed content to
stay within unchanged source budgets. Lint before/after: JSON300/297,
MUI244/244, engine branches111/111, panels113/113, context-menu branches14/14.
Eleven beta tier2/3 entries remain (database8 and row workflows3), alongside
the separately recorded native inventory, shared UI and protected-result gaps.

MySQL database operation descriptors (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Eight database entries bring the operation total to84: analyze, check, optimize,
repair, checksum, logical backup, restore and separate restored-data verification.
Their eight legacy portfolio forms and overrides are removed. The existing
common-profile path now resolves the descriptor adapter; native permissions and
mutation classes are retained. Legacy browser form gates explicitly refuse the
retired registry instead of accepting an empty fallback as UI evidence.

Histogram import uses typed attributes and bucket records, including singleton,
equi-height, empty histograms, integer endpoints, native numeric conversion,
encoded string bounds and temporal values. Shell filters use string lists and
partition/condition records. Optional collection switches preserve absent versus
explicit empty input. Duplicate/unknown filter or bucket fields are refused;
existing native arrays, maps and encoded API transports remain admitted.

All eight entries remain draft/unsurfaced pending Decision12 and presentation
acceptance. Their native/API evidence qualifies projected inputs, not an actual
OperationDialog round trip. Three row workflows still lack descriptors (Decision14). Dynamic
column types, row identity and concurrency must be reconciled with the shared
Data editor rather than represented as raw JSON. Independent native inventory,
protected RANDOM PASSWORD delivery and other recorded shared UI work remain
open. Group9 is not complete. Parsed family, capability and navigator content is
unchanged after compact formatting; no shared renderer/schema/family tests were
edited. Lint before/after: JSON297/297, MUI244/244, engine branches111/111,
panels113/113, context-menu branches14/14.

MySQL installed-interface catalog facts (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Explorer plugin discovery and server DDN capture now retain all eleven native
``information_schema.PLUGINS`` fields, including version/type/library versions,
author, description and load option. Existing status/type/library/license aliases
remain compatible. The query is explicit; MariaDB retains its own SHOW PLUGINS
contract. The existing Plugin inspect capability documents this projection.

Server DDN now includes all five native ``user_defined_functions`` fields.
A NULL library remains NULL for runtime service registrations; it is not an
inferred shared-library filename or authorization to remove a service function.
Usage counts are volatile observations, excluded from migration state. Server
migration plans still refuse function creation/removal from these observational
rows; existing native provider lifecycle operations are separate. Denied SELECT
produces an unavailable section with its native code instead of an apparently
successful empty inventory. The Loadable function inspect capability records
this native metadata scope.

These additions preserve native metadata and existing operation contracts. They
do not complete the independent installed-feature/workflow inventory or qualify
new shared UI rendering. Family/operation statuses, the84 operation entries and
Decisions9/11/12/13/14 remain unchanged. Lint before/after: JSON297/297,
MUI244/244, engine branches111/111, panels113/113, context-menu branches14/14.

MySQL relay coordinate admission (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing Start channel descriptor retains a text relay position and now
explains native ULONG_MAX review/revalidation. Wide coordinates are bound to
the target's metadata and server UUID before dispatch; neither the application's
word size nor a universal 32-bit limit determines support. Native 32-bit or
unavailable ceilings refuse wide requests. Small-position behavior is retained.
Both CHANGE and UNTIL receive native/API qualification; channel create/alter
source-option forms and shared OperationDialog projection remain separate gaps.

Common draft/render/SQL-tab prose is consolidated into the engine README;
operation-specific native constraints, key-material exclusions, execution-host
and verification trust details are retained. Static options are parsed-identical
after compact formatting. No operation count or completion status changes:
84 entries remain draft, three beta row entries and shared Decisions9/11/12/13/14
remain open. Lint before/after: JSON297/297, MUI244/244, engine branches111/111,
panels113/113, context-menu branches14/14. The independent inventory and
protected generated-password delivery remain open.

MySQL retry-count admission (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing channel create/alter backend now admits wide SOURCE_RETRY_COUNT
values under the target-bound unsigned-long guard. Native/API qualification
does not migrate those legacy source-option forms: their descriptor population
and actual shared dialog round trip remain unsurfaced work. No new operation,
field, descriptor status or lint count is claimed. Existing 84 draft entries,
three missing beta row-action entries and Decisions9/11/12/13/14 remain as
recorded above. Protected generated-password delivery remains open.

MySQL tool openers and Engine-object lifecycle (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Twenty-five existing endpoint/database tool openers now live in
``mysql/tools.json``: diagnostics, spatial inspection, content search, workload,
DDN capture, dashboards/collector configuration/editor, host/Router service
administration, native backup/archive/replay/clone jobs, sandboxes, topologies
and test data. Their legacy menu appenders are deleted. Stable command and
handler IDs, permission gates, offline owner access for retained jobs, database
scope, mutation classes and category/priority are retained. Labels name actions.
The viewer, collector configuration and DDN editor remain separate entries.
No native operation, renderer, family or operation status is added by this move.

Decision15 records the missing Engine-object lifecycle editor for channel
create/alter. Its typed form cannot pass the current family resolver/schema;
it remains unsurfaced without reclassifying lifecycle actions or inventing a
family. The four existing channel operation descriptors remain draft, as do
all 84 operation entries. Independent diagnostics overlays, native inventory,
protected generated-password delivery and shared Decisions9/11/12/13/14 remain
open. Lint before/after: JSON297/297, MUI244/244, engine branches111/111,
panels113/113, context-menu branches14/14.

MySQL replication receiver metadata (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Existing channel inspection now retains all27 native receiver-configuration
fields in both explorer and server/DDN exchange. Wide retry counts use decimal
text; NULL/empty cipher-suite settings remain distinct. No new operation, form,
menu or renderer is introduced. The native/API metadata receipts do not qualify
channel create/alter forms or resolve Decision15. All84 operation entries remain
at their recorded status; shared UI, independent inventory and protected-result
gaps remain open. The operations document is compacted with parsed-identical
content to retain the fixed source budget. Lint before/after: JSON297/297,
MUI244/244, engine branches111/111, panels113/113, context-menu branches14/14.

MySQL applier configuration and status (2026-10-26)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Existing channel inspection adds seven native applier-configuration fields and
four applier-status fields. Receiver and applier grants are independent; partial
visibility preserves the known channel identity and leaves unobserved fields
absent. Server/DDN capture merges facts into that same channel, with transient
status outside configuration comparison. No new form, operation or renderer is
added. Channel lifecycle remains unsurfaced under Decision15, and the84 operation
entries retain their status. Selected MySQL JSON documents are compacted with
parsed-identical contents to preserve the existing source budget. Lint
before/after: JSON297/297, MUI244/244, engine branches111/111, panels113/113,
context-menu branches14/14. Other replication inventory and protected results
remain open.

MySQL Group9 backend and shared integration boundary, 2026-10-26
---------------------------------------------------------------

User authentication and factor mode choices now include Generate password,
bound to native RANDOM PASSWORD. The native producer reserves protected delivery
before DCL and returns reference IDs only. Real native create/rotation/login,
lease closure and post-acknowledgement failure handling are qualified through
both connectors. Ordinary authenticated application requests refuse before DCL
without the protected service. Decision16 records the missing shared storage,
authorization, reference resolution and reveal/recovery bridge. The User variant
stays draft/unsurfaced for that workflow; no family or operation status advances.
Decision10 governs user keys only.

All20 receiver,15 coordinator and24 worker status fields are now observed through
independent grants. Live native diagnostic text is redacted from schema exchange;
transient status remains outside migration state. Retained catalog reads use a
private admitted peer and preserve source diagnostics/savepoints. Source active
roles and temporary objects remain unobserved (Decision17), not inferred.

The owner reaffirmed that shared UI stays with the front-end team. No shared
schema, family renderer, shell or family-render test was edited. Decisions9 and
11–17 remain the explicit shared handoff; the native independent inventory is
not closed by these additions. Group9 is not complete. Lint before/after remains
JSON297, MUI244, UI engine branches111, panels113, context-menu branches14.

MySQL asynchronous failover operations, 2026-10-26
--------------------------------------------------

Five Replication descriptors accompany native candidate management: four scoped
channel actions (add/remove source and managed group) and a server-wide reset
with a separate all-channel acknowledgement. Controls are typed host, port,
weight, managed-name and confirmation fields. MySQL9.7 ignores the old namespace
argument; no editable namespace control is invented. Its native Latin1 conversion
refusal is retained. The operation count is89; family/operation statuses remain
draft except the previously accepted Database fields.

Native pure/C, parser, scoped grants, DDN comparison/application, failure and
restart/disabled-instrumentation receipts qualify the backend. Authenticated API
qualification does not replace shared dialog round trips. Shared shell, schema,
family-render tests and source-overlay/protected-result integration remain with
the front-end team. Lint before/after remains JSON297, MUI244, UI engine
branches111, panels113 and context-menu branches14.

MySQL seven-item Group9 backend reconciliation, 2026-10-26
--------------------------------------------------------

The Table descriptor now binds temporary creation, foreign-key update/delete
rules and CHECK enforcement. The Server descriptor binds protected per-target
credential references and independent pool options. Two typed operation entries
add explicit session metadata refresh and temporary-table removal; there are91
operation entries. Capabilities match the native catalog. Families stay draft;
backend/API evidence does not replace generated-form round trips or presentation
acceptance.

Decision16's backend service is implemented: authenticated encrypted expiring
storage, scoped references, recovery by plan and explicit no-store reveal. The
workspace action ``protected_password_result`` is backend-only until the shared
host provides recover/reveal controls. The User descriptor records that precise
remaining gap. Decision17's explicit refresh accepts a retained session,
diagnostic acknowledgement and typed database/name records. Its source snapshot
feeds completion until the next source command. Session selection and the new
refresh/drop interaction remain **unsurfaced** in the shared host.

The identified seven backend gaps are implemented; shared UI stays with the
front-end team. No shared shell, schema, renderer, panel, menu JavaScript or
family-render test was edited. Lint before/after: JSON297/297, MUI244/244,
UI engine branches111/111, panels113/113, context-menu branches14/14.

BI questions tool: query builder UI, 2026-10-28
-----------------------------------------------

The first Metabase-style UI slice is a registered tool, not a new panel:
module ``cdeadmin.bi`` / surface ``bi.questions`` under
``cdeadmin_ui/modules/bi/``. It offers a collections tree with search,
rename, move and archive, a visual query builder (source,
columns, typed filters, summaries with grouping, sort, limit, parameters, live
compile preview), execution with paging and redaction notes, the chart set
through the shared chart wrapper, a SQL mode with SQL-to-question conversion,
save, save as and revision history. A generic ``open_tool`` context-menu
handler (``context_menu.py`` and ``ProviderContextMenu.js``) opens any
registered surface; SQLite, DuckDB, Firebird, MariaDB and PostgreSQL declare the
entry in ``tools.json``. MySQL awaits its owner (:doc:`bi_ui_mysql_handoff`).
Structure, state model and gaps are in :doc:`bi_query_builder_ui`. No shared
schema, form or family renderer was edited. Lint before/after: JSON297/297,
MUI244/244, UI engine branches111/111, panels113/113, context-menu
branches14/14.

BI dashboards: editor and viewer UI, 2026-10-28
-----------------------------------------------

The dashboard editor and viewer extend the same ``cdeadmin.bi`` module and
``bi.questions`` surface; there is no new surface, panel or engine branch.
The collection tree gains a dashboards section (create, rename, move,
archive, duplicate, search), the workspace has Edit and View modes, and
"Import monitoring dashboard" opens a DDN file through
``bi_dashboard_from_ddn`` as an unsaved draft. Layout, filter mapping,
cross-filter and drill-through logic are pure reducers with Jest specs
against fixtures generated from the real backend validators. Structure, state
model and gaps are in :doc:`bi_dashboard_ui`. No shared schema, form or family
renderer was edited. Lint before/after: JSON297/297, MUI244/244, UI engine
branches111/111, panels113/113, context-menu branches14/14.
