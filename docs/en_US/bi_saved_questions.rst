.. _bi_saved_questions:

**********************************
BI saved questions and collections
**********************************

This note records the Stream C1 backend (``web/pgadmin/cdeadmin/bi``): saved
questions and collections, compiling builder state, executing a question
through the result service, SQL-to-question conversion. Dashboards are in
:doc:`bi_dashboards`. There is no UI yet.

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

``bi_question_compile`` renders filter values as escaped literals, for display
and preview only. Execution never uses that form (see below). Parameters are
bound from question defaults and the request and validated against their
declared types and ``allowed_values``.

Access
======

Requests use the existing workspace action route
(``POST`` workspace action, handled in ``servers/__init__.py``) with an
``action`` prefixed ``bi_``, dispatched to ``ProviderWorkspaceService.bi_action``
which resolves the owned server first. Every lookup goes through
``BIAccess.require`` (:doc:`bi_permissions`): without a grant only the owner
has access, and anyone else sees "unavailable", the same as semantic models.
Sharing actions are listed in :doc:`bi_permissions`.

Actions: ``bi_collection_list|create|update|delete``,
``bi_question_list|get|create|update|status|move|clone|delete|history|revision``,
``bi_question_compile``, ``bi_question_execute|page|export``,
``bi_cache_info|invalidate`` and ``bi_sql_to_question``. Dashboard actions are
listed in :doc:`bi_dashboards`.

Execution
=========

``bi/execution.py`` (``BIExecutor``) runs a question and owns no SQL execution
or row rendering of its own. The path is the existing one:

#. ``BIService.compile_definition(..., bind=True)`` compiles the question.
#. ``DataStudioService.open_session/execute/poll`` runs it on a fresh,
   short-lived session (closed afterwards, so no retained transaction state).
#. ``DataStudioService.admit_result`` hands the provider result to
   ``ResultService``, which produces the typed descriptor (``result_kind``,
   schema, grid contract, limits).
#. ``ResultService.restrict`` narrows the descriptor to the question's
   ``result_policy``; ``ResultService.render`` pages it and
   ``ResultService.export`` exports it.

Bound parameters
----------------

With ``bind=True`` no caller value is part of the statement text. The
semantic compiler (query field ``bind``: ``qmark`` or ``format``) writes the
engine's marker for every filter value and returns the values as the
positional ``parameters`` array, in the textual order of the markers (the
order is fixed after the whole statement is built, so time-intelligence and
window wrappers cannot reorder it). Markers by engine: SQLite, DuckDB and
Firebird ``?``; MySQL, MariaDB and PostgreSQL ``%s`` (a literal ``%`` is
doubled when values are bound). An engine with no entry in ``BIND_STYLES``
refuses to execute rather than fall back to inlining. Dashboard field filters
(``extra_filters``) are bound the same way.

Raw ``sql`` questions use ``{{name}}`` for a declared parameter. The lexer
(``bi/sqltext.py``) replaces only ``{{name}}`` tokens that sit outside string
literals, quoted identifiers and comments, rejects undeclared names, checks
each value against the declared type and ``allowed_values``, and refuses
``array`` parameters (use a builder filter with ``in``). Before running a raw
question the same lexer requires a single ``SELECT``/``WITH`` statement with
no write keyword. That is a lexical guard, not a sandbox: connection
privileges remain the authority.

Result policy
-------------

``result_policy`` on the question document (all optional):

``redact_columns``
    Column names masked in every page, the schema/grid contract and exports.
``export``
    ``{enabled, formats}``. Export is off unless a question opts in; the
    descriptor's own export formats are intersected with the list, so the
    result service refuses anything else as well.
``cache_ttl_seconds``
    0 to 86400, default 300. A request may only shorten it.
``page_size``
    Default page size, 1 to 500 (the result service bound).

``ResultService.restrict`` can only make a descriptor stricter. Results belong
to the executing principal: ``bi_question_page`` and ``bi_question_export``
refuse another user's ``result_id`` (the generic ``result_page`` action is
endpoint-bound only, so BI results use the BI actions).

Result cache
------------

The cache keeps the admitted ``result_id``; rows stay in ``ResultService``'s
bounded store. The key is ``(question id, question revision, request
parameters and dashboard filters, compiled plan digest, principal, endpoint)``.
Because the compiled SQL and values are part of the key, a changed unpinned
semantic model, tenant claim or default parameter also misses. ``cache`` in
the response reports ``hit``, ``hits``, age and remaining TTL.

* A hit is reused until ``cache_ttl_seconds`` expires; ``bypass_cache``
  refreshes; TTL 0 never reuses.
