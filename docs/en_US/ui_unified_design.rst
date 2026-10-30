CDEadmin Unified UI Architecture and Canonical Form Specifications
==================================================================

Owner direction 2026-10-25. Status: adopted. Authoritative source: this file; a live copy exists in Claude Docs.

Purpose
-------

This document is the single design authority for every form, dialog, menu and tree in CDEadmin, across all engines and all contributors (human or AI). It replaces per-engine form reviews, the "human form-validation team" deferral, and ad-hoc panel additions with one object-centric model that PostgreSQL already uses and every other engine must converge on.

It does three things:

1. Fixes the target architecture (Section 4) so new work lands in one place instead of a new branch of ``ProviderWorkspaceContent.jsx`` or ``relational_admin.py``.
2. Specifies the canonical forms for the ten object families (Sections 5 and 6) so a table, view, role or database looks and behaves the same on PostgreSQL, MySQL, MariaDB, Firebird, DuckDB and SQLite, with engine differences confined to declared fields and one engine-specific tab.
3. Gives a phased migration plan with acceptance gates (Section 9) and standing agent rules (Section 10) that go into ``AGENTS.md``.

Scope for beta 1: full UI for the six engines above; basic (generic operation form) UI for the other 20 connector roots. Closed-source engine features stay out of scope, as already recorded in ``AGENTS.md`` (owner correction 2026-10-20).

How to use it: an agent picking up any UI task reads Sections 3, 5, 8 and 10 first, then the family spec it touches in Section 6. A task that cannot be done within this design is reported as an open decision (Section 11), not solved with a one-off panel.

Current state
-------------

CDEadmin has two UI stacks that share no form code, and the one used by every non-PostgreSQL engine is operation-centric (pick object kind, pick operation, fill a flat field list) rather than object-centric (open the object, edit it in tabs). The backend is well ahead of the UI because successive agents were told form validation belonged elsewhere, so each feature landed on the cheapest surface available. Figures are from ``master`` at ``b8bbb6f`` (2026-10-25).

==================================== ============================================================================== ===============================================================================================================================================================================================
Concern                              PostgreSQL                                                                     MySQL / MariaDB / Firebird / DuckDB / SQLite (+20 others)
==================================== ============================================================================== ===============================================================================================================================================================================================
Workflow (provider manifest)         ``legacy_preserved``                                                           ``provider_endpoint``
Tree                                 74 pgAdmin node modules, one per object type                                   One generic node type ``cde_resource`` (``hasProperties: false``, ``hasSQL: false``); Firebird has a special-cased virtual layout in ``navigator.py``
Object editing                       ``BaseUISchema`` + ``SchemaView``: 71 ``*.ui.js``, 17.3k lines, tabbed dialogs Python form dicts rendered by ``VisualAdminField`` as a flat list; only Firebird declares ``editor.sections`` in ``portfolio_catalog.json``; MySQL, MariaDB, DuckDB, SQLite tables declare none
Where form fields are decided        One schema class per object                                                    ``RelationalAdministration._form()`` in ``relational_admin.py`` (8,942 lines): an ``if engine_id == … and kind == …`` ladder plus per-engine subclass patches
Features that don't fit a field list pgAdmin tools                                                                  113 hand-written MUI panels in ``static/js/Dialogs/`` (Firebird 39, MySQL 32, SQLite 18, DuckDB 10, MariaDB 3), mounted by string checks inside ``ProviderWorkspaceContent.jsx`` (8,528 lines)
Menus                                pgAdmin node menus                                                             Two systems: categorised ``ProviderContextMenu`` for objects; 14 flat MySQL/MariaDB server entries in ``server.js``, all priority 9, all engine-prefixed labels
SQL preview                          SQL tab on every dialog                                                        Plan preview in the confirm step; no SQL tab
Form tests                           One Jest spec per ``*.ui.js`` (70)                                             None per form definition; ~40 specs cover the shared renderer and feature panels
Design system                        n/a                                                                            ``cdeadmin_ui`` (63 Zero-Grey components) mandated by ``ARCHITECTURE.md``; forms and panels import ``@mui/material`` directly
==================================== ============================================================================== ===============================================================================================================================================================================================

Concrete symptoms the user sees today:

-  MySQL Create Table is name + a ``code`` box + a ``json`` box, with every table option (engine, charset, collation, row_format, auto_increment) in one JSON field (``mysql_table_options.py:70``). Columns and constraints are JSON controls with a generic record-list editor attached.
-  The generic fallback ``alter`` form is a JSON textarea labelled "Requested changes"; the generic ``execute`` is free-text "Native action" plus JSON arguments. Any engine × kind × operation not caught by the dispatcher lands there. 39 ``json`` controls remain in ``relational_admin.py`` alone.
-  Clicking a table on a provider engine opens a docked workspace with eight tabs (Database Properties, Resource Explorer, Data Studio, Edit Data, Administration, Operations & Health, Cubes & Semantic Models, Import & Bulk) and a second tree inside it, instead of a properties dialog.
-  Firebird and MariaDB get a grouped layout (``compactNativeForms``), nobody else does. Firebird's tree is unsorted by design, every other engine's is sorted. These forks are why switching engines feels different.
-  Capability is read from three unrelated sources (``context_menu.py`` descriptors, per-operation ``native_supported``/``execution_available`` flags, ``form_contracts.py`` ``supported``); no provider implements ``get_capabilities``.

What is sound and should be kept: the provider contract and exact-version engine contracts; the plan → validate → confirm → execute lifecycle with native plan preview; the categorised ``ProviderContextMenu`` descriptors; the ``editor.sections`` concept and Firebird's use of it; ``compact_forms.rst`` as the presentation rulebook; the append-only ``SR-F`` form reference registry; the Zero-Grey component set and Interface Designer; the backend test corpus (5,669 tests).

Design principles
-----------------

These rules are binding on every engine. A change that violates one is rejected in review regardless of what feature it adds.

1.  **Object-centric, not operation-centric.** The user navigates to an object in the tree and opens it. Editing happens in one tabbed dialog for that object. Operations (backup, analyze, grant, truncate) are menu items on the object, never a list the user searches for a kind in first.
2.  **Same family, same skeleton.** A table on Firebird has the same tabs, in the same order, with the same primitives, as a table on MySQL or PostgreSQL. The engine changes which fields appear inside a tab and which are read-only; it never changes the tab set, their order, or their names. Engine-only concepts go in one tab named after the engine.
3.  **Native fields, structured controls.** Every native option gets a typed control (text, number, select, checkbox, grid, key/value, code). ``json`` is not a user-facing control. A ``code`` control is used only for a body the user writes as SQL/PSQL (view definition, routine body, check expression, trigger body).
4.  **No engine branches in shared UI code.** The renderer, tree, menus and layout contain no ``engine_id === '…'`` checks. Engine behaviour is expressed in the engine's declarative form definitions and capability descriptors. If a behaviour needs a branch, it becomes a declared option that any engine can use.
5.  **Nothing is faked, nothing is hidden silently.** A field or operation an engine lacks is absent. A field an engine has but the connected version lacks is shown disabled with the version reason. A field the backend has not yet surfaced is a recorded gap, not an omission.
6.  **SQL on every mutating dialog.** Every create/edit dialog has a SQL (or native-command) tab showing exactly what plan → execute will run, read-only, before confirmation. This is the plan preview the lifecycle already produces, moved into the dialog.
7.  **One source of capability.** What is enabled comes from one capability descriptor per object kind per profile. Menus, tabs, fields and buttons all read it. No feature reads ``native_supported`` from one place and ``supported`` from another.
8.  **The tree is the only navigator.** One tree, in the browser pane, for all engines. No second tree inside a panel. Virtual folders are a declared layout option available to every engine, not a Firebird special case.
9.  **Design system or nothing.** Provider and form code imports ``cdeadmin_ui`` components only; direct ``@mui/material`` imports in provider code fail lint. ``compact_forms.rst`` governs geometry, density and wording.
10. **Declared, validated, tested.** Form definitions are declarative data validated against a schema at build time, with one rendering test per family per engine asserting the canonical tab set and the absence of raw JSON controls.
11. **Wording is for the user, not the auditor.** Labels name the thing ("Character set", "Engine"), not its provenance ("Exact native MySQL character set reference"). Help text carries the native term where it differs. The engine name is not repeated in menu labels under an engine node.
12. **Expansion is additive.** Adding an engine, a kind, or an operation means adding declarative files and a capability entry. It never requires editing ``ProviderWorkspaceContent.jsx``, ``relational_admin.py``, ``server.js`` or any shared renderer.

Target architecture
-------------------

One engine-agnostic UI shell (tree, object editor, operation dialog, tools) renders from one declarative capability-and-form descriptor per engine profile, built on ``cdeadmin_ui``, and executed by the existing provider backends. Adding an engine means adding a descriptor folder; nothing shared is edited.

.. code:: text

   +-----------------------------------------------------------------------+
   | Shared UI shell (engine-agnostic, zero engine branches)               |
   |  [Object tree]   [Object editor]   [Operation dialog]   [Tools]       |
   |  one tree,       canonical tabs    backup/analyze/     query tool,    |
   |  layout from     per family,       grant..., same      data grid,     |
   |  descriptor,     fields from       renderer, plan/     DDN dashboards |
   |  menus from      form definition,  confirm/receipt,    and ERD,       |
   |  capability      SQL tab = plan,   long-tail lives     opened from    |
   |                  Engine tab        here                menus          |
   +-----------------------------------------------------------------------+
                                  | renders with
   +-----------------------------------------------------------------------+
   | cdeadmin_ui design system: fields, grids, tabs, dialogs, menus        |
   | (the only import allowed in UI code)                                  |
   +-----------------------------------------------------------------------+
                                  | reads
   +-----------------------------------------------------------------------+
   | Capability + form descriptors (one per engine profile, declarative,   |
   | schema-validated): object kinds, tree layout, editor tabs and fields, |
   | operations and their forms, version gates, menu placement.            |
   | postgresql/ mysql/ mariadb/ firebird/ duckdb/ sqlite/ ... one folder  |
   | each; nothing shared is edited to add an engine.                      |
   +-----------------------------------------------------------------------+
                                  | generated from and executed by
   +-----------------------------------------------------------------------+
   | Provider backends (unchanged contract): discover / inspect / plan /   |
   | validate / apply / receipts; exact-version dialect and metrics        |
   | contracts; native utilities, sessions, monitoring collectors.         |
   | PostgreSQL keeps its SQL templates behind the same descriptor.        |
   +-----------------------------------------------------------------------+

The shell has no engine knowledge; the descriptor layer carries all of it; the provider layer is unchanged.

The five components
~~~~~~~~~~~~~~~~~~~

