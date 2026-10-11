Firebird forms: FlameRobin comparison and adaptation contract
************************************************************

Review basis
============

Reviewed 2026-10-10 against FlameRobin source revision
97358ac6e429c8f49217e6c67fd22825daf303d3 under
/home/dcalford/CliWork/flamerobin. Reviewed control construction, sizer layout,
menu/event handlers and selected native execution paths. This is a source-based
form review, not a pixel comparison against a running wxWidgets application.
Native Windows/macOS/Linux widget appearance differs even within FlameRobin.

ScratchRobin counterpart: /home/dcalford/Sandbox/CDEadmin, revision
5aab659c8d29f1cd52b824617ddeba08a5eb849a with ongoing uncommitted Firebird UI work.
This document specifies adaptation; it does not claim forms have been restyled,
built, deployed or functionally qualified. No build/test was run for this review.

Conclusion
==========

Replicate FlameRobin's information hierarchy, compact grouping, immediately
visible options and task-specific interactions in the React forms. Retain
ScratchRobin's current native provider contracts and additional supported
options. Use platform/theme-consistent controls rather than fixed wxWidgets
pixel dimensions. Do not replace DDN ERD/dashboard tools with FlameRobin's
visualization implementation.

The current shared renderer is
web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx:
VisualAdministration renders a vertical list of VisualAdminField controls;
multiselects appear as dropdowns. Firebird backup/restore and many object forms
already have native field contracts. Therefore presentation changes can reuse
those fields and handlers instead of implementing new drivers.

Form-by-form mapping
====================

Paths in the FlameRobin column are relative to src/gui/. 'Existing' means an
implementation path was located, not that every control has live parity proof.

