MariaDB engine functional completion
====================================

The native qualification target is MariaDB 12.2.2 with the patched MariaDB
Connector/Python 1.1.14 described in ``mariadb_driver_development.rst``. MySQL
qualification is not MariaDB qualification. This contract supplements that
native driver contract, ``ddn_database_roundtrip.rst`` and shared navigation,
compact form, SQL editor and dashboard contracts. Existing driver receipts
establish their recorded scope only; completion requires current implementation
and native/browser acceptance of each requirement.

Acceptance requirements
-----------------------

MARIA-COMP-01: Native navigation and administration
  Discover server and database objects and their native children. Database and
  schema identify the same native namespace. Cover tables, views, sequences,
  columns, constraints, indexes, partitions, triggers, procedures, functions,
  packages and package bodies, events, accounts, roles, grants, storage engines,
  plugins, server links, replication, system variables, sessions and logs.
  Preserve system-versioned tables, application-time periods, partitioning,
  generated columns, exact native types/options and SQL-mode-dependent syntax.
  Gate features against observed server version, installed engines, SQL mode,
  privilege and edition. Do not expose MySQL components, JavaScript libraries,
  MySQL Shell or MySQL materialized views as MariaDB features. Discovery failure
  or denied metadata must not appear as an empty successful catalog.

MARIA-COMP-02: Connections and native ownership
  Explorer, active connection selection and SQL sessions agree on exact engine,
  endpoint and database. Provide explicit connect/disconnect, independently
  owned database sessions, native authentication and TLS, cancellation and pool
  generation retirement. Do not reconnect or replay established native work.
  Socket loss is not proof of commit or rollback. Preserve uncertain outcomes
  and require explicit reconciliation before issuing replacement work.

MARIA-COMP-03: Shared SQL editor and scripts
  Use the shared compact SQL editor with engine-labelled connections, native
  language/SQL-mode validation and completion, exact parameter binding, script
  boundaries, file tooling, bounded result pages and diagnostics. Expose native
  EXPLAIN and ANALYZE options and honestly scoped preparation/dispatch/fetch
  timing. Observe native autocommit and pending transaction state before policy
  changes; disable commit/rollback when native autocommit is on. Do not infer
  transactional rollback for implicit DDL commits or nontransactional tables.

  SQL history is optional and persistent, isolated by owner, endpoint,
  registered database target, engine and ``mariadb-sql`` language. Capture is
  disabled by default, bounded by record count/retention and omits bound values,
  results, explicit sensitive source, credential URIs and native authentication
  clauses including IDENTIFIED VIA, WITH and BY. Loading history only changes
  editor text. Store failure never blocks or retries native execution. History
  request observations never assert native transaction finality.

MARIA-COMP-04: Data, lifecycle and native maintenance
  Qualify native row editing, commit/rollback, bounded navigation, exact values,
  large objects, import/export and test data. Qualify database lifecycle,
  maintenance and separately installed MariaDB backup/restore executables with
  review, exact target checks, rediscovery and independent verification. Native
  MariaDB dump/restore behavior must not be substituted by MySQL Shell behavior.

MARIA-COMP-05: Native DDN roundtrip
  Capture selected objects, databases, server metadata and selected data using
  independent connections. Preserve exact identifiers, definitions, SQL modes,
  character sets, native type details, temporal clauses, sequence/package
  identities, dependencies, security and incomplete/denied observations. Use the
  sister project's renderer/designer. Generate native metadata and explicit
  reviewed diff/apply plans with target/digest/baseline validation, bounded
  receipts and rediscovery. View filtering and incomplete discovery are never
  deletion intent. Do not claim catalog reads are an atomic DDL snapshot or
  translate MySQL-only grammar into a MariaDB deployment.

MARIA-COMP-06: Dashboards and dedicated monitoring
  Provide engine/server/database display-only DDN dashboards with separately
  authorized dashboard editing. Use dedicated collector connections, selectable
  registration credentials or dedicated monitoring username/password/role,
  optional heartbeat and sampling/retention/lease policies. Refresh transaction
  scope every sample and continue collection without a viewer. Distinguish
  unavailable, denied and zero measurements. Retain bounded volatile samples.

MARIA-COMP-07: Contextual compact forms
  Route native tree items to engine-appropriate information/forms with stable
  form references. Share controls where appropriate without hiding supported
  MariaDB functionality or showing unsupported options. Use compact selectors,
  checkboxes, icon actions and navigable grids. Mutations require explicit
  review and exact selected-target authorization.

MARIA-COMP-08: Qualification and cleanup
  Qualify current source against native MariaDB, including independent
  sessions/databases, restricted privileges, cancellation/disconnection, native
  object lifecycle, backup/restore, DDN conversion/diff/apply and monitoring
  credentials. Refresh DDN before each build/commit qualification and run
  immutable captured inputs. Preserve evidence outside the source tree and
  remove owned disposable fixtures. MySQL receipts, static inventories, unit
  tests and old activation gates alone do not establish full MariaDB support.

Current-run exclusions
----------------------

Persistent monitoring history and its ScratchBird backend remain deferred.
Windows/macOS work and platform QA belong to the separate platform teams.
Persistent SQL history, dashboard definitions, recipes and native DDN conversion
are in scope. MariaDB completion does not authorize starting DuckDB.