==================== ========================================================================================================================================== ==================================================================================================================================================================================================================
Component            Replaces                                                                                                                                   Rule
==================== ========================================================================================================================================== ==================================================================================================================================================================================================================
**Object tree**      pgAdmin node modules for PG, ``cde_resource`` + in-panel ``ResourceExplorer`` for others, Firebird virtual layout hook                     One tree. Node kinds, icons, folder layout, sort order and virtual folders come from the descriptor's ``navigator`` section. Every node has properties and a context menu. The in-panel tree is removed.
**Object editor**    ``BaseUISchema`` dialogs (PG), ``VisualAdministration`` object editing (others), ``FirebirdDatabaseProperties`` and similar property pages One tabbed dialog per object family (Section 5). Tabs and fields come from the descriptor's ``editor`` section. Read mode = properties; edit mode = same dialog. SQL tab shows the provider plan.
**Operation dialog** Generic ``VisualAdministration`` operation picker, the 113 one-off panels where they are forms                                             One grouped-field renderer (the current ``VisualAdminField`` set, cleaned up) for operations opened from menus. Field groups, confirmation and receipt are declared. Long-running tasks show the receipt/log pane.
**Menus**            pgAdmin menus, ``ProviderContextMenu``, flat ``server.js`` entries                                                                         One categorised menu model (``ProviderContextMenu`` categories become the standard). Items come from the descriptor's ``operations`` with ``menu`` placement. No engine prefixes in labels.
**Tools**            Query Tool, data grid, DDN dashboards/ERD, schema compare, import/export                                                                   Opened from menus or the toolbar. Not the landing surface for a tree click. The eight-tab Provider Workspace is dissolved into these.
==================== ========================================================================================================================================== ==================================================================================================================================================================================================================

The descriptor layer
~~~~~~~~~~~~~~~~~~~~

Each engine profile owns a folder of declarative files (format in Section 8): ``navigator.json``, one ``<family>.form.json`` per object family, ``operations.json``, ``capabilities.json``. These are what ``portfolio_catalog.json``, ``navigation_design.json``, ``relational_admin._form()``, the per-module ``form()`` functions and ``form_contracts.py`` become once split by engine and made data. The validator fails the build when a beta engine's relational table lacks the canonical tabs or any field uses a ``json`` control.

The descriptor is also the single capability source (Principle 7). ``context_menu.py``, the per-operation flags and ``form_contracts.supported`` are collapsed into it; version gates (``minimum_version``, ``maximum_version_exclusive``, exact-version) live on fields and operations so the editor can disable rather than hide.

Where PostgreSQL fits
~~~~~~~~~~~~~~~~~~~~~

PostgreSQL keeps its SQL templates and backend, but its UI moves behind the same descriptor so the six engines are treated identically by the shell. Practically: the PG ``*.ui.js`` schemas are the reference for the canonical tab vocabulary, and are migrated last, family by family, once the shared editor renders the other five engines. Until then the shell routes ``legacy_preserved`` kinds to the existing pgAdmin dialogs. Nothing PG currently does regresses; the migration is validated by the existing 70 ``*.ui.spec.js`` tests plus the new family tests.

What is deleted when this is done
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ProviderWorkspaceContent.jsx`` (8,528 lines), ``RelationalAdministration._form()`` and the ``catalog()`` patching, the engine checks in ``navigator.py`` and ``servers/__init__.py``, the flat engine menu entries in ``server.js``, ``FirebirdFormLayout.jsx`` as a special case, and most of the 113 panels (those that were forms). Panels that are real tools (dashboard viewers, log tails, cluster topology) are re-homed under Tools and keep their code.

The object-family model
-----------------------

Every object kind on every engine is assigned to one of ten families. The family fixes the dialog skeleton: tab set, tab order, tab names, and the primitive used inside each tab. The engine descriptor fills the fields. A kind that fits no family (Firebird shadows, MySQL resource groups, DuckDB secrets) is an **Engine object** and uses the generic family skeleton: General, Definition, Engine, Security, SQL.

Canonical tab vocabulary
~~~~~~~~~~~~~~~~~~~~~~~~

Tab names are fixed strings. A family uses a subset, always in this order. An engine may omit a tab only when it has no fields for it; it may never add a tab outside this list except the single Engine tab.

============ ============================================================== ========================================================================================================================================
Tab          Primitive                                                      Holds
============ ============================================================== ========================================================================================================================================
General      Field group                                                    Name, owner, container (schema/database), comment, and the two or three options a user sets every time
Definition   Code editor (SQL/PSQL) or structured group                     The body: view query, routine source, trigger body, check expression, domain base type
Columns      Column grid                                                    Name, type (picker), length/precision/scale, nullable, default, identity/autoincrement, collation, computed expression, comment; reorder
Constraints  Nested tabs: Primary key, Foreign keys, Unique, Check, Exclude One grid per constraint kind
Indexes      Grid                                                           Existing indexes on the object with open-in-editor
Triggers     Grid                                                           Existing triggers with open-in-editor
Parameters   Grid or key/value                                              Routine arguments; storage/runtime parameters where the engine has a named list (PG ``WITH``, PG ``SET``)
Partitions   Grid + strategy group                                          Partition strategy, key, partitions list
Options      Field group                                                    Engine-neutral options the family always has (fill factor, tablespace, charset/collation, deterministic, security invoker/definer)
Engine       Field group                                                    Everything that exists only on this engine, named for the engine ("MySQL", "Firebird"). Help text carries the native keyword
Security     Privilege grid + security labels/policies                      Grants per grantee with grant option; default privileges where the engine has them
Dependencies Two read-only grids                                            Depends on / dependents
Statistics   Read-only property groups                                      Live counters where the engine exposes them
Data         Paged data grid                                                Rows, following ``compact_forms.rst`` session rules
SQL          Read-only code                                                 The exact plan the provider will execute (create: full DDL; edit: the ALTER set). Replaces the confirm-step preview
============ ============================================================== ========================================================================================================================================

Families and their tab sets
~~~~~~~~~~~~~~~~~~~~~~~~~~~

======== =================================================================================================================================== ==============================================================================================================================================================
Family   Kinds mapped to it (across the six engines)                                                                                         Tabs
======== =================================================================================================================================== ==============================================================================================================================================================
Table    table, partition, foreign table (PG), materialized view (PG) as a variant                                                           General, Columns, Constraints, Indexes, Triggers, Partitions, Options, Engine, Security, Dependencies, Statistics, Data, SQL
View     view, materialized view (non-PG where present)                                                                                      General, Definition, Columns (read-only), Triggers (Firebird, PG instead-of, SQLite), Options, Engine, Security, Dependencies, Data, SQL
Index    index, unique index, expression index, spatial/fulltext (MySQL), computed/partial (Firebird)                                        General (table, columns/expressions grid, unique, method), Options, Engine, Dependencies, Statistics, SQL
Routine  function, procedure, package/package body (Firebird, MariaDB), macro (DuckDB), event (MySQL) as a scheduled variant, aggregate (PG) General, Parameters, Definition, Options, Engine, Security, Dependencies, SQL
Trigger  table trigger, view trigger, database/DDL trigger (Firebird, PG event trigger)                                                      General (object, timing, events, per row/statement, position/order), Definition, Options, Engine, Dependencies, SQL
Sequence sequence (PG, MariaDB, DuckDB), generator (Firebird), identity backing (read-only)                                                  General (start, increment, min, max, cycle, cache, current value), Engine, Security, Dependencies, SQL
Type     domain (PG, Firebird), type/enum/composite/range (PG), enum/struct/union (DuckDB)                                                   General (base type, default, not null, collation), Constraints (checks), Engine, Security, Dependencies, SQL
Role     role, user, group; MySQL/MariaDB user@host accounts; Firebird users and roles; SQLite none; DuckDB none                             General (name, host where applicable, password, login/expiry, limits), Membership (grid), Privileges (object grants grid, system privileges), Engine, SQL
Database database (PG, MySQL, MariaDB), database file/alias (Firebird, SQLite, DuckDB), attached database (SQLite, DuckDB)                   General, Options (charset/collation/dialect/page size), Engine, Security, Parameters (PG), Statistics, SQL
Server   server/endpoint registration and connection                                                                                         Connection, Authentication, SSL/TLS, Advanced, Engine (service manager, client library, routing), Tags/Group — registration is not a DDL object, so no SQL tab
======== =================================================================================================================================== ==============================================================================================================================================================

Two rules close gaps:

-  A family tab that exists on PostgreSQL today and on no other engine (PG table Inheritance, PG Advanced > Of type) goes under that engine's Engine tab, not a new canonical tab. The canonical list is the cross-engine intersection plus Engine.
-  A concept that is first-class on two or more of the six engines but is not a tab above (partitions, scheduled events, system versioning) is proposed as a new canonical tab through Section 11, not added by one engine alone.

Canonical form specifications
-----------------------------

Each family below gives the shared skeleton (tabs and fields every engine renders when it has the concept), then a per-engine matrix of what the six providers expose today and what changes. Fields are named by the ``field_id`` the descriptor will use; existing backend field ids are reused where they exist so no provider plan/validate/apply code changes. "Today" cells quote the current control so the gap is visible: **JSON** = raw JSON textarea to replace, [E] = JSON with a record-list editor to convert to a grid, PG = pgAdmin legacy dialog to port.

Legend for matrix cells: ✓ = exposed by the provider today; ✓v = exposed with a version gate needed; ✗ = engine has no such concept (tab or field omitted); gap = engine has the concept, provider does not expose it yet (recorded, not faked).

.. _61-table:

6.1 Table
~~~~~~~~~

**Tabs:** General · Columns · Constraints · Indexes · Triggers · Partitions · Options · Engine · Security · Dependencies · Statistics · Data · SQL

