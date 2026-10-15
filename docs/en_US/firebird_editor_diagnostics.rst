Firebird editor and diagnostics
*******************************

This section covers FB-COMP-01, 02, 04, 05, 06 and 10 for native Firebird
network and embedded attachments. Form validation remains assigned to the
human team. Native preparation, permissions and transaction outcomes remain
engine-owned.

Implemented workflows
=====================

* FB-COMP-01: The query workspace offers Run with native profiling after
  explicit consent to replace an existing attachment profile and permit native
  profiler storage. Admission checks RDB$PROFILER; native package/plugin
  execution enforces privileges. The result shows profile identity, PSQL,
  requests, statements and record-source measurements in nanoseconds, with
  bounded sections and explicit partial/error states. Failed admission never
  dispatches user SQL. Uncertain start/finish or diagnostic transaction cleanup
  quarantines the attachment until it is closed.
* FB-COMP-02: Collect fresh attachment query statistics captures separate
  MON$ observations before execution and after fetch/cursor cleanup. Results
  identify both attachment IDs, original counter samples, nonnegative deltas,
  missing samples, attachment changes and counter resets. Host elapsed time
  includes dispatch, execution, fetch and cursor release. It is not CPU time
  or an isolated server statement counter. Observation transactions never
  finalize the user's transaction.
* FB-COMP-04: The language editor supplies Firebird lexical highlighting,
  exact native metadata completion, token-preserving whitespace formatting,
  UTF-8 file import/export and explicit selected/current/from-cursor previews.
  PSQL blocks and ISQL terminators protect internal statement boundaries;
  only inherited client settings accompany scoped execution. Source, endpoint,
  target, language or client-dialect changes invalidate prepared previews.
  Native SQL execution and retained script controls require an explicit action.
* FB-COMP-05: SQL history is persisted independently in the application
  configuration store, scoped by authenticated owner, server, registered target
  and client dialect. Capture is opt-in; parameters/results are excluded and
  credential-bearing/sensitive or oversized source is omitted. Retention,
  search, reload, previous/next and explicit scoped clearing are implemented.
  A storage failure does not replay or cancel a native request. History records
  request observations, not native transaction outcomes. Monitoring history
  remains a separate ScratchBird-backed feature.
* FB-COMP-06: Selected grid rows generate INSERT, UPDATE, UPDATE OR INSERT and
  IN-list previews. Native names, exact numbers, binary values, temporal values,
  NULL and explicit matching columns are preserved. Parameter output supports
  values without an admitted inline codec. Computed/identity write admission
  follows native column metadata. Preview, copy and editor handoff never execute
  SQL; execution retains the ordinary explicit transaction controls.
* FB-COMP-10: Object-context templates provide native SELECT, INSERT, UPDATE,
  DELETE, trigger, procedure, execute-block and available definition extraction.
  Custom templates support native metadata substitutions and reusable JSON
  file import/export. Generation checks reject stale metadata. Mutation
  templates respect system/view/column capabilities; UPDATE/DELETE start with
  FALSE predicates. Render and editor handoff do not execute SQL.

Verification entry points
=========================

Backend regressions are under ``tools/tests/test_firebird_*``. The editor,
history, row SQL, templates and diagnostics have component and helper tests
under ``web/regression/javascript/cdeadmin/Firebird*``. History tests reopen a
new application-store engine to check persistence and authenticated scope.

``tools/firebird_profiler_native.py``, ``firebird_editor_native.py``,
``firebird_row_sql_native.py`` and ``firebird_templates_native.py`` exercise
actual SQL/PSQL against uniquely owned disposable Firebird databases. Profiler
proof includes same-transaction preservation, rollback, native record-source
measurements and SQL failure without replay. Row/template proofs execute the
reviewed generated text only in those test-owned databases and verify rollback.
These helpers are also consumed by the native development qualification and
schema-planning gates. The native setup guide is
``tools/development/NATIVE.md``.

The owning acceptance contracts, diagnostic limitations and exact behavior are
in ``firebird_functional_completion.rst``. Retained test receipts belong in the
external work area, not this source tree. Runtime versions and invocation scope
must accompany any completion claim; a unit test alone is not native evidence.
