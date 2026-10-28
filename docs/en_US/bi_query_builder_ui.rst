.. _bi_query_builder_ui:

*****************************************
BI questions: the query builder UI
*****************************************

Stream C, first UI slice. The backend (saved questions, execution, result
cache) is described in :doc:`bi_saved_questions`; dashboards in
:doc:`bi_dashboards` have no UI yet. This page covers the front end of
"BI questions": a registered workbench tool that talks to one endpoint through
the ``bi_*`` workspace actions and nothing else.

Opening it
==========

Select a verified endpoint in the object tree, open its context menu and
choose **BI questions...** (group "information"). The entry comes from each
engine's ``ui_descriptors/<engine>/tools.json`` and uses the engine-neutral
``open_tool`` handler, which calls
``CDEadminCommandContext().openSurface('bi.questions', ...)``. There is no new
panel in ``ProviderWorkspaceContent.jsx`` and no engine branch in React.
MySQL is pending: see :doc:`bi_ui_mysql_handoff`.

Structure
=========

All code is under ``web/pgadmin/static/js/cdeadmin_ui/modules/bi/`` and is
registered by ``registerBIModule`` from ``platform/bootstrap.js`` as module
``cdeadmin.bi`` with surface ``bi.questions``. The surface is lazy: the chart
and editor libraries load on first open.

Pure modules (no React, covered by Jest)
    ``queryState.js`` (reducer, ``toQuestion``, ``fromQuestion``),
    ``validateState.js``, ``outputs.js``, ``columnTypes.js``,
    ``collectionTree.js``, ``sourceCatalog.js``, ``chartData.js``,
    ``executionModel.js`` and ``biClient.js`` (every request and response
    shape the UI relies on).

Hooks
    ``useBICatalog`` (tables from ``resource_page``, columns from
    ``resource_inspect``, models from ``semantic_model_*``, cached) and
    ``useQuestionSession`` (reducer, debounced compile preview, run, paging,
    save, save as, reload, SQL conversion).

Components
    ``BIQuestionsTool`` (collections plus the open question),
    ``CollectionBrowser``, ``QuestionEditor``, ``BuilderPanel`` with
    ``SourcePicker``, ``ColumnsSection``, ``ModelFieldsSection``,
    ``SummariesSection``, ``FiltersSection``, ``OrderSection``;
    ``SqlPanel`` (code editor and conversion report), ``SqlPreview``,
    ``ResultPane`` (``PagedDataGrid`` or ``BaseChart`` through ``ChartView``),
    ``ParametersPanel``, ``RevisionHistory`` and ``Dialogs``. Only
    ``cdeadmin_ui`` primitives and theme tokens are used; there are no
    ``@mui`` imports and no hard-coded engine names.

State model
===========

The builder state is a flat object: ``mode`` (``builder`` or ``sql``),
``source`` (table relation or semantic model), ``columns``, ``groupBy``,
``aggregations``, ``dimensions``/``measures`` (model sources), ``filters``,
``orderBy``, ``limit``, ``parameters``, ``values`` (run-time parameter text),
``visualization`` and the identity of the stored question (``questionId``,
``revision``, ``collectionId``, ``dirty``).

``toQuestion(state)`` produces the question document the backend validates
(``contract_version`` is stamped by the backend, never sent), and
``fromQuestion(record)`` is its inverse; the two round-trip every fixture in
``web/regression/javascript/bi/biFixtures.js``. Rules worth knowing:

* Adding the first summary moves the picked columns into the grouping;
  removing the last gives them back.
* Filters keep their text and carry a type category (number, text, date,
  boolean) that selects operators and parsing. Categories come from the
  column's declared type by its leading word, never from the engine.
* Output names mirror ``bi/builder.py`` so sort targets are offered before a
  run. A sort that no longer names an output is dropped.
* Run-time values and catalog retyping do not mark the question dirty.
* Saving uses ``expected_revision``. A "revision has changed" error offers
  **Reload latest**. Restoring from history loads an unsaved draft; the next
  save appends a new revision.
* SQL conversion calls ``bi_sql_to_question``. Exact results switch to the
  builder directly, lossy results list each difference and require accepting
  them, and ``none`` results list the blocking reasons and stay in SQL.

Tests
=====

``web/regression/javascript/bi/``: reducer and round-trip specs against
fixtures generated from the real backend validator and converter (header of
``biFixtures.js`` cites ``tools/tests/test_cdeadmin_bi_*.py``), client payload
specs, and React Testing Library specs with a fake ``api.post`` for the
collection list, the editor, SQL conversion, revision history, the dirty
guard, module registration and the ``open_tool`` handler. Run::

   cd web && npx jest regression/javascript/bi regression/javascript/families
   npx eslint -c .eslintrc.js pgadmin/static/js/cdeadmin_ui/modules/bi regression/javascript/bi

What is not done
================

* Dashboards, sharing and permissions UI.
* Joins in the builder and joins in semantic models.
* Export UI for results.
* Endpoint scope only; there is no database-target scope.
* The endpoint route is a live handle that the tool descriptor cannot carry,
  so after a layout reload the tool asks to be opened again from the tree.
* No module manifest or screen specification JSON, so the schema-validated
  spec gates do not cover this module.
* Column type classification is a heuristic on the declared type name.
* Chart series colors are a fixed hue palette rather than theme tokens.
* Only archived questions can be hidden; deleting a question from the UI is
  not offered (collections can be deleted when empty).
* No test against a live database; the specs use a fake API.
