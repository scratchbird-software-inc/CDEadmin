.. _postgresql_wire_parity:

PostgreSQL-wire engine parity
=============================

Owner direction, 2026-10-29 (``AGENTS.md``, "Engine expansion to full
parity"): CockroachDB and YugabyteDB YSQL reach full functionality at the
level of PostgreSQL, including their distinctive native features. Forms are
shared where possible and filtered per engine, so nothing is offered that the
engine does not directly support. This page records the live evidence for
that filter and the plan that follows from it. The MySQL-wire engines have the
same record in :ref:`mysql_wire_parity`.

Method
------

``tools/cdeadmin_postgresql_wire_parity_probe.py`` runs a minimal native
statement sequence for each PostgreSQL object kind and clause, and for each
CockroachDB-native one, in a scratch database it creates and drops. Every
statement runs in autocommit on its own connection, so a failure never makes
a later statement fail for the wrong reason. A probe passes only when every
statement executes. Retention probes then read the object back from the
catalog (``pg_indexes``, ``pg_constraint``, ``information_schema``,
``pg_class``; CockroachDB-native clauses from ``SHOW CREATE TABLE``), because
an engine can accept a clause and discard it. The probe also keeps the
notices a statement draws: one that says the clause was ignored or will not
behave as asked marks the probe ``notice``.

Read the results with these limits:

-  Probes use PostgreSQL syntax. A "no" can mean different syntax, not a
   missing feature; the ``crdb-`` probes use CockroachDB's own syntax.
-  A "yes" shows the statements ran. It does not prove the semantics match
   PostgreSQL.
-  Results are for the pinned demo versions and their demo configuration
   (PostgreSQL 18.3, CockroachDB 26.1.3), probed 2026-10-30. Settings change
   results; each result file records the settings that gate features.
-  The CockroachDB demo is one insecure node with no locality and an empty
   ``enterprise.license`` setting. Probes that need regions or passwords fail
   on it for that reason, not because the engine lacks the feature (see
   below). Whether an unlicensed cluster is otherwise limited was not
   checked.
-  The demo turns ``kv.rangefeed.enabled`` on at each start, so changefeeds
   run (owner direction, 2026-10-30). The first probe run, with it off,
   refused them; the committed result is the second run.

Regenerate a column with the probe (password from
``CDEADMIN_PROBE_PASSWORD``; for CockroachDB use ``--maintenance-database
defaultdb``), copy the result to
``tools/reference_engine_demos/postgresql_wire_parity/<engine>-<version>.json``,
then refresh the table with ``tools/cdeadmin_postgresql_wire_parity_report.py``.
``--check`` fails when the table and the committed results differ.

``notice`` means the statements ran but a notice said the clause was not
honoured; ``not kept`` means the statement ran but the catalog did not show
the clause afterwards; ``no (code)`` gives the SQLSTATE of the refusal.

Matrix
------

.. parity-matrix-start

======================================  ===============  ==================
Probe                                   postgresql-18.3  cockroachdb-26.1.3
======================================  ===============  ==================
aggregate                               yes              no (0A000)
collation                               yes              no (42601)
column-alter-type                       yes              yes
column-collate                          yes              no (42601)
column-generated-stored                 yes              yes
column-generated-virtual                yes              yes
column-identity                         yes              yes
column-rename-drop                      yes              yes
comment                                 yes              yes
constraint-check                        yes              yes
constraint-deferrable                   yes              no (42601)
constraint-exclusion                    yes              no (0A000)
constraint-foreign-key                  yes              yes
constraint-not-valid                    yes              yes
constraint-primary-key-change           yes              no (42P15)
constraint-unique                       yes              yes
crdb-alter-primary-key                  no (42601)       yes
crdb-backup                             no (42601)       yes
crdb-backup-schedule                    no (42601)       yes
crdb-changefeed                         no (42601)       yes
crdb-column-families                    no (42704)       yes
crdb-column-not-visible                 no (42601)       yes
crdb-column-on-update                   no (42601)       yes
crdb-database-placement                 no (42601)       no (42602)
crdb-export                             no (42601)       yes
crdb-external-connection                no (42601)       yes
crdb-index-hash-sharded                 no (42601)       yes
crdb-index-inverted                     no (42601)       yes
crdb-index-storing                      no (42601)       yes
crdb-index-visibility                   no (42601)       yes
crdb-retained-families                  no (42704)       yes
crdb-retained-hash-sharded              no (42601)       yes
crdb-retained-not-visible-column        no (42601)       yes
crdb-retained-not-visible-index         no (42601)       yes
crdb-retained-on-update                 no (42601)       yes
crdb-retained-partition                 no (42601)       yes
crdb-retained-row-ttl                   no (22023)       yes
crdb-retained-storing                   no (42601)       yes
crdb-row-ttl                            no (22023)       yes
crdb-session-setting                    no (42704)       yes
crdb-show-ranges                        no (42601)       yes
crdb-split-scatter                      no (42601)       yes
crdb-statistics                         no (42P17)       yes
crdb-table-partition-list               no (42601)       yes
crdb-zone-config                        no (42601)       yes
database                                yes              yes
default-privileges                      yes              yes
domain                                  yes              no (0A000)
event-trigger                           yes              no (42704)
extension                               yes              yes
foreign-data                            yes              no (0A000)
function-plpgsql                        yes              yes
function-set-returning                  yes              yes
function-sql                            yes              yes
grant-column                            yes              no (42601)
grant-table                             yes              yes
index                                   yes              yes
index-brin                              yes              no (0A000)
index-concurrently                      yes              yes
index-desc                              yes              yes
index-expression                        yes              yes
index-gin                               yes              yes
index-gist                              yes              no (42704)
index-hash                              yes              no (0A000)
index-include                           yes              yes
index-nulls-not-distinct                yes              no (42601)
index-partial                           yes              yes
index-rename                            yes              yes
index-unique                            yes              yes
large-object                            yes              no (42883)
listen-notify                           yes              no (42601)
maintenance-analyze                     yes              yes
maintenance-cluster                     yes              no (42601)
maintenance-reindex                     yes              no (42601)
maintenance-vacuum                      yes              no (42601)
materialized-view                       yes              yes
materialized-view-concurrently          yes              yes
operator                                yes              no (0A000)
owner-change                            yes              yes
procedure                               yes              yes
publication                             yes              no (0A000)
retained-check                          yes              yes
retained-deferrable                     yes              no (0A000)
retained-fk-actions                     yes              yes
retained-generated-virtual              yes              yes
retained-identity                       yes              yes
retained-include                        yes              yes
retained-index-method-brin              yes              no (0A000)
retained-index-method-hash              yes              no (0A000)
retained-nulls-not-distinct             yes              no (42601)
retained-partial-index                  yes              yes
retained-security-barrier               yes              no (42601)
retained-sequence-options               yes              yes
retained-table-comment                  yes              yes
retained-unlogged                       yes              not kept
retained-view-check-option              yes              no (42601)
role                                    yes              yes
role-membership                         yes              yes
role-password                           yes              no (28P01)
row-level-security                      yes              yes
rule                                    yes              no (0A000)
schema                                  yes              yes
sequence                                yes              yes
sequence-owned-by                       yes              yes
statistics-extended                     yes              no (42601)
table                                   yes              yes
table-as                                yes              yes
table-inherits                          yes              no (0A000)
table-like                              yes              yes
table-partitioned                       yes              no (42601)
table-temporary                         yes              no (XCEXF)
table-unlogged                          yes              notice
text-search                             yes              no (0A000)
trigger                                 yes              yes
trigger-statement                       yes              no (0A000)
truncate                                yes              yes
type-composite                          yes              yes
type-enum                               yes              yes
type-range                              yes              no (0A000)
view                                    yes              yes
view-check-option                       yes              no (42601)
view-recursive                          yes              no (0A000)
view-security-barrier                   yes              no (42601)
column-collate-icu                      not run          yes
constraint-primary-key-change-not-null  not run          yes
crdb-table-temporary-opt-in             not run          yes
======================================  ===============  ==================

.. parity-matrix-end

Findings per engine
-------------------

CockroachDB 26.1.3
~~~~~~~~~~~~~~~~~~

Shared surface it does not have (refused, so not offered):

-  Aggregates, operators, collations (``CREATE COLLATION``), domains, range
   types, rules, event triggers, text search configurations, publications,
   foreign data wrappers (``postgres_fdw`` is "not yet supported"), large
   objects, ``LISTEN``/``NOTIFY``, table inheritance and declarative
   ``PARTITION BY ... PARTITION OF`` partitioning.
-  ``VACUUM``, ``CLUSTER`` and ``REINDEX``; ``ANALYZE`` works.
-  Index methods ``hash``, ``brin`` and ``gist`` on ranges; ``NULLS NOT
   DISTINCT``. ``gin`` works (CockroachDB's inverted index).
-  Deferrable constraints and exclusion constraints.
-  Views ``WITH CHECK OPTION``, ``WITH (security_barrier)`` and recursive
   views.
-  Column-level ``GRANT SELECT (col)``.
-  Statement-level triggers ("not yet supported"); row-level ``BEFORE``
   triggers with a PL/pgSQL function that assigns ``NEW`` run.
-  PostgreSQL's extended-statistics form (``CREATE STATISTICS name
   (dependencies) ON a, b``); CockroachDB's own ``CREATE STATISTICS name ON
   col FROM t`` runs.

Shared surface with different behaviour:

-  ``UNLOGGED`` is accepted with the notice "UNLOGGED TABLE will behave as a
   regular table" and the table is permanent (``relpersistence`` ``p``).
-  ``CONCURRENTLY`` is accepted with a notice that it is not required: every
   index build and materialized-view refresh is already online.
-  ``CREATE TABLE ... AS`` copies no indexes, defaults or constraints and
   adds a hidden ``rowid`` primary key (its notice says so).
-  A primary key on a nullable column is refused; PostgreSQL makes the
   column ``NOT NULL`` itself. Declaring ``NOT NULL`` first works.
-  ``COLLATE "C"`` is not a CockroachDB locale; ICU locale tags such as
   ``"en-US"`` work.
-  ``CREATE EXTENSION`` works for the extensions CockroachDB builds in
   (``fuzzystrmatch`` probed); others are refused.
-  An identity or serial primary key draws a notice recommending UUIDs.

Configuration-gated on the demo (the feature exists; the demo does not
enable it):

-  Passwords: "setting or updating a password is not supported in insecure
   mode". Passwordless users work.
-  Temporary tables: refused unless the session sets
   ``experimental_enable_temp_tables`` (then they work).
-  Changefeeds: need ``kv.rangefeed.enabled``. The demo now sets it and
   ``crdb-changefeed`` passes (a ``null://`` sink, so no sink delivery is
   checked).
-  Multi-region (primary region, survival goals, table locality): the node
   has no locality, so the cluster has no regions.

CockroachDB-native surface that runs: hash-sharded, ``STORING`` and
inverted indexes, index visibility (``NOT VISIBLE``, partial ``VISIBILITY``),
``NOT VISIBLE`` columns, ``ON UPDATE`` columns, column families,
``ALTER PRIMARY KEY``, row-level TTL, ``PARTITION BY LIST`` with
``DEFAULT``, zone configurations, ``SPLIT AT``/``SCATTER``/``UNSPLIT``,
``CREATE STATISTICS``, external connections, ``BACKUP`` and backup
schedules, ``EXPORT`` (with a deprecation notice), ``SHOW RANGES`` and
session settings. Row-level security (``ENABLE ROW LEVEL SECURITY``,
``CREATE``/``ALTER``/``DROP POLICY``) runs, as do PL/pgSQL functions,
procedures and enum and composite types.

Untested on CockroachDB
~~~~~~~~~~~~~~~~~~~~~~~

Owner decision, 2026-10-30: no multi-node, multi-region demo. These need more
than the demo's one node without locality, so neither the probe nor any live
round trip has exercised them. Where the editor offers them, they rest on
CockroachDB's documentation, not on evidence here:

-  Regions: database primary and added regions, survival goals (zone and
   region), table locality (``REGIONAL BY TABLE``, ``REGIONAL BY ROW``,
   ``GLOBAL``), super regions, ``PLACEMENT RESTRICTED``.
-  Range placement across nodes: zone-configuration replica counts and
   constraints actually being satisfied, lease preferences, replica
   relocation and rebalancing. ``SPLIT AT``, ``SCATTER`` and ``UNSPLIT`` pass
   on one node, which proves only that they run.
-  Node operations: decommission, recommission and drain, and node status
   for more than one node.
-  Changefeed delivery: the probe uses the ``null://`` sink, so no Kafka,
   webhook or cloud-storage sink has been checked.

Provider findings (2026-10-30)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The catalog flags ``pg_catalog``, ``information_schema`` and
   ``crdb_internal`` objects as system objects but not ``pg_extension``,
   CockroachDB's own schema for ``spatial_ref_sys`` and the geometry
   catalogs, so its objects appear as user objects.
-  Hidden columns appear as ordinary columns: ``rowid`` (a table without a
   primary key) and the hash-sharded index's ``crdb_internal_..._shard_N``.
   ``information_schema.columns.is_hidden`` identifies them. An editor that
   reopens such a table would try to drop or re-add them.
-  Column records carry only the type and nullability: no position,
   default, generation or key membership, so a table editor cannot reopen a
   table faithfully (the MySQL-wire reader was enriched the same way for
   Dolt).
-  Node and locality records need the ``cockroach`` CLI (``cockroach_path``
   in the route), which the demo route does not set, so the catalog has no
   nodes. ``crdb_internal`` reads are refused in 26.1 unless the session sets
   ``allow_unsafe_internals``. Fixed the same day: the demo writes a
   ``cockroach`` wrapper (a one-shot container of the demo image on the host
   network) and registers it with ``cockroach_insecure``; the catalog now
   lists node 1, and ``node status --decommission`` reads through it.
   Decommission and recommission were not run (see "Untested on
   CockroachDB").
-  The provider passes CockroachDB through the generic relational forms:
   the trigger form offers Firebird's ``active`` and ``position`` and an
   ``INSTEAD OF`` timing; the user form offers MySQL's ``host`` and
   ``plugin`` and requires a password; the table form takes columns and
   constraints as JSON. ``type`` is inspect-only although enum and
   composite types run, and there is no policy kind although row-level
   security runs.
-  Fixed the same day: ``pg_extension`` is flagged as a system schema;
   hidden columns are marked (``hidden``) with CockroachDB's own type
   expression (``native_type``) and key membership (``column_key``);
   columns carry position, default, generation and identity (in the shared
   reader, with the narrow query as fallback); constraints come from
   ``pg_constraint`` with ordered columns, references, rules and check
   clauses, which leaves out the ``<ids>_not_null`` pseudo-checks
   ``information_schema`` lists; the constraints on hidden columns
   (``rowid``'s primary key, a shard column's check) are dropped and their
   index marked hidden; indexes carry columns, directions, ``STORING``,
   uniqueness, method (``inverted`` for gin), hash sharding with its bucket
   count, partial predicate and visibility.

Plan
----

#. Catalog: flag ``pg_extension``; mark hidden columns and keep them out of
   the editor's column grid; carry position, default, generation, identity
   and key membership on columns, and definitions on constraints and
   indexes (including ``STORING``, hash-sharded, inverted, partial and
   visibility).
#. Demo: a ``cockroach`` CLI wrapper for node status, decommission and
   recommission, as the Vitess demo has for ``vtctldclient``. Proposed, for
   the owner to decide: an opt-in demo setting for rangefeeds, and an
   opt-in multi-node, multi-region demo for the region and range
   operations, which one node cannot prove.

   Owner decision, 2026-10-30: rangefeeds are on in the demo; there is no
   multi-node demo, and what it would have proved is listed under
   "Untested on CockroachDB" below. The CLI wrapper is in the demo.
#. Provider forms per family, reusing the PostgreSQL provider's field ids:
   table (columns, constraints, families, TTL, locality), index (method,
   storing, hash-sharded, partial, visibility), trigger (row-level only),
   user and role (passwordless where the cluster requires it), type (enum,
   composite), policy (new kind), and the native surface on the Engine tab
   or as engine objects.
#. A descriptor folder ``ui_descriptors/cockroachdb`` drafted from the
   provider's effective forms, filtered by this matrix, with a form becoming
   ``complete`` only after a live round trip checks what the engine holds.
#. The shared PostgreSQL descriptors are still ``draft`` and are another
   stream's work; CockroachDB takes field ids from the PostgreSQL provider's
   effective forms, not from those drafts.
