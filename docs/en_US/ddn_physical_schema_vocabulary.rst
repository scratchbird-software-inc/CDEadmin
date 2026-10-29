DDN physical-schema vocabulary (``x_record``)
*********************************************

Status: ``scratchrobin.physical-schema@1``, a ScratchRobin consumer convention
proposed to the DDN foundation under DDN-DB-004 (:doc:`ddn_database_roundtrip`).
DDN's public ``index`` and ``constraint`` element roles exist, but their property
schemas carry no key columns, uniqueness, predicate or referential actions, so the
facts below ride in the ``metadata.x_record`` of a companion record, exactly like the
native identities and column facts the ERD emitters already publish. Nothing here is
a DDN language change, and nothing relies on invented syntax.

Stream B items B1 (contract) and B3 (diagram-delta to plan adapters) of
:doc:`robin_master_plan` use this vocabulary. The code is
``workspace/physical_schema.py`` (shared rules), ``postgresql_physical.py`` and
``embedded_physical.py`` (SQLite, DuckDB), ``mysql_physical.py`` (MySQL, MariaDB), the reverse reader
``workspace/ddn/read_relations.mjs`` and the hand-off in
``firebird_relational_review.py``.

What the ERD emitters publish today
===================================

Every ``*_erd.py`` writes one workspace file ``relations.ddn`` whose header comment is
``// ScratchRobin mapping: scratchrobin.<engine>.relations``. This is the vocabulary
that already exists and is not changed by this document.

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - DDN construct
     - Content
   * - ``element ... as "table"`` or ``"view"``
     - ``title`` (display label, presentation only) and ``members`` (field refs). One
       per native relation. PostgreSQL also emits ``partitioned-table``,
       ``foreign-table`` and ``materialized-view`` natives under these two roles and
       records the exact native kind in ``native_kind``; SQLite adds ``virtual-table``
       and ``fts-table``.
   * - ``element ... as "field"``
     - ``title`` (column name), ``content`` with ``datatype`` and ``nullable`` and an
       optional ``description``. ``shape: array`` appears only through the
       annotation's ``field_properties_json`` (PostgreSQL, Firebird arrays).
   * - ``relation ... as "ref"``
     - One edge per visible foreign key, ``properties.enforcement = "database"`` and
       two ``endpoints``. Label ``name (cols) -> (cols)``. Foreign keys whose target is
       outside the visible selection are omitted with a warning, never redirected.
   * - ``view ... as "ddn@1"``
     - ``relations_N`` pages of at most 25 relations plus their one-hop FK targets;
       the layout and legend are presentation only.
   * - annotation record (``element "relations.mapping_<id>" as "record"``)
     - ``metadata.x_record`` envelope, below. One per annotated element.

The annotation envelope (identical for all six engines):

.. code-block:: text

   x_record:
     module   "scratchrobin.<engine>.relations"
     block    "relations"
     uid      "<engine>:<endpoint>:<database target>:<native resource id>"
     name_json  JSON text of the original native name
     exact_text_json  (only when a value contains CR, LF or NUL)
     record:
       subject_id    id of the annotated element
       subject_kind  the element's DDN role: table | view | field | ref
       ...           keys below

Keys by subject, as emitted before this document:

.. list-table::
   :header-rows: 1
   :widths: 14 22 64

   * - Subject
     - Keys
     - Engines and notes
   * - table, view
     - ``resource_id``, ``native_kind``, ``native_json``
     - All six. ``native_json`` is the exact native catalog facts and is the baseline
       authority. Firebird additionally nests ``diagram_columns`` (every column's
       native facts) inside ``native_json``.
   * - field
     - ``parent_id``, ``field_title_json``, ``field_properties_json``
     - All six. The field's ``uid`` is the parent uid plus ``:<attnum>`` (PostgreSQL),
       the column resource id (SQLite, DuckDB, Firebird) or the quoted column name
       (MySQL, MariaDB). Fields have no ``resource_id`` row of their own; the reader
       returns them under their parent.
   * - ref
     - ``native_json`` (always), ``resource_id`` (PostgreSQL, Firebird)
     - SQLite, DuckDB, MySQL and MariaDB edges carry the constraint JSON but no
       ``resource_id``, so the reader cannot return them as editable rows. Firebird
       edges also carry ``source_columns`` and ``target_columns`` inside
       ``native_json``.
   * - draft field
     - ``uid`` = ``<table uid>:new:<uuid>`` (PostgreSQL), ``ddn-new-field:<id>``
       (MySQL, MariaDB)
     - Annotation optional; unannotated PostgreSQL fields get a deterministic
       parent-scoped draft uid from the reader.

