.. _robin_master_plan:

ScratchRobin master plan: three goals
=====================================

Owner goals, 2026-10-28:

1. MySQL, MariaDB, Firebird, PostgreSQL, SQLite and DuckDB are fully supported:
   every open-source / open-code management, query and special function is usable
   in Robin.
2. All DDN diagramming is two-way for those six engines.
3. A full superset/Metabase-class editor for BI and dashboards is implemented
   inside Robin.

Decisions taken: the DDN foundation is the public repository
``scratchbird-software-inc/Diagram-Design-Notation`` (``ddn-next-1``); BI starts
with query builder, saved questions and dashboards; the three goals run as
parallel streams with the acceptance gates below. MySQL descriptors stay with the
MySQL stream. Closed-source features remain post-beta.

Baseline (survey, 2026-10-28)
-----------------------------

Goal 1
~~~~~~

* Open backlog in :doc:`six_engine_remaining_work`: per-engine ``*-CONTINUITY``,
  ``*-ARCHIVES``, ``*-HA-LIFECYCLE``, ``*-LANGUAGE-CAPABILITIES`` items, the
  independent ``INV-*`` native inventories (open for all six), plus shared
  ``ALL-EVIDENCE``, ``HUMAN-FORMS`` and ``NATIVE-PLATFORMS`` (platform and human
  teams own those).
* UI unification (:doc:`ui_unification_status`): Firebird, MariaDB, DuckDB, SQLite
  forms complete; MySQL forms draft (MySQL stream); **PostgreSQL forms all draft,
  no tier 2/3 operations, legacy stack** (phase 5, open decision 1).
* Acceptance rule: a capability closes only when discoverable, admitted, usable and
  observable with its failure and recovery paths, backed by native fixture evidence.

Goal 2
~~~~~~

* Forward ERDs exist for all six engines. The reverse reader
  (``ddn/read_relations.mjs``) covers only Firebird, PostgreSQL, MySQL, MariaDB:
  **SQLite and DuckDB have no reverse path.**
* Diagram edits reach a reviewed plan only for type, nullability, comment and new
  columns; renames, drops, indexes, constraints, FK actions, views, routines and
  triggers do not flow from the diagram. Only Firebird has per-object plan modules
  and an exchange gate.
* The DDN repo has no physical-schema vocabulary; native facts ride in
  ``metadata.x_record`` conventions that DDN-DB-004 says still need agreement.
* Doc drift: ``ddn_adopted_runtime.rst`` names a sandbox path (now the public repo),
  ``static/vendor/ddn/README.md`` says 0.8.0.

Goal 3
~~~~~~

* Substrate: provider-neutral semantic models (``semantic_models/``: sources, joins,
  dimensions, measures, parameters, visualizations, dashboards, schedules, row
  filters), scheduler and delivery services, result rendering/export, data studio.
* Missing: saved-question entity and visual query builder, rich chart set and
  formatting, dashboard filter widgets and drill-through, collections/search,
  sharing and per-principal permissions, embedding, result cache, threshold alerts.
  Monitoring dashboards (DDN project assets) and semantic dashboards are two
  unrelated systems.

Streams and acceptance gates
----------------------------

Stream A: engine completeness (goal 1)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. A1 PostgreSQL convergence (phase 5): tier 2/3 operations and family forms
   ``complete`` by live round trip (PostgreSQL 18.3 profile; the container has
   PostgreSQL 16), then route the tree through the shared editor.
#. A2 Independent native inventory ``INV-*`` per engine: enumerate every open
   feature against the catalog/editor/operation/receipt chain; each gap becomes a
   tracked item. Start with Firebird (``FB-NATIVE`` is not enumerated) and SQLite.
#. A3 Close the per-engine items (DuckDB, SQLite, Firebird first; MariaDB and
   PostgreSQL next; MySQL by its stream).
#. Gate: ``make ui-descriptors-check`` clean, inventory shows zero unowned gaps,
   every closed item has a native receipt.

Stream B: two-way DDN (goal 2)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. B1 Contract: a versioned physical-schema vocabulary for ``x_record`` (types,
   defaults, identity, indexes, constraints, FK actions, partitioning, views,
   routines, triggers) proposed to the DDN repo; then refresh the vendored runtime
   and fix the doc drift.
#. B2 Reverse readers for SQLite and DuckDB.
#. B3 Diagram-delta to plan adapters per engine, generalising the Firebird
   relational review: rename, drop (with explicit confirmation), indexes,
   constraints, FK actions; then views, routines, triggers.
#. B4 Exchange gates per engine modelled on
   ``tools/cdeadmin_firebird_ddn_exchange_gate.py``: database -> DDN -> edit ->
   plan -> apply -> re-inspect -> identical diagram.
#. Gate: a round-trip gate passes live for each of the six engines for every
   object kind the engine supports.

Stream C: BI editor (goal 3)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. C1 Domain model and storage: saved questions (builder state or SQL, backed by a
   semantic model), collections, dashboards with filters and parameter mapping,
   sharing; one dashboard format for both BI and monitoring.
#. C2 Query builder (table/column picking, filters, summaries, joins from the
   semantic layer, SQL view, SQL-to-question).
#. C3 Chart set and formatting, dashboard editor with filter widgets, tabs, text
   cards, drill-through.
#. C4 Collections, search, permissions (done, see :doc:`bi_permissions`), threshold alerts and subscriptions (done, see :doc:`bi_alerts`), embedding, result cache.
#. C5 Retire ``SemanticModelWorkspace`` from ``ProviderWorkspaceContent.jsx`` per the
   unified design (panel dissolution). Done: the Models view of the BI module
   replaces it (:doc:`bi_models_view`); "Convert to subscription" waits for the
   alerts/subscriptions branch.
#. Gate: the same question and dashboard run on each of the six engines through the
   dialect contract; Jest and live round trips for builder state -> SQL -> result.

Cross-cutting rules
-------------------

* Descriptor layer first: UI for engine facts comes from ``ui_descriptors``, never an
  engine branch in React.
* No new panel or ``_form()`` branch (``AGENTS.md``); every item updates the tracker.
* Risks accepted by the owner are documented with restore steps (see
  :doc:`ui_server_editor_retirement`).
