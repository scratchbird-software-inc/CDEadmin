# ScratchRobin project instructions

## Shared development branch

Owner direction, 2026-10-15: `master` is the shared development branch. Review
and integrate published development branches, preserving their commits and the
current UX and backend functionality. Temporary integration branches/worktrees
may be used for conflict resolution and verification; synchronize completed work
back to `master` and advance the development branches to the same commit. Keep
deployment output such as `gh-pages` separate from application source.

Preserve uncommitted files and staged changes in existing checkouts. Refresh DDN
and run affected regression checks before publishing integrations. Report native
qualification that is still running separately from completed verification.

## Disposable build and verification artifacts

Owner direction, 2026-10-21: remove superseded builds, detached verification
snapshots, temporary database fixtures, browser profiles and test output when
they are no longer needed. Git retains source history; do not accumulate a
parallel history of build directories or artifacts. Keep only the current build,
required runtime dependencies, active verification inputs and concise current
verification evidence. Bound the number of snapshots used during verification
and remove superseded copies after publication. Preserve other teams' working
files, occupied branch checkouts and database data that is not a disposable
fixture owned by this task.

## Firebird feature completion

Owner direction, 2026-10-10: all functionality identified in the FlameRobin
comparison is required. The owning requirements and acceptance checklist are
`docs/en_US/firebird_functional_completion.rst`. Preserve current edits and
implement engine-specific behavior; generic forms or placeholders do not prove
native support, and (owner direction 2026-10-25) a native backend operation
without a `ui_descriptors` entry does not count as surfaced. Do not introduce unsupported features on an engine/version.

## Diagram-Design-Notation integration and freshness

Owner-designated sister project:
`/home/dcalford/Sandbox/ScratchWeaver/project/ddn/`.
Superseded by owner direction 2026-11-03 (below): the sister project is now the
public `/home/dcalford/Sandbox/Diagram-Design-Notation/` repository.
Use its tools for ERD and dashboard display and editing. ScratchRobin owns
provider metadata/data adapters, authorization, persistence and native-operation
execution; DDN owns diagram/dashboard rendering and visual editing. Do not build
another ERD or dashboard editor in ScratchRobin.

Owner direction, 2026-11-07: the DDN software is a proof of concept. ScratchRobin
is the concern; what it needs from DDN is either a rewrite or an expansion of its
own DDN capture, with nothing pushed back to the DDN repository. The projects that
use DDN are open source, so the changes remain source-available there. Make such
changes as reviewed consumer patches in `tools/dependency_patches/`, applied by the
intake to the isolated capture and recorded in the vendored manifest. The refresh
and provenance rules below still apply.

Before EVERY build, and before every test run intended to validate a commit:
1. Read the current sister-project revision, working-tree status, public API and
   distribution/build instructions. Preserve the other team's working files.
2. Refresh ScratchRobin's consumed DDN copy from that current project. Refresh
   runtime and editor/tool together, with declarations, required assets, license
   and notices. Do not silently reuse an older copy when refresh fails.
3. Record the exact revision and hashes of consumed artifacts and any uncommitted
   source state in the vendored provenance manifest. Confirm distributions match
   source; if rebuilding is required, use an isolated snapshot in the designated
   temporary work area, not the other team's active checkout.
4. Reconcile public API changes and run affected adapter/consumer checks. A file
   copy is not compatibility proof. Do not relabel old libraries as current.
5. Build/test one immutable refreshed snapshot. If the sister project changes
   during capture, retry capture; later changes are consumed on the next run.
   Review and retain the refreshed dependency and manifest with the commit.

This gate is automated on both development paths. On Linux,
`bash tools/development/dev.sh ddn` runs `tools/refresh_ddn.py`, and the
`frontend` stage runs the refresh before building. On native Windows/macOS,
`native.py` runs the same refresh before its build and test stages. Direct
webpack, pytest or Jest invocations bypass those entry points: run
`bash tools/development/dev.sh ddn` (or `tools/refresh_ddn.py`) explicitly
first and record it.

Owner direction, 2026-10-28: migrate generation, dashboard generation and
DDN-to-native-metadata exchange to ScratchWeaver's standalone open DDN
`ddn-next-1` utility API 1.0. The old dialect is incompatible. Consume only
`project/ddn` and its public build dependencies; never consume commercial Weaver.
Publication of this standalone DDN integration is authorized by the owner
(2026-10-28); commercial Weaver remains excluded. Source
workspaces use `ddn-source-workspace@1`; native DDN ModelSnapshot is a different
contract. Legacy saved designs require an explicit, loss-reported conversion,
never a format relabel. Refresh with `tools/refresh_ddn.py`; review the exact
source revision and artifact hashes in the provenance manifest.