.. list-table:: Forms and required adaptation
   :header-rows: 1
   :widths: 22 38 40

   * - FlameRobin source/form
     - Look and behavior to retain
     - ScratchRobin counterpart / remaining work
   * - ServerRegistrationDialog.cpp
     - Compact Display name, Hostname, Port rows; Register/Save and Cancel.
     - Existing endpoint connection forms. Keep engine identity and verification;
       apply aligned labels and compact geometry to the Firebird profile.
   * - DatabaseRegistrationDialog.cpp
     - Display name and database path; authentication, user/password, charset,
       role, key data and client-library controls; creation-only settings.
     - Existing database target and creation forms. Separate registration from
       physical creation. Keep server-side paths distinct from browser files;
       show only admitted native creation/authentication options.
   * - UsernamePasswordDialog.cpp
     - Small credential prompt with endpoint context, masked password and Connect.
     - Existing credential flow. Preserve transient/saved credential semantics;
       avoid replacing it with a generic administration panel.
   * - BackupFrame.cpp / BackupRestoreBaseFrame.cpp
     - Filename at top, visible option checkboxes, grouped execution/statistics
       settings, Start Backup and an output log below.
     - Existing backup_logical form. Reorganize its fields into file/options/
       selection/encryption/execution groups; preserve split-volume support.
   * - RestoreFrame.cpp / BackupRestoreBaseFrame.cpp
     - Backup input and destination; restore flags; page/cache/access settings;
       execution controls and output log.
     - Existing restore_logical form at SERVER scope. Preserve explicit target,
       multi-file support and replacement confirmation. Never require an existing
       attached database. Hide page sizes unsupported by the target version.
   * - Physical backup/restore equivalents
     - Same service-task family presentation, with native-specific controls.
     - Existing backup_physical/restore_physical forms. Keep backup level/GUID,
       chains, direct I/O and retention options; do not force these into gbak UI.
   * - ShutdownFrame.cpp / ShutdownStartupBaseFrame.cpp
     - Database-mode radio group, shutdown method and timeout; action/output.
     - Existing shutdown_database form. Render mutually exclusive modes/methods
       as explicit choices instead of ambiguous combinations of checkboxes.
   * - StartupFrame.cpp
     - Compact database-mode choice and action/output.
     - Existing bring_online form. Must remain available without database attach.
   * - MaintenanceFrame.cpp
     - Clear sweep/validation/repair/upgrade choices, related flags and workers.
     - Existing separate service operations. A common maintenance shell may share
       layout, but must retain each native operation's distinct options/confirmation.
   * - UserDialog.cpp
     - Identity/name fields, password plus confirmation, plugin and save/cancel.
     - Existing user operations in providers/firebird/users.py and administration.
       Add UI-only password confirmation where absent; never send it as a native
       field. UID/GID/plugin controls require actual provider support.
   * - PrivilegesDialog.cpp
     - Action and grantee groups, privilege checkboxes, column selectors, SQL
       preview and Add to list/Remove/Execute all statement queue.
     - Existing privilege/object-privilege/role operations. Reuse native planners;
       native queue and per-item receipts use SR-F-001373, specified below.
   * - CreateIndexDialog.cpp
     - Name, Unique, ascending/descending radio group, column list and WHERE.
     - Existing native index form. Use selectable ordered columns and condition
       editor; retain expression indexes and other supported options beyond FR.
   * - FieldPropertiesDialog.cpp
     - Column/domain/type controls with dependent size, scale, charset/collation,
       NOT NULL, identity and legacy generator/trigger settings.
     - Existing column/domain/identity forms. Use conditional native descriptors;
       domain editing navigates to its owner. Do not silently synthesize triggers
       when the user selected native identity.
   * - ReorderFieldsDialog.cpp
     - Ordered column list and First/Up/Down/Last buttons, followed by SQL review.
     - POSITION backend already exists; add a whole-table ordering form and
       explicit ordered apply plan rather than rewriting the driver.
   * - MetadataItemPropertiesFrame.cpp / html-templates
     - Object-specific summaries, DDL, columns, constraints, indexes, triggers,
       dependencies and privileges, with links to related objects.
     - Existing object inspector/owner-section tabs. Improve property layouts;
       absent detail sections must not masquerade as empty native metadata.
   * - InsertDialog.cpp
     - Typed per-column grid, explicit NULL/default behavior and Insert another.
     - Existing row editor/typed inputs. Adapt compact input grid and repeat-insert
       workflow without resetting native transactions or conflating omitted/NULL.
   * - InsertParametersDialog.cpp
     - Parameter name/type/value grid, NULL control and Execute/Run.
     - Existing query/routine parameter support. Add metadata-driven parameter
       dialog where only serialized inputs exist; preserve exact native types.
   * - EditBlobDialog.cpp
     - Dedicated text/binary views, file load/save, NULL and line-ending controls.
     - Existing Firebird streaming and typed values. Add a focused dialog using
       those APIs. FR's binary pane is read-only, not proof of a hex-edit facility.
   * - ExecuteSqlFrame.cpp
     - Editor with toolbar, transaction controls, data/log/statistics/profiler
       views and split-view execution feedback.
     - Existing provider workspace and native script/plan/stream components.
       Editor completion/formatting, profiler and query-statistics work remains
       as recorded in firebird_functional_completion.rst.
   * - StatementHistoryDialog.cpp
     - Search row, dated statement list, SQL preview, copy/open/delete actions.
     - New persistent history workflow; current bounded event/result history is
       insufficient. Preserve user/database/dialect scope.
   * - FindDialog.cpp
     - Find/replace fields, search options and predictable keyboard navigation.
     - Bind shared editor search to the Firebird editor; avoid a separate SQL
       parser or text buffer that diverges from the active session.
   * - AdvancedSearchFrame.cpp
     - Criteria list, selected databases, result list and definition preview.
     - Reuse shared search presentation with new Firebird catalog integration;
       inherited PG_DEFAULT_DRIVER search is not an equivalent implementation.
   * - EventWatcherFrame.cpp
     - Named-event list with Add/Remove/Load/Save and Start/Stop; received log.
     - New native event subscription service/form. FR's IBPP path requires
       qualification with its current backend; do not port that dependency.
   * - DataGeneratorFrame.cpp
     - Tables/columns left, recipe editor right; row counts, ranges/masks, source
       columns/files, NULL percentage, copy settings and save/load/generate.
     - New generator workflow over existing native execution contracts. Need
       constraint-aware planning, cancellation and actual outcome reporting.
   * - CreateDockerFirebirdDialog.cpp
     - Explicit container/image/host-port configuration and create action.
     - New product form and provisioning boundary; developer demo scripts are
       not the end-user implementation. Define which machine runs Docker.
   * - ReplicationStatusFrame.cpp
     - Compact property/value status with Refresh and periodic refresh.
     - Use real provider observations and DDN dashboard display. FR currently
       inserts simulated status values; none may be copied as real telemetry.
   * - SchemaVisualizationFrame.cpp
     - Related tables/columns/keys with navigable context.
     - Use DDN display/editing and the bidirectional contract in
       ddn_database_roundtrip.rst, not FlameRobin's embedded HTML renderer.
   * - PreferencesDialog.cpp / ShortcutCustomizationDialog.cpp
     - Categorized preferences and searchable command/shortcut assignment.
     - Reuse application preferences and command registry; review active
       Firebird action coverage and shortcut conflicts across platforms.
   * - ProgressDialog.cpp / ServiceBaseFrame.cpp
     - Task title, useful progress, output, finish/failure state and close action.
     - Reuse native operation-result/lifecycle components. A spinner is not a
       measured percentage; closing a form is not cancellation or rollback.
   * - AdvancedMessageDialog.cpp / MultilineEnterDialog.cpp / SimpleHtmlFrame.cpp
     - Clear consequence/confirmation text, multiline input and help/preview.
     - Reuse shared confirmation/input/help surfaces with native object context
       and stable form references; these need no separate provider implementation.

