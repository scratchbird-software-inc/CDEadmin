Compact forms and data navigation
=================================

All engine forms use compact, content-sized actions and responsive field groups.
Native fields, version gates, confirmations and stable form reference numbers
remain authoritative. Single choices use selects or short radio groups; multiple
choices use checkboxes or multi-selects. Repeated navigation choices use selects,
not walls of action buttons. Editors and grids may occupy the available width;
action buttons do not stretch with their containers. Labels and errors wrap,
keyboard focus remains visible, and enlarged text must not be clipped. The main
menu wraps within the viewport and its measured height sizes the remaining
workbench, preserving access to menus at enlarged text sizes.

Repeated grid actions use named, tooltip-equipped icon buttons. Read-only grids
must not imply write or transaction capabilities. Editable provider row grids
start in view mode; edit mode exposes admitted native row editors. Saving a row
stages it in the owning provider session. An Autocommit checkbox defaults off.
When checked, each successfully saved mutation requests a native session commit
before reloading; Commit and Rollback buttons are disabled. The checkbox cannot
change with unsubmitted drafts or staged work. A failed automatic commit turns
autocommit off, retains the unresolved transaction, and never retries the mutation.
Commit and rollback are native session operations, never navigation side effects. Unsubmitted drafts block
navigation, mode changes and reload until saved or explicitly discarded.

Row navigation provides first, previous page, next page and last controls.
Forward-only provider cursors retain fetched pages for backward navigation; last
is disabled until the end or retrieval cap is known. No total count or random
access is invented. Maximum retrieved rows bounds the retained browsing result;
page size controls each native request and respects provider page limits. A
continuation keeps its original native batch size. Providers may prefetch a full
final batch: excess rows are discarded from the browsing result and the cursor
is closed at the cap without deciding its transaction. The UI reports retained
rows separately from final-batch excess; the setting does not limit rows scanned
or server-side work. A reload, mutation
or transaction outcome invalidates cached pages and row identity tokens.

Finite in-memory result grids may paginate their existing result independently
of native fetch controls. Pagination must preserve row identity and selection
and must never pretend to bound the original database execution. Streaming BLOB
and array interfaces preserve their bounded native stream and lifetime contracts.
Horizontal and vertical scrollbars appear when the grid content exceeds its
viewport; navigation remains outside the scrolling cell region.

Acceptance covers generated native-operation forms, connection and registration
forms, properties, SQL/script/result tools, Firebird administration and service
forms, monitoring policy and display-only dashboards, DDN host forms, preferences,
and shared dialogs. Each renderer family is reviewed in the private form audit;
engine-specific fields are inherited from their unchanged provider contracts.

Firebird row-grid session admission
----------------------------------

The grid opens a dedicated ``firebird-row-grid`` session purpose. It uses native
SNAPSHOT/WRITE with auto-commit disabled, normal undo and limbo handling and a
bounded lock wait. This overrides only that session's registration defaults;
ordinary SQL sessions keep their registered policy. Native permissions and
read-only database restrictions still apply. Row saves execute within the
session's native savepoint. With UI autocommit selected, the grid requests commit
after successful mutation/savepoint completion, rather than enabling native
statement autocommit that can invalidate the savepoint. Otherwise the user
explicitly commits or rolls back.
A transport error remains an unknown outcome; UI state is never finality proof.

SQL editor connection and result buffers
----------------------------------------

The SQL workspace keeps a visible connection banner above its scrolling editor:
registered endpoint name and ID, selected database name and target ID, verified
engine/profile, selected language and Firebird statement dialect, plus native
session state. Changing language or target follows the existing session boundary;
source text never selects an engine. Plans, diagnostics and transaction actions
come from the selected provider/language capabilities. Passwords are never shown.

Maximum rows per fetch is an editable integer from 1 through 500, bounded further
by the admitted result renderer. Result descriptors advertise their admitted
maximum page size so subsequent fetches observe that limit too. It controls each server-to-browser result page,
including the first page. It is distinct from Firebird's total native fetch limit
and from driver/server prefetch. Buffered query polls return result rows only via
the bounded rendered page; duplicate raw native row arrays are omitted after the
original native result has been admitted to server-side result storage. Native
diagnostic and transaction observations remain available.

Navigation retains server result/cursor references, not additional row copies.
First/previous revisit admitted pages without re-executing SQL or advancing the
native cursor. Next consumes local server-result pages before asking for a native
continuation. Last is enabled only after the end is observed. Expired server
results produce an error, never an automatic query replay. Native BLOB/ARRAY
streams retain their separate reference-lifetime contract.

Firebird streaming receives the same per-fetch limit on open (1–500 rows); it
retains its additional one-MiB page budget and native BLOB/ARRAY reference expiry.
The limit is fixed while that stream owns the session. Existing streaming callers
that omit the limit retain the 100-row default.

Unified SQL workspace
---------------------

Owner direction, 2026-10-11: the native PostgreSQL Query Tool is the presentation
baseline for the general and Firebird SQL forms. Shared frame, compact icon
toolbar and execution/transaction controls use the same components. Native
adapters supply actions, enablement and engine-specific options; presentation
controls never synthesize transaction outcomes or issue PostgreSQL commands
against another engine. Connection/dialect selection stays visible. Query source
and results occupy separate panes; result, plan, message and engine-option tabs
retain mounted content when switching so cursors and drafts remain owned.
The global SQL tab also shows the query-tool toolbar, source pane, result tabs
and metrics when disconnected; it must not fall back to a bare editor. Execution
and transaction actions remain disabled until a connection is selected.
Unsupported actions remain absent. PostgreSQL's existing native docking, file,
history and debugging facilities must be preserved during the migration.

All provider SQL actions activate the global SQL tab. Its active-connection
selector prefixes every connection label with its engine type, including
connections registered before an editor is opened. It retains a separate
editor/session for each admitted endpoint/database;
switching connections never commits, rolls back, or replays a statement. The
same syntax-editor surface is used for every language, with native capabilities
selecting preparation, plans and diagnostics. Advanced execution options are
collapsed by default. The source pane can be resized vertically; results scroll
independently so navigating them does not hide the source. Results show buffered row counts and native timing/plan
observations when available; unavailable measurements are explicitly labelled,
never represented as zero or inferred from network elapsed time.

Monitoring configuration can delegate the selected connection's credentials to
its independent collector. It never borrows the interactive transaction. Missing
credentials require the normal connection authentication flow; passwords are not
returned to the browser or written into dashboard definitions.

Explorer connection lifecycle
-----------------------------

Saved credentials and persisted verification are not a current connection.
Expanding a provider database first authenticates the endpoint in the current
browser session. An authenticated database is registered in the global SQL
connection selector without opening or focusing an editor; its editor is created
on first selection. Server and database context menus expose Connect and, for
Firebird, Disconnect server (all databases). Disconnect uses the existing native
release guard: active work must be explicitly completed and closed first. Only
a successful disconnect removes SQL entries and unloads database internals.
Registered database names remain browsable while disconnected.


Administration refresh stability
--------------------------------

The context's initial object type and operation initialize an administration
workspace; catalog/resource refreshes must not reapply them over later user
choices. A newly requested context may initialize a new selection. If the active
kind or operation actually disappears from the current permitted descriptor,
choose an available value and invalidate the old plan. Inspection of a transform
must retain the transform form, target and matching form reference.