Owner direction, 2026-11-03: Weaver is starting its intended divergence from
the public DDN sources. Consume DDN only from the public Diagram-Design-Notation
repository (`/home/dcalford/Sandbox/Diagram-Design-Notation`, subtree
`project/ddn`); Weaver maintains its own copy and is no longer a source.
`tools/refresh_ddn.py` and `native.py` default to that checkout, and CI clones
the public repository. The 2026-10-28 direction above is otherwise unchanged.

## Bidirectional native metadata and DDN

Owner direction, 2026-10-10: DDN is also the database-design exchange format.
Follow `docs/en_US/ddn_database_roundtrip.rst`: discover object/database/server
metadata and selected data into one or more DDN views; read DDN to generate
engine-native metadata; compare desired/live/baseline metadata to produce native
migration statements. Preserve exact types, identities, names and dependencies.
A view filter is never deletion intent. Current DDN illustrative SQL export and
visual diff views do not constitute deployable native schema generation/diff.

## Shared DDN designer and viewer libraries (owner direction, 2026-11-09)

Unlike the standard DDN tools, ScratchRobin's DDN work is done mostly on the
server: server-side code, not client-side JavaScript, performs the
calculations, tiles larger diagrams and does the designer work. There is one
shared set of libraries, a server-side set and a client-side set, for the
designer and the viewer. Each task-specific tool (the cube designer, the ERD
and data modelling designer, the BI designer, the screen mesh designer) uses
those libraries differently: their appearance, interaction and behaviour
differ, but all of them produce DDN and all display it through the same
underlying viewer. Build task behaviour on the common libraries; do not give
a tool its own rendering or its own DDN handling.

Owner decisions, 2026-11-09:
- The planning for the cube, ERD, BI and screen mesh designers found areas
  where the DDN dialect cannot hold all the data those tasks need. Expand
  the dialect to hold it, as part of ScratchRobin's own DDN capture (the
  consumer-patch rule above), rather than keeping task data outside DDN.
  Known gaps so far: wireframe controls beyond the seven-control stencil
  (grid, dropdown, radio, tabs), control-to-data bindings, regions on an
  image, screen-to-screen navigation, dimensional (cube) elements, and
  BI question and dashboard content.
- For the initial uses, the local server-side store is SQLite, not JSON
  documents, with DDN import and export. The planned move to SBsql comes
  later.

## Cube design through DDN (owner direction, 2026-11-08)

Planning only: implementation waits until the PostgreSQL provider-tree
migration is further along. Cube (semantic model) design uses a specialised
DDN designer, as ERD design does and BI dashboard design will; do not build
a separate cube canvas in ScratchRobin.
- DDN is the design and transfer layer: the cube's metadata and SQL editor.
  The ScratchRobin semantic-model store holds the data structures that
  implement the cube, so the data is ready when people use it.
- A store-to-DDN process connects them. The designer reads the store into
  DDN to edit an existing cube, or starts a new one, and saves design
  changes back. The round trip must not lose design content.
- Like stored procedure source, a cube's DDN, with its comments and other
  elements, can be kept in the ScratchRobin store. Git keeps the DDN, not
  the values in the store. Operations include new cube, save a draft
  locally (in the ScratchRobin store), save to Git, load from local and
  load from Git.
- A cube's DDN is versioned with directed save points, using DDN's user-set
  statuses (Draft, In-progress, In-review, Accepted). Accepted means
  applied: accepting a version makes it the active cube in the store;
  earlier save points change nothing in use.
- Who may accept follows the security setup and is flexible: the user
  specifies who or what authenticates and authorizes an approval.
- Database changes (for example materialized aggregates) are highlighted as
  changes in the DDN generated from, and compared with, the store. They are
  executed only through ScratchRobin's native-operation review.
- Leaving an accepted version is the user's decision: roll back to an
  earlier accepted version, or force a new draft version with a minor
  version bump.
- ScratchRobin assumes no changes by others while a draft is edited.
  Changes someone else accepted are detected when saving or accepting, and
  the draft takes them in through a DDN diff (its base version against the
  active version) before it can be accepted. ScratchRobin does not provide
  concurrent editing.