=============================================================================================================================================================================================== =================================================================================================== ====================================================================================================================================================================== ========================================================================================== =============================================================================================== ==================== =============================================================== =====================================================================================================================================================================================================================================
Tab / field                                                                                                                                                                                     PostgreSQL                                                                                          MySQL                                                                                                                                                                  MariaDB                                                                                    Firebird                                                                                        DuckDB               SQLite                                                          Today
=============================================================================================================================================================================================== =================================================================================================== ====================================================================================================================================================================== ========================================================================================== =============================================================================================== ==================== =============================================================== =====================================================================================================================================================================================================================================
General: ``name``, ``parent`` (schema / database), ``comment``                                                                                                                                  ✓                                                                                                   ✓                                                                                                                                                                      ✓                                                                                          ✓ (no schema)                                                                                   ✓                    ✓                                                               ✓
General: ``table_type`` (ordinary / temporary / unlogged / GTT / external / virtual)                                                                                                            ✓ (``relpersistence``)                                                                              ✓ (temporary)                                                                                                                                                          ✓                                                                                          ✓ (``table_type``, ``on_commit``, ``external_file``)                                            ✓ (temporary)        ✓ (temporary, ``virtual-table`` kind, ``fts-table`` kind)       Firebird ✓; SQLite virtual tables are separate kinds, fold into a type select
Columns grid: ``name``, ``type`` (picker from dialect), ``length``, ``precision``, ``scale``, ``nullable``, ``default``, ``identity``, ``collation``, ``computed`` (code), ``comment``, reorder ✓ PG                                                                                                [E] 6 fields                                                                                                                                                           [E] 6 fields                                                                               [E] full (domain, blob subtype, charset, collation, generation, expression, dimensions)         [E] 6 fields         [E] 6 fields                                                    Grid; MySQL/MariaDB/DuckDB/SQLite items gain length/precision/collation/comment/identity (backend already parses them in ``_structured_record_controls``); Firebird keeps ``domain`` and ``dimensions`` as Engine columns of the grid
Constraints: Primary key, Unique, Foreign key, Check, Exclude (PG)                                                                                                                              ✓ PG                                                                                                [E]                                                                                                                                                                    [E]                                                                                        [E]                                                                                             [E]                  [E]                                                             Nested tabs with one grid each; FK grid has referenced table picker, column pairs, on update / on delete, deferrable (PG, Firebird)
Indexes (read-only grid, open → Index editor)                                                                                                                                                   ✓                                                                                                   ✓                                                                                                                                                                      ✓                                                                                          ✓                                                                                               ✓                    ✓                                                               New: read from catalog
Triggers (read-only grid, open → Trigger editor)                                                                                                                                                ✓                                                                                                   ✓                                                                                                                                                                      ✓                                                                                          ✓                                                                                               ✗                    ✓                                                               New
Partitions: ``is_partitioned``, ``partition_type``, ``partition_keys``, partitions grid; actions add / coalesce / reorganize / exchange / truncate / drop / remove                              ✓ PG                                                                                                ✓ (``partition_by``, ``add_partitions``, ``coalesce_partitions``, ``remove_partitioning``, partition kind ops)                                                         ✓ (+ ``convert_from_table``, ``convert_to_table``, repair)                                 ✗                                                                                               ✗                    ✗                                                               Promote from loose operations to the tab (open decision 4)
Options: ``tablespace``, ``fillfactor``, ``character_set``, ``collation``, ``sql_security``, ``with_oids``-class toggles                                                                        ✓ (``spcname``, ``fillfactor``)                                                                     ✓ (charset, collation, tablespace)                                                                                                                                     ✓                                                                                          ✓ (``sql_security``, ``publication``)                                                           ✗                    ✓ (``WITHOUT ROWID``, ``STRICT``: gap — read-only flags today)  MySQL: split out of ``mysql_table_options`` JSON
Engine tab                                                                                                                                                                                      Inheritance (``coll_inherits``), Of type, ``like_relation``, replica identity, RLS, vacuum settings ``engine``, ``row_format``, ``auto_increment``, ``encryption``, ``compression``, ``secondary_engine``, ``key_block_size``, ``stats_*``, index key-cache assign/preload as MySQL + system versioning (gap: not a kind today), ``transactional``, ``page_checksum`` ``on_commit``, ``external_file``, ``publication``; ``recreate``, ``reorder_columns`` as actions ✗ (no table options) ``module``, ``module_options`` for virtual/FTS (today raw JSON) MySQL: one typed field per option from ``mysql_table_options.py`` (``field()`` already lists them)
Security: privilege grid (``grantee``, privileges, grant option, column lists)                                                                                                                  ✓ (``relacl``)                                                                                      ✓ via ``privilege.grant``                                                                                                                                              ✓                                                                                          ✓ (``grant``/``revoke`` on table with ``update_columns``, ``reference_columns``)                ✗                    ✗                                                               Firebird column lists become sub-grid
Dependencies, Statistics                                                                                                                                                                        ✓                                                                                                   ✓ (stats via catalog)                                                                                                                                                  ✓                                                                                          ✓ (sections already declared)                                                                   ✓                    ✓                                                               Read-only
Data                                                                                                                                                                                            ✓                                                                                                   ✓                                                                                                                                                                      ✓                                                                                          ✓ (``firebird-row-grid`` session rules)                                                         ✓                    ✓                                                               Existing paged grid
SQL                                                                                                                                                                                             ✓                                                                                                   plan                                                                                                                                                                   plan                                                                                       plan                                                                                            plan                 plan                                                            Move plan preview into the tab
=============================================================================================================================================================================================== =================================================================================================== ====================================================================================================================================================================== ========================================================================================== =============================================================================================== ==================== =============================================================== =====================================================================================================================================================================================================================================

Alter mode: the same dialog, prefilled; the SQL tab shows the ALTER set. ``add_columns`` / ``drop_columns`` / ``rename_columns`` disappear as separate forms; the column grid diff produces them. MySQL ``MySQLControlledChange`` (ALGORITHM / LOCK) becomes an Options group shown only in alter mode. SQLite ``SQLiteAlterDesign`` / ``SQLiteColumnDesign`` (table rebuild) become the SQLite behaviour of the same alter flow with the rebuild plan shown on the SQL tab.

.. _62-view:

6.2 View
~~~~~~~~

**Tabs:** General · Definition · Columns · Triggers · Options · Engine · Security · Dependencies · Data · SQL

======================================================================================================= ================================================ ========================================================================================= =========== ======================================================= ====================================== =========== ==================================================================================================
Tab / field                                                                                             PostgreSQL                                       MySQL                                                                                     MariaDB     Firebird                                                DuckDB                                 SQLite      Today
======================================================================================================= ================================================ ========================================================================================= =========== ======================================================= ====================================== =========== ==================================================================================================
General: ``name``, ``parent``, ``comment``, ``materialized`` (variant switch)                           ✓ (+ ``materialized-view`` kind)                 ✓ (+ ``materialized-view`` kind)                                                          ✓           ✓                                                       ✓                                      ✓           Materialized is a variant that adds Options fields (``with_data``, ``tablespace``, refresh action)
Definition: ``query`` (code, SQL)                                                                       ✓ ``definition``                                 ✓ ``definition`` (multiline today)                                                        ✓ ``query`` ✓ ``query`` / ``definition``                            ✓ ``query``                            ✓ ``query`` Normalise to ``query``, code control
Columns: column alias list (grid)                                                                       ✗                                                **JSON** ``columns``                                                                      gap         [E] ``columns``                                         ✗                                      ✗           Grid of names
Triggers (read-only grid)                                                                               ✓ (instead-of)                                   ✗                                                                                         ✗           ✓                                                       ✗                                      ✓           New
Options: ``check_option``, ``security_barrier``, ``security_invoker`` / ``sql_security``, ``algorithm`` ✓                                                ✓ (``algorithm``, ``sql_security``, ``check_option``, ``definer_user``, ``definer_host``) gap         ✗                                                       ✗                                      ✗           Definer as one ``definer`` field with ``user@host`` picker
Engine                                                                                                  ``with_data``, ``amname``, vacuum (materialized) —                                                                                         —           ``create_or_alter``, ``recreate`` actions; view row DML ``duckdb.view.alter`` acknowledgements —           DuckDB acknowledgements become the confirm step, not fields
Security                                                                                                ✓                                                ✓                                                                                         ✓           ✓                                                       ✗                                      ✗           
Dependencies, Data, SQL                                                                                 ✓                                                ✓                                                                                         ✓           ✓                                                       ✓                                      ✓           
======================================================================================================= ================================================ ========================================================================================= =========== ======================================================= ====================================== =========== ==================================================================================================

.. _63-index:

6.3 Index
~~~~~~~~~

**Tabs:** General · Options · Engine · Dependencies · Statistics · SQL

========================================================================================================================================================= ================================= ====================================================== ======== ========================================== =========== ======= =========================================================================
Tab / field                                                                                                                                               PostgreSQL                        MySQL                                                  MariaDB  Firebird                                   DuckDB      SQLite  Today
========================================================================================================================================================= ================================= ====================================================== ======== ========================================== =========== ======= =========================================================================
General: ``name``, ``table`` (picker), ``unique``, columns grid (``column`` or ``expression``, ``sort_order``, ``nulls``, ``collation``, ``opclass``)     ✓                                 [E]                                                    [E]      [E] + ``expression``, ``direction``        [E]         [E]     Grid; expression and direction are per-row columns, not form-level fields
General: ``where`` (partial / ``condition``)                                                                                                              ✓                                 ✗                                                      ✗        ✓ ``condition``                            ✗           ✓ (gap) 
Options: ``method`` / ``index_kind`` (btree, hash, gin, …; fulltext, spatial; Firebird kind), ``include``, ``fillfactor``, ``concurrent``, ``tablespace`` ✓                                 ✓ (``index_kind`` gap: BTREE/HASH/FULLTEXT/SPATIAL)    ✓        ✓ ``index_kind``                           ✗           ✗       
Engine                                                                                                                                                    ``nulls not distinct``, clustered ``visibility`` (action today), key block size, comment as MySQL ``active``, ``refresh_statistics`` (alter) ``comment`` —       Visibility and active become checkboxes in alter mode
Dependencies, Statistics, SQL                                                                                                                             ✓                                 ✓                                                      ✓        ✓                                          ✓           ✓       
========================================================================================================================================================= ================================= ====================================================== ======== ========================================== =========== ======= =========================================================================

.. _64-routine:

6.4 Routine
~~~~~~~~~~~

Covers function, procedure, package, macro, external function, exception and scheduled event. The family has three variants chosen on General: **Routine** (function / procedure), **Package** (header + body), **Scheduled** (MySQL / MariaDB event). Firebird ``exception`` and ``external-function`` are Engine objects that borrow this skeleton.

**Tabs:** General · Parameters · Definition · Options · Engine · Security · Dependencies · SQL

========================================================================================================================================================== ======================================== =============================================================================================================== ======================================================== ==================================================================================================================================================================================== ================================================== ====== ================================================================================
Tab / field                                                                                                                                                PostgreSQL                               MySQL                                                                                                           MariaDB                                                  Firebird                                                                                                                                                                             DuckDB                                             SQLite Today
========================================================================================================================================================== ======================================== =============================================================================================================== ======================================================== ==================================================================================================================================================================================== ================================================== ====== ================================================================================
General: ``name``, ``parent``, ``routine_kind`` (function / procedure / package / macro / event), ``returns`` (type picker), ``language``                  ✓                                        ✓ (``returns``)                                                                                                 ✓                                                        ✓ (``returns``)                                                                                                                                                                      ✓ macro (``table_macro`` → kind)                   ✗      
Parameters grid: ``name``, ``mode`` (in / out / inout / variadic), ``type``, ``default``                                                                   ✓ ``arguments``                          [E] ``parameters``, **JSON** ``return_parameters``                                                              [E] / **JSON**                                           [E] ``parameters``, [E] ``return_parameters``                                                                                                                                        **JSON** ``parameters``                            ✗      One grid; output parameters are rows with mode ``out``
Definition: ``body`` (code, language-aware); Package variant: ``header`` + ``body`` as two code panes                                                      ✓ ``prosrc``                             ✓ ``body``                                                                                                      ✓ (``header``, ``body`` for package)                     ✓ ``body`` / ``header`` / ``declaration``                                                                                                                                            ✓ ``expression`` / ``source``                      ✗      ``declaration`` (whole CREATE OR ALTER text) is retired; the editor generates it
Options: ``security`` (definer / invoker), ``deterministic``, ``data_access``, ``volatility``, ``strict``, ``parallel``, ``cost``, ``rows``, ``leakproof`` ✓                                        ✓ (``sql_security``, ``data_access``, alter-only today)                                                         ✓                                                        ✓ (``sql_security``)                                                                                                                                                                 ✗                                                  ✗      Alter-only MySQL options move to the shared tab in both modes
Scheduled variant (Options): ``schedule``, ``completion``, ``status`` / ``enabled``, ``time_zone``, ``preserve``                                           ✗ (pg_cron not in scope)                 ✓ event                                                                                                         ✓ event                                                  ✗                                                                                                                                                                                    ✗                                                  ✗      
Engine                                                                                                                                                     ``probin``, ``proretset``, ``variables`` ``definer``, ``library``, ``loadable-function`` (``return_type``, ``aggregate``, ``library``) as Engine objects ``loadable-function``, package spec/body replace actions ``create_or_alter`` / ``recreate`` actions, ``external-function`` (``entrypoint``, ``module_name``, return mechanism) as Engine object, ``exception`` (``message``) as Engine object DuckDB macro alter acknowledgements → confirm step —      
Security                                                                                                                                                   ✓ ``acl``                                ✓                                                                                                               ✓                                                        ✓ grant / revoke (EXECUTE)                                                                                                                                                           ✗                                                  ✗      
Dependencies, SQL                                                                                                                                          ✓                                        ✓                                                                                                               ✓                                                        ✓                                                                                                                                                                                    ✓                                                  ✓      
========================================================================================================================================================== ======================================== =============================================================================================================== ======================================================== ==================================================================================================================================================================================== ================================================== ====== ================================================================================

