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

What is sound and should be kept: the provider contract and exact-version engine contracts; the plan → validate → confirm → execute lifecycle with native plan preview; the categorised ``ProviderContextMenu`` descriptors; the ``editor.sections`` concept and Firebird's use of it; ``compact_forms.rst`` as the presentation rulebook; the append-only ``SR-F`` form reference registry; the Zero-Grey component set and Interface Designer [2026-11-05, owner direction: the Interface Designer's functionality is kept but its form is retired in favour of proper dialogs; appearance now lives in View > Appearance and Accessibility]; the backend test corpus (5,669 tests).

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

Owner decision, 2026-11-10 (PostgreSQL M2, per-server tree choice): a PostgreSQL
registration keeps its preserved workflow (inherited Connect, driver, saved
password and every inherited tool) and can be browsed, per server, through the
provider tree instead of the inherited object tree (*Browse with the provider
tree* / *Browse with the inherited object tree* on the server menu). The choice
is presentation only. Under the provider tree the database nodes are the
preserved catalog's targets by OID and object nodes come from the shared
workspace navigator, each carrying the inherited identity chain. Registering
PostgreSQL as a provider endpoint was surveyed the same day and cannot verify
today (the endpoint route carries no server id, the provider reads the version
from a driver only the inherited Connect opens, and saved passwords are stored
as credential bundles the driver would pass through), so the opt-in lives on the
preserved registration rather than on a second manifest.

Owner direction 2026-11-08, M3 first slice (2026-11-11): a PostgreSQL provider
node's inspector now carries the reverse-engineered SQL (the ``ddl`` section),
the dependencies and the dependents that the inherited tree's panels showed,
produced by the inherited node views through the node's identity chain, so
pgAdmin's tested SQL templates are reused rather than rewritten. An index that
backs a primary key, unique or exclusion constraint routes to the constraint
node, as the inherited tree lists it. Every section reports its own state
(``inherited`` or ``unavailable: <reason>``); user mappings and foreign servers
are unavailable until the chain carries the foreign-data-wrapper id, and
password literals in inherited SQL are redacted. Second slice (2026-11-11):
the ``statistics`` section carries the inherited statistics for the kinds
whose inherited node had them (databases, tables, materialized views,
sequences, indexes, functions and procedures, subscriptions, primary and unique
keys); one object's statistics show as a name and value list. Third slice
(2026-11-11): a PostgreSQL server browsed through the provider tree carries
the inherited tree's *Login/Group Roles* and *Tablespaces* collections beside
its databases; their members come from the inherited node templates at server
scope, each with its identity chain, so the same inherited SQL, dependencies
and (for tablespaces) statistics apply. Fourth slice (2026-11-11): tables,
partitioned tables, views, materialized views and foreign tables carry a
*Columns* group whose members come from the attribute facts the catalog capture
already holds; each column has its identity chain, so the inherited column SQL,
statistics and dependencies apply. Fifth slice (2026-11-11): system objects
follow the inherited *Show system objects* preference; when it is on, the
provider capture includes them and the database branch gains the navigator's
*sys* group (system schemas such as ``pg_catalog`` and ``information_schema``,
casts, languages, access methods), each object inspecting as any other. Each
state of the preference has a listing cache of its own, so turning it on or
off takes effect on the next expansion. Unlike the inherited tree, temporary
schemas (``pg_temp_*``) appear among the system schemas. Sixth slice
(2026-11-11): inspecting a captured provider node no longer re-captures the
whole database to find the node again; the explorer hands the listed resource
to the provider, which confirms the object with one catalog row on a private
attachment and then adds the inherited sections. A node whose object is gone
reports that it no longer exists. Seventh slice (2026-11-11): a provider-tree
server carries the inherited *Replica Nodes* collection under the inherited
module's own rule (only when the server has replication slots); its members
are the inherited template's rows (streaming walsenders joined to their
slots, named ``Standby [address]`` and keyed by the walsender pid), with the
row's columns as properties. The inherited node shows properties only, so the
SQL, statistics and dependency sections report that state. Eighth slice
(2026-11-11): the inherited *pgAgent Jobs* collection, under the inherited
module's own rule (the ``pgagent`` schema usable in the maintenance database);
each job is the inherited properties row (class, agent, last run status, next
run), with the inherited job SQL (job, steps and schedules) and the inherited
run-log statistics. Jobs live in pgAgent's tables, not in ``pg_depend``, so
the dependency section says so. This closes the M3 parity list; the
inherited tree's job steps and schedules as child nodes are not offered.
Follow-ups (2026-11-11): the provider's *Types* group hides array types and
relation row types as the inherited node does (row types return when system
objects are shown); and the identity chain carries the foreign-data-wrapper
id, so foreign servers and user mappings inspect with the inherited SQL
(password literals redacted) and dependencies instead of reporting the gap.
The inspector's *Statistics* section shows several inherited rows (a pgAgent
run log, per-index counters) as one table with the rows' keys as columns;
one object's statistics stay a name and value grid.

