.. _mysql_wire_parity:

MySQL-wire engine parity
========================

Owner direction, 2026-10-29 (``AGENTS.md``, "Engine expansion to full
parity"): Dolt, TiDB and Vitess reach full functionality at the level of
MySQL and MariaDB, including their distinctive native features. Forms are
shared where possible and filtered per engine, so nothing is offered that the
engine does not directly support. This page records the live evidence for
that filter and the plan that follows from it.

Method
------

``tools/cdeadmin_mysql_wire_parity_probe.py`` runs a minimal native
statement sequence for each MySQL/MariaDB object kind and clause. It works in
a scratch database it creates and drops, or, for Vitess, in the existing
``test_keyspace`` keyspace. A probe passes only when every statement executes.
Retention probes then read ``SHOW CREATE TABLE`` back, because some engines
accept a clause and discard it.

Read the results with these limits:

-  Probes use MySQL syntax. A "no" can mean different syntax, not a missing
   feature. The MariaDB column shows this: its ``constraint-check``,
   ``index-invisible`` and ``index-spatial`` failures are MySQL-only syntax
   (``DROP CHECK``, ``INVISIBLE``, ``SRID``) for features MariaDB has.
-  A "yes" shows the statement ran. It does not prove the semantics match
   MySQL.
-  Results are for the pinned demo versions and their demo configuration
   (Dolt 1.86.6, TiDB 8.5.6, Vitess 23.0.3, MySQL 9.7.0, MariaDB 12.2.2),
   probed 2026-10-29. Server settings can change a result (see TiDB below).
-  The Vitess probe ran in the sharded ``test_keyspace``. Unsharded
   keyspaces allow more (see Vitess below).

Regenerate a column with the probe (password from
``CDEADMIN_PROBE_PASSWORD``), then refresh the table with
``tools/cdeadmin_mysql_wire_parity_report.py``. ``--check`` fails when the
table and the committed results differ.

Matrix
------

``yes``: executed. ``no (errno)``: refused with that native error.
``ignored``: accepted, but ``SHOW CREATE TABLE`` no longer shows it.

.. parity-matrix-start

==========================  ===========  ==============  ===========  ==========  =============
Probe                       mysql-9.7.0  mariadb-12.2.2  dolt-1.86.6  tidb-8.5.6  vitess-23.0.3
==========================  ===========  ==============  ===========  ==========  =============
analyze-table               yes          yes             yes          yes         yes
auto-increment              yes          yes             yes          yes         yes
binary-log                  yes          yes             yes          no (1064)   yes
charset-collation           yes          yes             yes          yes         yes
check-table                 yes          yes             no (1105)    no (1064)   no (1105)
column-generated            yes          yes             yes          yes         yes
component                   yes          no (1146)       no (1146)    no (1146)   yes
constraint-check            yes          no (1064)       yes          yes         yes
constraint-foreign-key      yes          yes             yes          yes         yes
constraint-unique           yes          yes             yes          yes         yes
database                    yes          yes             yes          yes         no (1235)
event                       yes          yes             yes          no (1064)   no (1105)
explain                     yes          yes             no (-1)      yes         yes
explain-analyze             yes          no (1064)       yes          yes         yes
flush-privileges            yes          yes             yes          yes         yes
function                    yes          yes             no (1105)    no (1064)   no (1105)
index                       yes          yes             yes          yes         yes
index-fulltext              yes          yes             yes          no (8200)   yes
index-functional            yes          no (1064)       no (1105)    yes         yes
index-invisible             yes          no (1064)       yes          yes         yes
index-spatial               yes          no (1064)       yes          no (1064)   yes
json-type                   yes          yes             yes          yes         yes
lock-catalog                yes          no (1146)       no (1049)    no (1146)   yes
lock-tables                 yes          yes             yes          yes         yes
optimize-table              yes          yes             no (1105)    no (8200)   yes
partition-hash              yes          yes             yes          yes         yes
partition-range             yes          yes             no (1105)    yes         yes
plugin                      yes          yes             yes          yes         yes
privilege                   yes          yes             yes          yes         no (1105)
procedure                   yes          yes             yes          no (8108)   no (1235)
replication-channel         yes          yes             yes          no (1235)   yes
resource-group-mysql        yes          no (1064)       no (1105)    no (1064)   no (1105)
resource-group-tidb         no (1064)    no (1064)       no (1105)    yes         no (1105)
retained-check              yes          yes             yes          ignored     yes
retained-fulltext           yes          yes             yes          ignored     yes
retained-generated-stored   yes          yes             yes          yes         yes
retained-index-invisible    yes          no (1064)       ignored      yes         yes
retained-partition-hash     yes          yes             ignored      yes         yes
retained-row-format         yes          yes             ignored      ignored     yes
retained-spatial            yes          no (1064)       yes          no (1064)   yes
retained-system-versioning  no (1064)    yes             ignored      no (1064)   no (1064)
retained-table-comment      yes          yes             yes          yes         yes
role                        yes          yes             yes          yes         no (1105)
savepoint                   yes          yes             yes          yes         yes
sequence                    no (1064)    yes             no (1105)    yes         no (1105)
server-link                 yes          yes             no (1105)    no (1064)   no (1105)
session                     yes          yes             yes          yes         yes
spatial-reference-system    yes          no (1109)       yes          no (1146)   yes
status-metric               yes          yes             yes          yes         yes
system-variable             yes          yes             yes          yes         yes
system-versioning           no (1064)    yes             yes          no (1064)   no (1064)
table                       yes          yes             yes          yes         yes
tablespace                  yes          no (1064)       no (1105)    no (1064)   no (1105)
temporary-table             yes          yes             yes          yes         no (1235)
trigger                     yes          yes             yes          no (1064)   no (1105)
user                        yes          yes             yes          yes         no (1105)
view                        yes          yes             yes          yes         no (1051)
xa                          yes          yes             no (1105)    no (1064)   no (1105)
==========================  ===========  ==============  ===========  ==========  =============

.. parity-matrix-end

Findings per engine
-------------------

Dolt 1.86.6
~~~~~~~~~~~

-  Silently discards hash partitioning, invisible indexes, ``WITH SYSTEM
   VERSIONING`` and ``ROW_FORMAT``. These must not be offered: the form would
   report success for a clause that has no effect.
-  Refuses stored functions, sequences, tablespaces, ``CREATE SERVER``, XA,
   ``OPTIMIZE TABLE``, ``CHECK TABLE``, MySQL resource groups and range
   partitions with ``MAXVALUE``. Has no ``performance_schema`` or
   ``mysql.component``.
-  The functional-index failure ("column could not be found") needs a second
   probe before it is treated as unsupported.
-  ``explain`` failed in the client ("Unread result found"), not in Dolt;
   ``EXPLAIN ANALYZE`` passed. Treat it as a probe defect, not evidence.
-  Supports triggers, events, procedures, users, roles and grants.
-  **Defect (Dolt 1.86.6, fixed in the provider 2026-10-29):** with system
   tables shown, ``information_schema.TABLES`` fails while the database has an
   uncommitted stored procedure ("dolt_procedures can not have conflicts
   because it is not updateable"). The provider's rebase check used that
   query, so the whole inventory failed for such a database. It now uses
   ``SHOW TABLES LIKE 'dolt_rebase'``, verified to find the table during an
   interactive rebase and not after it.
-  Generated-column expressions are not reported in
   ``information_schema.COLUMNS`` (``GENERATION_EXPRESSION`` is empty).

TiDB 8.5.6
~~~~~~~~~~

-  ``CHECK`` constraints depend on the global ``tidb_enable_check_constraint``
   (default ``OFF``). With it ``OFF`` they are accepted and discarded; with it
   ``ON`` they are kept and enforced (error 3819). Verified live, setting
   restored. The form must gate this on the server setting, not the version.
-  Silently discards ``FULLTEXT`` indexes and ``ROW_FORMAT``.
-  Refuses triggers, events, stored procedures and functions, spatial
   indexes, tablespaces, ``CREATE SERVER``, XA, ``OPTIMIZE TABLE``,
   ``CHECK TABLE``, MySQL resource groups and the binary-log and replica
   status statements.
-  Has sequences and its own resource groups (``RU_PER_SEC``), which MySQL
   lacks.
-  **Defect, fixed 2026-10-29:** TiDB lists ``CHECK`` constraints only in
   ``information_schema.TIDB_CHECK_CONSTRAINTS``; ``TABLE_CONSTRAINTS``
   omits them and the standard ``CHECK_CONSTRAINTS`` has no table name, so
   the inventory never showed them. It now reads TiDB's catalog.
-  ``CHECK`` with the setting OFF is now refused when applied, naming the
   setting, instead of being reported as created. An existing session sees
   a changed global setting (verified live).
-  Grants work on databases, tables, views and sequences; routine grants
   are refused (live). Passwordless users can be created and log in.
-  Native objects, verified live 2026-10-29 on PD + 3 TiKV + TiDB:

   -  **Defect, fixed:** ``ALTER PLACEMENT POLICY`` replaces every option.
      The provider sent only the edited ones, so changing followers dropped
      constraints, voters and survival preferences. Alter now starts from
      the policy's current options (the plan preview shows the full set). A
      change made by someone else after the policy was read can still be
      overwritten.
   -  Placement styles: region options (``PRIMARY_REGION``/``REGIONS``,
      ``SCHEDULE``) cannot be combined with label constraints or learners;
      followers, voters, voter constraints and survival preferences combine
      with either (every pair probed). The form shows one style at a time and
      the compiler refuses a mix. ``VOTERS``, ``VOTER_CONSTRAINTS`` and
      ``SURVIVAL_PREFERENCES`` are kept but absent from
      ``PLACEMENT_POLICIES``; the inventory reads them from ``SHOW CREATE``.
      The demo stores have no location labels, so region policies are
      accepted but cannot be scheduled there.
   -  **Defect, fixed:** ``ADMIN CANCEL DDL JOBS`` reports failure in a
      result row ("DDL Job:711 not found") instead of an error; the provider
      reported success. It now raises with TiDB's reason.
   -  **Defect, fixed:** DDL job state was lost (the shared record builder
      overwrote the ``state`` key); it is now ``job_state``.
   -  TiFlash replicas above the number of TiFlash servers are refused with
      the server count, before TiDB's own error (which the shared error
      policy hides). Setting 0 works.
   -  Added: resource-group runaway-query limits (``QUERY_LIMIT`` with
      DRYRUN/COOLDOWN/KILL, and removal); survival preferences; partition
      truncate, drop, analyze, exchange, reorganize and add. TiDB refuses
      CHECK/OPTIMIZE/REBUILD/REPAIR PARTITION (8200), so they are not
      offered. ``BACKGROUND`` settings apply only to the ``default``
      resource group.
   -  Records now carry placement policy and scheduling state on databases,
      tables and partitions; clustered or non-clustered primary key and
      row-ID sharding on tables; every policy and resource-group setting.
   -  Not run: TiCDC changefeeds and BR backup/restore (no TiCDC or BR in the
      demo); a successful DDL job cancel (needs a long-running job). Marked
      experimental, with the required component, in ``capabilities.json``.
      Update 2026-10-30, with the opt-in demo components (owner direction):
      changefeed create, pause, resume and remove, database BR backup and
      restore, and TiFlash replicas (replica available, query read through
      TiFlash) were verified live. Still not run: cluster BR restore (needs an
      empty cluster), point-in-time restore (needs a log backup), table-level
      BR, and a successful job cancel.
   -  **Defect, fixed 2026-10-30:** changefeed state was lost the same way as
      DDL job state; it is now ``changefeed_state``.
   -  **Defect, fixed 2026-10-30:** the TiDB guards (``CHECK`` refusal,
      TiFlash server count, job-cancel result) read the plan preview from the
      top of the request, but the visual-admin executor passes it under
      ``plan``, so in the real UI path they would not have run. The tests had
      used the raw plan; they now use the executor's request shape. A
      provider action reaching the SQL path without its plan, which would run
      nothing and report acceptance, is now refused.
   -  **Defect, fixed 2026-10-30:** resource-group alter filled in create-time
      defaults for untouched fields; it now sends only the supplied ones.
   -  TiFlash and the demo: Docker Desktop's VM has 8 GB here. Starting
      TiFlash beside three TiKV stores got stores OOM-killed, and a BR restore
      then failed because a store was down. ``dev.sh start tidb_tiflash`` now
      refuses below 12 GiB of Docker memory.
-  Distinctive features present (live) but not yet exposed: ``AUTO_RANDOM``,
   ``SHARD_ROW_ID_BITS``/``PRE_SPLIT_REGIONS``, TTL tables, cached tables,
   SQL plan bindings, ``FLASHBACK TABLE``, ``SPLIT TABLE`` regions, global
   indexes on partitioned tables, ``ADMIN CHECK TABLE``. Stale reads and
   table attributes need a re-probe (the probe table had been cached); SQL
   ``BACKUP`` needs storage every TiKV store can reach.

Vitess 23.0.3 (through vtgate, sharded keyspace)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  **Defect:** ``DROP VIEW IF EXISTS <keyspace>.<view>`` returns success but
   leaves the view on every shard; the unqualified form is refused ("no
   database selected", even after ``USE``). The provider's view drop uses
   the qualified form, so it reports success without dropping anything.
   ``vtctldclient ApplySchema --sql "DROP VIEW ..."`` does drop it, and the
   provider already has a typed vtctld control plane. Reproduced twice.
-  Refuses ``CREATE DATABASE`` through vtgate. Keyspaces are a control-plane
   concept.
-  Refuses users, roles and grants through vtgate. Authentication is
   vtgate's configured auth server; tablet MySQL accounts are separate.
-  Refuses stored procedures and temporary tables on sharded keyspaces
   (Vitess names the restriction). Unsharded keyspaces were not probed.
-  Refuses triggers, events, stored functions, sequences (Vitess sequences
   are VSchema-backed tables, not ``CREATE SEQUENCE``), tablespaces,
   ``CREATE SERVER``, XA and ``CHECK TABLE``.
-  DDL on a sharded keyspace reaches vtgate's schema tracking
   asynchronously. Read-after-write of the schema needs to wait.

Shared MySQL-wire catalog reader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  **Defect, fixed 2026-10-29:** index uniqueness was read with
   ``bool(NON_UNIQUE)``. TiDB returns ``'0'``/``'1'`` strings, so every TiDB
   index, ``PRIMARY`` included, was reported non-unique.
-  Columns were listed alphabetically, without defaults or key membership,
   and indexes without their columns, so an editor could not re-open an
   existing table. The reader now keeps definition order and reports
   defaults, key membership and index columns. Live on Dolt, TiDB and
   Vitess (2026-10-29).

Demo environment
~~~~~~~~~~~~~~~~

-  The Vitess demo's three Consul servers refused to restart after more than
   seven days stopped (``server_rejoin_age_max``, default 168h). The demo
   topology now raises the limit, and the existing cluster restarted on its
   old data.
-  ``dev.sh start`` returns before MariaDB and Dolt accept logins. The probe
   waits for them. Other callers may need the same wait.
   Fixed 2026-10-29: ``dev.sh start`` now waits for the MySQL protocol
   greeting for MySQL, MariaDB and Dolt (Docker's port proxy accepts TCP
   before the server listens).

Distinctive native features (already modelled by the providers)
---------------------------------------------------------------

==========  ====================================================================
Engine      Native kinds in the provider catalog today
==========  ====================================================================
Dolt        branch, tag, commit, remote, working-set, merge, rebase, conflict,
            backup
TiDB        cluster, node, placement-policy, resource-group, tiflash-replica,
            job, changefeed, backup, sequence, partition
Vitess      cluster, cell, keyspace, shard, tablet, vtgate, vttablet, vschema,
            vindex, routing-rule, workflow, vreplication-stream, materialize,
            online-ddl, sequence, backup
==========  ====================================================================

None of the three has a UI descriptor folder yet. They render through the
generic operation forms that ``ui_unified_design.rst`` decision 14 assigned to
non-beta engines before this direction.

Plan
----

#. Dolt first (single container, closest to MySQL), then TiDB, then Vitess.
   TiDB progress 2026-10-29: ``ui_descriptors/tidb`` exists; table, view,
   index, sequence, database and role forms are ``complete`` (live round
   trip in ``tools/tests/test_ui_descriptor_roundtrip_tidb.py``). Routine
   and trigger families are omitted (refused live). Open TiDB gaps: the
   grant dialog's privilege list is JSON; ``IDENTIFIED WITH`` an
   authentication plugin is not emitted; placement policies, resource
   groups, TiFlash replicas, DDL jobs and changefeeds use the provider's
   own dialogs (not yet descriptor forms).
   Dolt progress 2026-10-29: ``ui_descriptors/dolt`` exists. Table, view,
   index, trigger and routine forms are ``complete`` (live round trip in
   ``tools/tests/test_ui_descriptor_roundtrip_dolt.py``); role and database
   are ``draft``. Open Dolt gaps: database character set and collation
   (Dolt accepts them; the provider does not expose them), schema- and
   table-level grants in the inventory, trigger ordering, and creating
   passwordless users (owner decision).
   Later the same day: database character set and collation (create and
   alter), database- and table-level grants in the inventory, trigger
   FOLLOWS/PRECEDES, and passwordless users (owner direction: allowed on
   engines that support them; Dolt and TiDB through an explicit
   authentication mode) were added; all seven Dolt family forms are
   ``complete``. Remaining Dolt gap: the grant dialog's privilege list is a
   JSON field. One unexplained Dolt server exit was seen once during
   trigger probes and did not recur on the same statements.
   Correction, 2026-10-29: MariaDB 12.2.2 accepts several events per
   trigger (``BEFORE INSERT OR UPDATE``; MDEV-10164, fix version 12.0.1).
   Dolt does not (live). Both refuse ``INSTEAD OF``, which MariaDB's trigger
   form offered and no longer does.
#. For each engine, run the forms through the draft and review tools in
   ``ui_descriptors/README.md`` to make a descriptor folder. Reuse MySQL's
   field ids where the backend field is the same, and filter by this matrix.
   Kinds the engine lacks go to ``omitted_families.json`` with the evidence.
   Native kinds go on the Engine tab or as engine objects.
#. Add live round-trip tests (``CDEADMIN_ROUNDTRIP_DOLT`` / ``_TIDB`` /
   ``_VITESS``). A form becomes ``complete`` only after one passes.
#. Fix the Vitess view drop, and gate TiDB ``CHECK`` on
   ``tidb_enable_check_constraint``.
#. Fix the MySQL-wire registration defect from the 2026-10-29 smoke test:
   registration stores ``database_password_2`` / ``_3`` secret slots for these
   engines, and endpoint verify then fails.
   Fixed 2026-10-29: unsupplied optional credentials are no longer required.
   The same day, by owner direction, MySQL-wire and MariaDB connections gained
   an explicit **Passwordless account** switch. The Dolt, TiDB and Vitess demo
   accounts, which have no password, are registered with it.
#. Later and separately: replace the exact-profile pins with coarse version
   ranges, per the owner's rule of tracking only compatibility breaks.
