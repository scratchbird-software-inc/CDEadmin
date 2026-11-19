Data Navigator: Data Viewer and SQL Editor specification
========================================================

Authority and scope
-------------------

This document records the owner's approved design and corrections from the
Data Navigator planning conversation, consolidated on 2026-11-17. It is the
persistent specification for subsequent implementation and handoff, including
after conversation context compaction. Read it before changing either surface.
The owner's later instruction to implement supersedes historical "planning
only" notes in the temporary review material; it does not turn every mockup
proposal into an approved decision.

The final agreed architecture is **two surfaces sharing components**: Data
Viewer and SQL Editor. Earlier discussion of combining them into one form is
superseded. Preserve existing UX and native backend functionality while sharing
presentation and controls. These requirements supplement :doc:`ui_unified_design`,
:doc:`compact_forms` and :doc:`project_shell_behaviour`. Engine capabilities
remain native and version-specific; shared presentation must not reduce the
product to the lowest common denominator.

Approval, implementation and human acceptance are separate. Requirements below
are approved unless explicitly marked open. The implementation ledger records
only verified work, not an assertion that this whole specification is complete.
Mockups show fixture content and do not establish native engine qualification.

Module, surface and display-area vocabulary
-------------------------------------------

DN-01. Data Navigator is a module, like BI or Projects. A module owns:

* The left drawer, containing one common set of module-wide contents; Data
  Navigator uses the Data Explorer.
* The right drawer, whose contents depend on the selected object or current
  activity: properties, inspection or specialised controls.
* The status line, describing current activity and state.
* The main work area and its surfaces.
* Its menus, tabbed-icon-bar (TiB) contribution and module-instance tab.

DN-02. Launching/focusing a module installs its menus and TiB, creates or focuses
its instance tab (default Data Navigator name: "Data Navigator #"), and presents
its default surface. Data Navigator starts with database connectors. Selecting
a surface installs that surface's work-area content, TiB and menus. Losing
surface focus removes its contributions, leaving the shell ready for the next
surface. Do not leave stale actions or menus from a previous focus.

DN-03. A surface is a task workspace. A single or dual display area is contained
inside that surface. Moving focus between its two areas does not switch modules
or surfaces or replace their menu/TiB ownership. The area's selection supplies
context for applicable actions.

Two surfaces, shared components
-------------------------------

DN-04. Data Viewer displays an identified table/view through its baseline query
(for example ``SELECT * FROM <table>``). Grid selections, filters, sorting and
display choices update its Information representation. It has **no visual
designer**, including no Visual SQL launch entry. Opening its query in the SQL
Editor remains available.

DN-05. SQL Editor accepts any valid statement supported by the connected engine,
including DDL, DML and PSQL. It supports the visual SQL designer, query execution,
results, metrics and plans. Preserve existing parameters, scripts, result-set
selection, saved queries/snippets, messages and native session operations.
Designer conversion must preserve its existing fidelity reporting; do not
silently replace SQL that cannot be represented by a visual model.

DN-06. Share the grid, record forms, column visibility/order, formatting, field
editors and applicable navigation controls. The Data Viewer's existing grid and
form layout are the visual authority. Keep provider calls, permissions, native
sessions, transactions, drafts and result identity in the owning controllers;
sharing presentation does not share or merge database sessions.

Content, presentation and placement
-----------------------------------

DN-07. Treat these as independent choices: **what to show**, **how to show it**,
and **where to show it**. A content choice must not silently change presentation
or placement. Apply presentations only where the content supports them.

The content choices are:

* **SQL:** the statement text; in SQL Editor this includes any supported
  DDL/DML/PSQL. Data Viewer remains based on its object query.
* **Visual designer:** visual query editing, SQL Editor only.
* **Data:** query results, when the statement returns data.
* **Metrics:** execution metrics and plan, preserving current functionality.
* **Metadata:** available when an SQL object such as a table, view, procedure
  or function is in context. It has four areas, in order: create statement,
  **object comment**, objects depending on it, and objects it depends on.
  The comment is not a comment on the create statement.
* **Information:** for an SQL object, a grid of its descriptive/catalog data.
  Users choose columns and order, and copy the chosen information as CSV, TSV
  or plain text to the clipboard. In query context without an SQL object, it
  shows the generated SELECT with the grid's filters/sorts so users can save
  the query they configured. Preserve parameter values/bindings when handing
  a query to another tool.

DN-08. The four agreed data presentations are:

* **Grid:** the existing Data Viewer grid.
* **Mini-form:** compact adaptive record forms as in the existing Data Viewer.
* **Full-form:** the current record uses the full available form area.
* **Hybrid:** the grid with its current record shown in a mini-form.

DN-09. Support a single display area or two display areas within the surface.
Each area selects its content and applicable presentation independently.
Dual display is stacked: the first area is above the second, as in the
owner-provided SQL/editor and data-grid example. Display area content and
applicable presentation controls belong on Format & Layout and in the View
menu. Both stacked areas are reserved for the selected content. A SQL + Data split is not proof that
arbitrary independent dual-area content has been implemented.

Grid, adaptive forms and preservation
-------------------------------------

DN-10. Retain the current grid's record gutter, row number/current-record and
bookmark/staging markers, pinned/resizable columns, header chooser, sorting and
filter indicators, cell/row selection, scrolling and keyboard movement. Keep
column visibility and order configurable for grid and form contexts.

DN-11. Keep automatic field placement: compute each field's width from its
actual data/type and any explicit width, then place and wrap fields against the
available form width in aligned grid positions. Reflow on viewport/drawer size
changes. Do not replace it with equal-width stretching or a fixed column count.
Mini-form, full-form and hybrid must use the common placement logic. A saved
explicit width remains a user preference.

DN-12. Show available help/object-field comment immediately below the focused
field; remove it when that field loses focus. Do not reserve a blank help block
when no help exists. New settings need meaningful localizable descriptive help;
existing record-comment behaviour alone does not qualify those new settings.

DN-13. Preserve the existing Data Explorer appearance using PgTree's
``FileTreeItem`` and ``TreeBranchGuides``: curved joins and continuation lines,
circular expand/collapse controls, spacing, selected node and active branch
trace. Do not substitute the simplified tree from rejected mockups.

DN-14. Preserve global colour schemes, custom palettes, typography and language
selection. Shared views, menus, drawers and dialogs inherit existing semantic
style tokens and translation mechanisms. Localize new labels/help. Do not
translate database identifiers, stored values or stored object comments.

Formatting and persistent layouts
---------------------------------

DN-15. Allow font and alignment defaults by field type. A user can save and
reload a layout for a particular connection/server + database + optional schema
+ table/view. Do not collide identically named objects on different endpoints.
Schema is optional according to the engine's naming model.

DN-16. The owner explicitly approved **property-by-property precedence**, highest
priority first:

1. Current explicit field choice.
2. Saved field setting in the object's layout.
3. Field-type default.
4. Application default.

Changing alignment must not discard an inherited font or other properties.
Saving a layout retains the user's selected properties for later visits.
Persisted layout changes do not themselves mutate database data or commit a
transaction. Preferences are saved by users. Templates can be saved and
shared between users. The precise storage schema remains an implementation task.

Specialised editors and reversible display conversion
-----------------------------------------------------

DN-17. Provide specialised editors appropriate to the value, including Markdown
(for comments) and JSON. Use the common field components in both surfaces.
This approval concerns editing actual structured/text data; it does not reverse
the prohibition on raw JSON substitutes for native administration forms.

DN-18. Support an explicitly configured forward display function and reverse
edit function. Example: display binary UUID bytes using the native binary-to-text
UUID function, and attempt the corresponding text-to-binary function on edits
before updating the underlying value. A binary field's length of 16 does not
establish UUID semantics. Conversion failure is visible to the user and retains
the original value; never overwrite it with an invalid or silently substituted
value. Native function availability, argument typing and version capabilities
must be respected. Configure the editor and conversion choice per field in the
saved object layout. Available forward/reverse function pairs come from engine
capabilities, and the user selects a pair. The invocation contract must preserve
native authorization and types.

Navigation, editing and database controls
-----------------------------------------

DN-19. The required primary navigation order is: first record, previous page,
previous record, bookmark current record, next record, next page, last record.
Preserve existing previous/next bookmark and jump functionality; their final
placement is open. Keyboard and TiB/menu actions must address the same current
record and page, and bookmarks must refer to the correct result/window identity.

DN-20. Provide edit mode and preserve applicable insert, duplicate, delete,
set-NULL, accept/revert and staged-work inspection controls. Honour read-only
results/fields and native identity requirements. Accepting a local row draft,
staging a mutation and committing a native transaction are distinct. Retain
unsaved-work/transaction close guards; navigation, presentation and focus changes
must not silently commit, roll back or discard work.