M4 first slice (2026-11-11), the sequence editor: create, alter and drop on
a PostgreSQL provider-tree sequence run through the provider's own native
route (validate, plan with the exact statement text, apply inside one
transaction on a private attachment), like the advanced-object forms. The
dialog's field ids follow the inherited sequence dialog (owner, comment,
current value, increment, start, minimum, maximum, cache, cycled,
persistence, owned-by table and column, privileges, security labels); alter
emits only the clauses that differ from the captured facts, grants are
additive with an explicit revoke list, and drop needs the typed name.
Inspection of a sequence stays the provider tree's own. The inherited
dialog remains reachable through the inherited tree. Second slice
(2026-11-11), the extension editor on the same route: create with schema,
version, CASCADE and comment; alter updates to a version, moves relocatable
extensions between schemas and sets the comment; drop needs the typed name.
Third slice (2026-11-11), the row security policy editor: create with the
table, permissive or restrictive, the command, roles, USING and WITH CHECK
expressions and a comment; alter changes roles, expressions, comment and
name while the type and command stay fixed, as PostgreSQL fixes them; drop
needs the typed name. Expressions are admitted only when PostgreSQL's own
parser reads them as one balanced expression. The capture now names a
policy's roles so the dialog can show them. Fourth slice (2026-11-11), the
schema editor: create with owner, comment, privileges, default privileges
for new tables, sequences, functions and types, and security labels; alter
renames, changes the owner and comment, grants and revokes; drop with
CASCADE needs the typed name. Fifth slice (2026-11-11), the database editor
from the server scope, attached to the maintenance database: create is one
statement outside a transaction, as PostgreSQL requires, with owner,
template, encoding, locale provider and locales, tablespace, connection
limit and the allow-connections and template flags; alter renames, changes
the owner, limit, flags, comment and privileges in one transaction, and a
tablespace change runs alone. Drop stays with the inherited dialog. Sixth
slice (2026-11-11), the domain and type editors: a domain is created from a
base type with collation, default, NOT NULL, check constraints, owner and
comment, and altered through rename, owner, NOT NULL, default, added,
dropped and validated constraints, comment and schema; a composite,
enumeration or range type is created with owner and comment, and altered
through owner, comment, rename, schema, enumeration values added (before or
after a value) or renamed, and composite attributes added, dropped,
renamed or retyped. External and shell types, type privileges and security
labels stay with the inherited dialog. Type names are admitted by
PostgreSQL's own parser and spelled canonically. Seventh slice
(2026-11-11), the view and materialized view editors: a view is created
from one SELECT with the check option, security barrier and security
invoker, owner and comment, and altered through rename, schema, owner,
options set or reset, comment, and a changed query as CREATE OR REPLACE; a
materialized view is created with access method, fill factor, tablespace
and WITH or WITHOUT DATA, and altered through rename, schema, owner,
tablespace, fill factor, comment, and a changed query as drop and create in
one transaction, as the inherited dialog does. The query is admitted only
when PostgreSQL's own parser reads it as one SELECT. WITH CHECK OPTION,
which YugabyteDB refuses, is offered here. Eighth slice (2026-11-11), the
function and procedure editors: arguments with mode, name, type and
default, a return type including SETOF and TABLE, language, body,
volatility, strictness, leak-proofness, security definer, parallel safety,
cost, rows and SET parameters, with owner and comment; a changed body or
option runs CREATE OR REPLACE with the unchanged signature, while a changed
signature is refused; rename, owner, schema and comment address the
routine by its catalog identity. The alter dialog reads the current
definition back through PostgreSQL's own parser, so its values are exact.
C-language routines, support and window functions, privileges and security
labels stay with the inherited dialog. A trigger function is a function
returning ``trigger``. Ninth slice (2026-11-11), the index editor: columns
or expressions with collation, operator class, sort order and NULLs
placement, any access method the server has (BRIN and GiST, which
YugabyteDB refuses, included), unique, NULLs not distinct, include columns,
fill factor and other storage parameters, tablespace, a WHERE predicate and
comment; alter renames, moves tablespace, sets or resets storage
parameters, clusters the table on the index and sets the comment, while the
columns stay fixed. A concurrent build or drop runs alone outside a
transaction. Reindex was already native. Tenth slice (2026-11-11), the
trigger, event trigger and rule editors: a trigger with timing, events and
UPDATE OF columns, row or statement scope, WHEN condition, constraint
trigger with deferrability, transition tables, the function and its
arguments and a comment, altered through CREATE OR REPLACE for a changed
definition (constraint triggers are dropped and created), enable state,
comment and rename; an event trigger with event, command tags, function,
owner and comment, altered through enable state, comment, owner and
rename, with a changed event, tags or function as drop and create, as the
inherited dialog does; a rule with event, condition, INSTEAD or ALSO and
its commands, altered through CREATE OR REPLACE, enable state, comment and
rename. Transition tables and constraint triggers, which YugabyteDB
refuses, are offered here. Internal constraint triggers belong to their
constraint and are not edited. Eleventh slice (2026-11-11), the role and
tablespace editors from the server scope: a role with login, superuser,
create database, create role, inherit, replication and bypass-RLS
attributes, connection limit, expiry, membership of and members with the
admin option, per-role parameters and a comment, altered through rename,
the attributes a user chooses to change, membership granted and revoked,
parameters set and reset, and the comment; passwords never travel in a
plan and stay with the inherited dialog. A tablespace is created with
owner, location and options as one statement outside a transaction, as
PostgreSQL requires, altered through rename, owner, options, privileges
and comment, and dropped outside a transaction. This closes the M4 editor
list of the parity matrix.