## ERD and data modelling design (owner direction, 2026-11-08)

The ERD designer is a data modelling design tool, not only a diagram tool,
and it goes beyond what most ERD tools support. As with cube design, the
design is kept separate from the database and its current implementation:
nothing applies to a database immediately. The tool combines four roles:
- Whiteboard: free-form drafting before all information is known, with
  name-only entities and relationships; nothing touches a database.
- Conversion: a sketch becomes a typed design for a chosen engine; a design
  converts from one engine to another through data type conversion maps
  the user can edit; designs come in from a live catalog, a DDL script or
  an exchange format.
- Design: the full modelling surface, with versions saved as checkpoints.
- Modification: an existing database is loaded into a design and changed;
  versions, the live database or a script are compared, the user chooses
  which differences to carry, and the result is a generated change plan
  that reaches a database only through ScratchRobin's native-operation
  review.
TMS Data Modeler is a feature specification and interface reference only.
It is a Delphi/Pascal code base, incompatible with ScratchRobin, and
source-available rather than open source: never copy its code.
Planning only until the PostgreSQL provider-tree migration is further
along.

Owner decisions, 2026-11-08:
- A design's DDN is a text document holding the current state. It is kept
  in the ScratchRobin store and in Git; earlier versions and history live
  in the store and Git history, not in the DDN. Because renames are read
  from that history, every element keeps a stable stored identity.
- A model has four levels: conceptual (the whiteboard), logical, physical
  and deployment. All levels are in the DDN document, linked by DDN's own
  relations, and each can be viewed or edited as elements of the model at
  a given state. A design may cross database engines, platforms, databases
  and schemas, and may describe machines, racks, cloud locations and
  instance types, and reporting.
- Deployment details may be entered by hand (the usual case), taken from
  ScratchRobin's registered servers, or imported from outside sources;
  which outside sources to support is researched during implementation.
- An accepted design produces alter scripts. A change to metadata may lose
  data, so ScratchRobin warns that it may be destructive and not
  reversible: the metadata can be recreated, but the data it referred to
  cannot, unless the database keeps versions (for example ScratchBird).
- ScratchRobin assumes no changes by others while a design is edited.
  Changes are tested when the design is saved: possible conflicts are
  shown and can be recorded in the DDN's notes, or the change can be
  reversed or cancelled. ScratchRobin does not provide concurrent editing.
- An ERD exists in one of three places: the physical database (the
  metadata of what exists), the ScratchRobin store (tables holding the
  design), or Git (a DDN text file under version control).
- System diagrams are limited by the hooks each environment offers. For
  example, monitoring clients such as Nagios can supply information from
  the network; such tools differ widely in what they support, and some
  environments allow automated updates. What is possible is investigated
  at implementation.
- Task-specific viewers and designers are used rather than the
  proof-of-concept DDN viewer and designer, which stay off the menus for
  now.

## BI questions and dashboards (owner direction, 2026-11-08)

BI design (questions, dashboards and their alerts) follows the same process
as cube and ERD design: it is a specialised DDN task, and the patterns in
those two sections apply. The DDN holds the current state and is kept in
the ScratchRobin store and in Git; the store holds the implementation;
versions use directed save points; approval follows the user's security
setup; changes are tested at save. BI tools may use, and be called from,
other ScratchRobin tools such as the visual SQL builder. The existing BI
module was a first pass built without firm design specifications; it is
early work, reused where it fits as the planned elements are implemented.
Mock-ups and a full specification come first; they are a to-do item.

Owner decisions, 2026-11-08 (BI):
- Plan a single query model shared by BI questions and the visual SQL
  builder, possibly expressed in SBsql and translated to each target
  engine, with workarounds for that engine's limits.
- BI designs are DDN, so their text form is kept in Git.
- ScratchRobin's local store is planned to use SBsql (ScratchBird); it
  tracks version details and freshness. The open-source ScratchBird
  edition has fewer features but supports this to a point.
- Metabase and Apache Superset are references only. Rewrite rather than
  bring in code built on different assumptions or with licence questions;
  ScratchRobin is under the PostgreSQL Licence.
- Importing Metabase and Superset content and converting it to DDN is a
  key feature. DDN can define dashboards, graphs, diagrams and dynamic
  data sources.
- ScratchRobin includes a dashboard server for displaying dashboards on
  remote devices, and can also display dashboards itself.