Vocabulary v1
=============

Keys are flat scalars in ``record``. ``*_json`` values are JSON text, like
``native_json``. Types are enforced: a mistyped or unknown key is an error, never
ignored.

.. list-table::
   :header-rows: 1
   :widths: 24 12 64

   * - Key
     - Type
     - Meaning
   * - ``physical_kind``
     - text
     - ``index``, ``primary-key``, ``unique``, ``check`` or ``foreign-key``.
       Required on new objects; on existing objects it states the baseline kind and
       cannot be edited.
   * - ``physical_name``
     - text
     - The native name of the table, column, index or constraint as of this design.
       Emitted for every table, column, index and constraint on PostgreSQL; on MySQL
       and MariaDB for every table, index, constraint and foreign key (columns are
       edited through their existing column annotation).
   * - ``rename_from``
     - text
     - The explicit rename mapping: the baseline native name. A rename is
       ``physical_name`` = new name together with ``rename_from`` = baseline name.
   * - ``columns_json``
     - JSON array
     - Ordered column names (1 to 32, distinct) of an index, PRIMARY KEY, UNIQUE or
       the referencing side of a FOREIGN KEY.
   * - ``unique``
     - bool
     - Index uniqueness.
   * - ``method``
     - text
     - Index access method (PostgreSQL: ``btree``, ``hash``, ...). Not used by MySQL or MariaDB (see ``index_type``).
   * - ``predicate``
     - text
     - Partial-index predicate (PostgreSQL, SQLite).
   * - ``expression``
     - text
     - CHECK expression, parsed by the native grammar before any statement exists.
   * - ``referenced_columns_json``
     - JSON array
     - Referenced columns of a FOREIGN KEY. The referenced table is the edge's target
       endpoint, so re-pointing the edge in the designer is a retarget.
   * - ``on_delete``, ``on_update``
     - text
     - ``NO ACTION``, ``RESTRICT``, ``CASCADE``, ``SET NULL`` or ``SET DEFAULT``
       (MariaDB has no ``SET DEFAULT``; an absent clause means ``NO ACTION`` on MySQL
       and ``RESTRICT`` on MariaDB).
   * - ``index_type``
     - text
     - MySQL, MariaDB: ``FULLTEXT`` or ``SPATIAL``; absent for an ordinary index.
   * - ``prefix_lengths_json``
     - JSON array
     - MySQL, MariaDB: one entry per key column, ``null`` or a prefix length 1 to 3072.
   * - ``directions_json``
     - JSON array
     - MySQL, MariaDB: one ``ASC`` or ``DESC`` per key column.
   * - ``visible``
     - bool
     - MySQL ``VISIBLE``/``INVISIBLE``; MariaDB ``NOT IGNORED``/``IGNORED``. Indexes
       and UNIQUE keys only. Changing it alone is ``ALTER INDEX``, not a replacement.
   * - ``enforced``
     - bool
     - MySQL CHECK ``ENFORCED``/``NOT ENFORCED``. MariaDB has no such clause and never
       emits it.
   * - ``drop``
     - bool
     - Explicit deletion intent. Never inferred.
   * - ``drop_confirmation``
     - text
     - Must equal the object's exact current native name when ``drop`` is true.

Subjects that carry the vocabulary:

* ``element ... as "index"`` (indexes) and ``element ... as "constraint"``
  (PRIMARY KEY, UNIQUE, CHECK), each listed in the owning table's ``members``. The
  annotation adds ``parent_id`` (the table element), ``resource_id``,
  ``native_kind`` and ``native_json`` for existing objects.
* ``relation ... as "ref"`` for FOREIGN KEY (the existing edge), with the vocabulary
  added to its annotation.
* table and field annotations carry only ``physical_name``, ``rename_from``,
  ``drop`` and ``drop_confirmation``.
* A **draft** is an annotated element with ``physical_kind`` and ``physical_name`` but
  no ``resource_id`` or ``native_json``. Its annotation ``uid`` must be
  ``<owning table uid>:new:<canonical uuid>``; the reader refuses any other draft
  identity. A FOREIGN KEY draft is a ``ref`` edge whose source endpoint is the owning
  table.