M5 first slice (2026-11-11), the cast, collation and language editors on
the same route: a cast from a source to a target type with a function,
binary coercion or I/O conversion, in explicit, assignment or implicit
context, with a comment, and dropped; the preserved surface admits no cast
alter, so none is offered. A collation from a locale, from LC_COLLATE and
LC_CTYPE, or copied from another, with provider, determinism, rules and
version, owner and comment; alter renames, moves schema, changes the
owner and comment, refreshes the version, and drops and recreates for a
changed locale, as the inherited dialog does. A procedural language with
handler, inline and validator functions, trusted or not, or from the
server's template, with owner and comment; alter renames and changes the
owner and comment, since handlers and trust are fixed once created.
Nondeterministic collations, which YugabyteDB refuses, are offered here.
Second slice (2026-11-11), the foreign data wrapper, foreign server and
user mapping editors: a wrapper with handler, validator, options, owner
and comment, altered through rename, owner, handler and validator set or
removed, options added, set or dropped, and comment; a server with type,
version, wrapper, options, owner and comment, altered through rename,
owner, version, options and comment, while the wrapper and type stay
fixed; a user mapping for a role, PUBLIC or the current user on a server
with options, altered through its options. The capture redacts these
options, so changes are explicit rows rather than a diff, and options that
carry a credential (password, passfile, SSL password and key) are refused
here and stay with the inherited dialog, so a plan never shows a secret.
Third slice (2026-11-11), the publication and subscription editors: a
publication for all tables, listed tables with column lists and row
filters, or tables in schemas, with the published operations, publishing
via the partition root, owner and comment, altered through rename, owner,
operations, tables and schemas added or dropped, and comment; a
subscription whose connection is built from the dialog's non-secret
settings (host, port, database, user, password file and SSL settings,
never a password), with publications and every option PostgreSQL 13 to 17
knows, created as one statement outside a transaction as PostgreSQL
requires, altered through rename, owner, enable state, options,
publication list and comment, with REFRESH PUBLICATION run alone; the
connection string is never shown and a change to it stays with the
inherited dialog. Column lists, row filters, schema publications and the
published-operation subset, which YugabyteDB refuses, are offered here.
Fourth slice (2026-11-11), the text search editors: a configuration from a
parser or copied from another, with token mappings added, altered or
dropped, owner and comment; a dictionary from a template with options set
or dropped in place, owner and comment, the template fixed once created; a
parser with its start, get-token, end, lextypes and headline functions and
a template with its init and lexize functions, where a changed function is
drop and create, as the inherited dialogs do; all with rename and schema
move. The preserved surface has no concept for these kinds, so the
provider admits them explicitly. M5 close-out (2026-11-11): domain
constraints are the domain editor's rows (add, drop, validate, and now
rename, which is the inherited child node's own edit) and their inspection
rides the identity chain, so no standalone kind is needed; the operator
kind, which the provider already created, altered and dropped natively, is
now declared in the capabilities descriptor so the provider tree lists it
with its native form; the aggregate kind keeps its native form (a parsed
full definition on create, and owner, schema, rename and comment on
alter), while the routine form's recorded gap for aggregates stays
accurate. This closes the M5 list of the parity matrix.

M6 first slice (2026-11-11), server operations: a provider-tree server
offers reload configuration, create restore point, and pause and resume
WAL replay as provider-native operations run from the server scope on the
maintenance attachment, each planned as one function call whose result
row is the receipt, with confirmation on reload and the replay controls;
the replay controls are accepted only by a standby in recovery. On a
primary the server rejects them, and that rejection reaches the browser
the way every rejected administrative statement does today: as the
fail-closed unknown-outcome response, with the server's message kept in
the application log only (a standing property of the apply contract, not
of this slice). Change password and clear SSH tunnel password stay with
the inherited dialogs since they carry credentials. On the way a
reachability defect was found and fixed: the client's session-ready check
accepted only provider-endpoint servers, so on a PostgreSQL provider-tree
server no descriptor entry, including the M4 and M5 editors, had been
reachable from the tree menu; a connected provider-tree server (whose node
reports the verification state ``legacy``) now counts as ready, and its
node carries an action list of its own so the menu is built. Observed
through the running application's workspace route against the demo
server (node payload, reload, restore point, rejected pause); the menu
itself was not screen-checked.

M6 second slice (2026-11-11), database and schema scope: VACUUM and
ANALYZE run at database scope (no table list, so they cover the connected
database, which the apply route checks is the one named) and at schema
scope, where PostgreSQL has no schema form, so the statement names the
schema's tables and materialized views as listed with the schema node; a
table created after that listing is not included and an empty schema is
refused. Database drop joined the database editor with a typed-name
confirmation and an optional FORCE, compiled as one DROP DATABASE run
from the server scope outside a transaction; FORCE terminates the other
sessions of that database first, including any this application holds to
it, and the server still refuses the connected database and templates.
Observed live on PostgreSQL 18.3: dead tuples cleared at both scopes,
statistics recorded for the materialized view, and a held session
terminated by the forced drop.

M6 third slice (2026-11-11), role and tablespace operations that act
inside one database: reassign owned objects and drop owned objects on a
role, and move objects to another tablespace (tables, indexes,
materialized views or all three, optionally only those owned by one role)
on a tablespace. These objects live at server scope while the statements
act on one database's objects, so the dialog picks the database from a
reference field and the plan's route runs in that database; the node's
own route is not used, matching the inherited dialogs' database choice.
Drop owned takes a typed-name confirmation and is destructive; the other
two confirm. Observed live on PostgreSQL 18.3: table ownership moved
between two roles, the dropped-owned role's objects gone, and indexes
then every relation moved from a scratch tablespace to pg_default.

M6 fourth slice (2026-11-11), the inherited utilities as openers: backup,
restore and the psql terminal on a provider-tree database node, backup and
restore on schema and table resources (restore also on function, trigger
and index), and import/export on tables, each declared in the engine's
tools file with the ``open_inherited_tool`` handler. The utilities
themselves are unchanged apart from one read: a client identity bridge
(``legacyNodeData`` in the tree utilities) turns a PostgreSQL provider
database target into the inherited database node keyed by its OID and a
provider resource into the inherited node its legacy route names, and the
tree hierarchy walk every inherited dialog relies on applies it, so the
dialogs see the same server, database, schema and table entries they see
on the inherited tree. The server node keeps its inherited menus, so
backup globals, backup server and psql at server scope were never lost.
Verified by unit tests of the bridge, the hierarchy walk and the handler,
and by the running application serving the opener actions on the demo
database node; the dialogs were not opened in a browser.

M6 fifth slice (2026-11-11): the grant wizard (database and schema scope)
and search objects (database, schema and table scope) join the openers
through the same handler and identity bridge; the grant wizard now takes
the clicked item rather than the tree selection, so a provider node opens
it with its schema preselected. Not opened in a browser.

