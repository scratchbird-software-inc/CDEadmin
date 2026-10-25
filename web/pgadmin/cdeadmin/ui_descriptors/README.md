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
    forms/<family>.form.json   the fields this engine shows on each canonical tab
```

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
6. Version-dependent fields get `version: {"minimum": "8.0.16"}`; the shell
   disables them with the reason instead of hiding them.
7. Move the form from `pending` to `draft` when all fields are listed, and to
   `complete` when a round trip (open object, change a field on every tab,
   apply, re-inspect) has been verified on the tested version. A `complete`
   form must carry every tab the skeleton marks required or list it in
   `omitted_tabs`.
8. Tier 2/3 operations (ANALYZE, backup, sweep, binlog replay...) go in
   `operations.json` with a `menu.category` from the fixed list and the same
   field rules. Labels name the action, never the engine.
9. Run `python3 tools/validate_ui_descriptors.py --counts` before committing;
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
