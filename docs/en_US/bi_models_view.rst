.. _bi_models_view:

BI Models view (retirement of the semantic-model workspace)
===========================================================

Stream C5 of :doc:`robin_master_plan`: the ``SemanticModelWorkspace`` panel that
lived inside ``ProviderWorkspaceContent.jsx`` is gone. The workspace tab
``semantic`` ("Cubes & Semantic Models") now mounts the **Models view** of the BI
module, ``cdeadmin_ui/modules/bi/models/``. The same view is registered as the
surface ``bi.models`` of module ``cdeadmin.bi`` and can be opened as a tool by
anything that calls ``open_tool`` with that surface id. No tools.json entry
exists for it yet (see the decisions at the end). Panel dissolution rules are in
:doc:`ui_unified_design`; the Questions and Dashboards halves of the module are
in :doc:`bi_query_builder_ui` and :doc:`bi_dashboard_ui`.

Nothing is stored differently. The model JSON schema
(``semantic_models/models.py``, ``contract_version`` 1.0.0) is unchanged and
every existing model opens, saves and queries as before.

Structure
---------

``BIModelsTool.jsx``
    Model list on the left (name, status, revision), editor on the right. Takes
    the workspace ``post`` function, or ``api`` and ``endpointUrl`` and builds
    one. Leaving unsaved edits asks first.
``useModelSession.js`` and ``modelSession.js``
    The open model: a pure reducer (``load``, ``new``, ``edit``, ``definition``,
    ``addSource``, ``status``, ``validated``, ``lineage``) and the hook that runs
    every lifecycle call. A failure becomes a message, never an exception.
``modelDraft.js``
    ``toDraft`` and ``fromDraft`` convert the stored document to flat grid rows
    and back. Keys the typed controls do not show (provider config, extra
    certification keys, predicates that are not simple equality, security
    extras, annotations, and the whole of ``visualizations``, ``dashboards``,
    ``reports`` and ``schedules``) are carried through unchanged, so a round
    trip of any backend document is the identity (checked in Jest on documents
    produced by ``validate_model``).
``modelForm.js``
    The forms, written as descriptors and rendered by ``FieldControl`` and
    ``RecordGrid`` (``ModelFields.jsx``). Vocabulary (source kinds,
    classifications, dimension and measure kinds, time-intelligence operations,
    window operations) comes from the provider's ``analytical_profile`` and
    capabilities, not from engine literals.
``ModelEditor.jsx``
    Toolbar (Save, Validate, status transitions, Clone, Delete) and the tabs:
    Model, Dimensions, Measures, Parameters & filters, Security,
    Materializations, Try it, Charts and reports, Lineage, Revisions, Advanced
    JSON. A published model is read-only until returned to draft.
``modelsClient.js``
    Every workspace action the view calls, in one place.

Capability map
--------------

(a) already in the BI module, (b) new in the Models view, (c) deliberately
dropped (justified below).