M6 sixth slice (2026-11-11): the inherited maintenance dialog joins the
openers at database scope and on schema, table, index and materialized
view resources, kept beside the provider-native maintenance operations
because it offers every VACUUM option and the constraint-backed index
cases the native forms do not. Not opened in a browser.

M6 seventh slice (2026-11-11), pgAgent jobs: the provider tree's pgAgent
job node gains create, alter, drop and run now through the provider's
native route. The job carries its steps and schedules as grids, as the
inherited job dialog did: a row with an id updates that step or schedule,
a row without one adds it, and an existing id left out removes it. Create
compiles to one ``DO`` block in which the new job id flows into its steps
and schedules, alter to plain update, insert and delete statements, drop
to one delete that pgAgent cascades, and run now to the inherited
``jobnextrun = now()``. Every value is a literal; a step connection string
may not carry a password, and remote steps are refused on a pgAgent whose
step table has no connection-string column. The provider's capture now
attaches each job's steps, schedules and that column's presence so the
editor opens with current values. Schedules and steps are not separate
editable kinds; they are edited on the job, which is where the inherited
dialog edited them. Verified live against a stand-in pgagent schema on the
demo server, because the demo image cannot install pgAgent; not checked
against a real agent, and the picker-less positions fields (minutes,
hours, days, months as comma lists) were not exercised in a browser.

M6 eighth slice (2026-11-11), Browse data on the provider tree: the
PostgreSQL manifest now declares the relation kinds its editor can read
(table, partitioned table, partition, view, materialized view, foreign
table), so the shared menu offers Browse data on those nodes, and the
provider answers the workspace's browse request with a SELECT of every
column from the cached catalog, quoted exactly as the inherited route
quotes (pgAdmin's keyword-aware identifier quoting), as schema.name; the
text is placed in the editor and not run. Observed through the running
application on the demo server's service.assets table.

M6 ninth slice (2026-11-11), the dashboard: the inherited Dashboard tab
follows the selected node through the same identity bridge, so a
provider-tree database node or any object under it shows the inherited
server and database dashboards (activity with cancel and terminate,
locks, prepared transactions, configuration, logs, system statistics,
replication) exactly as the inherited database node did; the bridged
database carries the connected flag the tab requires, since the provider
tree attaches to a database when it is browsed, and the dashboard routes
resolve the database OID through the maintenance connection either way.
The provider-backed per-database PostgreSQL dashboard and its monitoring
settings were already declared for the provider tree (M2). This closes
the M6 list of the parity matrix. The tab was not watched in a browser;
the routes it calls were observed answering for the demo database by OID.

M7 first slice (2026-11-11), the inherited table node's own operations:
count rows (a read whose result row is the receipt), reset statistics,
enable all triggers and disable all triggers join the provider-native
maintenance set on a table, each one statement in a transaction;
disabling confirms, since it also stops foreign-key enforcement until the
triggers are enabled again. Truncate with cascade and restart identity
was already native. Observed live on PostgreSQL 18.3: the count, the
counters reset, and a trigger's enabled state toggled.

M7 second slice (2026-11-11), scripts: the inherited Scripts menu's
INSERT, UPDATE and DELETE scripts open from provider-tree relations (the
SELECT script is Browse data) with the same placeholders and condition
marker the inherited node wrote, offered per relation kind as the
inherited nodes offered them (views insert only, materialized views
select only). They ride the Browse data channel: the studio source
request and the workspace's browse action carry a script kind, which the
provider's builder renders; the text is placed in the editor and not run.
The CREATE script is the provider tree's DDL state. Observed through the
running application on the demo table; not opened in a browser.

M7 third slice (2026-11-11), the column editor: create, alter and drop
on a provider-tree column through the provider's native route, compiled
as the inherited column dialog rendered them: ADD COLUMN with type,
collation, NOT NULL, default, identity or generated clause, then comment,
statistics, storage and compression; on alter one statement per changed
fact against the captured attribute row (rename, type with optional
collation, default set or drop, NOT NULL, identity add, change and drop,
statistics, storage, compression, comment); drop with optional CASCADE
and a typed name. Types and expressions are admitted by PostgreSQL's own
parser; a type change carries no USING clause, as the inherited dialog
did not. The capture now names each column's owning relation and carries
the editor's initial values. Column privileges, security labels and
attribute options stay with the inherited dialog. Observed live on
PostgreSQL 18.3 (create with every clause, identity and generated
columns, the alter set, identity transitions, cascade drop); the default
statistics target is read as -1 where PostgreSQL 17+ stores NULL. Reachability
finding, recorded for decision: the object editor renders only forms
from the descriptor bundle, and PostgreSQL ships no engine-object form
files, so the client offers Edit and Create only for kinds with a family
form (sequence, index, trigger, type, view, routine, role, database,
table); every engine-object kind edited natively since M4 (extension,
schema, row policy, cast, collation, language, foreign data wrapper,
foreign server, user mapping, publication, subscription, text search,
operator, pgAgent job, column) is reachable through the workspace API and
its operation dialogs but not yet through the tree's Edit entry. The
provider's own form builders carry every field; the proposed fix is a
client fallback to the endpoint's visual-administration catalog form when
the bundle has no form for an engine-object kind. Decided and done the
same day (owner decision 2026-11-11, option 1): the workspace gained a
``native_forms`` action returning the provider-native lifecycle forms of
one kind from the endpoint's visual-administration catalog; provider-tree
nodes and groups carry ``cde_native_editor``, the lifecycle operations
their provider edits natively, so the tree offers Edit and Create for
them; and the object editor, when the bundle has no form for the kind,
builds one from the provider's form (its fields on General, the provider
plan on SQL) and reads initial values along each field's
``initial_value_path`` into the inspected resource's native block. The
provider's Python form builders stay the single source; no form files
were generated. Verified by unit tests of the action, the flags, the
synthesized form and the menu, and by the running application returning
the column, extension, schema and role forms and flagging the column,
schema and server-scope group nodes; not watched in a browser.