Example, PostgreSQL (abridged):

.. code-block:: text

   element "n_9f..." as "constraint"
       with
           id "n_9f..."
           title "child_parent_fk"
   element "relations.mapping_n_9f..." as "record"
       with
           title "child_parent_fk"
           metadata
               x_record
                   module "scratchrobin.postgresql.relations"
                   block "relations"
                   uid "postgresql:ep:postgresql-database:1:postgresql:pg_constraint:33217"
                   record
                       subject_kind "ref"
                       resource_id "postgresql:pg_constraint:33217"
                       native_json "{...exact pg_constraint facts...}"
                       physical_kind "foreign-key"
                       physical_name "child_parent_fk"
                       columns_json "[""parent_id""]"
                       referenced_columns_json "[""id""]"
                       on_delete "CASCADE"
                       on_update "RESTRICT"

Rules
-----

#. **Compare with the baseline vocabulary.** The hand-off compares the edited
   record with the baseline diagram's record, key by key. It never compares with a
   normalised catalog guess, so unedited objects produce no change.
#. **Omission is not intent.** A key missing from the edited record, an element
   missing from a view, or an element missing from the document never clears a
   property and never deletes anything. A view filter is not deletion intent.
#. **Renames are explicit.** A changed ``physical_name`` without ``rename_from`` is
   rejected. ``rename_from`` must equal the baseline name. Removing one element and
   adding another with a similar shape stays a drop plus an add and is never
   converted into a rename.
#. **Drops are explicit and confirmed twice.** ``drop: true`` needs
   ``drop_confirmation`` equal to the exact name, and the drop cannot be combined
   with other edits to the same object. The plan marks the operation
   ``destructive: true`` and repeats the name in ``confirmation``.
#. **A rename and a replacement are different plan shapes.** Changing columns,
   uniqueness, predicate, expression or actions replaces the object (a drop followed
   by an add under the wanted name, both marked ``replacement``). Only objects whose
   native properties are fully described by the vocabulary may be replaced; an index
   with expression keys, DESC ordering, operator classes or INCLUDE columns, or a
   constraint that is deferrable, ``NOT VALID``, inherited or ``MATCH FULL``, is
   refused with a request to edit it natively.
#. **Live drift wins.** A plan compares the live object's vocabulary with the
   baseline's. A difference is a blocker, not an overwrite. A replaced object has a
   new OID, so a replaced baseline object is reported as converged only when the same
   table already holds the wanted object under the wanted name and definition.
