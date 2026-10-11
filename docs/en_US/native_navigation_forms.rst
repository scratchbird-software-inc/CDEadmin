Native navigation and form references
====================================

The provider Resource Explorer includes the checked-in native design from
``visual_admin/navigation_design.json``. Each endpoint renders its own engine
branch. Template nodes are presentation identities, never fabricated provider
resource IDs. Actual resources bind by kind and observed parent identity or
provider display path. Conditional branches require observed objects; this
conservative rule may hide supported branches until discovery supplies evidence.
Refresh/load-more retains the existing provider discovery boundary.

Selecting a bound object opens its object inspector. Definition children can
open the owner's specific tab. Unimplemented destinations open a numbered,
non-executing placeholder with engine, endpoint, owner and template context.
Context menus expose provider-declared object operations and scoped creation or
metadata placeholders; a placeholder never grants a capability.

``static/js/cdeadmin_ui/navigation/formReferences.json`` is the append-only form
reference registry. References identify reusable forms, not object instances.
Never renumber, recycle or derive IDs from render order. Existing common forms
(workspace, inspector, query editor, scripts, server/database setup and native
operation forms) display their shared reference. Missing native forms retain
their designated reference when the UX team implements them. Scoped creation and
metadata extraction each have their own reusable placeholder reference.

The native tree supplements the existing live browser/discovery tree. Its
unbound branches describe the design; they do not claim those objects exist on
the connected server. Discovery completeness and live engine/version capability
qualification remain provider-owned.

Firebird virtual layout
-----------------------

Firebird database roots group catalog objects under system, monitoring,
programming and security. Virtual branches appear first, sorted alphabetically;
actual objects follow in alphabetical order. Definition sections are virtual
items and participate in the same case-insensitive alphabetical ordering. User tables and views are direct root
children. System contains configuration, replication, database-triggers,
service, shadows, storage, character sets, collations and RDB$ relations.
Monitoring contains MON$ objects; security contains users, roles, grants,
authentication mappings and SEC$ objects. Programming contains procedures,
domains, filters, exceptions, external functions, functions, packages and
sequences. Additional native database-level kinds remain under system. There is no
redundant database folder or database-name child; storage retains the file entry.

Tables and views expose columns, indexes, triggers, constraints, dependencies,
comments and grants. Columns expose constraints, calculations, comments and
grants. Definition-only entries reference the real owner's inspector section;
they are not new database resources and have no independent mutation actions.
Unavailable metadata sections retain an explicit placeholder. Virtual folders
never alter native resource IDs, authority paths, parent ownership or grants.

Firebird database menus expose native logical/physical Backup forms and a
dedicated Export destination (SR-F-001348). Export now captures database or
native-object-branch metadata as a DDN catalog document (or bounded multi-file
workspace for large captures), with paged preview,
explicit refresh and exact-source download. The same form reads a local catalog
DDN file or workspace JSON and compares its exact native records with the authorized database
generation. Differences are paged, with changed field names and explicit
document-only/current-only states; no SQL execution or deletion is implied.
Within the same form, a loaded catalog serves as a baseline for a second,
edited desired DDN file. Native change preview refreshes the current catalog,
reports three-way conflicts, and downloads a review plan or unblocked SQL.
Structured planning covers canonical scalar and array domain creation, existing domain
defaults/nullability/checks/comments,
BLOB filter declarations/comments,
standalone role definitions/system privileges/comments,
sequence definitions, exception
messages/comments, ordered-column/computed/partial index creation and standalone
index state/comment changes on Firebird 5 dialect 3. Constraint indexes and
definition rebuilds are blocked. Native expression boundaries are checked before
creating the review artifact; native grammar and execution checks remain required.
Prepare application rechecks the preview and records an owner/target-bound
review. Explicitly confirmed Apply uses a dedicated native transaction, fresh
preflight and retained outcome receipt; the same review cannot dispatch twice.
The receipt reports native commit/rollback, unknown outcomes and rediscovery
separately. Complete native SQL and row-data export remain assigned to the export
workflow follow-up.
Redundant database-object and table-data browser shortcuts are omitted.
Logical and physical Restore belong to the server menu. Their service-manager
forms require an explicit destination filename, not an existing database target
or a database attachment. Existing native validation and confirmation remain.
The main explorer sorts Firebird virtual branches first, then alphabetically
within each group, including object sections.

Firebird functional completion and DDN ownership
================================================

The owning workflow requirements are in ``firebird_functional_completion.rst``.
ERD and dashboard display/editing use the Diagram-Design-Notation sister project.
Refresh its consumed snapshot before each build and commit-validation run as
required by the repository ``AGENTS.md``; the old bundled Designer/runtime pair
has been replaced with the sister project's current public integration boundary.

Native network Firebird server/database menus expose a read-only DDN dashboard
(``SR-F-001351``) and a distinct collection-policy form (``SR-F-001352``).
The latter starts/stops dedicated monitoring and optionally enables MGA-refresh
heartbeats. It is not a dashboard layout editor. The former performs only scoped
reads and cannot configure collection or modify definitions. See
``firebird_dashboards.rst`` for host admission, delegated credentials and the
remaining dashboard editor/fleet/history requirements.

The Firebird engine-root context menu also opens ``SR-F-001351`` at engine scope,
without requiring a selected server or connecting unmonitored endpoints. Its
DDN panels distinguish registrations, collector coverage, service-visible files,
and stale/failed/unknown/permission-limited observations. This scope shares the
read-only form; collection policy remains per server or registered database.

Firebird engine/server/database menus expose **Edit dashboard draft...** in the
separate ``SR-F-001353`` form, hosting DDN's unified editor ``SR-F-001350``.
It reads/saves scoped versioned layout drafts with no live collector feed and
prompts before discarding unsaved source. Drafts are not automatically published.