First concrete adaptation: backup and restore
============================================

Use a compact modal/workspace layout with a fixed contextual heading (engine,
server, database where applicable), stable SR-F reference, responsive field
rows, visible native option groups, action row and resizable output region.
On narrow windows groups stack without losing labels or keyboard access.
Do not introduce a fresh operation selector when a tree action already selects
one exact operation.

For ``firebird_backup_logical`` preserve these existing field IDs and bindings:

* Files: split_backup, backup_file, backup_volumes.
* Backup options: backup_flags, displayed as a labelled checkbox group using
  the provider's actual options/values and defaults, not copied flag constants.
* Data selection: skip_data, include_data.
* Execution/output: parallel_workers, statistics, verbose, verbose_interval.
* Encryption/authentication: key_holder, key_name, crypt_plugin, role.

For ``firebird_restore_logical`` preserve:

* Source: backup_file, additional_backup_files.
* Destination: restore_database, multiple_database_files, primary_file_pages,
  database_file_volumes and replace_existing.
* Restore options: restore_flags as visible native checkbox choices.
* Database properties: page_size, page_buffers, access_mode, replica_mode.
* Execution, filtering and encryption: the same existing named controls as above.

Advanced groups may collapse only with a clear indication of non-default values.
Conditional fields still obey provider visibility and validation. Never drop
unknown/new provider fields from the form: surface them in a labelled additional
native-options section until they receive a specific layout.

Use Preview and task-specific execution labels such as Start backup / Start
restore while retaining the existing plan/confirmation lifecycle. A changed
field invalidates the previous plan. Preserve destructive replacement warnings,
field validation, native output and the existing close-while-running guard.
File selectors must distinguish browser upload/download from server-side paths;
a local desktop browse button cannot be transplanted into a remote web dialog.

Review and acceptance
=====================

Implement layouts as Firebird presentation profiles over existing field
contracts and callbacks. Keep other engines' forms intact. Static form reference
numbers continue identifying the same form wherever reused. Preserve native
option supersets rather than reducing ScratchRobin to the reference form's
older options or disabled controls.

Per form verify control-by-control mapping, defaults, conditional visibility,
keyboard focus/tab order, narrow-window layout, actual submitted native values,
invalid inputs, permissions, running/failed/unknown outcomes and tree refresh.
Password fields must stay masked and out of logs. Check Windows/macOS/browser
presentation with the UX/platform teams; source review does not prove pixels.

Current implementation increment
================================

Firebird engine catalogs and explicitly identified ``firebird_*`` native forms
now render through a compact presentation profile, including dynamically
supplied native object forms. Files/destination, options,
database settings, selection, encryption/authentication and execution/statistics
are visible groups. Native multiselects render as checkbox groups; shutdown and
online modes/methods are exclusive radio choices. Array/record controls retain
their existing editing semantics. Unmapped fields remain visible under
Additional native options. Existing form references, conditional fields,
validation, preview invalidation and confirmation/apply behavior are retained.
Password fields require a matching UI-only confirmation before preview/apply;
the additional value is never submitted as a native provider field.

This increment does not claim all the form-by-form workflows above are complete.
Later increments below supersede this baseline for focused dialogs, the
privilege queue and table ordering. Platform UX qualification remains with the
platform teams; native workflow acceptance follows the owning completion list.

Before any subsequent build or commit-validation run, perform the required DDN
refresh and public API migration checks in AGENTS.md. This review itself changes
only the adaptation contract, not the running test server or rendered forms.

Firebird workflow form routing
=============================

The following additional forms have stable references in the shared form
registry. They are reachable through a Firebird workspace, preserving its
server/database context; other engines do not expose these controls.

* SR-F-001360: dedicated BLOB editor from a native grid BLOB field. Text/binary
  file controls, NULL/empty mode, line endings and explicit staging reuse the
  row editor's save and transaction lifecycle. Read-only objects permit viewing.
* SR-F-001361: registered-database metadata search from the workspace's Search
  database metadata control. Select databases and criteria, inspect bounded
  results/coverage, then open the exact native object in its own scoped form.