.. list-table::
   :header-rows: 1
   :widths: 30 10 60

   * - Old capability
     - Class
     - Where it lives now
   * - Model create, edit, delete, clone
     - b
     - Toolbar and Model tab. Delete asks for confirmation; clone asks for a
       name.
   * - Revisions and history
     - b
     - Revisions tab: every stored revision with status, and a field-level
       comparison of any two (``semantic_model_compare``).
   * - Status draft, published, archived
     - b
     - Toolbar transitions: Publish and Return to draft confirm; Archive and
       Restore do not. Publishing is required to authorize scheduled reports.
   * - Source editor (resource, native relation, kind, classification, grain)
     - b
     - Model tab grid plus a picker for discovered resources.
   * - Join editor
     - b
     - Model tab grid (left and right source, join type, cardinality, equality
       key). Joins with several or non-equality predicates are kept as stored.
   * - Relationship editor
     - b
     - Model tab grid.
   * - Dimension, hierarchy, level and time-role editors
     - b
     - Dimensions tab (nested hierarchy and level grids, time role, timezone,
       fiscal year start).
   * - Measure and calculation editors, certification
     - b
     - Measures tab. Calculations are ``measure operator measure``; a more
       complex stored expression is kept and shown as such (edit it on the
       Advanced JSON tab).
   * - Parameter editor
     - b
     - Parameters & filters tab (typed default and allowed values) and default
       filters.
   * - Time-intelligence and window editors
     - b
     - Time intelligence is configured per dimension (Dimensions tab) and used
       in the Try it query (operation, dimension, period, anchor). Analytical
       windows are Try it fields, offered only when the provider lists window
       operations.
   * - Security row filters, tenant filter, roles
     - b
     - Security tab.
   * - Materializations
     - b
     - Materializations tab, with the provider plan preview and the confirmed
       apply (``visual_admin_apply``), unchanged in behaviour.
   * - Query builder, compile, run
     - b
     - Try it tab: axes, slices, parameter values, drill, time intelligence,
       windows, totals and limit. A clean saved model is queried by id; an
       edited one is sent as the draft.
   * - Cellset and pivot
     - b
     - Cellset grid under Try it: transpose, drill up and down, active slice,
       CSV and JSON export.
   * - Diagnostics and reproducibility manifest
     - b
     - Try it tab, "Query diagnostics".
   * - Lineage
     - b
     - Lineage tab (nodes and edges from the validator).
   * - Compare
     - b
     - Revisions tab.
   * - Embedded visualizations, dashboards: reading
     - b
     - "Charts and reports" tab, read-only tables.
   * - Embedded visualizations, dashboards: running and sharing them
     - a
     - After migration they are saved questions and BI dashboards, with
       collections, sharing (:doc:`bi_permissions`), filters, cross-filters and
       drill-through.
   * - Reports and schedules: definitions
     - b
     - "Charts and reports" tab, read-only. They keep running through
       ``report_scheduler``.
   * - Report schedule authorization, revoke, occurrences, cancel
     - b
     - "Charts and reports" tab, for published models when the endpoint can
       execute scheduled reports (``report_scheduler_*`` actions, unchanged).
   * - Authoring new charts, dashboards, reports, schedules inside a model
     - c
     - Dropped from the typed UI; see below.
   * - Manual "Run report" and manual delivery from the workspace
     - c
     - Dropped; see below.
   * - Legacy dashboard runner, chart-click cross-filter
       (``semanticCrossFilter``) and ``SemanticChartView``
     - c
     - Replaced by the BI dashboard viewer.
   * - Relationship diagram view
     - c
     - It was a text listing of source pairs. The Model tab grid and the
       Lineage tab show the same facts.

Dropped capabilities and why
----------------------------

* **Authoring in-model charts, dashboards, reports and schedules.** BI
  questions and dashboards are the supported place for charts and boards; a
  second editor for the same objects would diverge. Existing content stays in
  the model and stays valid, can be migrated, and can still be edited as JSON on
  the Advanced JSON tab.
* **Ad-hoc "Run report", manual delivery and the ResultControls delivery and
  export profile pickers for semantic results.** The scheduler still delivers
  scheduled reports. Manual delivery and report subscriptions belong to the BI
  alerts and subscriptions work, which has not merged. Cellset results can be
  exported as CSV or JSON from the grid.
* **The in-model dashboard runner and chart-click cross-filter.** The BI
  dashboard viewer implements cross-filtering, and the migration converts a
  dashboard with ``cross_filtering`` on into dashboard filters and links.
* **Relationship diagram.** See the table.

Migration helper
----------------

``web/pgadmin/cdeadmin/bi/model_migration.py`` (``ModelMigration``) and the
workspace action ``semantic_model_migrate`` with
``{model_id, dry_run, accept_loss, collection_id}``. ``dry_run`` defaults to
true and must be a boolean.

* Each embedded **visualization** becomes a saved **question** of the semantic
  kind (``group_by``, ``aggregations``, field filters, ``order_by``, ``limit``)
  that points at the model revision that was read. Model parameters used by a
  filter are declared on the question.
* Each embedded **dashboard** becomes a BI **dashboard** whose cards pin the new
  question revisions. The legacy tile layout is scaled to the 24-column grid
  (it is assumed to be 12 columns; tiles without a layout flow two per row).
  ``cross_filtering`` becomes one dashboard filter per chart and a
  ``click_<card>`` link per card.
