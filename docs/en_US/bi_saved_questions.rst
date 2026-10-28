.. _bi_saved_questions:

**********************************
BI saved questions and collections
**********************************

This note records the Stream C1 backend (``web/pgadmin/cdeadmin/bi``) and the
first C2 step, compiling builder state. There is no UI yet.

Model
=====

``Collection``
    Owner-scoped folder with ``parent_id`` (self-referencing, depth limit 16,
    unique sibling names, no cycles). A collection must be empty to delete.

``SavedQuestion``
    Endpoint-scoped, owner-scoped. Fields: name, description, collection,
    optional ``semantic_model`` reference ``{id, revision}``, a ``query``
    spec, a ``visualization`` spec (``type`` from the semantic chart set plus
    free ``settings``) and typed ``parameters``. ``query.kind`` is one of:

    ``builder``
        Ad hoc builder state over one relation: ``source.relation``,
        ``columns``, ``filters``, ``aggregations`` (sum, count,
        count_distinct, min, max, avg), ``group_by``, ``order_by``, ``limit``.
    ``semantic``
        Builder state over a semantic model (requires ``semantic_model``):
        ``group_by`` dimension or level ids, ``aggregations`` of
        ``measure_id``, semantic filters, ``order_by`` on output ids.
        ``semantic_model.revision`` pins the model revision; omit it to use
        the current model.
    ``sql``
        Raw SQL, stored and passed to the provider unchanged.

Persistence
===========

Tables ``cde_bi_collection``, ``cde_bi_saved_question`` and
``cde_bi_saved_question_revision`` (migration ``cde_bi_saved_questions_v1``).
Every create, update, archive or move bumps ``revision`` (optimistic check via
``expected_revision``) and appends an immutable revision row, as
``cde_semantic_model_revision`` does. The ORM refuses updates to revision rows.
Like the other recent CDEadmin migrations, this one does not bump
``SCHEMA_VERSION``.

Compilation
===========

No new SQL generator exists. Builder state is turned into a synthetic one-source
semantic model plus a semantic query (``bi/builder.py``) and passed to
``SemanticModelService.compile``, so the provider's own dialect contract and
``semantic_models/compiler.py`` produce the SQL. The compiler gained one
backward-compatible query field, ``order_by`` (``[{id, direction}]`` over
output columns), because semantic queries previously ordered only by axes.

Dialect differences come entirely from the provider contract:

=========== ========= =========================== =====================
Engine      Quote     Row limit                   Notes
=========== ========= =========================== =====================
PostgreSQL  ``"x"``   ``LIMIT n``
MySQL       backtick  ``LIMIT n``
MariaDB     backtick  ``LIMIT n``
Firebird    ``"x"``   ``ROWS 1 TO n``             no native rollup
SQLite      ``"x"``   ``LIMIT n``                 no native rollup
DuckDB      ``"x"``   ``LIMIT n``
=========== ========= =========================== =====================

Filter values are rendered as escaped literals by the compiler; parameters are
bound from question defaults and the compile request and validated against their
declared types. Raw ``sql`` questions are not rewritten, so their parameters are
returned to the caller for provider binding.

Access
======

Requests use the existing workspace action route
(``POST`` workspace action, handled in ``servers/__init__.py``) with an
``action`` prefixed ``bi_``, dispatched to ``ProviderWorkspaceService.bi_action``
which resolves the owned server first. Every repository lookup filters on the
owner's ``user_id`` (and ``endpoint_id`` for questions), so another user sees
"unavailable", the same as semantic models.

Actions: ``bi_collection_list|create|update|delete``,
``bi_question_list|get|create|update|status|move|clone|delete|history|revision``
and ``bi_question_compile``.

Tests
=====

``tools/tests/test_cdeadmin_bi_saved_questions.py`` covers validation,
per-engine SQL for all six engines, quoting and limit differences, the service
lifecycle, owner isolation, and executes compiled SQL on real SQLite and DuckDB
fixture tables.

Next
====

Execution and result caching of saved questions through the result service,
joins from the semantic layer in the builder, SQL-to-question, dashboards
(C1 remainder), sharing and permissions beyond the owner (C4).