M7 fourth slice (2026-11-11), the five constraint kinds: one ``constraint``
kind on the provider tree with a kind selector (primary key, unique,
foreign key, check, exclusion) whose fields follow the inherited dialogs.
Create compiles the ``ALTER TABLE ... ADD CONSTRAINT`` each inherited
template rendered: columns or an existing unique index with INCLUDE,
fill factor, index tablespace and deferrability for primary key and
unique; column pairs, the referenced table, MATCH, ON UPDATE and ON
DELETE actions, deferrability and NOT VALID for a foreign key; the
expression, NOT VALID and NO INHERIT for a check; access method,
elements (columns or expressions with operator class, order and
operator), predicate, INCLUDE and index options for an exclusion. Alter
emits one statement per changed fact: rename, validate for a foreign key
or check created NOT VALID, a foreign key's deferrability, the backing
index's fill factor (set, or reset through its own flag because the
validator drops empty values) and tablespace, and comment; columns,
references and expressions are not changed in place. Drop takes a typed
name with optional CASCADE. Observed live on PostgreSQL 18.3 for all
five kinds; PostgreSQL 18 also stores NOT NULL as a constraint row, which
the tree lists but the editor leaves alone.

M7 fifth slice (2026-11-11), the table editor: create, alter and drop
of a table through the provider's native route, with the table family
form as the dialog. Create compiles the one ``CREATE TABLE`` the
inherited template rendered: LIKE source with its INCLUDING options, OF
type, the Columns grid (each column clause from the column editor's
rules: type, compression, collation, NOT NULL, default, identity or
generated), the five constraint grids (each body from the constraint
editor's rules), PARTITION BY with column or expression keys, INHERITS,
access method, storage options including custom autovacuum parameters,
and tablespace; then owner, row security, security labels, grants, the
table comment and column and constraint comments. Alter emits one
statement per changed table-level fact: rename, schema, owner,
persistence, tablespace, row security, storage options set or reset
(resets through their own flags, added to the family form), replica
identity, labels, grants and revocations, comment. Columns and
constraints of an existing table are edited on their own nodes, so those
grids act at creation only; the partitions grid, OIDs and the read-only
properties are not compiled; owner, tablespace and access method are
OIDs in the captured row, so a value the dialog supplies is applied
rather than compared. The data operations and inspection stay with the
inherited grid. Observed live on PostgreSQL 18.3: a table created with
identity, generated and commented columns, four constraints, storage and
autovacuum options, row security, owner and a grant; then renamed, moved
to another schema, made logged, reset, given a replica identity and
revoked; then dropped. The family form keeps its draft status until its
recorded gaps are closed.

M7 sixth slice (2026-11-11), partitions and foreign tables. Partitions:
a partitioned table (``relkind p``, now a declared kind that takes the
table editor) offers create partition (``CREATE TABLE child PARTITION OF
parent`` with a bound or DEFAULT, optional sub-partitioning, access
method, storage options, tablespace, owner and comment) and attach
partition (``ATTACH PARTITION`` of an existing table); a table that is a
partition offers detach partition in the plain, CONCURRENTLY and FINALIZE
forms, the concurrent one outside a transaction, naming its parent from
the captured inheritance row. A partition bound is text the user writes
and is admitted only when PostgreSQL's parser accepts it inside a
``CREATE TABLE ... PARTITION OF``. Foreign tables: create compiles the
``CREATE FOREIGN TABLE`` the inherited template rendered (columns with
their options, INHERITS, SERVER, OPTIONS, then owner, check constraints,
comments, grants and labels); alter emits rename, schema, owner, options
added, set or dropped through three grids (the capture strips a foreign
table's options, so they are stated rather than diffed), comment, grants,
revocations and labels; drop takes a typed name. The table family form
gained the foreign server and option grids. Observed live on PostgreSQL
18.3: a range-partitioned parent with a created range partition, a
created default partition and an attached table; plain and concurrent
detaches (PostgreSQL refuses a concurrent detach while a default
partition exists, which the test observes); a foreign table over
postgres_fdw created, re-optioned and dropped. The partitions grid of the
table create form is still not compiled; partitions are created from the
parent instead.

M7 seventh slice (2026-11-11), the debugger and Schema Diff openers,
closing the parity matrix: a provider-tree function or procedure offers
Debug (direct) and Set breakpoint (indirect), a trigger offers Set
breakpoint, and a database node offers Schema Diff, all through the
inherited tools. The debugger reads the clicked item through the
identity bridge, so a provider routine stands for the inherited function
or procedure node, and the server, database, schema and function ids it
builds its routes from come from the bridged hierarchy; the node carries
the routine's language for the debugger's own check. The demo image has
no pldbgapi extension, so the live check stopped at the debugger's
initialisation route answering for the bridged ids; the debugger session
itself was not exercised. On the way a regression from the partitions
slice was found and fixed: a loop variable named ``parent`` shadowed the
listing's parent, so every resource after the first table lost its
parent id and the provider tree's navigator refused the page; the live
listing test now asserts every item names the listing's parent.

Rejection reporting (owner decision 2026-11-11): a server rejection the
provider vouches for is now a known outcome. When PostgreSQL refuses an
administrative statement before any commit, the provider raises a
rejection carrying the SQLSTATE and the server's first message line; the
private attachment rolls back on release, so nothing changed. The shared
apply records it as its own stage (``provider_rejected``, not an unknown
outcome) and the receipt returns 409 ``PROVIDER_OPERATION_REJECTED`` with
the SQLSTATE and message in the error text, where the dialogs already
show it. Every other failure keeps the fail-closed unknown-outcome
response: a failure during COMMIT, after a server-file export was
dispatched, from a driver error without a SQLSTATE, or from a provider
that does not vouch that nothing changed. Observed live: pausing WAL
replay on the demo primary now answers SQLSTATE 55000 with the server's
own words through both the harness and the running application.

Table form gaps closed (owner direction 2026-11-11). The capture now
names a relation's owner, tablespace and access method beside their
OIDs, so the table editor diffs them and emits SET ACCESS METHOD only on
a known change. The Partitions grid is compiled: on create each row
creates a partition or attaches an existing table after the table; on
alter a new row creates or attaches; a row left out never detaches,
since detaching is the partition's own Detach operation (owner
direction 2026-11-11). MAINTAIN is the ``m`` privilege code
for PostgreSQL 17 and later. The table family form is marked complete,
with its deliberate differences from the inherited dialog recorded in
its notes: the data type is typed and admitted by PostgreSQL's parser
rather than picked, the grids do not cross-sync, and columns and
constraints of an existing table are edited on their own nodes. Observed
live on PostgreSQL 18.3: a list-partitioned table created with two
partitions and an attached table from the grid, then one partition added
through the grid on alter with the others left in place; owner and access method
reported back by name and an unchanged pair refused as no change.

Column and menu gaps closed (owner direction 2026-11-11). The column
editor gained column privileges (stated through a grid, revoked through
a grid of grantees), security labels (the relation's labels with the
column's attribute number, now carried on the column node), attribute
options (n_distinct and n_distinct_inherited, set and reset) and a USING
expression on a type change; the inherited dialog's remaining column
features are covered. The database node now lists the database-scoped
kinds the provider creates natively, so its Create submenu offers the
engine-object kinds beside the family-form kinds, as the group nodes
already did. Observed live on PostgreSQL 18.3: a column granted, given
an option, retyped with USING, reset and revoked.

Form close-outs, database (owner direction 2026-11-11: close the
remaining PostgreSQL family forms the way the table form was closed).
The provider tree renders the family form and the provider validates the
draft against its own form, refusing any field it does not declare, so a
form is complete only when the provider admits and compiles every field
the dialog can send. A shared helper now reads privileges as the words
the family grids send or as aclitem codes, for tables, columns,
databases, schemas and sequences alike. The database editor admits every
family field: STRATEGY on create; per-database parameters set and reset
(a row with an empty value resets; a current setting left out resets
when the listing knows it); security labels; the four default-privilege
grids, which run inside the database, so such a plan attaches to it; a
Revoke grid; locale fields hidden by the provider choice are ignored.
CREATE DATABASE still runs alone, so the follow-up grids are refused on
create with that message, and the inherited tree's schema restriction is
refused as a browsing preference the provider tree does not store. The
pgAdmin field-id gate now lists the provider-tree-only ids (revocation
grids, storage resets, foreign option grids) that the M7 forms had
introduced without updating it. Observed live on PostgreSQL 18.3: word
privileges granted and revoked, parameters set per database and per role
then reset, default privileges applied inside the database.

Form close-outs, index. The index editor admits every family field and
reads the dialog's shapes: booleans for sort order and NULLs beside the
words, the access-method options the dialog shows as fields
(deduplicate_items, fastupdate, gin_pending_list_limit, pages_per_range,
autosummarize, buffering) as storage parameters that an empty value
resets on edit, a column row's statistics target as ALTER INDEX ... SET
STATISTICS, extension dependencies as DEPENDS ON EXTENSION, and
clustering on create after the create. Definition fields (columns,
uniqueness, method, predicate, INCLUDE, NULLs not distinct) are refused
as fixed once created rather than hidden. Observed live on PostgreSQL
18.3: an index created from the family shape with a statistics target
and an extension dependency, an option reset by an empty value, the
statistics target changed on edit, and a method change refused.

Form close-outs, role. The server-scope role listing already carried
every attribute, so the role facts now expose them all and the family
form's booleans are diffed against them; the connection limit and expiry
are diffed too. The INHERIT and SET membership columns compile to the
PostgreSQL 16 WITH list; security labels compile; the Revoke membership,
Remove members and Reset parameters grids join the family form so the
stated memberships and parameters can be removed. The password field is
admitted only to be refused: a provider-tree plan never carries a
password, so passwords stay with the inherited Properties dialog.
Observed live on PostgreSQL 18.3: attributes equal to the listing
produce no change, a membership granted with INHERIT FALSE and SET TRUE,
a password refused.

Facts surfaced for the family forms. The editor host fills a family
form's record from the resource's native block by field id, so the
editor facts each provider module computes (table, column, index,
routine, view, sequence, trigger, database, role, ...) are now surfaced
at the top level of the native block wherever no native key holds that
name. Observed through the running application: listed tables, columns,
indexes, views, sequences, functions and triggers carry their dialog
values. The facts take the dialog's shapes: booleans for an index
column's sort order and NULLs, the codes for a routine's volatility and
parallel safety.

Form close-outs, routine. The function and procedure editor admits every
family field: volatility and parallel safety as the dialog's codes or as
words, SETOF through the return-set flag, WINDOW, SUPPORT, C-language
routines by object file and link symbol (read back from the definition
too), EXECUTE grants stated through the grid and revoked through a Revoke
grid, security labels and extension dependencies. The aggregate variant
stays read-only, as in the inherited dialog. Observed live on PostgreSQL
18.3: codes read back and applied, EXECUTE granted as the word the grid
sends and PUBLIC revoked, an extension dependency recorded, a
set-returning function created through the flag.

Form close-outs, sequence. The sequence editor admits every family
field; persistence is the dialog's boolean (checked = UNLOGGED) beside
the words; the owner is a fact; the provider's No minimum, No maximum,
OWNED BY NONE and Revoke controls join the family form, since a cleared
number never reaches the provider; the table picker's schema.table is
accepted for OWNED BY. Observed live on PostgreSQL 18.3: persistence
switched through the boolean, USAGE granted as the word the grid sends,
the sequence re-owned through the picker's dotted path.

Form close-outs, trigger. The trigger family form serves two kinds, the
table or view trigger and the event trigger; both now admit every family
field. The dialog's column list arrives as plain names, the event
trigger's event as the dialog's upper-case option (the facts match it),
event trigger security labels compile, and the inline trigger code
field, an EDB feature, is refused with that message. Rewrite rules keep
their own engine-object form. Observed live on PostgreSQL 18.3: the
existing trigger, event trigger and rule lifecycles pass under the
family-field forms.

Form close-outs, view. The view and materialized view editor admits every
family field: privileges stated through the grid and revoked through a
Revoke grid, security labels, and for materialized views the TOAST tuple
target, the autovacuum grids (set and reset, as the table editor does),
the access method on edit (SET ACCESS METHOD, PostgreSQL 15 and later)
and extension dependencies; a recreate keeps the current storage
parameters under the dialog's changes; the owner, tablespace and access
method are facts. Observed live on PostgreSQL 18.3: SELECT granted on a
view as the word the grid sends and revoked, a materialized view created
with a TOAST tuple target and autovacuum off, the setting reset through
the dialog's "Not set".

Form close-outs, type and domain. The type family form serves the domain
and type kinds; both now admit every family field. External (base) types
are created from their support functions and storage properties, shell
types from their name, and a multirange is refused on its own since it
comes with its range type. USAGE is granted through the grid and revoked
through a Revoke grid, security labels compile, and a domain's or
composite member's length and precision join the type. The dialog's
full-set grids are diffed against the facts: new enumeration labels are
added after their predecessor and a dropped one is refused since
PostgreSQL cannot drop it, composite members are added, dropped or
altered, domain constraints are added, dropped or validated and a
changed expression is refused as fixed once created. Observed live on
PostgreSQL 18.3: a composite type reshaped through its grid, an
enumeration extended through its list, USAGE granted as the word the grid
sends and revoked, a shell type created, a domain's constraints replaced
through its grid.

Form close-outs, server (left as draft, deliberately). The PostgreSQL
Server family form maps the inherited registration dialog, not a DDL
object. A Server form marked complete reroutes registering and editing
PostgreSQL servers through the descriptor registration host, away from
the inherited dialog the provider tree uses today, and its five recorded
gaps (SSL fields stored as connection_params rows, the colour picker, the
db_res dynamic control, the runtime route and secret fields, the
connected-state read-only rules) are differences in that registration
path rather than in a provider compiler. Switching the registration path
is an owner decision and needs a browser pass, so the form stays draft
with this recorded in its notes; the nine DDL forms are complete.

Decided 2026-11-11 (owner): one registration path for every engine. Every
engine registers and edits its endpoints through the descriptor
registration host; the inherited dialogs remain only as the fallback when
the host cannot open. What this took:

- The PostgreSQL Server form is complete. Its field ids are the servers
  API's own keys, so the payload is the form draft plus the envelope the
  host adds (profile, intent, verification, and the server group from the
  tree). Verified against the running application: the pinned PostgreSQL
  18.3 demo registered, read back, edited and removed through the servers
  API with the form's payload.
- The eleven engines whose only descriptor is their Server form (Apache
  Ignite, Cassandra, ClickHouse, FoundationDB, InfluxDB, Milvus, MongoDB,
  Neo4j, OpenSearch with its SQL/PPL profile, Redis, TiKV) get a minimal
  package from ``tools/scaffold_registration_descriptors.py`` (the server
  kind, the nine object families omitted with the reason, an empty
  navigator and operations list) and a Server form drafted from their
  registration contract by ``tools/draft_server_descriptors.py``, which
  now places unlisted contract groups by what their names say and marks
  the maintenance database required when the profile requires one.
- The servers API fills the legacy username column from a contract
  username (or a placeholder, as embedded endpoints already did) without
  putting a placeholder into the provider route, where it would read as a
  credential.
- The route envelope. The endpoint service and the servers API add
  bookkeeping to every provider route beside the contract fields (route
  id, generic host, port, user and database, the legacy connection
  timeout, the database target, credential kinds and references). The
  strict providers rejected those keys as unknown, so a registration that
  verified at create failed for them: a latent defect the standard path
  exposed. ``transports/route_envelope.py`` names the envelope and the
  eight strict validators (Redis, MongoDB, Neo4j, ClickHouse, XTDB,
  Cassandra, Ignite, Milvus) and the shared HTTP route normaliser admit
  it. MongoDB's contract default of 0 for the pool idle and wait options
  now reads as unset, which is what pymongo 4 accepts; Redis reads the
  generic database as the text the servers API stores.

Decided 2026-11-12 (owner): the legacy registration dialog is retired for
every engine, and every registration intent (endpoint, register an
existing database file, create a database file) opens the descriptor
Server editor; a host that cannot open reports instead of falling back
(``LEGACY_REGISTRATION_RETIRED`` lists all 25 engine ids). The endpoint
service reads the PostgreSQL provider's identity from
``providers/postgresql/identity.py`` rather than importing the provider
module, which had dragged the application model into three
endpoint-registration unit tests that now pass again.

Verification (completed 2026-11-12, owner direction: every engine
through a live registration): all 24 engines, 26 profiles, registered
through the servers API with their form's payload against the pinned
demos, verified at create, read back and removed: PostgreSQL, MySQL,
MariaDB, Firebird, DuckDB, SQLite, Dolt, TiDB, Vitess, CockroachDB,
YugabyteDB (YSQL and YCQL), immudb, XTDB, Apache Ignite, Cassandra,
ClickHouse, FoundationDB, InfluxDB, Milvus, MongoDB, Neo4j, OpenSearch
(native and SQL/PPL), Redis and TiKV. The demos were verified in groups:
the Docker Desktop VM holds 7.5 GiB, and the whole estate at once
starves PD and CockroachDB and kills Cassandra and ClickHouse. What the
live runs corrected:

- Verification granted secret access to every provider; TiKV's manifest
  grants none, so its verification was refused. The grant now follows the
  profile (secret access only when it declares a secret) and adds what
  the provider's manifest requires of every context (FoundationDB reads
  its cluster file, so it requires the filesystem). FoundationDB's
  manifest now declares the secret access its TLS key password needs.
- The pinned MySQL-wire and PostgreSQL-wire demos speak plain TCP, so a
  registration sets the dialog's TLS switch off for them (ssl_disabled,
  ssl, sslmode disable); the contracts default to TLS on, as they should.
