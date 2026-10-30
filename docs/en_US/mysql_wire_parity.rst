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
   Fixed 2026-10-30: the view drop runs ``ApplySchema`` through vtctld;
   verified live that the view is gone from both shards.
-  Refuses ``CREATE DATABASE`` through vtgate. Keyspaces are a control-plane
   concept.
-  Refuses users, roles and grants through vtgate. Authentication is
   vtgate's configured auth server; tablet MySQL accounts are separate.
-  Refuses stored procedures and temporary tables on sharded keyspaces
   (Vitess names the restriction). Unsharded keyspaces were not probed.
   Probed 2026-10-30 on the unsharded ``lookup_keyspace``: ``CREATE`` and
   ``DROP PROCEDURE`` (qualified with the keyspace) and ``CREATE TEMPORARY
   TABLE`` work. ``CALL`` works for a procedure without a result set; one
   that returns rows fails (vttablet: "Multi-Resultset not supported").
   vtgate re-renders the procedure text before storing it (keywords come
   back lowercased). ``information_schema.ROUTINES`` answers only with a
   ``ROUTINE_SCHEMA`` predicate naming the keyspace; otherwise vtgate reads
   the session keyspace.
-  Refuses triggers, events, stored functions, sequences (Vitess sequences
   are VSchema-backed tables, not ``CREATE SEQUENCE``), tablespaces,
   ``CREATE SERVER``, XA and ``CHECK TABLE``.
   Sequences probed 2026-10-30: a ``vitess_sequence`` backing table plus
   ``ALTER VSCHEMA ADD SEQUENCE`` works in the unsharded keyspace, and
   ``ALTER VSCHEMA ON ks.t ADD AUTO_INCREMENT col USING ks.seq`` makes
   inserts draw ids from it (three inserts drew 700-702 and the backing row
   moved to 710, one cache block). On a sharded keyspace ``ADD SEQUENCE``
   fails ("unsupported on sharded keyspace") after ``CREATE TABLE`` has
   already succeeded, so the provider refuses before running anything.
-  **Defect (provider, fixed 2026-10-30):** vtgate reads
   ``information_schema`` for the keyspace an equality predicate on the
   schema names, and otherwise for the session keyspace only; an ``IN``
   list of keyspaces returns no rows and no error. The catalog read without
   a predicate, so tables, columns, indexes, constraints, views, partitions
   and sequences outside the connection's keyspace were never listed
   (sequences, which must live in an unsharded keyspace, never appeared at
   all). The shared reader now takes one schema, and the Vitess catalog
   reads each keyspace with an equality predicate.
-  Qualified VSchema DDL (``ALTER VSCHEMA ON ks.t``, ``DROP TABLE ks.t``,
   ``DROP SEQUENCE ks.s``, ``DROP VINDEX ks.v``) reaches any keyspace from
   any session (verified through vtctld ``GetVSchema``). The unqualified
   form acts on the session keyspace. The provider used the unqualified form
   for table VSchema registration and refused drops outside the
   connection's keyspace; both now use the qualified form.
-  ``ALTER VSCHEMA CREATE VINDEX`` in an unsharded keyspace that already
   has tables fails ("missing primary col vindex"); the vindex editor
   creates in the connection's keyspace only.
-  ``SHOW VSCHEMA TABLES`` also reflects schema tracking, and the VSchema
   change shows there after a delay; vtctld ``GetVSchema`` is the source
   for what the VSchema holds. vtgate's ``/debug/vschema`` names an attached
   sequence without its keyspace, so attachments are read from vtctld.
-  **Defect (provider, fixed 2026-10-30):** vtgate stores a single-quoted
   ``ALTER VSCHEMA ... WITH`` value with its quotes (``table`` became
   ``'lookup_keyspace.t'``), so a lookup vindex created through the vindex
   editor or the table form could not find its lookup table. Unquoted and
   backtick-quoted values are stored bare; the provider now backtick-quotes.
   Live test: a lookup vindex made in the editor, owned by a sharded table,
   is filled on insert and routes a query by its column to one shard.
-  ``ALTER VSCHEMA ON t ADD AUTO_INCREMENT col USING ks.seq`` succeeds for a
   sequence that does not exist. Dropping a table's last vindex removes the
   table from the VSchema (with anything else on its entry, such as an
   attached sequence).
-  ``ApplyVSchema`` accepted a reference table whose source is not in the
   source keyspace's VSchema; vtgate then reports the whole keyspace's
   VSchema in error (``/debug/vschema``) while still answering queries.
   ``--dry-run`` accepts it too.
-  Routing rules (probed 2026-10-30): ``ApplyRoutingRules`` accepts a rule
   with two target tables, but vtgate then refuses to route that table
   ("has more than one target"; visible in ``/debug/vschema``). The
   provider now refuses such a rule before running. An unqualified rule
   source applies only to sessions with no keyspace selected; from a
   keyspace session the source must be ``keyspace.table``. A rule whose
   source is in the unsharded ``lookup_keyspace``, queried unqualified from
   a ``lookup_keyspace`` session, had its table name rewritten but was sent
   to the session keyspace and failed; the qualified query worked.