DN-21. Start Transaction opens a dialog for non-default native transaction
parameters. Commit and Rollback remain separate native operations. The two
prepare controls require separate icons, labels and semantics:

* **Transaction preparation:** native transaction prepare/two-phase support,
  only where supported. Normal single-phase commit must not be presented as a
  fictitious native PREPARE operation. The owner's single/two-phase distinction
  is retained; exact dialog wording is still open.
* **Statement preparation:** obtain statement structure, columns/datatypes and
  available plan without executing the statement. Do not substitute execution
  or EXPLAIN ANALYZE that performs work.

DN-22. Backend capability and connected engine/version govern availability.
Unsupported operations must not be emulated or falsely advertised. Missing
backend hooks are recorded implementation gaps. Preserve native errors and
outcomes, and document the hook required by each UI action.

TiB, menus, icons and review status
-----------------------------------

DN-23. Applicable TiB and menu actions must have consistent availability and
semantics and follow surface focus ownership. Inventory existing functionality
before removing or relocating it. Review includes existing column order, sort,
filter, format/profile, staged SQL, fetch/page limits, jump, layout/template,
import/export, parameters, connection, history, query and snippet controls.

DN-24. Select icons for each module action from the application's existing
registry. Any additional approved icon must be included in the project with its
required licence and attribution before it is referenced or used. Transaction
prepare and statement prepare must have distinct icons. Individual icon choices
have not all been approved. The current implementation reuses the registered
information, dependency and column glyphs for the three distinct content views.
Statement preparation uses the preview eye. Transaction preparation uses the
lock glyph. The first and second display-area controls use window glyphs marked
at the top and bottom respectively.

Preserve the current three TiB subtabs and existing action placement initially;
add required controls where they fit and return the completed arrangement for
visual review:

* Data Viewer: Data; Format & Layout; Transfer & SQL.
* SQL Editor: Query; Format & Layout; Export & Files.

Their exact grouping, dropdowns and menu contents still need final agreement.
The rejected generic five/six-tab redesign is not a specification. V2 mockups
must follow the real Data Viewer grid, existing form controls and native tree.
Each TiB submenu and menu requires its own review image. Images of current
components are references; proposal images are not automatic acceptance.

Additional owner decisions, 2026-11-18
--------------------------------------

* A query and its layout/display preferences can be saved together under a name,
  treated like a saved SQL snippet, and made available as a hot button on the
  user's home dashboard. Preserve the query and layout as a single named item.
* The existing automatic switch to a form while editing remains an additional
  preference alongside the four presentation modes.
* A query involving multiple objects is read-only. Do not infer that its rows
  may be edited because a particular column resembles a key.
* Users save their preferences; templates support sharing preferences between
  users. Field-type font and alignment defaults are shared across modules.
* For an identifiable table or view, both surfaces automatically load the same
  saved object layout.
* For a multi-object query, the user can select a referenced object to review
  its metadata. When no object is selected, Information shows the effective
  query, including its filters and sorting.

Open details and required follow-up
-----------------------------------

* Exact TiB control placement, icons and final menu ordering require visual review.
* Exact native conversion invocation and transaction dialog options, prepare
  labels and engine-specific capabilities require implementation review.
* Review the remaining existing actions before changing them.

Implementation ledger and verification
--------------------------------------

Baseline for this ledger: commit ``74a6da838`` (2026-11-17).

Implemented in that commit:

* ``RecordDataView.jsx`` supplies shared grid, mini-form, full-form and hybrid
  rendering to ``DataEditSurface.jsx`` and ``SqlEditorSurface.jsx``.
* ``RecordForm.jsx`` holds the existing adaptive record form, default layout
  and ordering helpers; ``RecordColumnOrderDialog.jsx`` shares the chooser.
* Surface controllers retain their separate session and transaction ownership.
* Data Viewer no longer exposes its Visual SQL action; Open in SQL Editor stays.
* SQL integration handles shared paging action names and read-only metadata;
  draft conversion preserves unset insert values and avoids staging unchanged
  values merely because their converted representation differs.

Recorded verification: 16 targeted JavaScript tests passed across Data Viewer,
SQL Editor and record editing. Tests include adaptive sizing, bookmarks,
keyboard navigation/page movement and focused help. The descriptor gate passed:
159 tests passed and 66 skipped. DDN refresh verified source revision
``a0a26c621cc1d52572701f73854d1c3cb6aeaa82``. Existing lint errors remain; the
recorded changed-file count decreased from 12 to 9 errors (two warnings remain).
This is not a clean full-project lint claim.

