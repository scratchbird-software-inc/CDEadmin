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
     - draft (34f, 8g)
     - draft (4f, 4g)
     - draft (8f, 2g)
     - draft (4f, 2g)
     - draft (11f, 7g)
   * - View
     - draft (27f, 2g)
     - pending (0f, 0g)
     - draft (3f, 2g)
     - draft (2f, 1g)
     - draft (5f, 0g)
     - draft (3f, 1g)
   * - Index
     - draft (24f, 2g)
     - pending (0f, 0g)
     - draft (5f, 1g)
     - draft (10f, 0g)
     - draft (5f, 0g)
     - draft (5f, 1g)
   * - Routine
     - draft (57f, 4g)
     - pending (0f, 0g)
     - draft (11f, 3g)
     - draft (9f, 0g)
     - draft (7f, 1g)
     - n/a
   * - Trigger
     - draft (30f, 3g)
     - pending (0f, 0g)
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
     - pending (0f, 0g)
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
