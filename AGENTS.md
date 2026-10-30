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
Use its tools for ERD and dashboard display and editing. ScratchRobin owns
provider metadata/data adapters, authorization, persistence and native-operation
execution; DDN owns diagram/dashboard rendering and visual editing. Do not build
another ERD or dashboard editor in ScratchRobin.

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

## Bidirectional native metadata and DDN

Owner direction, 2026-10-10: DDN is also the database-design exchange format.
Follow `docs/en_US/ddn_database_roundtrip.rst`: discover object/database/server
metadata and selected data into one or more DDN views; read DDN to generate
engine-native metadata; compare desired/live/baseline metadata to produce native
migration statements. Preserve exact types, identities, names and dependencies.
A view filter is never deletion intent. Current DDN illustrative SQL export and
visual diff views do not constitute deployable native schema generation/diff.

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
