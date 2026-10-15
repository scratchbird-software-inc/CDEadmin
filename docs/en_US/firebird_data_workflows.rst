Firebird data workflows
***********************

This section covers FB-COMP-03, 07, 08 and 12 for native Firebird network and
embedded attachments. Form validation remains assigned to the human team.
Native permissions, preparation, constraints and transaction outcomes remain
engine-owned.

Implemented workflows
=====================

FB-COMP-03: Metadata and data exchange
------------------------------------

Object, branch and database catalog capture supports native SQL and documentary
DDN, with metadata, data or both selection. Native metadata SQL preserves
complete statements, dependencies, comments, grants and creating-user/external
prerequisites. Tables/keys precede deferred foreign keys; routine and package
signatures precede bodies. Explicit download does not connect, commit or apply
anything.

Data capture uses one dedicated read-only SNAPSHOT attachment/transaction,
retains lossless native typed values and excludes nonpersistent/external tables
explicitly. Limits are 100,000 rows, 8 MiB and 120 seconds; empty-table metadata
and the final page also obey the limits. Success and failures release owned
cursors and sessions. JSON and static DDN carry the captured values and scope.

Import review binds exact destination-native table/column types and identities,
then stages bound inserts in a separate non-autocommitting session. Identity
values are preserved explicitly; computed values are not inserted. Constraints
remain enabled. Explicit row order can resolve admissible cyclic layouts without
rewriting values. Commit and rollback remain explicit. Active/unknown native
observations keep work pending; allocation review is withheld until the native
transaction is observed idle. Sequence/identity restart is a separate operation.

FB-COMP-07: Generated test data
------------------------------

Recipes provide defaults, constants, seeded random/choice, exact sequential,
file-backed, existing-column and generated-column sources, with NULL percentages
and native FK ordering. Composite generated references retain row positions.
An explicit NULL in any composite FK segment breaks that FK dependency; omitted
defaults do not. Unresolved cycles are rejected without disabling constraints.

Numeric JSON tokens are checked before JavaScript rounding. Fractional/unsafe
values and signed zero use exact strings or native typed envelopes; fractional
NULL percentages remain available. Recipes and previews preserve native names,
including property names that resemble JavaScript built-ins.

Preview is bounded to 32 tables, 1,000 rows per table, 5,000 total rows and 4 MiB.
Save/load/download/preview do not mutate the database. Staging uses a dedicated
SNAPSHOT WRITE session with autocommit disabled. Each row needs native staged
receipt evidence. Stop prevents subsequent rows; failed/lost replies prevent
replay. Pending rows require explicit native transaction control. Late opens and
other async work retain their original route; close is attempted again after
in-flight work settles when the early release could not complete.

FB-COMP-08: Metadata search
-------------------------

Search explicitly selected registered databases independently, over names,
kinds, descriptions, native SQL/PSQL source and field metadata. Search is a
literal case-insensitive substring, never executable SQL or regex. Each database
retains its successes, access errors, missing-DDL counts, native coverage gaps
and warnings. Results carry native identities/generation for normal scoped
navigation. Stop ends the request sequence after the current database. Changing
scope discards late results and prevents the old sequence from continuing.

FB-COMP-12: BLOB viewing and editing
----------------------------------

Materialized text/binary BLOBs support strict UTF-8 or reversible binary import
and export, NULL/empty distinction, preservation of original line endings and
explicit LF/CRLF conversion. Apply stages a value in the row editor; row Save and
transaction controls remain separate. Read-only access cannot stage changes.
The dialog and delayed file reads are bound to the native row/column context.

The editor/import bound is 1 MiB. Larger values use bounded native chunk transfer
and streamed file writing. Chunk display supports Base64, exact-offset hex/ASCII
and strict UTF-8, reporting split characters without replacement. File streaming
obeys write backpressure, preserves bytes and aborts incomplete files on stop or
failure; it never silently substitutes a truncated value.

Native verification
===================

``tools/firebird_data_export_native.py`` exercises a 205-row snapshot with a
concurrent excluded commit, lossless numeric/BLOB/array values, static DDN and
independent native import with explicit rollback then commit and preserved
identities. ``firebird_ddn_sql_native.py`` replays dependency-rich SQL using
native ISQL and checks comments, grants, routines, packages and enforced FKs.

``tools/firebird_test_data_native.py`` materializes the real recipe helper,
stages ten native rows, checks exact BIGINT values, generated composite keys,
existing samples, a partially NULL self-reference, independent visibility,
enforced constraints and explicit rollback. ``firebird_metadata_search_native.py``
can reconcile two independent native databases with distinct catalog contents.
``firebird_blob_editor_native.py`` verifies exact text/binary editing and a
3.6 MB native BLOB in bounded chunks, including early stream release.
``cdeadmin_firebird_blob_file_gate.py`` separately qualifies real browser file
writers, bounded backpressure and aborted-file preservation.

Python regressions and browser component/helper tests cover failure, uncertainty,
retargeting and preview-only behavior. Retain versioned receipts, logs and source
hashes in the external work area. Current native proof uses Firebird 5.0.4 over
TCP and embedded attachments on Linux; other native OS qualification remains a
separate platform responsibility. See ``firebird_functional_completion.rst``
for the owning contracts and ``tools/development/NATIVE.md`` for native setup.