.. _65-trigger:

6.5 Trigger
~~~~~~~~~~~

**Tabs:** General · Definition · Options · Engine · Dependencies · SQL

========================================================================================================================================================================================================================================================================================================== ============================================== ============================================================== ======= ========================================================== ====== ================ ===================================================
Tab / field                                                                                                                                                                                                                                                                                                PostgreSQL                                     MySQL                                                          MariaDB Firebird                                                   DuckDB SQLite           Today
========================================================================================================================================================================================================================================================================================================== ============================================== ============================================================== ======= ========================================================== ====== ================ ===================================================
General: ``name``, ``table`` / ``view`` picker, ``scope`` (table / view / database / DDL), ``timing`` (before / after / instead of), ``events`` (checkbox group: insert, update, delete, truncate; Firebird connect/transaction/DDL events), ``columns`` (update of), ``active``, ``position`` / ``order`` ✓ ``fires``, ``evnt_*``, ``is_enable_trigger`` ✓ timing select, **JSON** ``events``, ``active``, ``position`` same    same + database triggers                                   ✗      ✓                ``events`` becomes a checkbox group on every engine
General: ``granularity`` (row / statement), ``when`` condition                                                                                                                                                                                                                                             ✓ ``is_row_trigger``, ``whenclause``           ✗ (row only)                                                   ✗       ✗                                                          ✗      ✓ ``WHEN`` (gap) 
Definition: ``body`` (code) or ``function`` picker (PG)                                                                                                                                                                                                                                                    ✓ ``tfunction``, ``tgargs``                    ✓ ``body``                                                     ✓       ✓ ``body``                                                 ✗      ✓ ``body``       
Options: ``deferrable``, ``constraint trigger``, transition tables                                                                                                                                                                                                                                         ✓                                              ✗                                                              ✗       ✗                                                          ✗      ✗                PG-only → Engine tab
Engine                                                                                                                                                                                                                                                                                                     ``rule``, ``event-trigger`` as Engine objects  ``follows`` / ``precedes`` (gap)                               same    ``create_or_alter``, ``recreate``; ``declaration`` retired —      —                
Dependencies, SQL                                                                                                                                                                                                                                                                                          ✓                                              ✓                                                              ✓       ✓                                                          —      ✓                
========================================================================================================================================================================================================================================================================================================== ============================================== ============================================================== ======= ========================================================== ====== ================ ===================================================

.. _66-sequence:

6.6 Sequence
~~~~~~~~~~~~

**Tabs:** General · Engine · Security · Dependencies · SQL

======================================================================================================================================================================================================== ====================================================== ======================================= ======================================= ================================================================================================ ======================= ====== ================================================
Tab / field                                                                                                                                                                                              PostgreSQL                                             MySQL                                   MariaDB                                 Firebird                                                                                         DuckDB                  SQLite Today
======================================================================================================================================================================================================== ====================================================== ======================================= ======================================= ================================================================================================ ======================= ====== ================================================
General: ``name``, ``parent``, ``start``, ``increment``, ``minimum``, ``maximum``, ``cycle``, ``cache``, ``current_value`` (read-only in create, editable in alter = restart / set_current), ``comment`` ✓                                                      ✗ (AUTO_INCREMENT is a column property) ✓ (``restart`` in alter)                ✓ (``start``, ``increment``, ``description``; ``set_current``, ``restart``, ``restart_initial``) ✓ (no alter today: gap) ✗      Firebird ``start`` is text today; make it number
Engine                                                                                                                                                                                                   ``owned_table`` / ``owned_column``, ``relpersistence`` —                                       ``nocache``, ``nominvalue`` style flags ``create_or_alter``, ``recreate`` actions                                                        —                       —      
Security                                                                                                                                                                                                 ✓                                                      —                                       ✓                                       ✓ grant / revoke (USAGE)                                                                         ✗                       —      
Dependencies, SQL                                                                                                                                                                                        ✓                                                      —                                       ✓                                       ✓                                                                                                ✓                       —      
======================================================================================================================================================================================================== ====================================================== ======================================= ======================================= ================================================================================================ ======================= ====== ================================================

MySQL and SQLite omit the family. Identity columns on every engine are shown on the Columns grid of the owning table; the sequence that backs a PG identity appears read-only under Dependencies.

.. _67-type:

6.7 Type
~~~~~~~~

Covers domain, enum / composite / range / base types, DuckDB alias / enum / struct / union, collations and character sets as Engine objects.

**Tabs:** General · Constraints · Engine · Security · Dependencies · SQL

================================================================================================================================================================================================================================== ===================================================================================================================================================== ========================================== ======= ========================================================================================================================================================================= ===================================== ======================= ============================================
Tab / field                                                                                                                                                                                                                        PostgreSQL                                                                                                                                            MySQL                                      MariaDB Firebird                                                                                                                                                                  DuckDB                                SQLite                  Today
================================================================================================================================================================================================================================== ===================================================================================================================================================== ========================================== ======= ========================================================================================================================================================================= ===================================== ======================= ============================================
General: ``name``, ``parent``, ``type_kind`` (domain / enum / composite / range / alias / struct / union / external), ``base_type``, ``length`` / ``precision`` / ``scale``, ``default``, ``not_null``, ``collation``, ``comment`` ✓ domain + type                                                                                                                                       ✗                                          ✗       ✓ domain (``data_type``, ``default``, ``not_null``, ``check``)                                                                                                            ✓ type (``type_kind``, ``base_type``) ✗                       
General: members grid (enum labels; struct / composite fields ``name`` + ``type``)                                                                                                                                                 ✓ ``composite``, ``enum``                                                                                                                             ✗                                          ✗       ✗                                                                                                                                                                         [E] ``enum_values``, [E] ``fields``   ✗                       Grid
Constraints: check grid (``name``, ``expression``, ``validated``)                                                                                                                                                                  ✓                                                                                                                                                     ✗                                          ✗       ✓ ``check``, ``drop_constraint``                                                                                                                                          ✗                                     ✗                       Firebird single check becomes a one-row grid
Engine                                                                                                                                                                                                                             range subtype / canonical / diff, external I/O functions, ``cast``, ``conversion``, ``operator*``, ``access-method``, ``transform`` as Engine objects ``character-set``, ``collation`` read-only same    ``character-set`` (alter default collation), ``collation`` (create: ``base_collation``, padding, case / accent sensitivity, [E] ``specific_attributes``), ``blob-filter`` —                                     ``collation`` read-only 
Security, Dependencies, SQL                                                                                                                                                                                                        ✓                                                                                                                                                     —                                          —       ✓                                                                                                                                                                         ✓                                     —                       
================================================================================================================================================================================================================================== ===================================================================================================================================================== ========================================== ======= ========================================================================================================================================================================= ===================================== ======================= ============================================

.. _68-role:

6.8 Role
~~~~~~~~

Covers roles, users and user@host accounts, their membership, and object or system privileges. Grants on a specific object are also reachable from that object's Security tab; this family is the grantee-side view.

**Tabs:** General · Membership · Privileges · Engine · SQL

===================================================================================================================================================================================================================================== ================================================================================================================ ========================================================================= =================================================================================================================== ============================================================================================================================================ =========================================================================================== ====== =========================================================================
Tab / field                                                                                                                                                                                                                           PostgreSQL                                                                                                       MySQL                                                                     MariaDB                                                                                                             Firebird                                                                                                                                     DuckDB                                                                                      SQLite Today
===================================================================================================================================================================================================================================== ================================================================================================================ ========================================================================= =================================================================================================================== ============================================================================================================================================ =========================================================================================== ====== =========================================================================
General: ``name``, ``host`` (MySQL / MariaDB), ``role_kind`` (login user / group role), ``password``, ``password_expiry`` / ``valid_until``, ``plugin`` / ``auth_method``, ``active`` / ``locked``, ``connection_limit``, ``comment`` ✓ (``rolcanlogin``, ``rolpassword``, ``rolvaliduntil``, ``rolconnlimit``)                                        ✓ user (``host``, ``password``, ``plugin``, ``active``)                   ✓ user (``authentication_mode``, ``plugin``, ``authentication_string``, ``account_lock``, ``password_expiration*``) ✓ user (``password``, ``plugin``, ``active``, ``first_name``, ``middle_name``, ``last_name``)                                                ✗                                                                                           ✗      
General: resource limits (``max_queries_per_hour``, ``max_updates_per_hour``, ``max_connections_per_hour``, ``max_user_connections``, ``max_statement_time``)                                                                         ✗                                                                                                                gap (engine has them)                                                     ✓                                                                                                                   ✗                                                                                                                                            ✗                                                                                           ✗      Group under General > Limits
General: TLS requirements (``tls_requirement``, ``tls_cipher``, ``x509_issuer``, ``x509_subject``)                                                                                                                                    ✗                                                                                                                gap                                                                       ✓                                                                                                                   ✗                                                                                                                                            ✗                                                                                           ✗      
Membership grid: ``role``, ``admin_option``, ``default`` (Firebird default role, MySQL default role)                                                                                                                                  ✓ ``rolmembership``, ``rolmembers``                                                                              **JSON** ``members``; ``grant`` / ``revoke`` / ``set_default`` as actions grant / revoke / set_default actions with ``member``, ``member_kind``                                               grant / revoke (``member``, ``member_kind``, ``default_role``, ``admin_option``, ``grantor``)                                                ✗                                                                                           ✗      One grid; grant / revoke become row add / remove; diff appears on SQL tab
Privileges: system privileges (checkbox group); object privileges grid (``object_type``, ``object``, privileges, ``grant_option``, column lists)                                                                                      ✓ (``rolsuper``, ``rolcreaterole``, ``rolcreatedb``, ``rolreplication``, ``rolbypassrls``) + ``privilege.grant`` ``administrator``; **JSON** ``privileges`` on ``privilege.grant``         ``privilege.grant`` with ``principal_kind``                                                                         ``system_privileges`` multiselect, ``admin_role``; ``privilege.grant`` with ``ddl_class``, ``database_privileges``, [E] column lists         ✗                                                                                           ✗      Privilege names come from the dialect contract per object type
Engine                                                                                                                                                                                                                                ``rolinherit``, ``variables`` (Parameters), security labels                                                      ``definer`` plugins, ``additional_authentication``                        **JSON** ``additional_authentication`` → grid                                                                       **JSON** ``tags`` → key/value, ``authentication-mapping`` / ``global-authentication-mapping`` as Engine objects, ``configure_admin_mapping`` ``secret`` as Engine object (**JSON** ``properties``, ``property_expressions`` → key/value) —      
SQL                                                                                                                                                                                                                                   ✓                                                                                                                plan                                                                      plan                                                                                                                plan                                                                                                                                         plan                                                                                        —      
===================================================================================================================================================================================================================================== ================================================================================================================ ========================================================================= =================================================================================================================== ============================================================================================================================================ =========================================================================================== ====== =========================================================================