* The model is **never modified**. Reports and schedules refer to the embedded
  dashboards and visualizations, so migration copies and does not remove.
* **Idempotent.** Every created object carries the marker
  ``[migrated-from-semantic-model <model_id> <visualization|dashboard> <id>]`` in
  its description. Running again finds the marker and reports ``exists``, even if
  the object was renamed. A name collision gets a " (migrated)" suffix.
* **Losses are explicit.** The saved-question contract has no time
  intelligence, analytical windows, rollup totals or drill modes, and cannot
  order by a window column. A chart that needs one is reported with its losses
  and **skipped** unless ``accept_loss`` is set; a dashboard that depends on a
  skipped chart is ``blocked``. Nothing is dropped silently.
* Created objects go into a collection named "Migrated: <model name>" unless a
  ``collection_id`` is given.
* The report (the same shape for dry run and apply) lists the collection,
  questions, dashboards, the reports and schedules (``kept-in-model``), a
  summary count by state and the subscription TODO below. The Models view shows
  it as a table with "Preview migration" and "Migrate to BI".

Tests: ``tools/tests/test_cdeadmin_bi_model_migration.py`` (conversion, dry run,
apply, idempotency, rename by marker, model JSON unchanged, losses, collisions,
workspace actions).

Reports and schedules
---------------------

They stay in the model, are validated by ``validate_model`` as before and keep
running through ``report_scheduler``. The Models view exposes them read-only:
the definitions, plus authorize, revoke, occurrences and cancel for published
models. Whether automatic execution is available comes from the
``scheduled_report_execution`` capability of the new
``semantic_model_capabilities`` action (the same blocks the workspace bootstrap
carried under ``semantic_models``, so the view no longer depends on the
bootstrap payload).

.. _bi_models_subscription_todo:

TODO: convert to subscription
-----------------------------

"Convert to subscription" (report or schedule to a BI subscription) is
**not built**. It needs the BI alerts and subscriptions branch, which has not
merged. Until then the Models view states this in place of a button and the
migration report carries ``subscription_conversion: {available: false, todo}``.
When that branch lands: add a ``semantic_model_convert_report`` step that maps
``report.dashboard_id`` to the migrated dashboard (found by the marker),
``schedule.expression`` and ``timezone`` to the subscription schedule and
``delivery`` to its recipients, make it idempotent with the same marker, and
only then retire the report from the model's scheduler.

Tests and fixtures
------------------

* Jest, ``web/regression/javascript/bi``: ``modelDraft.spec.js`` (round trip of
  real backend documents, session reducer, forms, query draft),
  ``modelsClient.spec.js`` (request shapes), ``BIModelsTool.spec.jsx`` (component
  flows with a fake workspace), ``module.spec.jsx`` (surface registration).
* ``web/regression/javascript/cdeadmin/ProviderWorkspaceContent.spec.jsx``: the
  four semantic-workspace tests were rewritten for the Models view; the
  cross-filter helper test now asserts the helper is gone.
* Fixtures ``bi/modelFixtures.js`` are generated from the real validators and
  workspace actions by
  ``tools/tests/fixtures/cdeadmin_bi/generate_model_ui_fixtures.py``.
* ``tools/cdeadmin_semantic_analytics_gate.py`` now looks for its UI strings in
  the Models view files.

Decisions for the owner
-----------------------

* Open the view from the object tree as a tool: add the ``bi.models`` entry to
  each engine's ``tools.json``. This was not done because it would touch
  ``ui_descriptors/mysql/``, which is outside this change.
* The legacy tile layout is assumed to be 12 columns wide.
* Cross-filter values are compared as text unless the dimension is a date or
  datetime.
* Lossy charts need an explicit "Also migrate charts that lose features".
* The tenant filter's principal claim is now editable. The old screen showed it
  read-only as ``user_id``, the only claim the workspace binds today, so any
  other value refuses queries when the filter is required.
* Authoring new in-model reports and schedules is dropped; confirm that BI
  subscriptions are the intended home.
