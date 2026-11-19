> Historical review before implementation. The owning specification is `../../data_navigator_surfaces.rst`; its decisions and ledger supersede historical status statements below.

# Revised surface review — current Data Viewer is the visual reference

Version 2 replaces the generic version 1 mockups. No application source was changed. All displayed rows, metadata, timings, plans, transactions and validation results are fixtures or illustrations, not live engine observations.

## What was reviewed and reused

The isolated harness imports the current committed DataEditSurface, SqlEditorSurface, AdaptiveRecordFormCard, ProjectShell, NotebookBar, Dialog, field primitives and SurfaceExportDialog. It renders them through the real React components, using mocked host responses. The Data Viewer grid reference therefore includes its actual:

- 58-pixel sticky record gutter, current-record marker, row numbers and row-state/bookmark affordances;
- sticky header, hamburger column chooser, saved column widths, column resizing and frozen-column positioning;
- key, pin, sort and filter indicators; numeric alignment and current-row/cell styling;
- adaptive mini-form labels, datatypes, natural field sizing and record boundaries;
- full-form and in-grid hybrid treatment, source scrolling and focus layout;
- existing compact segmented TiB controls, large primary actions, stacked secondary actions and group separators;
- rounded work islands, common left drawer, contextual right drawer and existing status-line arrangement.

The left navigation data is fixture data, rendered through the current PgTree FileTreeItem and TreeBranchGuides components. The simplified explorer from the earlier review was withdrawn; native line geometry, circular toggles, selection and active-trace styling are used throughout the refreshed images. The source capture uses the current light theme. Operator registration data, user profiles and databases are not accessed.

## Findings from the comparison

1. The existing SQL results grid is still a different implementation. In these captures it stretches columns differently, aligns the integer result differently and lacks the Data Viewer header's pin/sort affordances. The proposed SQL results use DOM rendered by DataEditSurface as the visual reference. This is a static review composition, not a completed component migration.
2. Both surfaces already import AdaptiveRecordFormCard, but their wrappers, viewport/scroll handling and supplied context callbacks differ. Current and proposed grid/mini-form/full-form/hybrid images are shown separately for both surfaces.
3. The existing TiB has three under-tabs per surface. This review retains that structure as its starting point: Data / Format & Layout / Transfer & SQL, and Query / Format & Layout / Export & Files. The five/six-tab redesign from version 1 is withdrawn. Final grouping remains subject to owner review.
4. Current Data Viewer source still has a Visual SQL launch entry. It is visible only in current-component captures; it is absent from every proposed Data Viewer control set, per the owner's correction.
5. The legacy fifth hybrid-when-editing mode is present in the current TiB. The proposal offers the four agreed presentations. Whether the old automatic editing behaviour should survive as a separate preference still needs a decision.
6. Existing dialogs/drawers were reviewed, including column order, multi-column sort, column format/profile, filter builder, staged SQL, fetch limits, jump, layout/template save/apply, import, query parameters, connection details, saved queries and export settings for CSV, TSV, XLSX, ODS, PDF, JSON and SQL INSERT/UPDATE.
7. New font/type defaults, Markdown, JSON, UUID conversion, custom transaction and statement-structure forms use the application's dialog and field vocabulary. Their content and acceptance/apply details remain proposals, not implemented functionality.
8. The fixture rendering exposed oversized TiB popup icons / missing inherited popup palette values, and clipped prototype dialogs when a small dialog hosted wide content. Proposal-only styles bound popup icons to the existing 17-pixel control size, use the native palette, choose the existing large-dialog width and match the grid's UI font. Current captures are retained without those overrides. Full application global styling may affect these observations; this is a visual-review finding, not native product qualification.
9. Metadata and Information proposals reuse the Data Viewer grid DOM for object lists/attributes. Metadata shows create statement, object comment, dependents and dependencies. Information has object attributes or a generated SELECT summary. The exact object/query context selection remains a discussion point.
10. The source SQL split renderer is reused for side-by-side and stacked SQL/data examples. Both areas remain inside the same surface. A Data Viewer Data + Information split is also illustrated. These are layout examples, not newly implemented independent-area state handling.

## Approved requirements retained

- Two surfaces sharing components: Data Viewer has an object/baseline query; SQL Editor supports any valid DDL/DML/PSQL and visual design. No visual designer in Data Viewer.
- What to show is separate from how to show it. Dual display belongs to the same surface; each area independently selects content and applicable presentation.
- Navigation order: first record, previous page, previous record, bookmark, next record, next page, last record.
- Separate transaction preparation and statement preparation. Statement preparation obtains columns/datatypes/plan without execution. Two-phase preparation is offered only where native support exists; ordinary one-phase commit is not labelled a fictitious PREPARE operation.
- Field-type font/alignment defaults and saved user layouts keyed by connection/server + database + optional schema + table/view.
- Approved precedence, independently per property: current explicit field choice > saved field setting > field-type default > application default.
- Specialized editors and explicit forward/reverse display conversions. A 16-byte binary value is not automatically a UUID. Failed reverse conversion preserves the original value.
- CSV, TSV and plain-text clipboard choices, including selectable and reorderable Information columns.

## Reading the gallery

Each surface gallery separates proposed TiB tabs, expanded dropdowns, menus, presentations, specialized forms and current-component reference images. PNG captions explicitly identify current versus proposed. Current captures are evidence of component appearance with fixtures only. Proposal compositions and sizing changes are documented here and in the provenance manifest.

These historical review captures use fixture data and do not establish backend completion, platform qualification or approval of proposed layouts.

## Explicit preservation checks added after owner review

The refreshed set uses the existing PgTree FileTreeItem and TreeBranchGuides renderer for the common explorer. Its curved guide paths, branch continuations, circular toggles and active path are not substituted with a new tree design. Labels and hierarchy are fixture data.

Real browser focus was applied to NAME in mini-form, full-form and hybrid views. The existing field comment appeared below the focused field and disappeared when focus moved to CITY. This verifies current record-form comment behaviour, not complete descriptive-help coverage for all newly proposed settings. New setting descriptions still have to be specified and localized.

The original shell colour-scheme selector was exercised: the dark scheme changed the rendered work-area colour and retained its scheme/typography state in the isolated browser profile. The original language mechanism was exercised with French: locale state and translated shell labels changed while database identifiers/data retained their spelling. These are focused checks of the existing mechanisms, not an audit of every translation string or every possible custom palette.

Examples are included in the Data Viewer gallery's preservation section. The shell controls are common to both surfaces. No operator preferences or application source were modified. The captures illustrate the focused preservation checks; see the owning specification for current implementation status.