The explorer, global colour and language mechanisms were left intact. Earlier
fixture-browser preservation checks exercised existing focused help, dark scheme
and French selection, but did not qualify every palette, locale or translation.
Human presentation acceptance and Windows/macOS qualification are not complete
by virtue of the Linux/JavaScript checks. No new desktop binary was built for
this commit.

**Not established as complete by that commit:** independent arbitrary dual-area
content, the new Metadata/Information contract, type-default persistence and the
full precedence resolver, specialised editors/conversion workflow, custom start
transaction and the two prepare workflows, or final TiB/menu/icon approval.
Existing partial facilities must be audited against this document before being
marked complete. Update this ledger with evidence as each requirement lands.

Working tree changes after the baseline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* DN-07 and DN-09: both surfaces can stack distinct content using the shared
  display-area component. SQL Editor saves pane choices, result filters and
  sorting with a named query. Saved result adjustments apply when the matching
  statement runs again. Both stacked areas can display the same data in
  different presentations. Data Viewer uses the TiB presentation for the
  upper area and offers a lower-area override. SQL Editor offers overrides for
  both areas. The selected result, current row and draft remain surface-owned.
* DN-07: Information exposes reorderable catalog columns and clipboard export.
  SQL Editor can inspect catalog-matched references from a parsed result through
  the existing resource inspection service. Query Information generates a
  SELECT over the selected result with the current grid filters and sorting.
  Saving it keeps the original result's parameter defaults and presentation.
* DN-15 and DN-16: both surfaces use the same user-specific object-layout store
  for identified results and the same user-specific field-type defaults.
  Result identity still depends on the SQL host's supported catalog matching.
* DN-17: record forms offer inline JSON editing with validation at staging and
  a saved per-field multiline Markdown mode.
* DN-19: both surfaces put the bookmark action between Previous Record and Next
  Record in the main navigation group and menu.
* Saved Quick Queries can be pinned to the User Dashboard. Each shortcut opens
  the saved item through its original registered database connection. Query
  text and parameter values stay in the server-side saved query store. Pinning
  is a browser preference for the current user.
* DN-21: SQL Editor exposes native Firebird Start Transaction options and
  Prepare Statement. The prepare operation uses the provider's prepare-only
  path and returns native input/output descriptors and plan text. Both operations
  require explicit provider receipts. The prepare path can start an implicit
  transaction on an idle attachment, as recorded in its native receipt.
* DN-21: Firebird Prepare Transaction invokes the native prepare operation on
  the active retained transaction. Once preparation is confirmed or its outcome
  is uncertain, the provider restricts the attachment to observation and explicit
  resolution. A failed commit, rollback or close keeps the surface open.
* DN-18: Firebird exposes UUID conversion for OCTETS fields. Users explicitly
  opt in per field and can save the choice with the layout. The provider uses
  bound parameters with UUID_TO_CHAR and CHAR_TO_UUID on a separate attachment.
  Conversion failure leaves the row draft and original value intact. Both
  directions passed a native embedded Firebird 3.0 round trip.
* Still open: native preparation and conversion support where additional
  providers expose relevant capabilities, host-only adjustments that have no
  native SQL representation, and six-engine live surface and visual acceptance.

The live surface smoke test exercised Browse Data, filter and layout save,
and read-only SQL result retrieval on SQLite 3.53.0, DuckDB 1.5.2,
MySQL 9.7.0, MariaDB 12.2.2 and Firebird 5.0.4 in network and embedded
modes. Both Firebird modes also passed native transaction start, statement
description, prepare/commit and UUID conversion through the surface APIs.
DuckDB's streamed result pages are retained when the terminal frame
contains no rows. PostgreSQL 18.3 passed a live provider-tree Data Viewer
check with multiple native cursor pages, an intentional buffer cap, filtering
and layout save, and a native SQL Editor query. Its cursor resolves a catalog
relation by OID on the retained session and expires at the transaction boundary,
completion or explicit cancellation. For a PostgreSQL base table with a
primary key, Data Viewer can stage native modifications on the retained
session. Each update or delete checks an opaque, session-owned identity
with the primary key and row version. A stale row aborts the entire batch.
The SQL Editor uses the same native row path for a single schema-qualified
SELECT * on an identified table. It restores the same object layout and
refreshes row identities after a commit. Other queries and relations without
qualifying identities remain read-only. The live PostgreSQL check verified
insert, update, delete, a shared SQL Editor layout and edit, and refusal of a
stale edit after a separate session changed the row. Visual acceptance
remains open.

