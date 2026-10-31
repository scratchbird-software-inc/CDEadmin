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
-  YugabyteDB YSQL 2025.2.2.2 (PostgreSQL 15.12 based) joined later the
   same day, with ``ysql-`` probes for its own syntax. Its demo is one node
   placed at ``cloud1.datacenter1.rack1``, so tablespace placement can be
   probed there (the probes use that placement). The PostgreSQL and
   CockroachDB columns were re-run with the extended probe; their earlier
   rows did not change.

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

======================================  ===============  ==================  =====================
Probe                                   postgresql-18.3  cockroachdb-26.1.3  yugabytedb-2025.2.2.2
======================================  ===============  ==================  =====================
aggregate                               yes              no (0A000)          yes
collation                               yes              no (42601)          yes
column-alter-type                       yes              yes                 yes
column-collate                          yes              no (42601)          yes
column-collate-icu                      no (42704)       yes                 no (42704)
column-generated-stored                 yes              yes                 yes
column-generated-virtual                yes              yes                 no (42601)
column-identity                         yes              yes                 yes
column-rename-drop                      yes              yes                 yes
comment                                 yes              yes                 yes
comment-function                        yes              no (0A000)          yes
comment-policy                          yes              no (42601)          yes
comment-view                            yes              no (42601)          yes
constraint-check                        yes              yes                 yes
constraint-deferrable                   yes              no (42601)          yes
constraint-exclusion                    yes              no (0A000)          no (0A000)
constraint-foreign-key                  yes              yes                 yes
constraint-not-valid                    yes              yes                 yes
constraint-primary-key-change           yes              no (42P15)          yes
constraint-primary-key-change-not-null  yes              yes                 yes
constraint-unique                       yes              yes                 yes
crdb-alter-primary-key                  no (42601)       yes                 no (42601)
crdb-backup                             no (42601)       yes                 no (42601)
crdb-backup-schedule                    no (42601)       yes                 no (42601)
crdb-changefeed                         no (42601)       yes                 no (42601)
crdb-column-families                    no (42704)       yes                 no (42704)
crdb-column-not-visible                 no (42601)       yes                 no (42601)
crdb-column-on-update                   no (42601)       yes                 no (42601)
crdb-database-placement                 no (42601)       no (42602)          no (42601)
crdb-export                             no (42601)       yes                 no (42601)
crdb-external-connection                no (42601)       yes                 no (42601)
crdb-index-hash-sharded                 no (42601)       yes                 no (42601)
crdb-index-inverted                     no (42601)       yes                 no (42601)
crdb-index-storing                      no (42601)       yes                 no (42601)
crdb-index-visibility                   no (42601)       yes                 no (42601)
crdb-retained-families                  no (42704)       yes                 no (42704)
crdb-retained-hash-sharded              no (42601)       yes                 no (42601)
crdb-retained-not-visible-column        no (42601)       yes                 no (42601)
crdb-retained-not-visible-index         no (42601)       yes                 no (42601)
crdb-retained-on-update                 no (42601)       yes                 no (42601)
crdb-retained-partition                 no (42601)       yes                 no (42601)
crdb-retained-row-ttl                   no (22023)       yes                 no (22023)
crdb-retained-storing                   no (42601)       yes                 no (42601)
crdb-row-ttl                            no (22023)       yes                 no (22023)
crdb-session-setting                    no (42704)       yes                 no (42704)
crdb-show-ranges                        no (42601)       yes                 no (42601)
crdb-split-scatter                      no (42601)       yes                 no (42601)
crdb-statistics                         no (42P17)       yes                 no (42P17)
crdb-table-partition-list               no (42601)       yes                 no (42601)
crdb-table-temporary-opt-in             no (42704)       yes                 no (42704)
crdb-zone-config                        no (42601)       yes                 no (42601)
database                                yes              yes                 yes
database-connection-limit               yes              no (0A000)          yes
database-template                       yes              yes                 yes
default-privileges                      yes              yes                 yes
domain                                  yes              no (0A000)          yes
event-trigger                           yes              no (42704)          yes
extension                               yes              yes                 yes
foreign-data                            yes              no (0A000)          yes
function-options                        yes              no (0A000)          yes
function-plpgsql                        yes              yes                 yes
function-set-returning                  yes              yes                 yes
function-sql                            yes              yes                 yes
function-variadic                       yes              no (0A000)          yes
grant-column                            yes              no (42601)          yes
grant-table                             yes              yes                 yes
index                                   yes              yes                 yes
index-brin                              yes              no (0A000)          no (XX000)
index-concurrently                      yes              yes                 no (0A000)
index-desc                              yes              yes                 yes
index-expression                        yes              yes                 yes
index-gin                               yes              yes                 yes
index-gist                              yes              no (42704)          no (XX000)
index-hash                              yes              no (0A000)          yes
index-include                           yes              yes                 yes
index-nulls-not-distinct                yes              no (42601)          yes
index-partial                           yes              yes                 yes
index-rename                            yes              yes                 yes
index-unique                            yes              yes                 yes
large-object                            yes              no (42883)          no (XX000)
listen-notify                           yes              no (42601)          notice
maintenance-analyze                     yes              yes                 yes
maintenance-cluster                     yes              no (42601)          no (0A000)
maintenance-reindex                     yes              no (42601)          no (0A000)
maintenance-vacuum                      yes              no (42601)          notice
materialized-view                       yes              yes                 yes
materialized-view-concurrently          yes              yes                 yes
operator                                yes              no (0A000)          yes
owner-change                            yes              yes                 yes
policy-alter-command                    no (42601)       no (42601)          no (42601)
procedure                               yes              yes                 yes
publication                             yes              no (0A000)          yes
retained-check                          yes              yes                 yes
retained-deferrable                     yes              no (0A000)          yes
retained-fk-actions                     yes              yes                 yes
retained-generated-virtual              yes              yes                 no (42601)
retained-identity                       yes              yes                 yes
retained-include                        yes              yes                 yes
retained-index-method-brin              yes              no (0A000)          no (XX000)
retained-index-method-hash              yes              no (0A000)          not kept
retained-nulls-not-distinct             yes              no (42601)          yes
retained-partial-index                  yes              yes                 yes
retained-security-barrier               yes              no (42601)          yes
retained-sequence-options               yes              yes                 not kept
retained-table-comment                  yes              yes                 yes
retained-unlogged                       yes              not kept            not kept
retained-view-check-option              yes              no (42601)          no (0A000)
role                                    yes              yes                 yes
role-comment                            yes              no (42601)          yes
role-connection-limit                   yes              no (42601)          yes
role-inherit                            yes              no (42601)          yes
role-membership                         yes              yes                 yes
role-password                           yes              no (28P01)          yes
role-rename                             yes              no (42601)          yes
role-superuser                          yes              no (42601)          yes
row-level-security                      yes              yes                 yes
rule                                    yes              no (0A000)          yes
schema                                  yes              yes                 yes
sequence                                yes              yes                 yes
sequence-comment                        yes              no (42601)          yes
sequence-cycle                          yes              no (0A000)          yes
sequence-owned-by                       yes              yes                 yes
statistics-extended                     yes              no (42601)          yes
table                                   yes              yes                 yes
table-as                                yes              yes                 yes
table-inherits                          yes              no (0A000)          yes
table-like                              yes              yes                 yes
table-partitioned                       yes              no (42601)          yes
table-temporary                         yes              no (XCEXF)          yes
table-unlogged                          yes              notice              notice
text-search                             yes              no (0A000)          yes
trigger                                 yes              yes                 yes
trigger-alter                           yes              no (42601)          yes
trigger-instead-of                      yes              no (0A000)          yes
trigger-or-replace                      yes              no (0A000)          yes
trigger-referencing                     yes              no (0A000)          no (0A000)
trigger-statement                       yes              no (0A000)          yes
trigger-truncate                        yes              no (0A000)          yes
trigger-update-of                       yes              no (0A000)          yes
truncate                                yes              yes                 yes
type-composite                          yes              yes                 yes
type-composite-alter                    yes              no (0A000)          no (0A000)
type-enum                               yes              yes                 yes
type-enum-alter                         yes              yes                 yes
type-range                              yes              no (0A000)          yes
view                                    yes              yes                 yes
view-check-option                       yes              no (42601)          no (0A000)
view-recursive                          yes              no (0A000)          yes
view-security-barrier                   yes              no (42601)          yes
ysql-colocated-database                 no (42601)       no (42601)          yes
ysql-hash-code                          no (42883)       no (42883)          yes
ysql-index-hash                         no (42704)       no (42804)          yes
ysql-index-nonconcurrently              no (42601)       no (42601)          yes
ysql-index-split                        no (42601)       no (42601)          yes
ysql-primary-key-hash                   no (42601)       no (42804)          yes
ysql-retained-primary-key-hash          no (42601)       no (42804)          yes
ysql-retained-split-at                  no (42601)       no (42601)          yes
ysql-retained-split-into                no (42601)       no (42601)          yes
ysql-retained-tablespace-placement      no (42601)       no (0A000)          yes
ysql-split-at                           no (42601)       no (42601)          yes
ysql-split-into                         no (42601)       no (42601)          yes
ysql-table-properties                   no (42883)       no (42883)          yes
ysql-tablegroup                         no (42601)       no (42601)          yes
ysql-tablespace-placement               no (42601)       no (0A000)          yes
======================================  ===============  ==================  =====================

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

