.. _bi_dashboards:

****************************************
BI dashboards and the dashboard format
****************************************

Stream C1 remainder (backend only, no UI). Saved questions, execution and the
result cache are in :doc:`bi_saved_questions`. The dashboard code is
``web/pgadmin/cdeadmin/bi/dashboard_models.py`` (document, validation, filter
resolution), ``dashboards.py`` (lifecycle, card runs) and ``dashboard_ddn.py``
(monitoring conversion).

The dashboard document
======================

One document format (``contract_version`` 1.0.0) serves BI dashboards and
monitoring dashboards. Top level: ``name``, ``description``, ``collection_id``,
``tabs``, ``cards``, ``filters``, ``cross_filters``, ``drill_throughs`` and
``settings``.

``tabs``
    ``[{id, name}]``, at least one (default ``main``), at most 16.
``cards`` (at most 100)
    Each card has ``id``, ``tab_id``, ``title`` and ``layout`` ``{x, y, w, h}``
    on a 24-column grid, and one of:

    ``question``
        ``question: {question_id, revision}``, a *pinned* saved-question
        revision (the revision must exist and belong to the owner), plus an
        optional ``visualization`` override.
    ``text``
        ``text: {markdown}``, up to 20000 characters.
    ``metric_panel``
        A static monitoring snapshot imported from a collector channel:
        ``panel_id``, ``columns`` and ``rows`` (``id, measure, value, unit,
        rate``). It carries no query and holds a frozen snapshot rather than a
        live collector stream (monitoring dashboards remain display-only views
        over collectors and never reuse BI questions).

``filters``
    Dashboard filters: ``id``, ``name``, ``type`` (string, integer, number,
    boolean, date, datetime), ``widget`` (text, select, multi_select, number,
    date, date_range, toggle), ``operator`` (default ``eq``; ``in`` for
    multiple; ``between`` for ``date_range``), ``default``, ``required``,
    ``allowed_values`` and ``targets``. A target names a question card and
    exactly one of:

    * ``parameter_id``: a declared parameter of the pinned question (type
      must match; a multiple or range filter may map to an ``array``
      parameter);
    * ``field``: ``{column}`` for a builder question or
      ``{source_id, field}`` for a semantic question. The filter becomes an
      extra bound filter on that field. Raw SQL questions only accept
      parameter targets.
``cross_filters``
    ``{id, source_card_id, source_column, filter_id, exclude_source}``. A
    click on a mark sets the filter to the clicked row's value; by default the
    clicked card is not filtered by its own click.
``drill_throughs``
    ``{id, source_card_id, trigger, label, target}``. ``trigger`` is a
    ``column`` or the whole ``row``. The target is a pinned ``question`` with
    ``parameter_mappings`` or another ``dashboard`` with ``filter_mappings``;
    each mapping takes its value ``from`` the clicked ``column``, a literal
    ``value`` or the current ``filter_id`` value.
``settings``
    ``auto_refresh_seconds`` and, for monitoring dashboards,
    ``monitoring: {module, channel, columns, entry, view}``.

Filter resolution (``resolve_filters``) validates values against the filter's
type and ``allowed_values``, applies defaults, skips filters without a value
(an error if ``required``) and returns, for each question card, the
``parameters`` and ``extra_filters`` to run it with. Values are only carried:
the executor binds them, they never enter SQL text.

Persistence and permissions
===========================

Tables ``cde_bi_dashboard`` and ``cde_bi_dashboard_revision`` (migration
``cde_bi_dashboards_v1``, chained after ``cde_bi_saved_questions_v1``).
Like saved questions, every create, update, archive or move bumps
``revision`` (``expected_revision`` is checked) and appends an immutable
revision row; the ORM refuses updates to revision rows. As owner-confirmed,
the migration does not bump ``SCHEMA_VERSION``.

