MySQL engine functional completion
==================================

Product-wide catalog, editor and complete native management acceptance is
defined in :doc:`six_engine_completion`. The scoped receipts below do not close
the open requirements recorded there.

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
  unavailable and zero metrics; retain a bounded volatile sample window and
  opt-in persistent history in the native ScratchBird archive. Historical reads
  require current owner/registration authorization, not an active collector or
  browser credential grant. Preserve exact values, epochs, metadata revisions,
  retention, rollups and ingestion gaps.

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

Implementation and qualification
--------------------------------

The October 16 implementation adds native server/security/storage DDN review
and application, typed relation-data DDN import, named durable test-data recipes
and MySQL persistent monitoring history. These complement the existing editor,
SQL history, database DDN and graphical design, backup/restore, maintenance,
dashboard/collector and connection ownership workflows.

Server DDN changes use explicit ``native.mysql_change`` instructions while the
captured facts remain immutable. The server UUID, registered endpoint, exact
native address, current section visibility and reviewed baseline are checked
before each statement. Missing selections never request deletion. Accounts,
role/default-role edges, global/database/table/column/routine grants, native
plugins/components, tablespaces, resource groups, selected system variables and
replication channels use engine-specific compilers. Authentication secrets are
excluded; new DDN accounts are locked and authentication is administered
separately. An unavailable account identity cannot authorize a privilege change.
Routine privileges use effective native ``SHOW GRANTS`` observations rather
than assuming private grant-table storage encoding identifies an account.

Server reviews expire after five minutes, persist each dispatched statement's
unknown state before I/O, retain the acknowledged prefix and stop on refusal,
unconfirmed replies or failed rediscovery. Native server operations are not an
atomic transaction; advisory locks coordinate ScratchRobin only. Recent receipts
can be reopened after restart. Repeated requests never dispatch again.

Data import reads the paired DDN public workspace contract and preserves native
column order, types, character sets, spatial SRIDs and invisible columns. It
retains explicit AUTO_INCREMENT values including zero, omits generated columns,
and binds exact integers, decimals, dates/times, JSON, opaque text, binary,
geometry and VECTOR data. VECTOR parameters explicitly use binary character
semantics without converting their float32 bytes. Import owns its transaction,
revalidates metadata while holding its metadata lock, commits explicitly and
independently rereads primary-key postimages. Native constraints/triggers remain
active. Nontransactional engines require an explicit acknowledgement and report
partial effects. Unknown COMMIT replies remain unknown. Imported rows disappear
from durable reviews before dispatch and never appear in public receipts.

Named test-data recipes use immutable project-asset revisions with owner,
endpoint and registered-database binding and optimistic version checks. Reading
a recipe, historical SQL or a DDN document never executes SQL. Human form
validation remains assigned to the UX team.

Reproducible gates (refresh DDN first; evidence belongs outside the repository)::

    python tools/cdeadmin_mysql_tasks_gate.py --output /work/mysql-tasks --ddn-work /work/ddn --mysqlsh /path/to/mysqlsh
    python tools/cdeadmin_mysql_catalog_completeness_gate.py --output /work/mysql-catalog
    python tools/cdeadmin_mysql_completion_gate.py --output /work/mysql-product
    python tools/cdeadmin_mysql_extended_gate.py --output /work/mysql-extended
    python tools/cdeadmin_monitoring_history_gate.py --config /etc/cdeadmin/history.json --engine mysql

The first four commands default to uniquely owned MySQL 9.7.0 Docker fixtures.
The product and extended gates also accept a credential-free ``--route`` JSON
and a ``--password-env`` variable for a disposable native estate. They qualify
both Connector/Python implementations. The native Windows/macOS fixture workflow
runs these portable consumers after the driver proof, retaining their separate
receipts. Native resource-group availability comes from the serving engine,
not the client operating system.

The physical clone workspace supports local and registered remote donors into a
new recipient-server directory. Remote reviews bind both native identities and
registrations, require explicit credential delegation, and preserve native TLS,
allowlist and privilege admission. Native completion, file verification and
independent recovery remain separate outcomes. Active-directory replacement,
production cutover and the wider physical continuity surface remain open.

The binary-log archive workspace integrates native MySQL Shell9.7
``util.dumpBinlogs`` on the explicitly recorded application host. It inspects
available logs and GTID lineage, reviews a native file/position or verified
previous archive, and records a durable claim before dispatch. New archives use
private owner/endpoint/job directories. Native none, gzip and Zstandard
compression, thread count and bounded or operator-permitted unbounded runtime
are exposed. The registered TLS policy and multi-factor credentials apply to
the utility's independent session; credentials travel in a private temporary
JSON file that preserves newline and Unicode passwords and is erased afterward.

Completed archives reconcile native completion metadata, source UUID, every
file's size/SHA256, streaming v4 event framing and CRC32 where the native log
contains checksums. Native checksum-disabled logs are identified explicitly.
Continuation stages an independent immutable input. A native no-op records no
new archive and never advances a continuation cursor. Restart/lost workers stay
unknown without replay; artifact verification does not assert process finality.
Receipts and paged file inventories remain available offline. Authenticated file
downloads verify retained bytes; explicit identity-confirmed removal keeps the
receipt. ``CDEADMIN_MYSQL_BINLOG_ROOT`` and
``CDEADMIN_MYSQL_BINLOG_MAX_RUNTIME_SECONDS`` are operator settings.

This closes the scoped GTID-enabled Shell archive workflow. Raw GTID-disabled
MySQL archives, native replay/PITR, continuous collection/retention and the
MariaDB binary-log workflow remain separate product requirements.

The consolidated administration gate covers all 105 declared tasks. Independent
catalog reconciliation compares 30 categories plus native DDN child facts for
privileged and restricted accounts and checks navigator reachability. These are
separate from broader product, browser and platform acceptance.

Persistent-history integration is wired. The owner correction of October 16
defers ScratchBird history testing until explicitly resumed. The earlier native
startup attempt failed its durable agent catalog seed with ``SECURITY.CONTEXT.EXPIRED`` / ``CATALOG_MUTATE`` before
archive SQL. No fallback database or security bypass is used. Windows/macOS
evidence remains with the platform teams and must match the final source before
cross-platform completion is claimed. Signing/release approvals remain separate.
