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
        A monitoring panel bound to a collector channel: ``panel_id``,
        ``columns`` and ``rows`` (``id, measure, value, unit, rate``). It has
        no query; live values come from the collector, never from a question.

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

Permissions are owner-only. Every lookup filters on ``user_id`` and the
endpoint, so another user sees "unavailable"; cards can only pin the owner's
own question revisions. A question used by a dashboard cannot be deleted, and
a collection holding a dashboard cannot be deleted. Sharing is C4.

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