- ScratchRobin has the option of using AI.

## Screen and form design (owner direction, 2026-11-08)

Screen mock-ups and forms are designed with a specialised DDN designer:
forms are designed, linked to the underlying data, and shared across
applications. The process is the same as for cube, ERD and BI design. This
is the last planning element of the current design stage; its research,
specification and mock-ups are to-do items.

Owner clarification, 2026-11-08 (later): ScratchRobin's part is limited to
the screen mesh (a wireframe of a form) or a screenshot, linked into the
rest of the diagrams, for example to the data a form shows. A full form
designer that builds working forms is outside ScratchRobin's scope.

## Dashboard viewer, collector and history separation

Owner correction, 2026-10-10: engine/server/database dashboards are display-only.
Use dedicated collector connections independent of user sessions; policy-enabled
collection continues without an open viewer. ScratchBird is the intended history
store. Layout/binding edits belong only in the separate DDN dashboard editor,
opened via an authorized context-menu item. Follow
`docs/en_US/firebird_dashboards.rst`; do not introduce editing or administration
controls into the viewer or equate collector access with viewer authorization.

## Current completion scope (owner correction, 2026-10-14)

The owner now requires PostgreSQL, Firebird network and embedded, MySQL,
MariaDB, DuckDB and SQLite to reach the same level of backend completion.
Persistent monitoring history and the ScratchBird connection are included in
that work. Form presentation acceptance belongs to the human team; form
structure is generated from `web/pgadmin/cdeadmin/ui_descriptors/` and gated by
the build (owner direction 2026-10-25, below). Windows/macOS work and
qualification remain with the platform teams, and their evidence is required
before a cross-platform completion claim. All recorded Firebird/DDN/dashboard
requirements remain in scope, including published live dashboard bindings,
native DDN roundtrip/diff/apply and remaining FlameRobin parity. Persistent
SQL history, dashboard definitions and recipes remain in scope. Follow the
acceptance rules in `docs/en_US/firebird_functional_completion.rst`.

## Full native product coverage (owner direction, 2026-10-16)

MySQL, MariaDB, PostgreSQL, DuckDB, SQLite and Firebird network/embedded must be
catalog complete, feature complete, provide predictive SQL completion and syntax
checking, and expose complete native management/maintenance workflows inside
ScratchRobin. Follow `docs/en_US/six_engine_completion.rst` alongside the owning
engine checklists. Declared-task counts and driver receipts qualify only their
recorded scope; they cannot establish full product completion. Missing adapters
are implementation gaps, not reasons to declare a native feature inapplicable.
Native utility dependencies must be integrated with explicit execution-host and
outcome handling; requiring another administration tool or hand-written SQL does
not close a required workflow. Preserve the existing human form-validation and
platform-team ownership boundaries.

Owner correction, 2026-10-16: ScratchBird is under heavy development. Wire its
client drivers and the history integration, but do not run history tests for now.
Keep history qualification explicitly deferred until the owner resumes it; its
absence must not block implementation of the rest of the six-engine matrix.

## Beta edition and source scope (owner correction, 2026-10-20)

Beta supports the open source and source available versions of the engines.
Closed source Enterprise functionality is post beta and must be recorded with
its native dependency and reason for deferral, separately from beta gaps.
Inspect the implementation source, not just grammar, service interfaces or
packaging references, before claiming source availability. Available native
implementations need real tests; absent closed source implementations must not
be replaced with application emulation or counted as beta completion blockers.
MySQL dynamic masking policy administration/execution is post beta: the pinned
community source contains core SQL hooks and column-reference handling, but no
implementation of the required Enterprise object_policy component. Existing
column-reference tests do not establish working masking.

## SQLite version range (owner direction, 2026-10-29)

SQLite is supported from a declared minimum floor, not one exact version. The
floor is 3.35.0, declared once in
`web/pgadmin/cdeadmin/ui_descriptors/sqlite/capabilities.json`
(`version_range.minimum`); 3.53.0 stays the reference profile. Detect the
runtime version and its compile options/modules, and gate each
version-specific feature on both. Grammar, keyword and function tables track
features added and removed across versions, older and newer, until the owner
explicitly retires an older version by raising the floor. Never widen a version
check without the matching gate. The existing 3.53.0 tests stay mandatory; a
version with no available runtime is reported as not run.

## PostgreSQL onto the provider tree (owner direction, 2026-11-08)