-  **Defect (provider, fixed 2026-10-30):** ``vtctldclient GetRoutingRules``
   prints ``from_table``/``to_tables`` while ``ApplyRoutingRules`` takes
   ``fromTable``/``toTables``. The provider's post-state check compared the
   two shapes, so it could never confirm a routing-rule change; it now
   reads both.
-  DDL on a sharded keyspace reaches vtgate's schema tracking
   asynchronously. Read-after-write of the schema needs to wait.
-  ``ALTER VIEW`` through vtgate does reach every shard (live, 2026-10-30),
   unlike ``DROP VIEW``.
-  A ``UNIQUE`` key that is not on the primary vindex is enforced within
   each shard only: two rows with the same value were accepted, one per
   shard (live, 2026-10-30). The table form offers unique constraints
   because vtgate accepts them; the guarantee is per shard.
-  The demo keyspaces run ``foreignKeyMode: unmanaged`` (vtgate leaves
   foreign keys to each shard). Foreign keys were not round-tripped.
-  vtgate's ``SHOW VITESS_KEYSPACES`` kept listing a keyspace after vtctld
   deleted it, and omits keyspaces and shards without serving tablets. The
   provider now takes keyspaces and shards from vtctld when it is
   configured (2026-10-30). Cause of the stale listing: ``DeleteKeyspace``
   leaves the keyspace in each cell's ``SrvVSchema``, which vtgate serves
   from. The provider's keyspace drop now runs ``RebuildVSchemaGraph``
   afterwards, and the round trip checks that vtgate forgets the keyspace.