Permissions default to owner-only: every lookup goes through
``BIAccess.require``, so a user with no access sees "unavailable"; cards can
only pin question revisions the saver can view. A question used by a dashboard cannot be deleted, and
a collection holding a dashboard cannot be deleted. Sharing (view, edit and
manage grants) is described in :doc:`bi_permissions`; with no grants this
owner-only behaviour is unchanged.

Because cards pin revisions, editing a question never changes a saved
dashboard; the dashboard editor re-pins deliberately.

Actions
=======

Through the existing ``bi_*`` workspace action route:
``bi_dashboard_list|get|create|update|status|move|clone|delete|history|
revision``, ``bi_dashboard_resolve`` (filters to per-card bindings),
``bi_dashboard_card_run``, ``bi_dashboard_run`` (every question card, or one
``tab_id``; a failing card reports ``error`` and does not stop the board),
``bi_dashboard_cross_filter``, ``bi_dashboard_drill``,
``bi_dashboard_from_ddn`` and ``bi_dashboard_to_ddn``. Card runs use the
question executor, so they share its bound parameters, result policy and
cache.

Monitoring dashboards in the same format
========================================

Existing monitoring dashboards are DDN projects
(``ddn-source-workspace@1``, one ``dashboard.ddn``, written by
``static/js/cdeadmin_ui/integrations/ddn/dashboardPanels.js`` and stored and
published by ``workspace/dashboard_definitions.py``). They are not rewired;
``dashboard_ddn.py`` converts in both directions.

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - DDN monitoring source
     - Dashboard document
   * - ``source "metric_feed"`` ``channel`` (``<module>.observations``)
     - ``settings.monitoring.channel``; ``module`` is the prefix
   * - ``panels.composed@1`` view (a page)
     - a tab (``id`` = view id, ``name`` = view title)
   * - composed ``columns`` (1 to 4)
     - ``settings.monitoring.columns``
   * - composed panel entry
     - a ``metric_panel`` card, ``title`` = entry title
   * - entry ``layout`` ``row`` / ``column``
     - ``x = column * 24/columns``, ``y = row * 8``, ``w = 24/columns``,
       ``h = 8``
   * - ``table.records@1`` view with a ``panel eq <id>`` filter
     - ``metric_panel.panel_id``
   * - ``data "observations"`` rows of that panel (``id, panel, measure,
       value, unit, rate``)
     - ``metric_panel.rows`` (``id``, ``measure``, ``value``, ``unit``,
       ``rate``)
   * - snapshot ``entry`` / ``view``
     - ``settings.monitoring.entry`` / ``view``

``ddn_to_dashboard(snapshot)`` returns ``{dashboard, loss}``.
``dashboard_to_ddn(dashboard, strict=False)`` returns ``{snapshot, loss}``.
The writer is a port of ``dashboardPanelFiles`` and reproduces the JavaScript
output byte for byte (the tests compare against fixtures generated by the real
encoder, ``tools/tests/fixtures/cdeadmin_bi/generate_monitoring_fixtures.mjs``,
and run the converted snapshots through the production publication
validator). Only ``ddn-source-workspace@1`` converts; legacy sources need the
explicit migration first, never a relabel.

Loss is reported, never silent. On import: declarations other than the metric
source, observations and views, panels that do not reference a filtered table
view, observations for panels with no card, and non-default columns. On
export: question and text cards, filters, cross-filters and drill-throughs
(DDN monitoring dashboards have none), and positions or tabs that the DDN
writer normalizes (fixed two columns, twelve panels per page). ``strict``
turns any loss into an error. Structural impossibilities (no metric feed, a
different observations schema, more than four columns, no metric panels,
no ``settings.monitoring``) raise ``ConversionError``.

Collector, viewer and editor boundaries are unchanged: the converter does not
grant collection authority, does not publish, and is not a second dashboard
editor. Publishing a converted snapshot still goes through
``DashboardDefinitions.save``/``publish``, which validate it.

Tests
=====