- The demo tool's TiKV definition is recreated when the advertised host
  address changes, and the FoundationDB host cluster file must carry the
  cluster's current connection string (a client rewrites it; a stale one
  reads as an unreachable coordinator).

Nothing was screen-checked: the browser extension reported no connected
browser for this account all day.

Browser pass, 2026-11-12 (the first time the application was seen in a
browser this cycle; Chrome, the throwaway instance, PostgreSQL 18.3 demo).
Passed: registering PostgreSQL from its connector through the descriptor
editor (values entered, server created with them); the SQLite create-new
and open-existing intents open the descriptor editor and create-new
creates the file; server-group menus offer no legacy server entry; the
Redis registration form renders its contract tabs; a sequence's family
form opens with its current values (increment, start, bounds, cache,
comment), Apply stays disabled with no change, and one change previews
and applies exactly ALTER SEQUENCE ... INCREMENT BY 7. Failed and fixed:

- A server's Properties (and Alt+Shift+E) and Copy Server still opened
  the legacy server dialog. The server node now routes edit and copy to
  the descriptor editor for every engine in the retirement set; copy
  prefills from the server's registration (without secrets) under the
  same group. Observed after the fix: Properties opens the descriptor
  editor with the current values, Copy opens it with "Copy of ...".
- The PostgreSQL registration editor showed the registration envelope
  (profile, registration action, verification, server group) as editable
  fields that were never sent. Form fields marked ``hidden`` are now kept
  in the record but never rendered, and the PostgreSQL Server form marks
  those four.