Functional audit of the desktop test build
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The build snapshot passed 22 targeted UI tests and 401 host and provider tests,
plus 25 subtests. The desktop smoke check confirmed startup and the Data
Explorer. The live checks above exercised selected workflows through the
surface APIs. Individual actions still need end-to-end UI checks.

The audit found these functional gaps before placement review:

* SQL Editor Cancel targets the active workspace execution occurrence. The
  final outcome comes from the provider poll, and a cancellation request
  prevents further script statements from being submitted. PostgreSQL also
  sends native cancellation to an active SQL Editor editable-row read,
  drops the interrupted row identity snapshot and skips ordinary SQL
  fallback. Roll back if PostgreSQL reports a failed manual transaction.
  Firebird network and embedded SQL Editor reads use the native attachment
  interrupt. Cancellation invalidates row identities for the interrupted
  session, without committing or rolling back the transaction.
  SQLite interrupts the retained connection and restores any pre-existing
  progress handler. Its cancelled read discards the row identities and
  preserves pending manual transaction changes.
  DuckDB interrupts the retained connection while it owns the editable-row
  read. The editor discards the interrupted row identities and skips SQL
  fallback. Roll back before continuing if DuckDB reports a failed transaction.
  MySQL and MariaDB cancel an active editable-row read using the connection's
  registered native identity. The cancelled read drops its row identities
  without committing or rolling back the transaction.
* Resolved after the test build: Firebird execution now forwards the selected
  client dialect for every statement. Dialects 1 and 2 use the ordinary native
  query path because the editable row reader has no client dialect option.
* Format SQL uses the retained session's native dialect for PostgreSQL,
  MySQL, MariaDB, SQLite and DuckDB and the Firebird token-preserving formatter
  for Firebird. It replaces the editor text only after native validation
  confirms the formatted source. It preserves Firebird client directives and
  refuses to rewrite whole MySQL or MariaDB scripts with DELIMITER. MariaDB's
  native validation observes the original session and can refresh its diagnostics.
* Information generates a native SELECT for supported result adjustments,
  preserving duplicate output labels by position and retaining the original
  parameter defaults when saved. The database applies its own collation and
  conversions, and evaluates the complete source query. Information flags a
  truncated grid buffer and explains when it cannot translate an adjustment.
  Unsupported cases include non-SELECT results, locking statements, staged
  row edits, some complex types, host numeric ordering of text, and wrapping
  a Firebird query run in dialect 1 or 2.
* MySQL SQL Editor runs accept authored ``:name`` markers and native
  ``%(name)s`` markers. Parameter detection uses the retained session's
  SQL mode and ignores markers inside quoted text, identifiers and ordinary
  comments. Repeated names use the same value. Information keeps the
  authored markers and their defaults when the effective query is saved.
* MySQL SQL Editor scripts consume positional ``?`` and ``%s`` values
  in statement order. The editor checks the total count before submitting
  the first statement. Each result retains the defaults for its own
  statement so its effective query can be replayed independently.
* SQL Editor Start Transaction offers native isolation and access settings
  for PostgreSQL, MySQL and MariaDB, and deferred, immediate and exclusive
  modes for SQLite. It verifies that a new transaction was started on the
  retained connection. Firebird retains its access, isolation and wait
  controls. DuckDB's retained-session driver manages transaction initiation
  and exposes no additional start options.
* PostgreSQL Prepare Statement uses native Parse/Describe. DuckDB uses
  native PREPARE and releases the temporary prepared statement before
  returning. It flags parameter types and result labels the native catalog
  did not supply. Neither operation executes the selected statement.
* Both record surfaces offer opt-in UUID conversion for PostgreSQL BYTEA,
  SQLite and DuckDB BLOB, and declared 16-byte MySQL and MariaDB binary
  columns. Each provider validates that the stored value contains exactly
  16 bytes and uses a separate connection for conversion. Firebird retains
  its existing UUID pair.