PostgreSQL still uses the inherited pgAdmin object tree, while every other
engine uses the provider tree, so each cross-engine feature (Browse data,
To Diagram, the menu and permission model) has needed separate PostgreSQL
wiring or is missing there. Owner direction: move PostgreSQL onto the
provider tree in phases; "the new systems are getting close to the quality
of the legacy and it would be better to make the new system able to support
the old system". This continues the 2026-10-11 direction to preserve the
native PostgreSQL administration surface: its strengths are carried into
the provider tree, not dropped.
1. Parity matrix: every inherited node type and action, and every tool
   entry point, mapped to provider kinds and operations; closed-source
   EDB Advanced Server items recorded as post beta.
2. PostgreSQL navigation on the provider tree, reusing the PostgreSQL-family
   descriptors (YugabyteDB YSQL), switchable per registration while both
   trees exist.
3. Port the tabbed property forms with SQL preview and the version-specific
   SQL templates as shared family forms, reusing pgAdmin's tested SQL.
4. Re-point the tools (debugger, maintenance, backup and restore,
   import/export, grant wizard, schema diff, PSQL, search) to provider
   nodes.
5. Make the provider tree the default when the matrix passes, keep the
   inherited tree for one release, then retire it with dated notes in a
   revertible commit. Do not remove inherited behaviour before its
   replacement is verified.

Owner decision, 2026-11-08: the parity matrix (step 1) is done, and its
proposed order for the remaining work is accepted:
- M2, prerequisites. A PostgreSQL registration can be served by the
  provider tree beside the inherited one; a PostgreSQL navigator; every
  provider resource carries the inherited identity chain (server,
  database, schema, parent relation and object ids) so the inherited tools
  and dialogs still open from provider nodes; Schema Diff and the Query
  Tool list provider endpoints; the inherited-only actions (dashboard,
  monitoring, catalog diagrams, test data, large objects) are declared for
  the provider tree. The supported PostgreSQL version range is an owner
  decision to take first.
- M3, read-only parity for every kind the catalog capture produces, plus
  roles, tablespaces, columns, system catalogs, replica nodes and pgAgent.
- M4, editors where a PostgreSQL-family form already exists, smallest gap
  first; features the YugabyteDB forms refuse are added back for
  PostgreSQL, not inherited as refusals.
- M5, kinds with no reusable form.
- M6, operations and tool openers that do not need the Table family.
- M7, the Table family last, then the debugger and Schema Diff.
- EDB Advanced Server and EDB Distributed items stay post beta.

Owner decision, 2026-11-08 (M2 version range): ScratchRobin supports the
PostgreSQL versions the PostgreSQL project currently supports. A version the
project no longer supports (end of life, archived) is not supported by
ScratchRobin; every version the project supports is. The supported set
changes over time, so check the project's versioning policy when
implementing.

## Engine expansion to full parity (owner direction, 2026-10-29)

Dolt, TiDB, Vitess, CockroachDB, YugabyteDB YSQL, immudb and XTDB are to reach
the same level as PostgreSQL, Firebird, MySQL, MariaDB, SQLite and DuckDB: full
functionality, including each engine's distinctive native features. Order:
the MySQL-wire engines (Dolt, TiDB, Vitess) first, then the PostgreSQL-wire
engines (CockroachDB, YugabyteDB YSQL); immudb and XTDB are not yet ordered.

Forms: use the same forms as much as possible, but never lowest common
denominator. Surface every feature and filter per engine, so nothing is offered
that the engine does not directly support. Each engine keeps its own descriptor
folder over the shared family skeletons, reusing the shared field ids where the
backend field is the same.

Versions: track only significant compatibility breaks, not every minor
version; newer clients generally serve older servers.

## MySQL priorities and MariaDB handoff

Owner direction, 2026-10-22: adopt the eleven comparison-derived MySQL work
items in `docs/en_US/mysql_implementation_priorities.rst`, including the
lower-priority spatial, deployment-automation and notebook workflows. Complete
them alongside the current MySQL beta backlog and native inventory, preserving
their native acceptance requirements. Priority determines sequencing, not
deferral of an accepted item. Once this implementation scope is complete,
stop MySQL feature development and move the active implementation focus to
MariaDB. Keep externally owned forms/platform acceptance, owner-deferred
ScratchBird history testing and post-beta Enterprise functionality separately
recorded; they do not hold up that implementation handoff or establish full
cross-platform product acceptance. Further comparison research must not
automatically expand the agreed MySQL feature queue.