* SR-F-001362: selected-row SQL previews in Edit Data. Select fetched rows,
  operation and matching columns, then inspect/copy SQL and ordered parameters
  or load one statement into the SQL editor without running it.
* SR-F-001363: native event monitor from Monitor database events. Edit or
  load/save event names, subscribe/stop, view exact counts and a bounded received
  observation log, and save that log separately. Release/gap state is visible.

These controls use the owning contracts in firebird_functional_completion.rst.
The mapping itself is not acceptance evidence for the remaining parity backlog.

Constraint-generated trigger ownership
--------------------------------------

An inspected trigger with native ``constraint_owner`` belongs to that constraint's
lifecycle. Its native properties and dependencies remain inspectable, but direct
trigger mutation/replacement is refused by both administration validation and
compilation. The refusal names the constraint. User triggers are not classified
by name prefix, source spelling or a NOT NULL field-name collision. Arbitrary
SQL remains subject to the engine's native permissions and metadata rules.


Firebird privilege statement queue
----------------------------------

SR-F-001373 adds provider-prepared GRANT/REVOKE plans to an ordered,
connection-scoped queue. Each item shows its native SQL and exact target; items
can be removed before execution. Editing the next form does not change queued
plans. Changing the connection invalidates the queue. The provider retains its
normal plan expiry, identity, authorization and single-use checks.

Execute all requires explicit confirmation and submits each original plan once,
in order, through the existing database-bound administration interface. The
queue is retired before dispatch. Execution stops on a failed, unknown or
unaccepted response or a connection-context change. Receipts distinguish returned
native responses, unknown outcomes and unattempted items; no automatic retry or
batch atomicity is claimed. Caller-owned transactions remain caller-owned and
must be committed or rolled back through their session. Metadata refresh failure
does not repeat execution. Closing the task is deferred while execution runs.


Database security collection routing
------------------------------------

Manage users, roles, and grants/privileges from a Firebird database retain that
database's registered connection target. They open a native object collection,
not an object identified by the registration UUID. Selected object actions still
carry the actual provider-native resource identity; collection routing must not
weaken missing-object rejection for those actions.

The grants/privileges collection opens the native Grant form initially because
it has no independent catalog privilege object to inspect. Revoke remains an
explicit sibling operation with its own required grantee confirmation.

Prepared native parameter editor
--------------------------------

SR-F-001374 supplements the positional JSON binding field with a compact native
parameter grid. Prepare parameters uses the existing prepare-only query path in
the selected SQL session and dialect; it never executes the statement or ends
pending user work. Native IMessageMetadata supplies ordered positions, available
relation/field names, type codes/names, subtype, byte length, scale, charset and
nullability. No names or types are inferred by counting question marks in text.

The descriptor receipt carries the prepared source's SHA-256 and dialect. The
grid is usable only for that exact current source/dialect and shows at most 512
parameters; the full count and an explicit incomplete status remain visible for
larger statements. Initializing/replacing bindings requires an explicit action.
NULL and empty values remain distinct. Integer/decimal values stay exact text,
Boolean values stay Boolean, binary values use the existing strict base64
envelope, and native time-zone/float envelopes retain their existing validation.
Unsupported structured input types retain an explicit per-value JSON editor.
Applying grid values changes only the binding draft; normal Run performs the
existing native execution and transaction workflow. Invalid or stale drafts do
not overwrite the positional bindings. Parameter values are not added to SQL
history or preparation telemetry.

DDN catalog, relational and server capture forms
-----------------------------------------------

SR-F-001375 edits complete catalog DDN through the paired DDN tool and hands the
authored native facts to SR-F-001371 for explicit preview/review/application.
Catalog and SR-F-001365 relational designs expose distinct named save/load
controls backed by immutable project-asset revisions. Prior revisions retain
their original baseline; concurrent saves require reloading the current version.
Explicit native refresh preserves authored source or reports a merge conflict.
The relational form also prepares catalog review from its original and edited
native definitions; it never executes diagram labels as SQL.

SR-F-001376 is reached from the Firebird server context menu. It captures selected
registered database catalogs, displays their actual registration names, and
provides a DDN overview plus individual database views/downloads. Failed targets
remain visible, and the result is explicitly an independently observed catalog
bundle rather than an atomic backup or cross-database deployment plan.

The monitoring detail form ``SR-F-001377`` is linked from server/database
read-only dashboards. It offers explicit server path/log reads or native-visible
security account inspection according to scope. SQL/plan inspection, including
compiled statements, shares ``SR-F-001372`` and remains a separate request from
periodic collection. These forms contain no execution or administration actions.
