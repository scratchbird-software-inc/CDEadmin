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
     - not started
     - Family table below
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

Values are the ``status`` field of ``ui_descriptors/<engine>/forms/<family>.form.json``:
``pending`` (skeleton only), ``draft`` (fields listed), ``complete`` (round trip verified
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
     - pending
     - draft
     - pending
     - pending
     - pending
     - pending
   * - View
     - pending
     - draft
     - pending
     - pending
     - pending
     - pending
   * - Index
     - pending
     - pending
     - pending
     - pending
     - pending
     - pending
   * - Routine
     - pending
     - pending
     - pending
     - pending
     - pending
     - n/a
   * - Trigger
     - pending
     - pending
     - pending
     - pending
     - n/a
     - pending
   * - Sequence
     - pending
     - n/a
     - pending
     - pending
     - pending
     - n/a
   * - Type
     - pending
     - n/a
     - pending
     - pending
     - pending
     - n/a
   * - Role
     - pending
     - pending
     - pending
     - pending
     - n/a
     - n/a
   * - Database
     - pending
     - pending
     - pending
     - pending
     - pending
     - pending
   * - Server
     - pending
     - pending
     - pending
     - pending
     - pending
     - pending

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