- Native editors rendered ``multiline`` (every comment field) and
  ``json`` controls as read-only "unsupported" boxes, so no comment could
  be edited from a provider-native form. Both are editable text now.

Save paths, checked the same day (servers API and lifecycle route against
the demos, then in Chrome):

- A PostgreSQL edit saved with the editor's envelope changes only the edited
  field; saved password, tags, connection parameters, host and port stay,
  and the server reconnects.
- MySQL registration changes pass the provider's lifecycle admission (owner
  work 2026-10-23), so the servers API refuses a MySQL update and the editor's
  Save failed for MySQL. The editor now saves a MySQL edit through the
  endpoint's workspace action with the provider edit form's complete values;
  a change to a field that form does not own (the comment) is refused with
  its name rather than dropped. Verified: one timeout change, every other
  route value unchanged.
- Copy registers once the password is entered (a copy never carries the
  secret); host, port, database, user, comment and connection parameters
  match the source. The copy's tags carried a display-only key, now
  stripped. A refused registration showed only "status code 401"; the
  editor now shows the servers API's reason.
- Moving a server between groups: the update API honours it, but the
  descriptor Server form has no usable group control (it is UI-only and
  the editor supplies no group list), so with the legacy dialog retired no
  screen moves a server between groups. Recorded for the owner; not built.