YugabyteDB YSQL 2025.2.2.2
~~~~~~~~~~~~~~~~~~~~~~~~~~

92 of the 141 probes run (the shared PostgreSQL surface is close to
PostgreSQL 15's). With the rows added later the same day for clauses first
checked by hand on CockroachDB, 112 of 164: YugabyteDB runs INSTEAD OF,
TRUNCATE, column-list, OR REPLACE and altered/commented triggers, SUPERUSER,
NOINHERIT, CONNECTION LIMIT, role rename and comment, sequence CYCLE and
comments, comments on views, functions and policies, VARIADIC and function
options, database CONNECTION LIMIT and TEMPLATE. It refuses transition
tables (``REFERENCING``) and composite ``ADD ATTRIBUTE``; ``ALTER POLICY ...
FOR`` is a syntax error there as on PostgreSQL 18.3 (so not a CockroachDB
restriction). Shared surface it does not have (refused, so not
offered):

-  Index methods ``brin`` and ``gist``; ``EXCLUDE`` constraints; ``VIEW
   WITH CHECK OPTION``; virtual generated columns (PostgreSQL 15 syntax has
   only ``STORED``).
-  ``CLUSTER``, ``REINDEX``, ``DROP INDEX CONCURRENTLY``, ``REFRESH
   MATERIALIZED VIEW CONCURRENTLY``, large objects. (Correction, same
   day: the probe row ``materialized-view-concurrently`` passes; the
   concurrent refresh I first tried by hand failed only because that view
   had no unique index, which PostgreSQL requires too.)

Accepted but not carried out (the notice says so):

-  ``UNLOGGED`` ("currently ignored"); ``VACUUM`` (a no-op: garbage
   collection is automatic); ``LISTEN``/``NOTIFY``/``UNLISTEN`` ("not
   supported yet and will be ignored").
-  ``USING hash`` becomes YugabyteDB's ``lsm (v HASH)`` ("substituting
   access method"); a sequence's ``CACHE`` is overridden by the server
   flag; table inheritance is a beta feature; tablegroups are beta and
   deprecated.
-  ``ALTER COLUMN TYPE`` and primary-key changes rewrite the table, with a
   notice that the rewrite "may lead to inconsistencies".

YSQL-native surface that runs: ``HASH`` and ``ASC``/``DESC`` key columns in
primary keys and indexes, ``SPLIT INTO n TABLETS`` and ``SPLIT AT VALUES``
(read back from ``yb_table_properties``), ``CREATE INDEX NONCONCURRENTLY``,
tablespaces with ``replica_placement`` (read back from ``pg_tablespace``),
colocated databases, ``yb_hash_code``. Partitioning, triggers (statement
level too), publications, row-level security and a large extension set
(``pg_trgm``, ``hstore``, ``vector``, ``pgcrypto``, ``pg_partman`` and
others) run as on PostgreSQL. Multi-node behaviour (tablet placement
across zones, leader preferences, xCluster) is untested on the one-node
demo.

YugabyteDB progress, 2026-10-30: ``ui_descriptors/yugabytedb`` exists and
YugabyteDB joined the beta-engine gate lists. Trigger and role (user, role)
forms are ``complete`` (``providers/yugabytedb/objects.py``, live round
trips in ``tools/tests/test_ui_descriptor_roundtrip_yugabytedb.py``): every
trigger timing, level and event, ``UPDATE OF`` columns, ``WHEN``, enable
modes, comments, ``CREATE OR REPLACE`` and rename; PostgreSQL role options,
connection limit, expiry, memberships, comments, rename and password
removal. Field ids match the CockroachDB forms where the concept is the
same. Trigger records come from ``pg_trigger`` (WHEN and ``UPDATE OF`` from
``pg_get_triggerdef``), one per trigger. The other families are drafts.

The table form is ``complete`` the same day (``providers/yugabytedb/
tables.py``): columns with identity, stored generated expressions,
collations and comments; primary keys with leading ``HASH`` columns and a
range order; unique, deferrable foreign-key and check constraints;
tablespace, ``SPLIT INTO``/``SPLIT AT``, colocation, partitioning, comment
and row-level security. Alter diffs columns and constraint grids against
the record (as for CockroachDB), changes identity, drops a stored
expression, restates the type to change a collation (the record carries
each column's type), rewrites the table to change its primary key (with a
warning) and moves it between tablespaces. Found live: deferrable
``UNIQUE`` constraints are refused ("not supported yet"; deferrable foreign
keys run), so the editor refuses them; the probe's deferrable row used a
foreign key. The constraint records now come from ``pg_constraint``
(``information_schema`` listed each NOT NULL column as a check). Table
DDL is slow on the one-node demo (the round trip takes about 11 minutes).

The index form is ``complete`` too (``providers/yugabytedb/indexes.py``):
keys with HASH / ASC / DESC (leading HASH keys hashed together),
``UNIQUE`` with ``NULLS NOT DISTINCT``, ``INCLUDE``, a partial predicate,
lsm or gin, tablespace, ``SPLIT INTO``/``SPLIT AT``, ``NONCONCURRENTLY``
and a comment; in place, rename, ``SET TABLESPACE`` and comment. Found
live: an index's ``SPLIT`` clause must come before ``WHERE`` (after
``TABLESPACE``); ``fillfactor`` is refused; gin reads back as ``ybgin``.

The type form (types and domains) is ``complete``
(``providers/yugabytedb/types.py``): enums (add and rename values;
dropping or reordering is refused, as PostgreSQL has no ``DROP VALUE``),
composites (fixed once created: YugabyteDB refuses every attribute
change), range types with a subtype and difference function, and domains
with base type, collation, default, ``NOT NULL`` and checks, of which only
the default, name and comment change afterwards (``ALTER DOMAIN`` ``NOT
NULL`` and constraint changes are "not supported yet"). Enum values use
the field id ``enum_values`` as YugabyteDB's and DuckDB's forms did; the
CockroachDB form's ``values`` is to be aligned when its demo next runs, so
the change is re-checked live.

Catalog speed, measured the same day: YSQL fetches catalog rows over RPC
and a new connection starts with a cold catalog cache. The column query
added for the table editor read every system relation (35 seconds cold);
it now reads user relations only, and a whole catalog read takes about
6 to 10 seconds on the demo, pooled or not. Earlier readings of 65 to 130
seconds were taken while a killed test's queries were still running.

The view form (views and materialized views) is ``complete``
(``providers/yugabytedb/views.py``): column names, recursive views,
``security_barrier`` and ``security_invoker``, comments, a materialized
view's tablespace and ``WITH NO DATA``. A view is altered by renaming
changed columns in place (``ALTER VIEW ... RENAME COLUMN``) and then
``CREATE OR REPLACE VIEW`` with the full column list; a materialized
view's query is fixed, its name, tablespace and comment change. YugabyteDB
had no refresh operation; it now has one (``CONCURRENTLY``, ``WITH NO
DATA``) in its control plane.

The sequence form is ``complete`` (``providers/yugabytedb/sequences.py``):
type, start, increment, bounds, cache, ``CYCLE``, ``OWNED BY``, restart,
comment and rename. ``pg_sequences`` reports YSQL sequences accurately
(CockroachDB's does not); a cache below the server's minimum is raised to
it (``CACHE 10`` read back as 100 on the demo).

The routine form (functions and procedures) is ``complete``
(``providers/yugabytedb/routines.py``): ``IN`` / ``OUT`` / ``INOUT`` /
``VARIADIC`` parameters with defaults, ``RETURNS [SETOF]`` or ``RETURNS
TABLE``, SQL and PL/pgSQL bodies, volatility, ``STRICT``, ``LEAKPROOF``,
``SECURITY DEFINER``, ``PARALLEL``, ``COST``, ``ROWS``, ``SET`` options,
comments and rename. Overloads share a name, so a routine's resource is
now ``name(argument types)`` (before, overloads collided on one name); its
parameters and return type are its identity and fixed once created, and
the rest is changed with ``CREATE OR REPLACE``.

Array types were refused by the editor, for routine parameters and table
columns alike, although YugabyteDB accepts them: the shared type check
had no brackets. A shared ``_safe_type`` now accepts array suffixes
(``int[]``, ``text[3][]``) and checks the base type as before; YugabyteDB
tables and routines use it, and a live test creates array columns and
changes one's type (``int[]`` to ``bigint[]``; ``text[3][]`` reads back
as ``text[]``, as PostgreSQL drops declared sizes). CockroachDB's table
editor still refuses arrays; it moves to ``_safe_type`` when its demo next
runs, so its narrower array support (no nested arrays) is checked live.

Provider finding, 2026-10-30: the shared relational apply runs a plan in
one transaction, and YugabyteDB refuses ``CREATE DATABASE`` and ``CREATE
TABLESPACE`` there ("cannot run inside a transaction block"), so the
provider's database and tablespace creation had always failed. Plans may
now set ``statements_outside_transaction``; YugabyteDB sets it for database
and tablespace create and drop, and such a plan runs on an owned
autocommit connection (each statement commits on its own, with a warning
when there are several). Index creation on a populated table and a failed
statement's rollback behaved correctly in the same check.

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
-  Triggers and principals, 2026-10-30. ``information_schema.triggers``
   lists a trigger once per event, so a trigger on two events appeared
   twice; trigger records now come from ``pg_trigger`` and carry timing,
   events, function, arguments and the ``WHEN`` clause. User and role
   records carry login, SQL login, role options, expiry and memberships from
   ``SHOW ROLES``. The trigger, user and role forms are CockroachDB's own
   (``providers/cockroachdb/objects.py``) and their descriptors are
   ``complete`` after live round trips
   (``tools/tests/test_ui_descriptor_roundtrip_cockroachdb.py``).

Checked live on 26.1.3 for those forms (not yet in the probe):

-  Triggers: only ``FOR EACH ROW``, ``BEFORE`` or ``AFTER``, on ``INSERT``,
   ``UPDATE`` or ``DELETE``, with string arguments and a ``WHEN`` clause.
   Refused: ``INSTEAD OF`` (on views too), ``TRUNCATE``, column lists
   (``UPDATE OF``), ``REFERENCING``, statement-level triggers,
   ``CREATE OR REPLACE TRIGGER``, and every ``ALTER TRIGGER``,
   ``ENABLE``/``DISABLE TRIGGER`` and ``COMMENT ON TRIGGER``.
-  A ``WHEN`` clause must write row fields as ``(NEW).col``; ``NEW.col`` is
   refused ("no data source matches prefix").
-  A trigger argument containing a single quote cannot be stored: however
   the literal is written (``''``, ``E'\''``, dollar quoting), CockroachDB
   re-renders the statement with the quote unescaped and fails to parse it.
   The provider refuses such an argument with that reason.
-  Role options that run: ``LOGIN``, ``SQLLOGIN``, ``CREATEDB``,
   ``CREATEROLE``, ``CREATELOGIN``, ``CONTROLJOB``, ``CONTROLCHANGEFEED``,
   ``CANCELQUERY``, ``VIEWACTIVITY``, ``VIEWACTIVITYREDACTED``,
   ``VIEWCLUSTERSETTING``, ``MODIFYCLUSTERSETTING``, ``REPLICATION``,
   ``BYPASSRLS`` (each with its ``NO`` form), ``PASSWORD NULL`` and
   ``VALID UNTIL``. Refused: ``SUPERUSER``, ``INHERIT``, ``CONNECTION
   LIMIT``, ``RENAME`` and ``COMMENT ON ROLE``. ``ALTER ROLE ... [IN
   DATABASE] SET`` and ``GRANT SYSTEM`` run but have no editor yet.
-  Enum types: ``ADD VALUE`` (with ``BEFORE``/``AFTER``), ``RENAME VALUE``,
   ``DROP VALUE`` and ``RENAME TO`` run; composite ``ADD ATTRIBUTE`` is
   refused. Later the same day: composite ``DROP``, ``RENAME`` and
   ``ALTER ATTRIBUTE`` are unimplemented too; ``DROP VALUE`` is refused
   while a row holds the value. ``pg_type`` lists every table's row type
   as ``typtype 'c'`` (the old catalog reported each table as a composite
   type; fixed: a composite is the one whose ``pg_class`` row is
   ``relkind 'c'``). A user type's ``pg_type`` oid is its descriptor id
   plus 100000 while ``pg_description`` keeps the bare id, so
   ``obj_description`` finds no type comment; the catalog joins with the
   offset, restricted to ``pg_type`` descriptions.
-  Policies: ``CREATE``/``ALTER``/``DROP POLICY`` run and ``pg_policy`` and
   ``SHOW POLICIES`` read them back; ``COMMENT ON POLICY`` is refused.
   Later the same day: ``ALTER POLICY`` takes ``TO``, ``USING``, ``WITH
   CHECK`` and ``RENAME TO``; ``AS`` and ``FOR`` are syntax errors there.
   ``USING (NULL)`` and ``WITH CHECK (NULL)`` are stored as the
   expression ``NULL`` (refusing every row), and nothing removes a clause,
   so the editor refuses clearing one rather than drop and recreate the
   policy (which would leave the table unguarded in between).
   ``pg_policies`` gives role names; ``pg_class.relrowsecurity`` and
   ``relforcerowsecurity`` reflect ``ENABLE``/``FORCE ROW LEVEL
   SECURITY``. Policies are the ``row-policy`` kind (as for PostgreSQL),
   children of their table; the table editor has the two switches.
-  ``ALTER COLUMN ... TYPE`` is refused while a policy expression references
   the column.
-  Tables are created with ``schema_locked = true`` by default (seen in
   ``SHOW CREATE TABLE``).
-  Tables, checked for the table editor:

   -  ``ALTER PRIMARY KEY`` keeps the old key's columns as a ``UNIQUE``
      index (``<table>_<columns>_key``). So does ``DROP CONSTRAINT``
      plus ``ADD CONSTRAINT ... PRIMARY KEY`` in one statement, which was
      expected not to. The editor uses ``ALTER PRIMARY KEY`` and its plan
      warns of the index.
   -  ``DROP IDENTITY`` is refused while the table is ``schema_locked``
      ("cannot automatically unlock the table"); the editor unlocks and
      relocks around it. The other column changes it emits unlock by
      themselves.
   -  A ``UNIQUE`` constraint is dropped with ``DROP INDEX
      table@name CASCADE``; ``ALTER TABLE ... DROP CONSTRAINT`` is
      refused for it.
   -  ``ALTER COLUMN ... DROP STORED`` turns a stored computed column into
      a regular one; a virtual column is refused. A virtual computed
      column cannot belong to a family.
   -  ``SET DEFAULT`` type-checks strictly (an ``INT`` default on a
      ``STRING`` column is refused).
   -  ``ON UPDATE`` expressions and column families are visible only in
      ``SHOW CREATE TABLE`` (``SHOW CREATE ALL TABLES`` for the catalog);
      NOT VISIBLE columns share ``is_hidden`` with the engine's own hidden
      columns (``rowid``, ``crdb_internal_expiration``, hash-shard
      columns), which the catalog tells apart by name and default.
   -  A collation tag is stored normalized (``"en-US"`` reads back as
      ``en_US``).
   -  ``obj_description(oid)`` without a catalog argument matches
      built-in function descriptions: an uncommented table read back a
      function's help text as its comment. Fixed 2026-10-30 (table and
      index comments now name ``'pg_class'``); a live check covers it.