## Unified UI design (owner direction, 2026-10-25)

The owning design document is `docs/en_US/ui_unified_design.rst`. It supersedes per-engine form reviews for structure; `compact_forms.rst`
still governs presentation. All UI work on every engine follows it.

1. Object-centric. A user opens an object from the one browser tree and edits it in
   the family editor. Do not add kind pickers, operation pickers, in-panel trees or
   workspace tabs as a way to reach an object.
2. Family first. Before adding or changing any form, name its object family and tab
   (Section 5 of the design). A field that fits no canonical tab goes on the Engine
   tab. A tab that exists on no family is proposed in the design's open decisions,
   never added by one engine.
3. Declarative only. Forms, tree layout, operations, menu placement and capability
   live in `web/pgadmin/cdeadmin/ui_descriptors/<engine>/`. Do not add branches to
   `relational_admin.py`, `ProviderWorkspaceContent.jsx`, `server.js`,
   `navigator.py`, `context_menu.py` or any shared renderer. If a feature cannot be
   expressed in the descriptor, stop and record it as an open decision with the
   exact field or behaviour that is missing.
4. No raw JSON. `json` and free-text "native action" controls are not user-facing
   controls. Every native option gets a typed control or a grid.
5. No engine branches in UI code. `engine_id ===`, `profile_id ===` and
   `languageProfile ===` comparisons are forbidden outside the descriptor loader and
   provider backends; the lint enforces it. Behaviour differences are declared
   options available to every engine.
6. No new panels. Do not create files under `static/js/Dialogs/`. A form is an
   operation dialog or an editor tab; a tool is registered under Tools and opened
   from a menu. The panel tracker in `ui_unification_status.rst` is reduced, never
   grown.
7. Menus are categorised. Items go in the fixed categories (Section 7). Labels name
   the action, never the engine. Flat engine-prefixed entries are not accepted.
8. Every mutating dialog has a SQL tab showing the provider plan. Do not add a
   separate confirm-step preview.
9. Design system only. Import `cdeadmin_ui` primitives; `@mui/*` imports in provider
   and form code fail lint.
10. Backend features ship with their UI entry. A new provider operation lands with
    its `operations.json` entry, its form, and its family test, or it is recorded as
    unsurfaced in the engine's status page; a declared-task count is not a UI.
11. Delete as you migrate. When an engine's descriptor for a family lands, remove
    that engine's legacy `_form()` branch, `form()` module and panels in the same
    change. Do not leave two implementations.
12. Gates decide. A change is complete when the descriptor validator, the lint rules
    and the family render tests pass. Report the lint counts (json controls, mui
    imports, engine branches, panels) before and after in the change summary.
13. Wording. Labels name the thing ("Character set"), help text carries the native
    keyword, no "exact native ... reference" phrasing in labels. Follow
    `compact_forms.rst` for density and geometry.
14. Scope. The six beta engines get full family editors. The other connector roots
    get the generic family skeleton; do not hand-build forms for them before beta.
    Closed-source features remain post-beta as already recorded.
    Owner direction 2026-10-30: the parity engines (Dolt, TiDB, Vitess,
    CockroachDB, YugabyteDB YSQL, immudb, XTDB) are added to the list of beta
    engines. Each joins the gate lists (`tools/validate_ui_descriptors.py`,
    `tools/tests/test_ui_descriptor_service.py`, the family render fixtures)
    when its descriptor folder lands.

Backend engine streams populate `web/pgadmin/cdeadmin/ui_descriptors/<engine>/`
(see its README.md); the front-end stream owns `families/`, `schema/` and the
shell. Run `make ui-descriptors-check` before publishing; it fails when a form
breaks its family skeleton or when a retired lint count grows
(`tools/ui_lint_maximums.json`). Track progress in
`docs/en_US/ui_unification_status.rst`.

Owner ruling on UI design Decision10, 2026-10-25: MySQL user-key inspection is
metadata-only for beta (key type and byte length). Raw-key retrieval/export is
excluded from the current beta by owner scope, not as closed-source Enterprise
functionality. Keep key material out of public plans, receipts and downloads;
private fingerprint binding and existing native setup/store/generate/remove
remain in scope. This ruling does not implicitly defer native RANDOM PASSWORD
credential delivery or other protected-result workflows.