``tools/tests/test_cdeadmin_bi_dashboards.py``: document validation,
lifecycle (revisions, optimistic checks, owner isolation, name/collection/
question guards), filter resolution (parameters, field targets of both
shapes, defaults, required, domains, multiple, range, cross-filter exclusion,
drill-through), live board runs on SQLite and DuckDB (filter binding,
injection through a filter value, per-card errors, caching, pinned revisions),
the migration round trip and the monitoring conversion.

Unified DDN BI dashboard designer, kiosk server and importers (2026-11-10)
==========================================================================

``pgadmin.cdeadmin.design_store.bi_ddn`` and
``cdeadmin_ui/integrations/ddn/BIDesignerSurface.jsx`` implement the
task-specific DDN BI dashboard designer on ``designs.db``:

* **Composed DDN views and wiring**: Dashboards render tabs via
  ``panels.composed@1`` and card/filter lineage via ``bi.analytics@1`` in the
  shared ``DDNViewerSurface``. Cards reference ``question`` designs by design
  ID (pinned version by default, with an opt-in to follow the latest accepted
  version). Imported ``metric_panel`` cards hold static snapshots only.
  Write-back and action buttons are refused in the first release.
* **Interaction defaults**: Card clicks cross-filter by default (with per-card
  ``inherit``/``cross_filter``/``highlight``/``none`` overrides), dashboard
  filters auto-apply, viewer filter state stays personal unless author-pinned,
  and drill-through carries active dashboard and cross-filter context.
* **Reviewed outward effects and remote dashboard server**: Accepting a
  dashboard activates the version without enabling subscriptions, embeds or
  remote publication. Publishing to the display-only dashboard server
  (``GET /cdeadmin/api/bi-server/dashboards/<publication_id>``) requires a
  separate reviewed switch under an explicit ``publisher_user_id``, with
  HMAC-signed device tokens that can only narrow results via locked filters.
* **Clean-room Superset and Metabase importers**: Clean-room PostgreSQL-licensed
  importers read Apache Superset YAML ZIP exports and Metabase serialization
  bundles into ``Draft`` ``question`` and ``dashboard`` DDN designs with
  explicit loss reports and stripped principals/recipients/secrets.

Post-first-release BI write-back review and collector bindings (2026-11-11)
===========================================================================

* **Action buttons routed through native-operation review**: BI questions remain
  strictly read-only, while BI dashboards in ``bi_ddn.py`` and
  ``BIDesignerSurface.jsx`` may declare structured ``action_buttons``
  (``insert_row``, ``update_row``, ``delete_row``, ``provider_operation``)
  stored in DDN as ``query_operation`` elements wired to ``dashboard_wiring``.
  ``POST /cdeadmin/api/projects/<project_id>/designs/<design_id>/bi/action-review``
  refuses non-human actors, display-only kiosk device tokens, unaccepted
  dashboards (unless ``dry_run``) and unkeyed ``UPDATE``/``DELETE`` buttons,
  compiles parameterized dialect SQL with destructive-data-loss warnings, and
  submits an ``OperationRequest(approval_required=True)`` to ``OperationBus`` in
  ``awaiting_approval`` stage without executing SQL directly.
* **Read-only collector bindings on metric_panel cards**: Imported monitoring
  ``metric_panel`` cards remain ``static`` snapshots by default. Authors may
  opt a ``metric_panel`` card into ``snapshot_mode: "collector_read_only"``
  with a typed ``collector_binding`` (``engine``, ``server_id``, ``target_id``,
  ``metric_group``, ``metric_keys``, ``freshness_budget_seconds``).
  ``POST /cdeadmin/api/projects/<project_id>/designs/<design_id>/bi/collector-panel``
  calls only the engine's read-only ``MonitoringHost.snapshot``, rechecks viewer
  authorization, reports ``live``/``stale``/``collector_disabled``/``unauthorized``
  freshness, never starts or mutates collectors, and never reuses BI questions
  for monitoring.