DuckDB and SQLite omit the family (open decision 5). DuckDB ``secret`` is an Engine object under Security in the tree.

.. _69-database:

6.9 Database
~~~~~~~~~~~~

Covers databases on server engines and database files / aliases on embedded engines, plus attached databases.

**Tabs:** General · Options · Engine · Security · Parameters · Statistics · SQL

========================================================================================================================================== ================================================================================================================== ============================================================================================================================================ ============================================ ================================================================================================================================================================= ====================================================================================================================================================================================== ============================================================================================================================================================================================================================= ========================================================================
Tab / field                                                                                                                                PostgreSQL                                                                                                         MySQL                                                                                                                                        MariaDB                                      Firebird                                                                                                                                                          DuckDB                                                                                                                                                                                 SQLite                                                                                                                                                                                                                        Today
========================================================================================================================================== ================================================================================================================== ============================================================================================================================================ ============================================ ================================================================================================================================================================= ====================================================================================================================================================================================== ============================================================================================================================================================================================================================= ========================================================================
General: ``name`` or ``database_path``, ``owner``, ``comment``, ``template`` (PG), ``if_not_exists``                                       ✓                                                                                                                  ✓                                                                                                                                            ✓ (``comment``, ``or_replace``)              ✓ ``database_path``                                                                                                                                               ✓ ``name``                                                                                                                                                                             ✓ ``name``                                                                                                                                                                                                                    
Options: ``encoding`` / ``character_set``, ``collation``, ``locale`` fields, ``page_size``, ``sql_dialect``, ``read_only``, ``encryption`` ✓ (``encoding``, ``datcollate``, ``datctype``, ``datlocaleprovider``, ``spcname``)                                 ✓ (``character_set``, ``collation``, ``encryption``, ``read_only``)                                                                          ✓                                            ✓ (``page_size``, ``default_charset``, ``sql_dialect``, ``forced_writes``, ``reserve_space``, ``stored_page_buffers``, ``sweep_interval``)                        **JSON** ``config`` → key/value from ``duckdb_settings()``                                                                                                                             ✓ (``page_size``, ``encoding``, ``auto_vacuum``, ``journal_mode``, ``synchronous``, ``application_id``, ``user_version``)                                                                                                     
Engine                                                                                                                                     ``datconnlimit``, ``is_template``, ``datallowconn``, ``datstrategy``, default privileges, ``schema`` as child kind ``analyze`` / ``check`` / ``optimize`` / ``repair`` / ``checksum`` tables as Maintenance actions; logical backup / verify / restore as tasks same + ``check_objects``, ``repair_objects`` ``linger_seconds``, ``default_sql_security``, shadows, difference files, 21 service operations as Maintenance / Backup tasks, limbo transactions, ``publication`` ``checkpoint``, ``vacuum``, ``analyze``, ``export_database``, ``import_database``, ``update_extensions``, ``attached-database``, ``schema`` as child kind, extensions (install / load) ``backup`` / ``restore``, integrity / quick / foreign-key checks, ``vacuum``, ``incremental_vacuum``, ``optimize``, ``analyze``, ``reindex``, ``wal_checkpoint``, ``attached-database``, pragmas (read-only grid), extensions All actions go to menus (Section 7); the tab holds only settable options
Security                                                                                                                                   ✓ ``datacl``, default privileges                                                                                   ✓                                                                                                                                            ✓                                            ✓                                                                                                                                                                 ✗                                                                                                                                                                                      ✗                                                                                                                                                                                                                             
Parameters: key/value of per-database settings                                                                                             ✓ ``variables``                                                                                                    ✗                                                                                                                                            ✗                                            ✗                                                                                                                                                                 ✓ (``config``)                                                                                                                                                                         ✓ (pragmas that are settable)                                                                                                                                                                                                 
Statistics                                                                                                                                 ✓                                                                                                                  ✓                                                                                                                                            ✓                                            ✓ (``FirebirdDatabaseProperties`` groups: storage, MGA, attachment activity)                                                                                      ✓                                                                                                                                                                                      ✓                                                                                                                                                                                                                             Existing read-only property groups become this tab
SQL                                                                                                                                        ✓                                                                                                                  plan                                                                                                                                         plan                                         plan                                                                                                                                                              plan                                                                                                                                                                                   plan                                                                                                                                                                                                                          
========================================================================================================================================== ================================================================================================================== ============================================================================================================================================ ============================================ ================================================================================================================================================================= ====================================================================================================================================================================================== ============================================================================================================================================================================================================================= ========================================================================

.. _610-server:

6.10 Server
~~~~~~~~~~~

Registration and connection for one endpoint; not a DDL object, so no SQL tab. Replaces ``form_contracts.py`` define / connect / edit / remove plus ``ServerProfileWorkspace`` and ``FirebirdRegistration``.

**Tabs:** Connection · Authentication · SSL/TLS · Advanced · Engine · Tags

======================================================================================================================================================== ======================= ===================================================== ============== ============================================================================================ ============================================================================================ ====================================================================================================================
Tab / field                                                                                                                                              PostgreSQL              MySQL                                                 MariaDB        Firebird (network)                                                                           Firebird (embedded) / DuckDB / SQLite                                                        Today
======================================================================================================================================================== ======================= ===================================================== ============== ============================================================================================ ============================================================================================ ====================================================================================================================
Connection: ``name``, ``group``, ``host``, ``port``, ``database`` / ``file`` (file picker on execution host), ``read_only``, ``connect_now``, ``colour`` ✓                       ✓                                                     ✓              ✓                                                                                            ✓ ``database`` file, ``alias``, ``read_only``                                                Embedded engines show a file picker instead of host / port
Authentication: ``username``, ``password``, ``save_password``, ``auth_plugin`` / ``auth_method``, ``role`` (PG, Firebird), ``service`` / tunnel          ✓ + SSH tunnel          ✓ (``auth_plugin``, ``use_pure``)                     ✓              ✓ (``role``, ``wire_crypt``, auth plugin)                                                    ✗                                                                                            
SSL/TLS: ``ssl_mode``, cert / key / CA paths, ``tls_cipher``, ``wire_crypt``                                                                             ✓ ``connection_params`` ✓                                                     ✓              ✓                                                                                            ✗                                                                                            
Advanced: timeouts, ``tool_workspace``, ``tool_timeout``, post-connection SQL, session defaults                                                          ✓                       ✓ (``allow_local_infile``, ``tool_*``)                ✓ (``tool_*``) ✓ (~37 attachment fields: protocol, ``decfloat_*``, ``transaction_*``, ``parallel_workers``) ✓ (``uri_mode``, ``journal_mode``, ``busy_timeout``; DuckDB **JSON** ``config`` → key/value) Firebird's 37 fields are grouped: Wire, Transaction defaults, DECFLOAT, Parallelism
Engine                                                                                                                                                   service, ``pgpass``     execution host (SSH) for utilities, Router, sandboxes execution host service manager, client library, Docker provisioning                                         extension directory, secrets storage                                                         Execution-host setup (``MySQLHost``) is shared Advanced > Execution host for every engine that runs native utilities
Tags                                                                                                                                                     ✓                       ✓                                                     ✓              ✓                                                                                            ✓                                                                                            
======================================================================================================================================================== ======================= ===================================================== ============== ============================================================================================ ============================================================================================ ====================================================================================================================

.. _611-panel-disposition:

6.11 Panel disposition
~~~~~~~~~~~~~~~~~~~~~~

Every hand-written panel under ``static/js/Dialogs/`` is tagged so phase 4 has a checklist. *Form*: dissolve into a family tab or an operation dialog from ``operations.json``. *Tool*: keep the code, register under Tools, open from the categorised menu. *Properties*: dissolve into the Statistics or Engine tab of the owning object. Cross-engine helpers (``ProviderRowInput``, ``ProviderArrayInput``, ``NativeDataImport``, ``ProviderTransactionObservation``) become ``cdeadmin_ui`` primitives.

========================= =============================================================================================================================================================================================================================================================================================================================================================================================================== =========================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================== ================================================================================================
Engine                    Form → family tab / operation dialog                                                                                                                                                                                                                                                                                                                                                                            Tool (keep, re-home under Tools)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            Properties → tab
========================= =============================================================================================================================================================================================================================================================================================================================================================================================================== =========================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================== ================================================================================================
PostgreSQL (11)           ``PostgresqlBinaryChunk``, ``PostgresqlLargeObjectFiles`` (large-object editor), ``PostgresqlTemporarySlots``, ``PostgresqlReplicationTemporarySlots``                                                                                                                                                                                                                                                          ``PostgresqlCatalog``, ``PostgresqlServerCatalog``, ``PostgresqlContinuity``, ``PostgresqlLogicalStream``, ``PostgresqlMonitoring``, ``PostgresqlTrendView``, ``PostgresqlTestData``                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        —
MySQL (34)                ``MySQLControlledChange`` (Table alter Options), ``MySQLDataImport``, ``MySQLHost`` (Server > Advanced), ``MySQLSourceLogs``, ``MySQLAlerts``                                                                                                                                                                                                                                                                   ``MySQLCatalog``, ``MySQLServerCatalog``, ``MySQLContentSearch``, ``MySQLDataDrift``, ``MySQLTestData``, ``MySQLQueryPlan``, ``MySQLWorkload``, ``MySQLMonitoring``, ``MySQLTrendView``, ``MySQLSandboxes``, ``MySQLTopologies``, ``MySQLRouters``, ``MySQLClone``, ``MySQLPhysical``, ``MySQLPhysicalBackupSchedule``, ``MySQLPhysicalBatchRetention``, ``MySQLInstanceBackups``, ``MySQLInstanceRestores``, ``MySQLInstanceAcceptance``, ``MySQLBackupProtection``, ``MySQLBinlogArchives``, ``MySQLBinlogReplay``, ``MySQLArchiveRetention``, ``MySQLRetentionSchedule``, ``MySQLRecoveryChains``, ``MySQLRecoveryCutover``, ``ContinuousBinlog``, ``ReceiverFileCleanup`` (all under Backup and restore / Replication and availability) ``MySQLSpatial`` (Table > Statistics or Columns)
MariaDB (3)               ``MariaDBSchemaChanges`` (SQL tab apply flow), ``MariaDBBackupStages`` (Backup task)                                                                                                                                                                                                                                                                                                                            ``MariaDBCatalog``                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          —
Firebird (39 + 8 helpers) ``FirebirdFormLayout`` (becomes the shared grouped layout), ``FirebirdPrivilegeQueue`` (Role > Privileges diff), ``FirebirdBlobEditor``, ``FirebirdBlobChunk``, ``FirebirdRowSql`` (Data grid cell editors), ``FirebirdDataImport``, ``FirebirdParameters`` (Query tool), ``FirebirdSessionTraps`` (Query tool session options), ``FirebirdRegistration`` (Server family), ``FirebirdDocker`` (Server > Engine) ``FirebirdCatalogDesigner``, ``FirebirdServerCatalog``, ``FirebirdExport``, ``FirebirdSchemaPlan``, ``FirebirdERD``, ``FirebirdDesignStorage``, ``FirebirdTemplates``, ``FirebirdMetadataSearch``, ``FirebirdTestData``, ``FirebirdResultStream``, ``FirebirdQueryPlan``, ``FirebirdQueryHistory``, ``FirebirdScript``, ``FirebirdIsql``, ``FirebirdStatementDetails``, ``FirebirdProfiler``, ``FirebirdEvents``, ``FirebirdEDSPool``, ``FirebirdRecoveryGroup``, ``FirebirdServiceObservation``, ``FirebirdMonitoring``, ``FirebirdMonitoringDetails``, ``FirebirdActivityView``, ``FirebirdDatabaseRanking``, ``FirebirdEngineTrends``, ``FirebirdHistoryView``, ``FirebirdTrendView``, ``FirebirdDashboardEditor``                       ``FirebirdLimboObservation`` (Database > Statistics, with commit / rollback actions on the menu)
DuckDB (10)               ``DuckDBAttachment`` (Database > attach action), ``DuckDBExtensions`` (Database > Engine), ``DuckDBSessionSecrets`` (Role / secret), ``DuckDBCopy`` (Table export task), ``DuckDBDatabaseCopy`` (Database task)                                                                                                                                                                                                 ``DuckDBCatalog``, ``DuckDBServerCatalog``, ``DuckDBTestData``, ``DuckDBOperationReceipts``, ``DuckDBTrendView``                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            —
SQLite (18)               ``SQLiteAlterDesign``, ``SQLiteColumnDesign`` (Table alter), ``SQLiteExtensions`` (Database > Engine), ``SQLiteSessionFTS`` (Table create, FTS variant), ``SQLiteNativeUpload``, ``SQLiteRecovery`` (Database task), ``SQLiteNativeArrays`` (Query tool)                                                                                                                                                        ``SQLiteCatalog``, ``SQLiteRetainedSchema``, ``SQLiteNativeSessions``, ``SQLiteChangesetInspection``, ``SQLiteChangesetApply``, ``SQLiteConflictDecisions``, ``SQLiteNativeTransforms``, ``SQLiteNativeDiff``, ``SQLiteCaptureExports``, ``SQLitePreupdate``, ``SQLiteTrendView``                                                                                                                                                                                                                                                                                                                                                                                                                                                           —
========================= =============================================================================================================================================================================================================================================================================================================================================================================================================== =========================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================== ================================================================================================

