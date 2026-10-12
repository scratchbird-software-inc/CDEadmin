MySQL engine functional completion
==================================

The current target is native MySQL 9.7.0 with Connector/Python 26.7.0.
MariaDB is a separate engine and is not accepted as MySQL qualification.
This checklist governs completion alongside ``mysql_driver_development.rst``,
``ddn_database_roundtrip.rst`` and the shared navigation/form contracts.
Existing experimental provider receipts establish only their recorded scope.
Completion requires current source and live UI evidence for every item below.

Acceptance requirements
-----------------------

MYSQL-COMP-01: Native navigation and administration
  Discover server/database/schema objects and their native children. Preserve
  database/schema equivalence in MySQL rather than inventing an extra namespace.
  Cover tables, views, materialized views where admitted by the selected server,
  columns, constraints, indexes, partitions, triggers, routines, events,
  security, storage, plugins/components, replication and system configuration.
  Gate edition/version/privilege-dependent objects explicitly. Support native
  properties, creation, alteration, removal, dependencies and grants where
  supported. A missing privilege or failed discovery is not an empty catalog.

MYSQL-COMP-02: Connection ownership and credentials
  Explorer, active connection selector and SQL sessions agree on connected
  state and exact database. Support explicit connect/disconnect and independently
  owned sessions on two databases. Cover authentication, TLS, cancellation,
  pool lease retirement and uncertain outcomes without reconnect/replay.

MYSQL-COMP-03: Shared SQL editor and script tools
  Use the shared compact editor, engine-labelled connection selection, native
  language validation, completion, parameter binding, scripts and file tools.
  Provide bounded result pages, typed values, diagnostics, native JSON/analyze
  plans and honestly scoped timing. Observe native autocommit before enabling
  commit/rollback. Refuse a policy change with pending work. Preserve unknown
  outcomes. SQL history is optional, persistent and owner/server/database/native
  language scoped; loading text must never execute it. History failure cannot
  prevent or replay execution. Credentials, bound values and result rows are
  excluded; explicit sensitive-source suppression and bounded retention apply.

MYSQL-COMP-04: Data operations and maintenance
  Qualify native editing, commit/rollback, paging, exact values, LOBs, export,
  import and test data. Qualify database lifecycle, maintenance and native
  MySQL Shell backup/restore with rediscovery and independent verification.
  Describe implicit DDL commits and nontransactional engine effects accurately.

MYSQL-COMP-05: DDN roundtrip
  Capture selected objects, databases and server metadata/data on independent
  connections. Preserve native definitions, exact identifiers/types/options,
  dependencies, security and scope/permission observations. Expose DDN views
  through the sister project's tools. Generate native definitions and reviewed
  semantic diff/apply plans with target/digest/revalidation and rediscovery.
  View filtering never authorizes deletion. MySQL catalog reads do not imply
  an atomic DDL snapshot; partial observations cannot authorize destructive apply.

MYSQL-COMP-06: Monitoring and dashboards
  Provide engine/server/database display-only DDN dashboards and separately
  authorized dashboard editing. Collect on dedicated connections, using either
  registration credentials or configurable monitoring credentials. Configure
  heartbeat and sample/retention/lease policies. Refresh transaction scope for
  each sample; collection continues without an open viewer. Distinguish denied,
  unavailable and zero metrics; retain only a bounded volatile sample window.

MYSQL-COMP-07: Forms and routing
  Context menus must lead to engine-appropriate compact forms with stable form
  references. Share appropriate controls without exposing unsupported engine
  features. Use checkboxes/selectors/icon buttons and bounded navigable grids;
  keep destructive operations reviewed and exact-target scoped.

MYSQL-COMP-08: Qualification
  Run native and browser acceptance on the exact engine, including independent
  sessions/databases, restricted privileges, disconnect/cancel, native object
  lifecycle, backup/restore, DDN roundtrip/apply and collector credentials.
  Refresh consumed DDN before builds and commit qualification, preserve logs
  outside the repository and clean owned disposable fixtures. Unit tests or
  old activation gates alone do not establish full support.

Current-run exclusions
----------------------

Persistent monitoring history and its ScratchBird backend remain deferred by
owner direction. Windows/macOS work belongs to the platform teams. Persistent
SQL history, dashboard definitions and DDN native conversion are not deferred.