-  Operations, checked through their descriptors: zone configuration and
   reset (database, table), scatter (table, index), refresh, changefeed
   create / pause / resume / add and drop table / set sink / cancel, job
   pause / resume / cancel, schedule pause / resume, backup and restore.
   Findings: ``BACKUP`` and ``RESTORE`` inside the provider's transaction
   are refused ("cannot be used inside a multi-statement transaction
   without DETACHED"), so the operation failed every time; they now run
   ``DETACHED`` and the job is followed. ``range_min_bytes`` and
   ``range_max_bytes`` must be set together. ``ALTER CHANGEFEED`` needs a
   paused changefeed, and a changefeed keeps its sink type ("Altering the
   sink type of a changefeed is disallowed"); the provider refuses a type
   change. A job that is still pausing cannot be resumed. The demo
   profile registers backup and sink allowlists inside the node's
   ``nodelocal`` directory (and ``null://``). Node, region, locality and
   range-relocation operations stay untested on one node.
-  Databases: ``CREATE DATABASE`` with ``ENCODING 'UTF8'`` and
   ``OWNER``, ``COMMENT ON DATABASE``, ``ALTER DATABASE ... OWNER TO``,
   ``RENAME TO``, ``SET``/``RESET`` run (session defaults read back from
   ``SHOW DEFAULT SESSION VARIABLES FOR ROLE ALL``). Refused:
   ``CONNECTION LIMIT``, ``TEMPLATE``, ``LC_COLLATE``, ``LC_CTYPE``
   (correction, same day: the probe row ``database-template`` shows
   ``TEMPLATE template0`` accepted without a notice; the refusal came from
   ``LC_COLLATE`` in the same statement. Its effect was not checked and the
   editor does not offer it. ``CONNECTION LIMIT`` is refused unless -1);
   ``ALTER DATABASE ... PLACEMENT`` needs the session setting
   ``enable_multiregion_placement_policy``. The catalog had listed
   CockroachDB's ``system`` database as a user database; it is now flagged
   as a system object.
-  Routines: SQL and PL/pgSQL; ``IN``/``OUT``/``INOUT`` parameters with
   defaults; ``RETURNS [SETOF]`` (``RETURNS TABLE`` renders as ``OUT``
   parameters and ``SETOF RECORD``); volatility, ``STRICT``,
   ``LEAKPROOF`` (immutable only), ``SECURITY DEFINER``; ``CREATE OR
   REPLACE`` (which resets every option it does not name) and ``RENAME
   TO``. Refused: ``VARIADIC``, ``PARALLEL``, ``COST``, ``SET`` options
   and ``COMMENT ON FUNCTION``/``PROCEDURE``. ``pg_proc.prosecdef`` stays
   false after ``ALTER FUNCTION ... SECURITY DEFINER`` while ``SHOW
   CREATE`` shows ``DEFINER``; ``pg_get_function_arguments`` gives
   PostgreSQL type names without defaults. The record reads ``SHOW CREATE
   ALL ROUTINES``, matched to ``pg_proc`` by name and parameter names.
   Overloads share a name, so routine resources are now named
   ``name(arguments)`` (they collided before) and are dropped by
   signature; a trigger names its function ``name()``.
-  Sequences: ``AS INT2/INT4/INT8``, ``START``, ``INCREMENT``,
   ``MINVALUE``/``MAXVALUE`` (or ``NO``), ``CACHE`` with ``PER NODE`` or
   ``PER SESSION``, ``OWNED BY`` (or ``NONE``), ``RESTART [WITH]`` and
   ``RENAME TO`` run; ``CYCLE`` is unimplemented and ``COMMENT ON
   SEQUENCE`` is a syntax error. ``pg_sequences.data_type`` reports bigint
   for an ``INT4`` sequence; ``SHOW CREATE ALL TABLES`` renders sequences
   exactly and the record reads it. The cache scope has state: a cache
   above 1 is ``PER NODE`` by default; a scope-less ``CACHE n`` on a
   ``PER SESSION`` sequence is silently ignored, as is ``PER NODE CACHE
   n``; node becomes session directly, but session becomes node only after
   ``PER SESSION CACHE 1``. The editor names the scope on every step and
   resets first when leaving ``PER SESSION``.
-  Views: ``CREATE OR REPLACE VIEW`` refuses to rename an existing column
   ("cannot change name of view column") or drop one, so the editor always
   sends the column list with a replacement. ``COMMENT ON VIEW`` and
   ``COMMENT ON MATERIALIZED VIEW`` are syntax errors, and ``COMMENT ON
   TABLE`` refuses a view; ``CREATE OR REPLACE MATERIALIZED VIEW`` is a
   syntax error. ``pg_matviews.ispopulated`` stays true after ``WITH NO
   DATA`` (selecting says "has not been populated"), so the record does not
   report it. A materialized view has a hidden ``rowid`` column.
   ``REFRESH`` (``CONCURRENTLY``, ``WITH NO DATA``) runs.
-  Indexes: keys with directions and expressions, ``UNIQUE``, inverted
   (``USING GIN`` or ``CREATE INVERTED INDEX``), hash-sharded with a bucket
   count, ``STORING`` (``INCLUDE`` is accepted and read back as
   ``STORING``), a partial predicate and visibility run; in place an index
   takes ``RENAME TO``, ``VISIBLE``/``NOT VISIBLE``/``VISIBILITY`` and
   ``COMMENT ON INDEX``. Expression keys read back as
   ``crdb_internal_idx_expr`` in ``information_schema.statistics``, so the
   record takes keys from the ``pg_indexes`` definition; NOT VISIBLE reads
   back as visibility 0. The provider admits index ``alter`` from
   2026-10-30. Fixed the same day: the catalog lost a partial predicate
   when visibility was below 1 (rendered after the predicate).

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
#. Provider forms per family, reusing the PostgreSQL provider's field ids
   (corrected 2026-10-30: the PostgreSQL provider has no effective forms of
   this kind to reuse, and its descriptors use pgAdmin's own ids.
   CockroachDB compiles through the shared relational administration, so
   its forms keep that layer's ids, as Vitess, TiDB and Dolt do):
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
   effective forms, not from those drafts (see the correction above: the
   ids are the shared relational administration's).

Progress, 2026-10-30: the descriptor folder exists; trigger and role
(user, role) forms are ``complete``; database, table, index, sequence, view
and routine are drafts and type is pending. The table form's existing
columns take add, drop and rename only (the shared column diff), so a type,
default or nullability change on an existing column is not yet sent.
Update, same day: the table form is ``complete``
(``providers/cockroachdb/tables.py``). It creates tables with identity,
computed (stored or virtual), NOT VISIBLE, ON UPDATE, family and comment
per column, the four constraint kinds with foreign-key actions, row-level
TTL and a table comment; in alter mode it changes existing columns (type,
default, nullability, visibility, ON UPDATE, identity, stored to regular,
comment) and diffs each changed constraint grid against the table record.
Key membership and family stay fixed on existing columns.
The sequence and routine forms are ``complete`` too (``sequences.py``,
``routines.py``; the provider admits function and procedure alter).
The database form is ``complete`` the same day (``databases.py``), which
leaves no CockroachDB family form in draft. Row security policies followed as a new
``row-policy`` kind (``policies.py``; ``portfolio_catalog.json`` lists
it for CockroachDB), with a ``complete`` engine-object form.
The view (with materialized views; alter is admitted for them, which
``portfolio_catalog.json`` had excluded), index and type forms are
``complete`` the same day
(``providers/cockroachdb/indexes.py``, ``types.py``; the provider admits
type create, alter and drop).