Counts to track in ``ui_unification_status.rst``: 115 panels today; target after phase 4 is the Tool column only (about 70), all registered through Tools and none mounted by name inside a workspace host.

Operations, menus and the long tail
-----------------------------------

Each engine exposes roughly 80 to 150 operations. They are classified into three tiers; the tier decides the surface. No operation is dropped by the classification, and no operation gets a bespoke panel without an Engine-object or Tool justification recorded in its descriptor.

=========================== ===================================================================== ==================================================================================================== ============================================================================================================================================================================
Tier                        Definition                                                            Surface                                                                                              Examples
=========================== ===================================================================== ==================================================================================================== ============================================================================================================================================================================
1 — Object lifecycle        create, alter, rename, drop, comment, grant/revoke on a family object The object editor (Section 5). ``alter`` is the same dialog in edit mode; the SQL tab shows the diff table.create, view.alter, role.grant, sequence.restart
2 — Object operation        A native action on an existing object with a small parameter set      Menu item on the object → grouped operation dialog with plan, confirm, receipt                       ANALYZE / OPTIMIZE / CHECK (MySQL), VACUUM (PG, SQLite, DuckDB), sweep (Firebird), truncate, reindex, refresh materialized view, checkpoint
3 — Server or database task Long-running, utility-backed, or produces a log                       Menu item → task dialog: same renderer, plus execution-host selector, progress and output log pane   gbak/nbackup (Firebird), mysqldump/clone/binlog replay (MySQL), pg_dump/pg_basebackup (PG), EXPORT DATABASE (DuckDB), .backup (SQLite), shutdown/restart, user-count reports
=========================== ===================================================================== ==================================================================================================== ============================================================================================================================================================================

Menu model
~~~~~~~~~~

The categorised ``ProviderContextMenu`` structure becomes the standard for every node on every engine, including PostgreSQL. Category order is fixed:

1. Create ▸ (one entry per child kind the node can contain)
2. Open (Properties, Query tool, View data, Dashboard)
3. Definition and lifecycle (Edit, Rename, Drop, Comment, Scripts ▸ CREATE / ALTER / DROP / SELECT)
4. Maintenance ▸ (tier-2 operations)
5. Backup and restore ▸ (tier-3)
6. Replication and availability ▸
7. Security ▸
8. Diagnostics ▸ (statistics, dependencies, validation, logs)
9. Refresh

Rules: an engine omits a category it has nothing for; it never adds one. Labels name the action ("Binary-log archives..."), never the engine. A submenu with one item is flattened into its parent. Disabled items show the reason on hover (not connected, version too old, permission missing, utility not installed). The 14 flat MySQL/MariaDB entries in ``server.js`` move into Backup and restore, Replication and availability, and Maintenance.

The long tail and the other 20 engines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Operations that today only exist as the generic ``execute`` ("Native action" + JSON) are either promoted to tier 2 with real fields or removed from the beta menu; a free-text native action is a Query Tool job, not a form.
-  For the 20 non-beta connector roots, tier 1 uses the generic Engine-object skeleton with whatever fields the provider declares, tier 2 and 3 use the operation dialog. They get the same tree, menus and editor chrome; only field depth differs. This is the "basic support" promised for beta.
-  Each of the 113 panels in ``static/js/Dialogs/`` is tagged in the migration tracker as one of: *form* (dissolve into the operation dialog or an editor tab), *tool* (keep, re-home under Tools, open from a menu), or *properties* (dissolve into the Statistics or Engine tab of its object). Section 6's inventory lists the tag per panel.

Declarative form format and validation gates
--------------------------------------------

Form and capability definitions become JSON files owned by the engine, validated by a schema at build time, rendered by one renderer, and tested by one family test. The field vocabulary is the existing ``portfolio_catalog`` field shape, extended with grids, groups, version gates and tab placement; the backend plan/validate/apply contract does not change.

Layout on disk
~~~~~~~~~~~~~~

.. code:: text

   web/pgadmin/cdeadmin/ui_descriptors/
     schema/                      JSON Schemas: navigator, form, operations, capabilities
     families/                    canonical skeletons: table.family.json, view.family.json, ...
     postgresql/
       navigator.json             tree layout, icons, sort, virtual folders
       capabilities.json          kinds, operations, version gates (single capability source)
       operations.json            tier 2/3 operations with menu placement and form refs
       forms/table.form.json      fields per tab for this family on this engine
       forms/view.form.json ...
     mysql/  mariadb/  firebird/  duckdb/  sqlite/  ...

Field definition
~~~~~~~~~~~~~~~~

.. code:: json

   {
     "field_id": "character_set",
     "label": "Character set",
     "tab": "Options",
     "group": "Storage",
     "control": "select",
     "option_values_path": ["native", "character_sets"],
     "default_path": ["database", "default_character_set"],
     "required": false,
     "editable_after_create": true,
     "version": {"minimum": "5.7.0"},
     "native_keyword": "CHARACTER SET",
     "help": "Default character set for new columns.",
     "visible_when": {"field": "engine", "in": ["InnoDB", "MyISAM"]}
   }

Allowed controls: ``text``, ``number``, ``boolean``, ``select``, ``multiselect``, ``radio``, ``password``, ``secret-reference``, ``code`` (with ``language``), ``grid`` (with ``columns``: a list of field definitions and ``reorderable``), ``keyvalue``, ``privileges``, ``reference`` (object picker by kind), ``file`` (execution-host path). Removed: ``json``, ``multiline`` as a data carrier. A migration lint lists every remaining ``json`` control with its file and line until the count reaches zero for the six beta engines.

A grid column is a field definition, so a column grid is declared once in ``families/table.family.json`` and each engine overrides only the type picker source, the collation visibility and its Engine extras.

Version gating
~~~~~~~~~~~~~~

``version`` on a field, tab or operation is evaluated against the verified runtime version of the connected endpoint. Below minimum: the control is shown disabled with "Requires MySQL 8.0.16 or later". Above maximum: hidden with a recorded deprecation note. This is how the exact-version profiles (MySQL 9.7.0, Firebird 5.0.4, ...) open up to version ranges without the UI lying about support; the dialect contracts continue to decide what the backend will plan.

Gates that fail the build
~~~~~~~~~~~~~~~~~~~~~~~~~

