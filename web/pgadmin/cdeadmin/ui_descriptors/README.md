# UI descriptors

This folder is the single declarative source for what the CDEadmin UI shows
for each engine: object kinds, their object-family editors, tier 2/3
operation dialogs, menu placement, tree layout and version gates.
The owning design is `docs/en_US/ui_unified_design.rst` (owner direction
2026-10-25). Progress is tracked in `docs/en_US/ui_unification_status.rst`.
The build gate is `tools/validate_ui_descriptors.py` (`make ui-descriptors-check`).

Backend engine streams populate this folder. The front-end stream builds the
shell that renders it. Neither edits the other's code: a field that cannot be
expressed here is an open decision in the design document, not a new branch in
`relational_admin.py` or `ProviderWorkspaceContent.jsx`.

## Layout

```text
ui_descriptors/
  schema/            JSON Schemas (do not edit without a design change)
  families/          canonical skeletons, one per object family (front-end owned)
  <engine>/
    capabilities.json    every kind the engine exposes, its family, tier-1 ops, version gates
    operations.json      tier 2/3 operations: menu category, fields, confirmation
    navigator.json       tree groups, sort order, icon keys
    omitted_families.json families the engine has no concept for (with reasons)
    options.json         option sources: static dialect lists (types, privileges, auth plugins) and
                         catalog lists resolved from the endpoint's resources by kind
    tools.json           tool, dashboard and registration openers for the Object Explorer menu
                         (what context_menu.py used to add with engine_id branches)
    forms/<family>.form.json   the fields this engine shows on each canonical tab
```

### tools.json (phase 4: menus from descriptors)