The dashboard editor now has an explicit **Publish saved revision** action.
Save continues to create drafts. Publishing validates the immutable source and
scope bindings on the host and creates a separate published revision. The viewer
loads that revision on refresh, shows its version, and binds current authorized
metrics without mounting editor controls. Native collection policy is unchanged.

Retained monitoring observations
--------------------------------

The passive dashboard links registered engine/server/database targets using
current owner authorization. Navigation does not admit a collector or change its
policy. ``SR-F-001354`` displays the selected metric over a bounded volatile
sample window through DDN, with separate exact-value and gap details. Its point
chart never interpolates across collection gaps; source epochs and monotonic
elapsed time identify reconnect boundaries. Collection and editing stay in their
separate forms.

Monitoring account and activity forms
-------------------------------------

``SR-F-001352`` now configures registration authentication or a dedicated native
monitoring username/password/role. It displays the active account, clears the
submitted password, and requires Stop before changing an admitted account.
``SR-F-001355`` provides read-only attachment, transaction and statement detail
tables from the latest retained collector snapshot. The database dashboard links
to it without admitting another source or running a query on viewer navigation.
Coverage, truncation, freshness and collector exclusion remain visible.

Firebird table ordering
======================

The table context Reorder columns operation opens SR-F-001356. The fixed native
column list provides move-up/down controls and the existing administration
preview, confirmation and refresh flow. Backend permutation validation and a
native relation/order recheck precede POSITION statements. Other engines do not
receive this Firebird operation.

Firebird query diagnostics and history
======================================

The native query workspace links SQL history (SR-F-001357), with owner/database/
dialect policy, search, previous/next source loading and explicit clear. Loading
source never executes it. Its credentials-sensitive omission control applies to
the next normal execution or retained script preparation.

An explicitly confirmed profiled run displays native PSQL and record-source
measurements in SR-F-001358. It uses the existing attachment and exposes native
profile storage and replacement semantics before dispatch. Optional fresh
attachment query counters appear in SR-F-001359 with before/after values, deltas,
observation failures and host elapsed time. Neither form controls user commit or
rollback. Each diagnostic result remains separate from the SQL outcome.

Firebird workspace utility destinations
--------------------------------------

Native row fields link to SR-F-001360 (BLOB viewer/editor). Edit Data links to
SR-F-001362 (selected-row SQL previews). Firebird workspaces link to SR-F-001361
(metadata search across selected registered databases) and, when scoped to a
registered database, SR-F-001363 (native events). Search-result links open the
corresponding server/database/resource object workspace; they do not change the
SQL attachment's database. All references are appended to the shared registry.

Firebird external ISQL
---------------------

``SR-F-001366`` is the Firebird database-context external ISQL form. It displays
an owner-scoped TCP description without exporting stored credentials. Linux
Electron selects local executables and launches the independent native tool;
browser-only clients display the desktop requirement. Process launch does not
assert attachment success or transaction finality. See FB-COMP-14.

Firebird test-data generation
----------------------------

Database context action ``database.firebird.test_data`` opens SR-F-001367,
with exact database target and Firebird language binding. Its separate retained
session stages validated inserts and exposes explicit transaction controls.
Recipe/preview imports do not execute. See FB-COMP-07 for source, dependency,
bounds, cancellation and outcome contracts.

Firebird Docker provisioning
---------------------------

Connector-root action ``connector.firebird.docker`` opens SR-F-001368 on the
Linux desktop. Browser clients see the execution-host requirement and cannot
start server-side Docker processes. Confirmed provisioning hands host, native
database filename, port and SYSDBA username to the existing Firebird registration
form; it does not submit registration or reuse bootstrap credentials implicitly.

Firebird registration clone and move
-----------------------------------

Database registration actions ``database.firebird.registration_clone`` and
``database.firebird.registration_move`` open SR-F-001369 without requiring a
native connection. They select an exact same-owner destination registration,
a distinct display name and an explicit credential policy. The resulting target
is inactive; native verification remains separate. Database filenames are not
registration identities. Configuration guards reject mutation while sessions
need either endpoint. The form never repeats a mutation after a lost response.
Same-host registrations of the same interface show their distinct ports in the
tree. Repeated registrations at the same port additionally show registration IDs;
interface names alone cannot distinguish two Firebird servers on different ports.

The Firebird export workspace (SR-F-001348) includes a native object/branch
selector, DDN capture, exact native metadata SQL and data-only/metadata-plus-data
archives. SQL preview lists blockers, external dependencies and creating-user
requirements. Data capture releases its independent read-only snapshot before
publishing a download. SR-F-001370, within that workspace, reviews a versioned
data archive against the destination and stages rows in its own write session.
Its commit/rollback controls never finalize the user's SQL editor transaction.
Identity preservation and required allocation reconciliation are explicit.

The Firebird native schema preview within SR-F-001348 also lists package header
and final body statements separately. Its downloaded script uses ISQL SET TERM
for PSQL; direct application retains complete native statements and one owned
transaction. Column ADD and final-position statements are shown in these same
phases, including their stable parent and column identities.

SR-F-001371 identifies the native DDN schema review/application panel embedded
in Firebird export (SR-F-001348). Supported-change detail is collapsed by default
for compact presentation. The panel shows complete primary and final statements,
source locations, scope, blockers and owned application receipts; it now includes
standalone procedure/function signatures and bodies as well as packages and
columns. The static reference remains visible when reused within the export form.

SR-F-001372 is the read-only statement SQL/plan inspection within the database
monitoring activity form's Statements category. It uses the dedicated collector,
revalidates the selected sampled identity and displays bounded native text through
DDN. It offers no statement execution or session mutation controls.