* A result stays pageable and exportable for a lease of at least 10 minutes
  even when not reusable. The store holds at most 64 results; the oldest is
  released first.
* Invalidation: ``bi_cache_invalidate`` (by ``question_id``, ``result_id`` or
  all of the caller's entries) releases the descriptors, and updating,
  archiving or deleting a question invalidates all of its entries
  automatically. Archiving also stops the question, and its pinned revisions,
  from running.
* Entries of one principal are never visible to another.

SQL-to-question
===============

``bi_sql_to_question`` (``bi/convert.py``) maps a raw SELECT onto builder
state only where the mapping is unambiguous: one relation, plain columns and
SUM/COUNT/COUNT DISTINCT/MIN/MAX/AVG, AND-ed ``column op literal``, ``IN``,
``BETWEEN``, ``IS [NOT] NULL`` filters (a right-hand side may be
``{{parameter}}``), GROUP BY, ORDER BY and LIMIT. The result is:

``fidelity``
    ``exact``: the builder reproduces the statement. ``lossy``: mapped, with
    differences listed in ``loss`` (for example a missing LIMIT becomes the
    default cap of 500, comments are dropped, a generated aggregate name).
    ``none``: not mapped.
``question``
    The builder question, or for ``none`` a raw ``sql`` question holding the
    exact original text.
``loss``
    ``{code, severity, detail}``; severity ``blocking`` entries name every
    construct that prevented mapping (joins, subqueries, ``*``, expressions,
    OR, DISTINCT, HAVING, window functions, set operations, CTEs, LIKE,
    native placeholders ...).

Nothing is guessed: a statement that does not map stays raw SQL.

Tests
=====

``tools/tests/test_cdeadmin_bi_saved_questions.py`` covers validation,
per-engine SQL for all six engines, quoting and limit differences, the service
lifecycle, owner isolation, and executes compiled SQL on real SQLite and DuckDB
fixture tables.

``tools/tests/test_cdeadmin_bi_execution.py`` covers bound parameters for all
six dialects, injection attempts (compile level and live), raw-SQL markers and
the read-only guard, typed descriptors, paging bounds, redaction, export
gating, principal isolation, revision pinning, cache hit/miss/TTL/bypass/
invalidation/eviction, and SQL-to-question (including that mapped questions
return the same rows as the original SQL on both engines).

The live tests use ``tools/tests/bi_live_harness.py``: real semantic compiler,
real ``ResultService``, real ``sqlite3``/``duckdb`` connections. The production
SQLite/DuckDB providers refuse a runtime that differs from their admitted
profile (3.53.0, 1.5.2), so the harness replaces only the Data Studio session.
Running through the production providers is the remaining qualification step.

Next
====

Joins from the semantic layer in the builder, sharing and permissions beyond
the owner, scheduled threshold alerts (C4). Row-level policy for raw SQL
questions is not enforced by the common layer; use a semantic question when a
row filter or tenant claim must apply.

Raw SQL hardening (2026-10-28)
------------------------------

Raw SQL questions run with the connection's database privileges, so the
lexical guard is defence in depth, not a sandbox. ``assert_read_only_select`` now
also refuses:

* side-effecting or host-reaching calls on any engine (``pg_sleep``, ``pg_read_*``,
  ``pg_advisory_*``, ``lo_*``, ``dblink*``, ``nextval``/``setval``, ``set_config``,
  ``load_file``, ``sleep``, ``benchmark``, ``get_lock``, ``load_extension``,
  ``readfile``/``writefile``, ``read_*``/``write_*`` table functions and similar;
  the full list is in ``bi/sqltext.py``);
* row locks (``FOR UPDATE``/``SHARE``/``NO KEY UPDATE``, ``LOCK IN SHARE MODE``);
* file output (``INTO OUTFILE``/``DUMPFILE``) and a file literal after ``FROM``/``JOIN``.

The guard now runs on every raw compile, previews included.

Raw SQL does not pass through semantic row policies. ``BIService.assert_raw_sql_allowed``
therefore refuses raw questions on an endpoint whose semantic models declare
``security.row_filters`` or ``tenant_filter``. ``add_raw_sql_policy(callback)``
replaces that built-in rule: every registered callback must approve
``(user_id, endpoint_id)``, so the host can grant raw SQL to specific principals.

Residual risk: a lexical guard cannot see through dynamic SQL or an engine-specific
function it does not list. Run raw questions through a database principal that only
has SELECT on what the user may read. Engine-level read-only sessions (for example
``BEGIN READ ONLY`` on PostgreSQL) need Data Studio support and are not done.