* MySQL and MariaDB Prepare Statement use COM_STMT_PREPARE on the retained
  session, including its temporary tables and SQL mode. The patched C
  connectors expose result column names, type codes, flags, character set,
  lengths and decimal counts. They report native parameter slots, while
  the dialog marks parameter types unavailable because both C libraries
  omit them. MySQL's pure connector continues to expose the parameter
  metadata it receives from the server. Older unpatched C connectors use
  their existing incomplete receipts. Explicit MariaDB preparation
  refreshes session diagnostics. Both providers release the native
  statement without executing it.
* SQLite Prepare Statement uses the native configuration bridge on the
  retained connection. It reports result names, types declared by SQLite,
  and parameter slots, then finalizes without stepping the statement.
  SQLite supplies no declared type for parameters or computed result columns.
  The connection's authorizer stays in force and prepare-time PRAGMA effects
  are suppressed. Without the native bridge, the EXPLAIN compilation path
  can verify unparameterized SQL and reports metadata as incomplete.
* PostgreSQL Prepare Transaction requires an active transaction and checks
  the instance's ``max_prepared_transactions`` setting before preparing.
  SQL Editor applies Auto-Commit to its retained PostgreSQL connection.
  Turning it off lets ordinary statements open a native transaction.
  Start Transaction can set its isolation and access before a statement
  starts one. Changing Auto-Commit requires an idle connection and no
  staged edits. With Auto-Commit on, PostgreSQL handles statement
  boundaries, including explicit transaction blocks. The status line
  shows the generated transaction ID after preparation. Commit
  and Rollback resolve that ID with native prepared-transaction commands.
  A lost outcome keeps the ID visible and blocks retry from that session.
  After a connection loss or application restart, use Recover Prepared
  Transaction in the Query menu. It lists up to 200 ScratchRobin prepared
  transactions visible to the current role in the selected database.
  The selected ID is verified again on a dedicated connection before
  native Commit or Rollback.
* MySQL and MariaDB Start Transaction offer Start XA Transaction as a separate choice.
  Start XA before issuing SQL against a transactional table. Prepare
  Transaction ends and prepares the branch. Commit and Rollback resolve
  that branch. Commit before Prepare uses native one-phase resolution.
  Managed XA uses editor SQL for writes. Grid row staging is unavailable
  during the branch. The status line displays the generated XA identifier.
  Detached prepared branches use the existing server-level XA inspection
  and resolution workflows.
* The Data Viewer and SQL Editor refresh their TiB, menus and visible surface
  labels when the interface language changes. The bundled catalogs cover the
  principal surface controls, shared TiB action hints, segmented-control
  tooltips, and the SQL Editor transaction, parameter-binding, Save and
  Quick Queries, fetch limits and connection details dialogs in all supported
  locales. Some secondary controls still fall back to English.
* Shareable layout templates are managed in Data Viewer and can be applied in
  SQL Editor through Format & Layout or the View menu. Applying a template
  changes the current result presentation. Use the existing save commands to
  keep the applied layout for an object or named query.

Resume and acceptance checklist
-------------------------------

See :doc:`data_navigator_outstanding_work` for the current handoff checklist.

On resuming work, read this document, inspect the current source and ledger, and
continue outstanding requirements without treating the mockups as implemented.
Preserve uncommitted files. Refresh DDN before build/commit-validation tests as
required by ``AGENTS.md``. Keep disposable files in the designated work area.

Live acceptance for these two surfaces covers PostgreSQL, MySQL, MariaDB,
Firebird (network and embedded), SQLite and DuckDB. Verify shared workflows
on all six engines. Verify each native operation on the engines and versions
that expose it, and verify its control is unavailable on the others.

For each completed requirement, record its DN identifier, shared component and
backend hooks, capability/read-only behaviour, focused regression evidence and
remaining human/platform acceptance. Exercise both surfaces and all applicable
presentations, including narrow/wide work areas, draft guards, focus help,
colour/typography and language preservation. A menu entry or fixture screenshot
alone does not prove a native operation works.

Project-contained review assets
-------------------------------

The historical fixture review gallery and all images it uses are included in
``design_assets/data_navigator/`` alongside these documentation sources. Open
`the review gallery <design_assets/data_navigator/index.html>`_ or read
`its asset notes <design_assets/data_navigator/README.md>`_. The local
``assets.json`` records project-relative filenames and SHA-256 hashes.

Captures describe the pre-implementation source revision stated in the asset
notes. Current/proposed captions refer to that historical snapshot; proposals
are not blanket approval. This specification and its implementation ledger take
precedence over historical review findings. No external planning files, image
galleries or icon maps are dependencies. Future required assets must also be
included in the project and referenced by project-relative paths.
