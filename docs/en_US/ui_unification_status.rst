.. _ui_unification_status:

UI unification status
=====================

Tracker for :doc:`ui_unified_design`. Updated by whoever moves a form, operation
or panel; counts are produced by ``python3 tools/validate_ui_descriptors.py --counts``
(``make ui-descriptors-check``). This page records progress; it never certifies
acceptance on its own.

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
     - in progress
     - ``ui_descriptors/schema``, ``ui_descriptors/families`` (10), validator in ``make check``; ESLint rules pending
   * - 2
     - Shell: tree, object editor, operation dialog, menu model
     - not started
     - 
   * - 3
     - Engine descriptors (Firebird, MySQL, MariaDB, DuckDB, SQLite)
     - in progress
     - Drafts generated for all six engines; review to ``complete`` per engine pending. Family table below
   * - 4
     - Operations, panels, menus
     - not started
     - Panel count below
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
     - draft (4f, 4g)
     - draft (8f, 2g)
     - draft (4f, 2g)
     - draft (11f, 7g)
   * - View
     - draft (27f, 2g)
     - draft (8f, 3g)
     - draft (3f, 2g)
     - draft (2f, 1g)
     - draft (5f, 0g)
     - draft (3f, 1g)
   * - Index
     - draft (24f, 2g)
     - draft (14f, 4g)
     - draft (5f, 1g)
     - draft (10f, 0g)
     - draft (5f, 0g)
     - draft (5f, 1g)
   * - Routine
     - draft (57f, 4g)
     - draft (48f, 8g)
     - draft (11f, 3g)
     - draft (9f, 0g)
     - draft (7f, 1g)
     - n/a
   * - Trigger
     - draft (30f, 3g)
     - draft (11f, 1g)
     - draft (8f, 2g)
     - draft (7f, 2g)
     - n/a
     - draft (8f, 2g)
   * - Sequence
     - draft (19f, 0g)
     - n/a
     - draft (8f, 0g)
     - draft (7f, 0g)
     - draft (7f, 1g)
     - n/a
   * - Type
     - draft (47f, 4g)
     - n/a
     - n/a
     - draft (7f, 0g)
     - draft (5f, 0g)
     - n/a
   * - Role
     - draft (18f, 2g)
     - draft (40f, 5g; privilege variant pending)
     - draft (22f, 2g)
     - draft (11f, 1g)
     - n/a
     - n/a
   * - Database
     - draft (33f, 2g)
     - pending (0f, 0g)
     - draft (6f, 0g)
     - draft (11f, 0g)
     - draft (2f, 3g)
     - draft (9f, 0g)
   * - Server
     - draft (46f, 5g)
     - pending (0f, 0g)
     - draft (32f, 0g)
     - draft (47f, 0g)
     - draft (4f, 2g)
     - draft (11f, 1g)

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
     - 8528
     - Phase 5 (deleted)
   * - ``relational_admin.py`` lines
     - 8942
     - Phase 3 (``_form()`` and ``catalog()`` patching removed)

Change log
----------

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

The privilege variant remains pending (0fields/1gap); the Role family is partial.
Named-account role aliases expose native membership actions without inventing
persisted CREATE ROLE origin. All accounts remain visible under Users for policy
editing. Initial role grants have separately acknowledged native statements; a
later grant failure does not undo creation. The legacy MySQL role field factory
and create-role dispatch were removed. Shared rendering/round trips remain
pending. Lint before/after: JSON303/303, MUI244/244, branches111/111, panels113/113.
