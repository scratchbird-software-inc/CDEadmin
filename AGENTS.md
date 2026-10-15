# ScratchRobin project instructions

## Firebird feature completion

Owner direction, 2026-10-10: all functionality identified in the FlameRobin
comparison is required. The owning requirements and acceptance checklist are
`docs/en_US/firebird_functional_completion.rst`. Preserve current edits and
implement engine-specific behavior; generic forms or placeholders do not prove
native support. Do not introduce unsupported features on an engine/version.

## Diagram-Design-Notation integration and freshness

Owner-designated sister project:
`/home/dcalford/Sandbox/Diagram-Design-Notation/`.
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

This is a prerequisite even for direct webpack/pytest/Jest invocation. Until an
automated gate covers those entry points, perform and document it explicitly.
Do not claim the gate is automated when it is only a contributor instruction.

At introduction of this instruction the checked-in loader still expects DDN
0.5.0-draft.2 and Designer 0.1.0-preview.1. The sister project is 0.8.0 and its
shipping designer is the unified tool. Migrate that boundary before treating
ERD/dashboard integration or a build using the old pair as compliant.

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
that work. Form validation belongs to the human team. Windows/macOS work and
qualification remain with the platform teams, and their evidence is required
before a cross-platform completion claim. All recorded Firebird/DDN/dashboard
requirements remain in scope, including published live dashboard bindings,
native DDN roundtrip/diff/apply and remaining FlameRobin parity. Persistent
SQL history, dashboard definitions and recipes remain in scope. Follow the
acceptance rules in `docs/en_US/firebird_functional_completion.rst`.