#. **No SQL from text.** Identifiers go through the engine's identifier quoting,
   expressions and predicates are parsed by the native grammar (``pglast`` for
   PostgreSQL, SQLite's own compiler for SQLite), and every statement is checked to
   be exactly one statement of the expected class before it enters a plan.

Plan entries produced
=====================

PostgreSQL (``postgresql_schema_plan.build_plan``; statements run only through the
existing reviewed application, which locks the table and re-plans before executing):

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - ``operation``
     - Statement
   * - ``add_index``
     - ``CREATE [UNIQUE] INDEX name ON schema.table USING method (cols) [WHERE (p)]``
   * - ``drop_index`` (+ ``destructive``)
     - ``DROP INDEX schema.name RESTRICT``
   * - ``rename_index``
     - ``ALTER INDEX schema.old RENAME TO new``
   * - ``add_constraint``
     - ``ALTER TABLE ONLY t ADD CONSTRAINT name PRIMARY KEY | UNIQUE | CHECK | FOREIGN KEY ...``
       with ``MATCH SIMPLE``, the stated ``ON UPDATE``/``ON DELETE``, ``NOT DEFERRABLE``
   * - ``drop_constraint`` (+ ``destructive``)
     - ``ALTER TABLE ONLY t DROP CONSTRAINT name RESTRICT``
   * - ``rename_constraint``
     - ``ALTER TABLE ONLY t RENAME CONSTRAINT old TO new``
   * - ``rename_relation``, ``rename_column``
     - existing adapters, now reachable from ``physical_name`` + ``rename_from``
   * - ``drop_relation``, ``drop_column`` (+ ``destructive``)
     - existing adapters, now reachable from ``drop`` + ``drop_confirmation``

Guards: a PRIMARY KEY or UNIQUE constraint that a foreign key depends on cannot be
dropped or replaced alone; a second PRIMARY KEY is refused; a foreign key needs a
visible target table whose referenced columns carry a PRIMARY KEY or UNIQUE
constraint; physical edits on partitioned, inheriting or inherited tables are refused;
a table rename and a column rename are reviewed separately (existing rule); a
constraint-backed index is edited through its constraint.

SQLite (``sqlite_schema_plan.plan``): ``create`` for a drafted index, ``replace`` for
an index whose columns, uniqueness or predicate changed. The desired row's DDL and
catalog metadata come from the drafted index built on a throwaway in-memory copy of the
table, so the post-apply comparison is exact.

DuckDB (``duckdb_schema_plan.plan``): ``create`` for a drafted index, ``drop`` for an
index carrying ``drop`` and the exact name (carried as the existing
``duckdb_change = {action: drop, confirmation: name}``). A replacement is a drop plus a
new index under a new name.

Firebird (``firebird_physical.py``, planned by ``firebird_schema_plan.build_plan`` and
``firebird_lifecycle_plan``; applied by ``schema_application.apply_review``, which runs
every statement of a review in one native transaction, commits once and rediscovers).
Differences from the PostgreSQL vocabulary, all Firebird facts:

* Index extras: ``descending`` (``CREATE DESCENDING INDEX``), ``inactive``
  (``ALTER INDEX x INACTIVE``/``ACTIVE``), ``expression`` for a ``COMPUTED BY`` index,
  ``predicate`` for a partial (``WHERE``) index, ``unique``. An index is keyed by columns
  or by one expression, never both. ``method`` does not apply.
* PRIMARY KEY, UNIQUE and FOREIGN KEY carry ``descending`` for their backing index. The
  constraint owns that index: it is edited through the constraint, and a constraint
  created from a draft creates a backing index of the same name
  (``USING ASCENDING|DESCENDING INDEX name``).
* PRIMARY KEY columns must already be NOT NULL (Firebird refuses otherwise); the hand-off
  says so before any SQL. A table has one PRIMARY KEY, and a PRIMARY KEY or UNIQUE key
  that a foreign key references cannot be replaced or dropped alone.
* FOREIGN KEY actions are ``NO ACTION`` (Firebird stores it as ``RESTRICT``), ``CASCADE``,
  ``SET NULL`` and ``SET DEFAULT``; ``on_update``/``on_delete`` outside that set and a
  target without a PRIMARY KEY or UNIQUE key on the referenced columns are rejected.
* Index and constraint names are database-wide; a draft that reuses a name is refused.
* Renames: only a **column** rename with ``physical_name`` + ``rename_from``
  (``ALTER TABLE t ALTER COLUMN old TO new``) is carried, and it must be reviewed apart
  from index and constraint changes on that table. Firebird 5.0 has no rename for tables,
  views, indexes or constraints; those mappings are rejected at the hand-off with
  ``Not carried to Firebird: ...`` and the reason, and produce no operation. A rename the engine refuses (for example a column a view
  depends on) is a blocker with the engine's reason.
* Drops: ``drop: true`` plus ``drop_confirmation`` equal to the exact name, for indexes,
  constraints, foreign keys, columns and tables. Operations are ``destructive: true``;
  column and table drops name the constraints and foreign keys they take with them, and
  a table that another table references is refused.
* A replaced index is ``DROP INDEX`` then ``CREATE INDEX`` under the same name in the same
  transaction (the plan carries ``operation: replace``); a changed constraint (operation
  ``alter``) is ``DROP CONSTRAINT`` then ``ADD CONSTRAINT``. A row that violates the new definition
  rolls the whole review back.
* A replayed review converges: after apply, planning the same baseline and desired
  documents against the new catalog yields no operations, because a live index or
  constraint that already equals the reviewed definition counts as converged. Any other
  object found live that the baseline did not have remains a blocker.

Per-kind matrix, Firebird 5.0.3 (``tools/tests/test_firebird_physical_roundtrip.py``).
Every cell was exercised live; "n/a" means the engine or the vocabulary has no such
operation, and "refused" means the hand-off or planner rejects it with a reason before
any SQL exists.

.. list-table::
   :header-rows: 1
   :widths: 17 11 18 12 20 22

   * - Kind
     - Forward
     - Edit (vocabulary)
     - Reverse
     - Plan (operation)
     - Apply, re-inspect
   * - index
     - ``index`` element, columns, ``unique``, ``descending``, ``inactive``
     - columns, unique, descending, inactive
     - hand-off diff
     - ``replace`` (DROP + CREATE), ``alter`` for active/inactive
     - ALTER INDEX; re-plan empty; next diagram carries the value
   * - index, computed / partial
     - ``expression``, ``predicate``
     - to and from key columns, expression, predicate
     - hand-off diff
     - ``replace``
     - converged; expression text read back
   * - index, new draft
     - n/a
     - draft element with ``<table uid>:new:<uuid>``; columns or expression; unique, descending, inactive
     - draft read
     - ``create`` (plus ``ALTER INDEX ... INACTIVE``)
     - converged; appears in next diagram
   * - index rename
     - ``physical_name``
     - ``physical_name`` + ``rename_from``
     - mapping read
     - not carried (no ``ALTER INDEX RENAME``): the hand-off rejects it with that reason; without ``rename_from``, rejected
     - nothing applied
   * - index drop
     - n/a
     - ``drop`` + exact name
     - drop intent
     - ``drop``, destructive; wrong name refused
     - DROP INDEX; index gone
   * - primary key
     - ``primary-key``, columns, ``descending``
     - columns; add on a table without one
     - hand-off diff
     - ``create`` or ``alter`` (DROP + ADD CONSTRAINT); nullable column, second key, referenced key refused
     - converged; backing index same name
   * - unique
     - ``unique``, columns
     - columns; new draft
     - hand-off diff
     - ``alter`` (DROP + ADD CONSTRAINT) or ``create``
     - converged
   * - check
     - ``check``, ``expression``
     - expression; new draft
     - hand-off diff
     - ``alter`` or ``create``; unparsable expression is a blocker
     - converged; engine enforces it
   * - foreign key
     - ``ref`` edge, columns, referenced columns, ``on_delete``, ``on_update``
     - actions, columns; new draft edge; ``NO ACTION`` stored as ``RESTRICT``
     - hand-off diff
     - ``alter`` or ``create``; bad action or target refused
     - converged; rules read from ``RDB$REF_CONSTRAINTS``
   * - constraint rename
     - ``physical_name``
     - ``physical_name`` + ``rename_from``
     - mapping read
     - not carried (no constraint rename): rejected at the hand-off
     - nothing applied
   * - constraint drop
     - n/a
     - ``drop`` + exact name
     - drop intent
     - ``drop``, destructive; referenced key refused
     - ALTER TABLE DROP CONSTRAINT
   * - column rename
     - ``physical_name`` on the field
     - ``physical_name`` + ``rename_from``
     - mapping read
     - ``rename``; never inferred without mapping; engine refusal is a blocker
     - ALTER COLUMN ... TO; converged
   * - column drop
     - n/a
     - ``drop`` + exact name
     - drop intent
     - ``drop``, destructive, names removed constraints
     - ALTER TABLE DROP column
   * - table rename
     - ``physical_name``
     - ``physical_name`` + ``rename_from``
     - mapping read
     - not carried (no table rename): rejected at the hand-off
     - nothing applied
   * - table drop
     - n/a
     - ``drop`` + exact name
     - drop intent
     - ``drop``, destructive; referenced table refused; parent and child together drop the foreign key first
     - DROP TABLE

Live drift between the baseline and the database blocks a plan instead of overwriting;
an object replaced or dropped live since the baseline is not resurrected; an unedited
diagram, and a diagram with omitted vocabulary keys, yield an empty plan.

MySQL and MariaDB (``mysql_schema_plan`` / ``mariadb_schema_plan`` through
``mysql_physical``): the whole native definition is one ``SHOW CREATE TABLE`` text, so
the vocabulary edits are applied to the desired definition's clauses and the clause
difference becomes **one ``ALTER TABLE`` per table** (``operation`` ``alter``; a
rename-only change is ``ALTER TABLE ... RENAME TO``). Each operation lists its
``changes`` (``object`` = ``index``, ``primary-key``, ``check``, ``foreign-key`` or
``column``; ``action`` = ``add``, ``drop``, ``replace``, ``rename`` or
``alter-visibility``).

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Change
     - Clause in the ``ALTER TABLE``
   * - add / replace index, UNIQUE
     - ``ADD [UNIQUE | FULLTEXT | SPATIAL] INDEX name (col[(prefix)] [DESC], ...)`` and
       ``INVISIBLE`` (MySQL) or ``IGNORED`` (MariaDB) when not visible
   * - rename index
     - ``RENAME INDEX old TO new``
   * - visibility only
     - ``ALTER INDEX name INVISIBLE | VISIBLE`` (MySQL), ``IGNORED | NOT IGNORED`` (MariaDB)
   * - PRIMARY KEY
     - ``ADD PRIMARY KEY (cols)``
   * - CHECK
     - ``ADD CONSTRAINT name CHECK (expr)`` (MySQL ``[NOT] ENFORCED``)
   * - FOREIGN KEY
     - ``ADD CONSTRAINT name FOREIGN KEY (cols) REFERENCES t (cols) ON DELETE ... ON UPDATE ...``
   * - drop (+ ``destructive``)
     - ``DROP INDEX``, ``DROP PRIMARY KEY``, ``DROP FOREIGN KEY``, ``DROP CHECK`` (MySQL) or
       ``DROP CONSTRAINT`` (MariaDB), ``DROP COLUMN``, ``DROP TABLE``
   * - column / table rename
     - ``CHANGE COLUMN old new <definition>`` (indexes follow the column), ``RENAME TO``

Rules specific to these engines: DDL is **not transactional**. Every statement commits
on its own and a failure cannot be rolled back, which the plan states
(``ordering_rule``): operations run creations, additions and in-place changes, foreign
key additions after the keys they need, table renames, and every drop last, so a failure
part-way leaves the schema a superset of the old one. Foreign-key checks are never
disabled and no ``ALGORITHM``/``LOCK`` hint is invented. A foreign key whose definition
changes needs a new name with ``rename_from``. Dropping a key a foreign key uses, a
column a key uses, or renaming a table and a column together is refused. A CHECK edit
accepts only ``expression`` and ``enforced``.

Convergence after apply tolerates what the server adds on its own: the plain index it
creates for a foreign key is named after that key (and is re-created under the new name
when the key is renamed), and every PRIMARY KEY column becomes ``NOT NULL``. A re-plan
ignores such an index and a missing ``DEFAULT NULL`` on key columns; every other
difference is still reported.

What is still missing
=====================

Vocabulary and engine coverage that no emitter or adapter provides yet. These are the
open items for Stream B (B1 vocabulary, B3 adapters); none is claimed by this document.

#. **Engines.** PostgreSQL, SQLite, DuckDB, Firebird, MySQL and MariaDB all emit and consume this
   vocabulary (Firebird and MySQL/MariaDB in their own sections above). For MySQL and MariaDB,
   functional (expression) key parts, ``USING BTREE|HASH``, index
   ``COMMENT``/``KEY_BLOCK_SIZE``/``PARSER``, ``WITHOUT OVERLAPS`` and period constraints,
   MariaDB system-versioning, and ``ALGORITHM``/``LOCK`` choice are read from the catalog but
   refused for replacement with a request to edit natively.
#. **SQLite and DuckDB constraints.** UNIQUE, CHECK, PRIMARY KEY and FOREIGN KEY edits
   need a table rebuild (SQLite ``rebuilds``, DuckDB ``rebuild-*`` actions) and are
   not expressed by the diagram. The reader rejects them. Their foreign-key edges are
   not editable rows.
#. **SQLite and DuckDB renames and drops.** SQLite renames and deletions are plan
   arguments plus row absence, which the diagram cannot state without removing catalog
   records; DuckDB renames create a new resource identity. Table, column and SQLite
   index renames/drops are rejected with a reason. DuckDB index replacement does not
   exist as a plan.
#. **Index detail.** Per-key ordering, operator class, collation, INCLUDE columns,
   ``NULLS NOT DISTINCT``, storage parameters and tablespace are not in the
   vocabulary; such indexes are read-only for replacement.
#. **Constraint detail.** ``DEFERRABLE``/``INITIALLY DEFERRED``, ``MATCH FULL``,
   ``NOT VALID``, exclusion constraints, ``NOT NULL`` as a named constraint (a column
   ``nullable`` edit remains the path) and domain constraints.
#. **Other physical facts named by the master plan**: defaults, identity and generated
   columns beyond the existing native edits, partitioning, views' defining queries,
   routines, triggers, sequences and domains.
#. **Designer-originated elements.** The reader requires an annotation (with the draft
   uid) on a new index, constraint or foreign key. An unannotated ``index`` or
   ``constraint`` element placed by the DDN designer is rejected rather than guessed;
   a designer palette entry that writes the annotation is needed.