- Tree chevrons work: a first open fetches the node's children and took
  several seconds on the loaded machine; reopening takes a quarter second.

Observed, not changed: the SQL tab of an
applied native plan shows the plan's JSON envelope rather than the
statement alone; an owner whose catalog value is an OID shows empty in the
schema and sequence editors (documented: empty keeps the owner).

Verification of the close-outs. Every PostgreSQL unit suite, the
descriptor service and field-contract suites, the pgAdmin field-id gate
and the Jest family specs pass; the live lifecycles ran against
PostgreSQL 18.3 through the harness with temporary objects created and
dropped. Nothing was screen-checked: the browser extension stayed
disconnected, so the dialogs themselves have not been seen rendering the
surfaced values.

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
Form reference           Every form in a descriptor carries its ``SR-F`` reference (``SR-F-020001``..``SR-F-020122`` stamped across ``ui_descriptors/*/forms/*.form.json`` and checked by ``tools/validate_ui_descriptors.py``; task-specific designers register ``SR-F-010016``..``SR-F-010029``); new forms allocate from the registry                                       existing ``formReferences.json`` tooling
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

20. Empty typed values in registration routes (2026-11-04, parity server
    forms): ``provider_route_options`` drops a contract field whose value is
    ``None`` or ``''``, which is what the legacy dialog sent for an empty
    ``json`` field. A typed grid or key/value control sends ``[]`` or ``{}``
    instead, and that is kept. For MySQL-wire ``failover`` (Dolt, TiDB,
    Vitess) an empty list makes the connector refuse the connection ("Select a
    bounded native failover target list", live on the pinned demos). Dropping
    every empty value in the shared builder is not safe: DuckDB and SQLite
    ``attached_databases`` default to ``[]``, and for MongoDB
    ``auth_oidc_allowed_hosts`` an empty list plausibly differs from leaving it
    unset. The form schema has no way to declare "omit when empty" for one
    field. Default: the Dolt, TiDB and Vitess server forms stay ``draft`` with
    this recorded in their ``gaps``; registration keeps the legacy dialog.
    Decided 2026-11-04: fields declare ``empty_as_null``, which sends ``null`` for an
    empty value (the backend then leaves it unset); set on the MySQL-wire ``failover``
    and TLS list fields. The forms are ``complete``.
