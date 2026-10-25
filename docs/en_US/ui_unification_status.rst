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
     - pending
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

* 2026-10-25: design adopted; descriptor schemas, ten family skeletons, engine
  stubs for the six beta engines, MySQL table worked example and the validator
  added. All other forms ``pending``.