#. **Expression equivalence.** Convergence after apply compares parsed expressions
   after removing the redundant string-literal casts PostgreSQL adds. Expressions that
   PostgreSQL rewrites further (for example ``IN`` lists) are reported as a name
   collision on the re-plan instead of converged, and the application's rediscovery
   flags them.
#. **Foreign-key retarget across schemas for non-PostgreSQL engines**, and
   cross-database references.
#. **Upstream.** The vocabulary is a ScratchRobin convention; it still has to be
   proposed to and agreed with the DDN repository before DDN tooling (designer
   inspector, table-records view columns) can present it.

Verification
============

Forward, edit, reverse and plan are exercised against real engines:

* ``tools/tests/test_postgresql_physical_roundtrip.py`` (live PostgreSQL, default port
  ``54329``, superuser ``qa``; override with ``QA_PG_PORT``): every object kind above,
  each followed by executing the planned statements and proving that a re-plan has
  nothing left to do.
* ``tools/tests/test_firebird_physical_roundtrip.py`` (live Firebird 5.0.x; set
  ``CDEADMIN_ROUNDTRIP_FIREBIRD`` to ``{"host","port","user","password","database_root"}``
  and ``CDEADMIN_FIREBIRD_CLIENT_LIBRARY`` to a Firebird 5 ``libfbclient``; skipped
  otherwise): every row of the matrix above, each applied through the real owned
  transaction and re-planned to nothing. The qualification gate
  ``tools/cdeadmin_firebird_ddn_exchange_gate.py`` has a ``physical`` scenario
  (``tools/firebird_physical_native.py``).