-  Driver errors reach the user redacted ("relational administration
   execution failed (ProgrammingError)"), so vtgate's VT12001 text is never
   shown. The provider refuses a procedure on a sharded keyspace before
   executing, with the reason.

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
Update 2026-10-30: all three now have descriptor folders (see Plan).
Vitess also gained ``procedure`` (unsharded keyspaces).

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
   Vitess progress 2026-10-30: ``ui_descriptors/vitess`` exists. Table
   (with its primary vindex), view, routine (procedures, unsharded
   keyspaces only), and the keyspace, shard and vindex engine-object editors
   are ``complete`` (live round trip in
   ``tools/tests/test_ui_descriptor_roundtrip_vitess.py``); index and
   sequence are ``draft``. Index and sequence became ``complete`` later on
   2026-10-30: index create and drop checked on every shard; sequence
   create, reopen (next value and cache), alter and drop, plus the table
   form's sequence-filled column, which a live insert draws ids from. Database, trigger and role families are omitted
   with live evidence; type is omitted because the MySQL dialect has no
   user-defined types (not a live probe). Records now carry keyspace sharding and
   durability, shard key range and primary, tablet serving state (renamed
   from ``state``, which the shared record builder overwrote), table
   vindexes, constraint columns and references, and view queries rewritten
   from the physical ``vt_`` schema to the keyspace. Workflow, reshard and
   traffic operations take cell, table and shard lists as rows instead of
   JSON, and keyspace and tablet pickers. Open Vitess gaps: the routing
   rules dialog is still the provider's JSON field (removed from the
   descriptor operations until a rules grid exists); the routine form's
   keyspace picker cannot yet filter out sharded keyspaces (descriptor
   reference fields have no record filter, front-end follow-up);
   ApplyVSchema and online DDL submission (``ddl_strategy``) are not
   exposed; tablet backup and restore were not run live. Also open: the
   sequence picker has the same sharded-keyspace filter gap, and the
   table's sequence is a ``keyspace.sequence`` text field because a
   reference picker cannot yet carry the keyspace; attaching or detaching a
   sequence (like changing the primary vindex) is create-time only; the
   three-statement sequence create is not atomic (a failure after the
   backing table leaves the table behind).
   Routing rules have an engine-object editor since 2026-10-30 (``complete``,
   live round trip): Vitess replaces the global rule set whole, so the
   editor reopens with the current rules and its alter sends the edited
   set; one target per row. The JSON ``apply`` operation remains for the
   legacy dialog. The shared ``OperationDialog`` now sends values in the
   provider's own shapes (string grids as plain lists); it is not yet
   mounted by any host. **Correction (2026-10-30, later the same day):**
   that was wrong. ``web/pgadmin/browser/static/js/ProviderObjectEditor.jsx``
   already opened it for tier 2/3 operations from the object tree, so the
   list-field bug was reachable in the app. The same review found the
   dialog received no option context, so every reference picker and
   dialect list in it was empty; it now gets the editor's context plus the
   target resource. Reference fields gained ``reference_value`` (what the
   picker sends; tablet aliases, backup names and TiDB's exchange table send
   the bare name instead of the dotted path), ``reference_filter``
   (procedure and sequence keyspaces offer unsharded keyspaces only; a
   keyspace whose sharding is unknown is not offered) and
   ``reference_scope`` (restore offers the target tablet's own keyspace and
   shard backups; reparent offers the shard's own tablets).
   Also 2026-10-30, live: tablet backup and restore ran (a ``lookup_keyspace``
   replica backed up, restored from that named backup, back to serving as a
   replica; the replica's log shows the restore used the requested
   timestamp), and the backup deleted. Online DDL submission is exposed on
   table alter (``ddl_strategy`` direct, vitess or mysql, with postponed
   launch and cut-over); a migration was submitted with both postponed,
   launched, completed, and the column checked on every shard. Both
   ``vitess`` and ``mysql`` strategies were probed and return a migration
   id. Remaining: ApplyVSchema is not exposed; the catalog keeps one record
   per migration although ``SHOW VITESS_MIGRATIONS`` has a row per shard, so
   a migration's status is one shard's (fixed the same day: the record now
   carries each shard's status, progress and readiness, and reports one
   status only when every shard agrees, otherwise ``mixed``); the backup
   timestamp on restore is text, not a backup picker (restore now picks
   from the target tablet's own shard backups, later the same day).
   Structured VSchema editing (2026-10-30, live round trips):

   -  A keyspace VSchema editor (``engine_object:vschema``) edits the
      sharded flag, foreign key mode, explicit routing, tables (normal,
      reference with its source, sequence, pinned, sequence column), each
      table's vindexes in order (the first is the primary) and the
      keyspace's vindexes with parameters and owner. Vitess replaces a
      keyspace's VSchema whole, so the provider reads it at execute time,
      replaces only the sections sent, keeps what the editor does not show
      (column lists), refuses a sent section changed since the editor
      opened (vtctld has no compare-and-set), refuses what vtctld accepts
      but vtgate cannot serve (missing reference source or sequence,
      undefined vindex, sharded table without placement, unsharding a
      multi-shard keyspace), applies in one ``ApplyVSchema``, and confirms
      vtgate serves the keyspace without error.
   -  The VSchema travels as one command-line argument because the tool may
      run where host files are not visible; above 128 KiB (Linux
      ``MAX_ARG_STRLEN``) the edit is refused with that reason.
   -  The routing rules editor also edits keyspace and shard routing rules
      (``ApplyKeyspaceRoutingRules``, ``ApplyShardRoutingRules``; input in
      camelCase, printed in snake_case, like table rules). vtctld accepted a
      shard rule for a shard the target keyspace lacks; the provider refuses
      it. A keyspace rule may name a keyspace that does not exist; its
      queries then go to the target (verified).
   -  Mirror rules are shown read only: vtctld has no command to apply them
      (MoveTables mirrortraffic sets them). Their row fields follow the
      Vitess MirrorRule message and have not been seen with live data.
   -  Setting ``sharded`` on a keyspace whose tables lack a primary vindex
      is refused by vtctld itself; unsharding a two-shard keyspace passed
      vtctld's dry run, so the provider refuses it.
   -  The table editor's VSchema fields (primary vindex, sequence column)
      remain create-time; alter-time table vindex and sequence edits live in
      the keyspace VSchema editor. The vindex editor still creates in the
      connected keyspace; vindexes of other keyspaces are edited in their
      keyspace's VSchema editor.
#. Correction 2026-10-30 to the ``complete`` table forms of Dolt, TiDB and
   Vitess: in alter mode an edit to an existing column's type, default,
   nullability or key flags was not sent (the column diff carried only add,
   drop and rename), and an edit to a constraint grid was sent but ignored
   by the shared table alter. Beside an added column both were lost without
   an error. Now the diff sends them as ``alter_columns`` and the shared
   alter refuses ``alter_columns`` and constraint edits with the reason, so
   nothing is dropped silently; applying them on these engines is open
   work. The forms stay ``complete`` for what their round trips check.
   The same day the parity engines joined the beta-engine gate lists (owner
   direction), and ``editable_after_create: false`` is enforced by the
   editor (it was declared in these forms but not honoured).
#. For each engine, run the forms through the draft and review tools in
   ``ui_descriptors/README.md`` to make a descriptor folder. Reuse MySQL's
   field ids where the backend field is the same, and filter by this matrix.
   Kinds the engine lacks go to ``omitted_families.json`` with the evidence.
   Native kinds go on the Engine tab or as engine objects.
#. Add live round-trip tests (``CDEADMIN_ROUNDTRIP_DOLT`` / ``_TIDB`` /
   ``_VITESS``). A form becomes ``complete`` only after one passes.
#. Fix the Vitess view drop, and gate TiDB ``CHECK`` on
   ``tidb_enable_check_constraint``.
   Vitess view drop fixed 2026-10-30 (see Vitess above).
#. Fix the MySQL-wire registration defect from the 2026-10-29 smoke test:
   registration stores ``database_password_2`` / ``_3`` secret slots for these
   engines, and endpoint verify then fails.
   Fixed 2026-10-29: unsupplied optional credentials are no longer required.
   The same day, by owner direction, MySQL-wire and MariaDB connections gained
   an explicit **Passwordless account** switch. The Dolt, TiDB and Vitess demo
   accounts, which have no password, are registered with it.
#. Later and separately: replace the exact-profile pins with coarse version
   ranges, per the owner's rule of tracking only compatibility breaks.