`context_menu.py` builds the provider context menus and used to append
engine-specific entries behind `if engine_id == '...'` branches. Those entries
are now declared per engine in `tools.json` and appended by
`declared_tool_actions(engine_id, scope, slot, state=..., base=...)` at the
slot where the branch used to be, so category ordering is unchanged. An entry
names its `scope` (connector / endpoint / database / resource_group /
resource), optional `slot`, `handler`, `icon`, `group`, `priority`,
`mutation`, `arguments` (merged over the scope's base ids; `inherit_base:
false` + `base_keys` keeps only the listed ids), `when` filters (route kind,
localhost placeholder, resource kinds, database target, system/temporary
objects) and `enabled_when` conditions (`verified`, `owner`, `available`) with
optional per-condition `disabled_reasons`. Labels and ids may use `{display}`
and `{engine_id}`.

Read-only dashboard openers may declare `arguments.dashboard_viewer`:
`firebird_monitoring` or `relational_monitoring` selects an existing DDN
viewer. The shared dashboard pane reads this option from the resolved bundle's
`tools` list, using `endpoint` or `database` scope. It passes the engine and
registered target identity, never collector policy or editing arguments.
Monitoring APIs authorize each read independently of interactive SQL sessions.

Only openers belong here. Tier 1 lifecycle comes from the family forms and
tier 2/3 operations from `operations.json` (the tree already retires a legacy
entry whose operation id a descriptor operation covers). The validator counts
the remaining `engine_id` branches in `context_menu.py`
(`engine_branches_in_context_menu`, maximum in `tools/ui_lint_maximums.json`);
lower the maximum as an engine's branches move into its `tools.json`. The
MySQL and MariaDB branches are the MySQL stream's to migrate.

## Regenerating a first draft

Three tools turn the provider's live form contracts into reviewed draft
descriptors so no field id, option list or visibility rule has to be retyped:

```text
python3 tools/dump_provider_forms.py --out /tmp/forms          # effective forms per engine
python3 tools/draft_ui_descriptors.py --forms /tmp/forms --engine firebird --write
python3 tools/review_ui_descriptors.py --engine firebird --write      # canonical shapes
```

The review pass splits a combined constraints grid into the four canonical
grids (bound back to `constraints[kind=...]`), types trigger events, turns
table/parent fields into reference pickers, marks one-column grids as string
lists (`item_kind: string`), and sets `record_key` on the column grid so an
existing object pre-fills the editor from the provider's native record.

Pre-fill is declared per field (and per grid column) with these keys, all
optional and all handled identically by the shell and the Python twin:

| key | meaning |
| --- | --- |
| `record_key` | key or dotted path in the native record/row (`type_editor.data_type`) |
| `record_truthy` | coerce `"0"`/`"1"`/null style flags to a boolean |
| `record_derive` | `{cases: [{key, truthy\|equals, value}], default}` — first matching case wins (column mode, timing, direction) |
| `record_filter` | grid: keep rows whose `key` equals a value — the reverse of `backend_field_id: list[kind=X]` |
| `record_pluck` | grid column: take one key from each item of a list of objects (`backing_index.segments` → `field_name`) |
| `record_pattern` | regular expression whose first group is the value (strip `DEFAULT `, `CHECK (...)`, outer parentheses) |
| `ui_only` | never sent to the provider (variant switches) |
| `record_children` (form level) | `{field_id: {resource_kind}}` — fill a grid from the object's child resources when the inventory lists columns/constraints separately (MySQL family); each child is `{name, ...native}` |

When a native record lacks a usable shape (catalog type codes instead of a
type expression, an undecoded event mask), add the decoded value to the
provider's native record rather than teaching the descriptor engine logic;
the Firebird provider's `type_editor`, `type_sql`, `trigger_timing` /
`trigger_events` and parameter `type_sql` keys are the pattern.

The acceptance step for `complete` is a round trip through the form's own
fields: `tools/ui_descriptor_roundtrip.py` maps a UI draft onto the provider
draft exactly as the shell does (`backend_draft`, `record_draft`), and
`tools/tests/test_ui_descriptor_roundtrip_<engine>.py` plans, applies and
re-inspects on a real database. SQLite and DuckDB run on a file; the server
engines skip unless an environment variable points at a live server:

| engine | environment |
| --- | --- |
| Firebird | `CDEADMIN_ROUNDTRIP_FIREBIRD='{"host","port","user","password","database_root"}'` plus `CDEADMIN_FIREBIRD_CLIENT_LIBRARY` (a Firebird 5 `libfbclient`) |
| MariaDB | `CDEADMIN_ROUNDTRIP_MARIADB='{"host","port","user","password"}'` (an account that may create databases and accounts; needs the patched connector from `tools/cdeadmin_build_mariadb_driver.py`) |

Each test creates and drops its own database/objects under a unique name.

The drafter places fields on canonical tabs by id, turns array/object editors
into grids, downgrades bare JSON boxes to `keyvalue` and lists each one under
`gaps` as `typed_from_json`, classifies non-lifecycle operations into tiers
and menu categories, and adds any provider kind the seed list missed as an
Engine object. It never touches a form whose status is `complete`, and it
leaves `navigator.json` and `omitted_families.json` alone. Re-run it after a
provider gains a field; then do the review steps below.

## How a backend engine stream fills it in

1. Open `families/<family>.family.json` to see the tabs and the primitive each
   tab uses. Those are fixed. Your form lists fields and says which tab each
   one sits on (`"tab": "Options"`).
2. For each field, reuse the provider's existing `field_id` where one exists so
   `plan` / `validate` / `apply` keep working. If the UI name differs from the
   backend name, set `backend_field_id` (dotted for a key inside an object the
   backend still accepts, e.g. `mysql_table_options.row_format`; bracketed for
   a record kind inside a list, e.g. `constraints[kind=foreign_key]`).
3. Pick a typed `control`. `json` and free-text "native action" are not
   controls. A list of records is a `grid` with `columns`; a bag of named
   values is `keyvalue`; a long SQL body is `code` with `language`; a choice is
   `select`/`radio`; a pick of an existing object is `reference` with
   `reference_kind`. `option_values_path` points at the dialect or catalog
   list that supplies the choices.
4. Engine-only options go on the `Engine` tab (`engine_tab_title` names it).
   Use `group` to cluster them (Storage hints, Statistics, Files...).
5. Record what the engine has but the provider does not expose yet under
   `gaps`, and canonical tabs the engine has no concept for under
   `omitted_tabs`, each with a reason. Never fake a field.
6. A `select`/`multiselect` whose choices are not static lists its source as
   `option_values_path`: `["dialect", "<key>"]` for a list in `options.json`
   (`column_types`, `collations`, `privileges` keyed by object type, ...) or
   `["catalog", "<key>"]` for a list `options.json` maps to a resource kind on
   the connected endpoint (`tablespaces`, `databases`, `character_sets`).
   `["draft", "columns"]` reads the names in the form's own Columns grid. The
   validator rejects a path with no source.
7. Version-dependent fields get `version: {"minimum": "8.0.16"}`; the shell
   disables them with the reason instead of hiding them.
8. Move the form from `pending` to `draft` when all fields are listed, and to
   `complete` when a round trip (open object, change a field on every tab,
   apply, re-inspect) has been verified on the tested version. A `complete`
   form must carry every tab the skeleton marks required or list it in
   `omitted_tabs`.
9. Tier 2/3 operations (ANALYZE, backup, sweep, binlog replay...) go in
   `operations.json` with a `menu.category` from the fixed list and the same
   field rules. Labels name the action, never the engine.
10. Run `python3 tools/validate_ui_descriptors.py --counts` before committing;
   delete the legacy `_form()` branch or `form()` module for anything you have
   moved here in the same change, and quote the before/after lint counts in
   the commit summary.

`mysql/forms/table.form.json` is the worked example: every field there already
exists in the backend (`mysql_table_options.KEYS`,
`_structured_record_controls`); the descriptor only types them.

## What the front-end stream owns

`families/*.family.json`, `schema/*.json`, the shell components in
`static/js/cdeadmin_ui` that render these files, and the family render tests
under `web/regression/javascript/families/`. Changes to a skeleton are design
changes and go through the design document first.