* ``tools/tests/test_sqlite_physical_roundtrip.py`` (``sqlite3``) and
  ``tools/tests/test_duckdb_physical_roundtrip.py`` (``duckdb``): index create, replace
  or drop, and the rejected edits.
* ``tools/tests/physical_roundtrip.py`` edits the vocabulary through DDN's public
  source-patch API (``tools/ddn_edit.mjs``), as a records-table edit would.

The container runs PostgreSQL 16 and the PostgreSQL 18.3 catalog capture reads
subscription columns that only exist in 17 and later; the live test drops
``pg_subscription`` from the capture for that reason, which does not affect tables,
indexes or constraints.

MySQL and MariaDB verification
------------------------------

* ``tools/tests/test_mysql_family_physical_roundtrip.py`` runs every scenario (index
  kinds, UNIQUE, CHECK, PRIMARY KEY, FOREIGN KEY actions, visibility, renames, drops,
  refusals) against three fixtures: ``mysql-golden`` (MySQL 9.7 profile), ``mariadb-golden``
  (MariaDB 12.2.2 profile) and ``mariadb-live``. The live fixture needs
  ``CDEADMIN_ROUNDTRIP_MARIADB='{"host":..,"port":..,"user":..,"password":..}'``; it applies
  each plan and proves the re-plan has nothing left to do.
* Evidence level: the container has MariaDB 10.11.14 only (``/usr/sbin/mariadbd``); no
  MySQL server is installed. MySQL behaviour is therefore compile and golden level
  against hand-built catalogs in the capture module's shape, not live. The MariaDB live
  fixture reads the 10.11.14 server's own catalog; only the 12.2.2 version pin and the two
  12.x-only tables (``PERIODS``, ``KEY_PERIOD_USAGE``) are masked. MariaDB 12.2 behaviour
  that differs from 10.11 is not exercised live. A live MySQL 9.7 run remains open.

Change log
==========

* 2026-10-28: ``scratchrobin.physical-schema@1`` extended for MySQL and MariaDB (additive
  keys ``index_type``, ``prefix_lengths_json``, ``directions_json``, ``visible``,
  ``enforced``); ``mysql_physical.py`` and the MySQL/MariaDB plan modules read index,
  UNIQUE, PRIMARY KEY, CHECK, FOREIGN KEY, rename and drop edits into one reviewed
  ``ALTER TABLE`` per table. PostgreSQL, SQLite and DuckDB behaviour is unchanged.
* 2026-10-28: ``scratchrobin.physical-schema@1`` introduced for PostgreSQL, SQLite and DuckDB.