======================== ================================================================================================================================================================================================================================= ==================================================================
Gate                     What it checks                                                                                                                                                                                                                    Where
======================== ================================================================================================================================================================================================================================= ==================================================================
Schema                   Every descriptor file validates against its JSON Schema                                                                                                                                                                           ``tools/validate_ui_descriptors.py``, run in ``make check`` and CI
Family conformance       For each beta engine and each kind, the form's tabs are a subset of the family skeleton in the right order; required tabs present (Table: General, Columns, Constraints, SQL)                                                     same
No raw JSON              Zero ``json``/``multiline``-as-data controls on beta engines                                                                                                                                                                      same
Capability single-source No operation appears in a menu, panel or form that is not in ``capabilities.json``; ``context_menu.py`` and ``native_supported`` flags are generated from it, not hand-written                                                    same
Import boundary          ESLint rule: files under ``cdeadmin/``, ``cdeadmin_ui/``, ``Dialogs/`` and provider code may not import ``@mui/*``; only ``cdeadmin_ui`` primitives may                                                                           ``.eslintrc``
No engine branches       ESLint rule: ``engine_id ===``, ``profile_id ===``, ``languageProfile ===`` string comparisons are forbidden outside the descriptor loader and provider backends                                                                  ``.eslintrc``
Family render test       One Jest spec per engine per family: renders the editor from the descriptor against a fixture catalog, asserts tab set and order, asserts every field has a label and a typed control, snapshots the SQL tab for a fixture object ``regression/javascript/families/``
Form reference           Every form in a descriptor carries its ``SR-F`` reference; new forms allocate from the registry                                                                                                                                   existing ``formReferences.json`` tooling
======================== ================================================================================================================================================================================================================================= ==================================================================

The private form audit in ``compact_forms.rst`` remains the human acceptance step for look and wording; these gates make the structure correct before a human looks.

Migration plan
--------------

Six phases, each closed by a gate that fails the build rather than a review opinion. Phases 1 and 2 are the architecture investment and must be done by one agent stream; phases 3 and 4 fan out per engine once the shell is green; PostgreSQL converges last so nothing it does today regresses.

.. code:: text

   Phase 0  Freeze and inventory ............................ gate: tracker + baseline counts committed
   Phase 1  Foundations: schema, validator, lint, families .. gate: validator + lint in CI, skeletons validate
   Phase 2  Shell: one tree, editor, op dialog, menus ....... gate: Firebird + MySQL table render from descriptors
   Phase 3  Engine descriptors (FB, MySQL, MariaDB, DuckDB,
            SQLite) ......................................... gate per engine: 10 families conform, 0 json, tests green
   Phase 4  Operations, panels, menus ....................... gate: server.js entries gone, panels dissolved
   Phase 5  PostgreSQL convergence, beta acceptance ......... gate: PG ui.spec parity, workspace host deleted
   Other 20 engines ride phases 2 and 4 automatically (generic family skeleton, same shell).

Each band is a work package with one owner at a time; a later phase never starts on an engine before the earlier gate is green for that engine.

Work packages
~~~~~~~~~~~~~

===== ==================================================================================================== ========================================================================================================================================================================================================================================================================================================================================================================================= ===========================================================================================================================================================================================================
Phase Package                                                                                              Deliverables                                                                                                                                                                                                                                                                                                                                                                              Gate (must fail the build)
===== ==================================================================================================== ========================================================================================================================================================================================================================================================================================================================================================================================= ===========================================================================================================================================================================================================
0     Freeze and inventory                                                                                 ``AGENTS.md`` rule: no new panel, menu entry or ``_form()`` branch. Tracker table of the 113 panels tagged form / tool / properties with target family or tool. Baseline counts: ``json`` controls, ``@mui`` imports in provider code, ``engine_id ===`` checks.                                                                                                                          Tracker committed; counts recorded in ``docs/en_US/ui_unification_status.rst``.
1     Foundations                                                                                          ``ui_descriptors/schema/*.json``; ``families/*.family.json`` for the ten families from Section 5; ``tools/validate_ui_descriptors.py``; ESLint rules for import boundary and engine branches; ``regression/javascript/families/`` harness.                                                                                                                                                Validator and lint run in ``make check`` and CI. Family skeletons validate. New code under the lint is clean.
2     Shell                                                                                                ``cdeadmin_ui`` additions: ``ObjectEditor`` (tabbed, descriptor-driven), ``ColumnGrid``, ``ConstraintTabs``, ``PrivilegeGrid``, ``OperationDialog``, ``TaskDialog`` (receipt and log pane), ``MenuModel``. Tree: ``cde_resource`` nodes get properties and the categorised menu; the in-panel ``ResourceExplorer`` is removed; Firebird virtual folders become ``navigator.json`` layout. Firebird ``table`` and MySQL ``table`` open from the tree in the new editor with all canonical tabs; the SQL tab shows the provider plan; existing Firebird and MySQL backend tests unchanged and green.
3     Engine descriptors (one package per engine, in this order: Firebird, MySQL, MariaDB, DuckDB, SQLite) ``ui_descriptors/<engine>/`` complete for the ten families; each ``_form()`` branch and per-module ``form()`` for that engine deleted as its descriptor lands; ``form_contracts.py`` entries moved to ``server.form.json`` and ``database.form.json``.                                                                                                                                    Per engine: family conformance passes; zero ``json`` controls; one render test per family green; ``relational_admin.py`` has no branch for that engine.
4     Operations, panels, menus                                                                            ``operations.json`` per engine (tiers 2 and 3); the flat ``server.js`` entries removed; ``context_menu.py`` generated from ``capabilities.json``; every panel tagged *form* or *properties* dissolved; *tool* panels re-homed under Tools and opened from menus.                                                                                                                          Capability single-source gate passes; no panel in ``static/js/Dialogs/`` lacks a ``tool`` tag; ``ProviderWorkspaceContent.jsx`` reduced to the tool host only.
5     PostgreSQL convergence and acceptance                                                                PG families moved to the shared editor family by family (Table last), with the existing ``*.ui.spec.js`` expectations ported to the family tests; ``ProviderWorkspaceContent.jsx`` deleted; human form audit on all six engines against ``compact_forms.rst``.                                                                                                                            PG family tests and ported ``ui.spec`` tests green; ``ProviderWorkspaceContent.jsx`` gone; audit signed per engine; ``implementation_status.rst`` records UI acceptance separately from backend completion.
===== ==================================================================================================== ========================================================================================================================================================================================================================================================================================================================================================================================= ===========================================================================================================================================================================================================

Ownership boundaries
~~~~~~~~~~~~~~~~~~~~

-  One agent stream owns phases 1 and 2 end to end; it does not take engine feature work.
-  Engine streams (phase 3 and 4) own only ``ui_descriptors/<engine>/`` and the deletion of that engine's legacy form code. They may propose a shell change through Section 11, not make it.
-  The backend streams continue the six-engine completion work unchanged; a new backend operation ships with its ``operations.json`` entry and form, or it is not surfaced.
-  The existing ``AGENTS.md`` ownership lines (platform teams, deferred ScratchBird history, post-beta Enterprise) are unchanged.

What "done for beta 1" means for the UI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For each of the six engines: every object kind the backend exposes maps to a family or Engine object; every tier-1 operation is reachable from the tree in the family editor; every tier-2 and tier-3 operation is a categorised menu item; no raw JSON controls; the same tab names, order and menu categories as the other five; the human audit signed. For the other 20 engines: tree, menus and generic editor render from their descriptors with no errors.

Agent operating rules
---------------------

The following block goes into ``AGENTS.md`` verbatim as a new owner direction. It is written so that an agent with no other context will keep the design unified.

.. code:: markdown

   ## Unified UI design (owner direction, 2026-10-25)

   The owning design document is `docs/en_US/ui_unified_design.rst` (this document,
   exported). It supersedes per-engine form reviews for structure; `compact_forms.rst`
   still governs presentation. All UI work on every engine follows it.

   1. Object-centric. A user opens an object from the one browser tree and edits it in
      the family editor. Do not add kind pickers, operation pickers, in-panel trees or
      workspace tabs as a way to reach an object.
   2. Family first. Before adding or changing any form, name its object family and tab
      (Section 5 of the design). A field that fits no canonical tab goes on the Engine
      tab. A tab that exists on no family is proposed in the design's open decisions,
      never added by one engine.
   3. Declarative only. Forms, tree layout, operations, menu placement and capability
      live in `web/pgadmin/cdeadmin/ui_descriptors/<engine>/`. Do not add branches to
      `relational_admin.py`, `ProviderWorkspaceContent.jsx`, `server.js`,
      `navigator.py`, `context_menu.py` or any shared renderer. If a feature cannot be
      expressed in the descriptor, stop and record it as an open decision with the
      exact field or behaviour that is missing.
   4. No raw JSON. `json` and free-text "native action" controls are not user-facing
      controls. Every native option gets a typed control or a grid.
   5. No engine branches in UI code. `engine_id ===`, `profile_id ===` and
      `languageProfile ===` comparisons are forbidden outside the descriptor loader and
      provider backends; the lint enforces it. Behaviour differences are declared
      options available to every engine.
   6. No new panels. Do not create files under `static/js/Dialogs/`. A form is an
      operation dialog or an editor tab; a tool is registered under Tools and opened
      from a menu. The panel tracker in `ui_unification_status.rst` is reduced, never
      grown.
   7. Menus are categorised. Items go in the fixed categories (Section 7). Labels name
      the action, never the engine. Flat engine-prefixed entries are not accepted.
   8. Every mutating dialog has a SQL tab showing the provider plan. Do not add a
      separate confirm-step preview.
   9. Design system only. Import `cdeadmin_ui` primitives; `@mui/*` imports in provider
      and form code fail lint.
   10. Backend features ship with their UI entry. A new provider operation lands with
       its `operations.json` entry, its form, and its family test, or it is recorded as
       unsurfaced in the engine's status page; a declared-task count is not a UI.
   11. Delete as you migrate. When an engine's descriptor for a family lands, remove
       that engine's legacy `_form()` branch, `form()` module and panels in the same
       change. Do not leave two implementations.
   12. Gates decide. A change is complete when the descriptor validator, the lint rules
       and the family render tests pass. Report the lint counts (json controls, mui
       imports, engine branches, panels) before and after in the change summary.
   13. Wording. Labels name the thing ("Character set"), help text carries the native
       keyword, no "exact native ... reference" phrasing in labels. Follow
       `compact_forms.rst` for density and geometry.
   14. Scope. The six beta engines get full family editors. The other connector roots
       get the generic family skeleton; do not hand-build forms for them before beta.
       Closed-source features remain post-beta as already recorded.
       Extended by owner direction 2026-10-29 (``AGENTS.md``, "Engine expansion to
       full parity"): Dolt, TiDB and Vitess, then CockroachDB and YugabyteDB YSQL,
       then immudb and XTDB, get full family editors and their distinctive native
       features at the six engines' level. Same family skeletons and shared field
       ids, filtered per engine; never lowest common denominator.
       Owner direction 2026-10-30: these engines are added to the list of beta
       engines and join the gate lists as their descriptor folders land (Dolt,
       TiDB, Vitess and CockroachDB first).

Two existing ``AGENTS.md`` statements change meaning under this direction and should be amended in the same commit:

-  "Form validation belongs to the human team" becomes "Form *presentation acceptance* belongs to the human team; form *structure* is generated from the descriptors and gated by the build." The structural gaps this document closes were caused by reading the old sentence as "UI is not the agent's job".
-  "Generic forms or placeholders do not prove native support" stays, and gains its converse: "a native backend operation without a descriptor entry does not count as surfaced."

Open decisions for the owner
----------------------------

These need a ruling before the corresponding phase starts. Each has a default the plan assumes.

= ============================================================================================================================================================================================ ================================================================================== ===========================================================================================================================================================================
# Decision                                                                                                                                                                                     Default assumed above                                                              Why it matters
= ============================================================================================================================================================================================ ================================================================================== ===========================================================================================================================================================================
1 PostgreSQL migration depth for beta: converge PG onto the shared editor (phase 5) or ship beta with PG on pgAdmin dialogs and the other five on the new editor                               Converge, Table family last                                                        Converging is the only way "same look between engines" holds for the engine most users compare against; deferring it saves the most work but leaves two editors in the beta
2 Version policy: keep exact-version profiles for beta or open each profile to a tested range (e.g. Firebird 3.0 to 5.0, MySQL 8.0 to 9.7) with field-level gates                              Open to ranges in phase 3, backend dialect contracts stay exact per tested version A beta that refuses Firebird 4 or MySQL 8.0 will be judged on that before any form is seen
3 Workspace tabs: dissolve the eight-tab Provider Workspace entirely, or keep a reduced "Database overview" page (properties + statistics + dashboard link) as the landing for a database node Dissolve; database node opens its family editor in read mode                       A landing page is useful, but keeping it risks it becoming the dumping ground again
4 Partitions and scheduled events as canonical tabs: Partitions exists on PG, MySQL, MariaDB; scheduled routines on MySQL/MariaDB events and PG (pg_cron is an extension)                      Partitions canonical; events stay a Routine variant                                Decides whether MySQL events get first-class treatment or an Engine-tab variant
5 Role family on engines with no roles (SQLite, DuckDB embedded): hide the family entirely or show a read-only explanation node                                                                Hide                                                                               Principle 5 says absent, but a user switching from MySQL may look for it
6 Grid editor for columns: build ``ColumnGrid`` fresh in ``cdeadmin_ui``, or adapt pgAdmin's ``DataGridView`` column collection                                                                Build fresh on the Zero-Grey ``DataGrid``, port PG behaviours as tests             PG's grid carries years of edge cases; the new one must reach parity before phase 5
7 Who signs the human form audit per engine, and whether the ``SR-F`` reference labels remain visible in release builds or only in QA mode                                                     QA mode only                                                                       Visible reference numbers help the audit and confuse end users
8 Where this document lives: export to ``docs/en_US/ui_unified_design.rst`` and treat the RST as authoritative, or keep this doc live and link it                                              Decided 2026-10-25: exported to this file; Claude Docs copy is a mirror       Agents working from the repo cannot read this page
= ============================================================================================================================================================================================ ================================================================================== ===========================================================================================================================================================================

Once 1, 2 and 3 are decided, phase 0 can start immediately; nothing in phases 0 to 2 depends on the others.

9. Descriptor value projections and cross-operation grids (MySQL audit,
   2026-10-25): ``mysql_table_options.union`` requires a list of identifier-path
   arrays; a reference multiselect returns identifiers and a grid returns records.
   The field schema currently has no declared projection between these shapes.
   Similarly, ``privilege.grant`` and ``partition_by`` are separate operations,
   not table-create properties. The shell needs a declared projection/dispatch
   contract before those controls can participate in a table edit. Default:
   record them under the table descriptor's ``gaps``; retain the existing backend
   operations; add no JSON control, special renderer branch or fabricated field.
   Status 2026-10-25: the value-shape half is covered by declared projections in
   the field schema (``item_kind: string``, ``wrap_list``, ``backend_field_id``
   list discriminators, and the ``record_*`` pre-fill rules documented in
   ``ui_descriptors/README.md``), so a multiselect can feed a list-of-paths field
   without engine code. The cross-operation half (driving ``privilege.grant`` or
   ``partition_by`` from a table edit) is still open.

10. Protected operation results (user keys, 2026-10-25): **decided by the
    owner: metadata-only for beta**. User-key inspection returns key type and
    byte length. Raw key material is never placed in public plans, receipts or
    downloads. A private native fingerprint may still bind a reviewed change.
    Existing native setup, supplied-key storage, generation and removal remain
    in scope. User-facing raw-key retrieval/export is excluded from the current
    beta by owner direction; it is no longer an implementation blocker or a
    request for a protected-result control. This is an owner scope decision for
    source-available functionality, not closed-source Enterprise deferral.

    The ruling applies to user-key inspection/export. Native RANDOM PASSWORD
    credential delivery remains a separate unresolved protected-result scope;
    it is not implicitly deferred by this choice. No provider panel or shared
    result-schema change is introduced.

11. Server-family registration dispatch (MySQL audit, 2026-10-25): Server
    fields are native endpoint profile inputs, not visual_admin server DDL.
    The existing actions are ``endpoint_profile_update`` and
    ``endpoint_profile_remove``; initial registration uses the existing
    provider endpoint creation route. MySQL's Server descriptor must bind
    ``define`` / ``edit`` / ``remove`` to those registration paths, carry the
    selected profile/group context, and pass secret fields through the existing
    credential service. The current shared family host issues visual_admin
    create/alter, while the native server catalog deliberately has no such
    operations. Default: populate the typed Server descriptor and record it as
    draft/unsurfaced until the front-end stream declares this dispatch. Do not
    invent server SQL DDL, add a provider panel or branch the shared host.

12. Operation draft projections (MySQL audit, 2026-10-25): the shared
    OperationDialog currently submits its raw field values, whereas ObjectEditor
    applies ``toBackendDraft``. Typed scalar-list grids therefore submit records
    instead of strings; hidden defaults and ``backend_field_id`` mappings also
    need the existing declared projection. Exact examples are
    ``server.import_table_sdi.files`` and
    ``table.assign_index_cache.indexes`` / ``preload_index_cache.indexes``.
    Default: populate those typed operation descriptors, keep them draft and
    explicitly unsurfaced until the shared dialog applies the same projection.
    Native scalar-list APIs remain unchanged; do not stringify records or add
    an engine-specific renderer/input workaround. Descriptor-projected backend
    qualification is separate from an actual dialog round trip.

13. Navigator descriptor consumption (MySQL audit, 2026-10-25): the bundle
    serves ``navigator.json``, but the current tree builds from provider paths
    without consuming its ``groups``, ``kind_icons``, ``resource_children`` or
    ``system_object_group``. Default: populate the native kind inventory and
    mark the declared layout draft/unsurfaced in the status tracker. The
    front-end stream owns the generic descriptor-to-tree bridge; do not add
    another MySQL branch to ``navigator.py`` or a second in-panel tree.

14. Dynamic Data-editor row operations (MySQL audit, 2026-10-26): the
    remaining ``table.insert``, ``table.update`` and ``table.delete`` contracts
    take column-name maps (``values`` / ``changes``), a provider row selector
    and, where available, a concurrency token. A static string key/value grid
    cannot preserve column-derived native types, SQL NULL versus an omitted
    value/default, exact integers and binary values. The descriptor format has
    static grid columns and references, but no declared binding that derives
    cell controls from the selected table's column catalog and carries the
    opaque row identity/concurrency context from the shared Data grid.
    Default: use the canonical Data editor and preserve its native row API;
    keep these three operation entries explicitly unsurfaced until the
    front-end stream declares that binding. The engine stream supplies native
    metadata and contract tests; it does not expose raw JSON, turn all values
    into strings or add a second row editor. This does not block other typed
    operation descriptors or native backend work.

15. Engine-object lifecycle editors (MySQL audit, 2026-10-26):
    ``replication-channel`` is classified as ``engine_object`` with tier-1
    create/alter. The current shared family registry and form resolver have
    no Engine-object skeleton; the operation schema permits only tiers 2/3.
    Consequently no valid lifecycle form can currently host the channel's
    typed ``source_options.<native_option>`` fields and separate sensitive
    ``source_password``. This also needs omit versus explicit false/zero/empty,
    nullable TLS ciphersuites and privilege-check accounts, a numeric server-ID
    grid and independent source/relay position fields. Default: retain the
    native contract and record create/alter as unsurfaced until the front-end
    stream declares the Engine-object editor or an approved family mapping.
    Do not relabel lifecycle actions as tier 2/3, place them on an unrelated
    server editor, add a renderer branch or replace options with raw JSON.
    Existing channel start/stop/reset/filter descriptors and tool openers can
    migrate independently. This decision does not change the native engine's
    supported replication options or defer their backend implementation.
    Owner direction, 2026-10-29: the engine stream creates the Engine-object
    dialog now and the front-end team adjusts it afterwards. Implemented as
    ``families/engine_object.family.json`` (General, Definition, Engine,
    Security, SQL) with one form per kind, ``forms/<kind>.form.json``
    (``family: engine_object``, exactly one ``resource_kinds`` entry), held
    in the bundle as ``engine_object:<kind>`` and found by the existing
    ``formForKind``/kind index, so the family editor renders it with no new
    renderer branch and tier-1 create/alter stay tier 1. First users: TiDB
    placement policy and resource group (complete, live round trip) and
    TiCDC changefeed (draft). The MySQL replication channel above can use
    the same dialog; its typed source options and separate secret field are
    still open.

16. Protected generated-password delivery (MySQL audit, 2026-10-26):
    User authentication and factor mode ``RANDOM_PASSWORD`` now have a native
    producer and typed Role/User choices. The producer needs a trusted
    ``client.protected_password_receiver`` with a UUID ``binding_id`` and
    ``reserve(user, host, factors)``, ``publish(reservation, factor, lease)``
    and ``release(reservation)`` methods. Reservation precedes account DCL;
    publish receives a short-lived ``SecretLease`` and must return an
    endpoint-bound ``SecretReference`` of kind password. Release frees capacity
    without deleting published references. Public receipts contain factor and
    reference ID only. Missing or changed delivery refuses before DCL; delivery
    loss after native acknowledgement never causes replay. The owner subsequently
    requested completion of the identified Group9 backend gaps. The backend now
    provides authenticated operation/principal/endpoint binding, encrypted durable
    storage, reference resolution, expiry and recovery/reveal APIs. Invalid drafts
    return bounded field/code refusals (422); stale plans return 409. The shared
    stream owns the reveal/recovery controls. The workspace action is
    ``protected_password_result``: ``recover`` takes ``plan_id``; ``reveal`` takes
    ``reference_id`` and explicit ``confirmed=true``. Responses are no-store.
    Default: keep the User variant draft and its reveal/recovery controls
    explicitly unsurfaced until the shared host connects them. Never
    return the native password rowset through an ordinary operation result or
    store it in plans, logs, downloads or endpoint DTOs. Decision10 remains
    limited to metadata-only user keys.

17. Explicit source-session catalog overlays (MySQL audit, 2026-10-26):
    The stock native private-peer interfaces used for SQL completion do not
    expose another session's active roles or user temporary-table definitions.
    Committed catalog reads can preserve the original diagnostic area; native
    ``CURRENT_ROLE()`` and selected-table inspection on the source session can
    replace it. There is no existing descriptor/editor interaction declaring
    that distinction or selecting temporary tables without writing SQL.
    The owner's request to finish the identified backend gaps authorizes an
    explicit ``server.refresh_session_metadata`` operation, with retained-session
    binding, a typed database/name grid and required ``replace_diagnostics=true``.
    It captures active roles, committed metadata and selected temporary shadows
    on the source. Later automatic completion can read that snapshot without a
    source command until the next execution or administration attempt invalidates
    it. Explicit inspection also works with Performance Schema disabled; its C
    conversion allowance is scoped to that task and does not change ordinary
    editor admission. The shared stream connects the session selection and
    explicit inspection controls; they remain unsurfaced.
    Default: retain private automatic reads when there is no explicit snapshot,
    report source overlays unobserved and ``complete=false``, and do not
    substitute an original-session query. Do not infer all
    temporary objects from committed catalogs, replay earlier role commands,
    or call a private peer's roles the source's active roles.

18. Shared dashboard pane (owner-approved integration, 2026-10-26): the
    existing dashboard pane may display an engine's read-only DDN viewer.
    ``tools.json`` declares ``arguments.dashboard_viewer`` on endpoint and
    database dashboard openers; the resolved descriptor bundle includes those
    tools. The shell dispatches registered viewer implementations without
    engine conditionals. Monitoring APIs authorize reads independently of
    interactive SQL-session state; PostgreSQL polling is never used for a
    provider endpoint. Target changes remount the viewer. Collector policy
    and layout editing remain separate tools. This does not add workspace
    tabs or change the object-family editor landing behavior in Decision3.

19. Engine-filtered option values and provider operation support (owner
    direction, 2026-10-29: forms are shared as far as possible but never
    lowest common denominator; every feature is surfaced and filtered so an
    engine is not offered anything it does not directly support). Option
    values (field ``options`` and ``options.json`` dialect lists) may carry a
    ``version`` gate and a ``requires_resource`` (resource kind and native
    name); the resolver marks gated values, and the shell offers a value only
    when it is available and the connected endpoint reports the required
    resource. Unknown resources mean the value is not offered. Declared
    ``capabilities.json`` operation gates are evaluated too. Descriptor menu
    operations are disabled, with a reason, when the endpoint's provider
    reports them unsupported (``cde_unsupported_operations`` on tree nodes),
    so per-version provider proof is not copied into descriptors. Endpoint
    tree nodes also carry ``verified_runtime_version`` and
    ``version_support`` after a reload. Capability-filtered bundles for
    network engines must not be cached by engine and version alone; key them
    on the endpoint or a capability digest when those engines adopt this.
