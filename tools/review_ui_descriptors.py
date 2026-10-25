#!/usr/bin/env python3
"""Structural review pass over generated engine forms (design section 6).

Applies the canonical shapes the drafter cannot infer from provider field
lists, identically on every engine that uses them:

* a combined ``constraints`` grid with a ``kind`` column becomes one grid per
  constraint kind (Primary key / Unique / Foreign keys / Check) bound back to
  ``constraints[kind=<SQL kind>]`` so the provider still receives one list;
* trigger ``events`` becomes a multiselect fed by ``dialect.trigger_events``;
* ``table``/``parent``/``references_table`` text fields become reference
  pickers; index column lists become selects over the target's columns;
* the SQLite table variants (virtual / FTS) get their own module-column grid
  instead of a second ``columns`` field.

Idempotent: a form already in the reviewed shape is left unchanged, and a
``complete`` form is never touched. Run after ``draft_ui_descriptors.py``.

Usage: python3 tools/review_ui_descriptors.py [--engine firebird ...] [--write]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESCRIPTORS = REPO / "web" / "pgadmin" / "cdeadmin" / "ui_descriptors"
ENGINES = ("firebird", "mariadb", "duckdb", "sqlite")

CONSTRAINT_GRIDS = [
    ("primary_key", "Primary key", "PRIMARY KEY", ["name", "columns"]),
    ("unique_constraints", "Unique", "UNIQUE", ["name", "columns"]),
    ("foreign_keys", "Foreign keys", "FOREIGN KEY", ["name", "columns", "references_table", "references_columns"]),
    ("check_constraints", "Check", "CHECK", ["name", "expression"]),
]


def field(fid, label, control, **kw):
    out = {"field_id": fid, "label": label, "control": control}
    out.update(kw)
    return out


def constraint_column(fid):
    return {
        "name": field("name", "Name", "text"),
        "columns": field("columns", "Columns", "multiselect", required=True, option_values_path=["draft", "columns"]),
        "references_table": field("references_table", "Referenced table", "reference", required=True, reference_kind="table"),
        "references_columns": field("references_columns", "Referenced columns", "multiselect", required=True,
                                    help="Columns of the referenced table, in key order."),
        "expression": field("expression", "Expression", "code", required=True, language="sql"),
    }[fid]


def split_constraints(form, changes):
    fields = form["fields"]
    index = next((i for i, f in enumerate(fields) if f["field_id"] == "constraints" and f["control"] == "grid"
                  and any(c["field_id"] == "kind" for c in f.get("columns", []))), None)
    if index is None:
        return
    original = fields[index]
    replacement = []
    for fid, label, kind, columns in CONSTRAINT_GRIDS:
        replacement.append({**field(fid, label, "grid", tab=original.get("tab", "Constraints"), group=label,
                                    backend_field_id=f"constraints[kind={kind}]",
                                    columns=[constraint_column(c) for c in columns])})
    fields[index:index + 1] = replacement
    changes.append("constraints grid split into Primary key / Unique / Foreign keys / Check")


def trigger_events(form, changes):
    for f in form["fields"]:
        if f["field_id"] == "events" and f["control"] in ("keyvalue", "text"):
            f["control"] = "multiselect"
            f["option_values_path"] = ["dialect", "trigger_events", "table"]
            f.pop("columns", None)
            changes.append("trigger events typed as a multiselect from dialect.trigger_events")
    form["gaps"] = [g for g in form.get("gaps", []) if not g["concept"].endswith(".events")]


def references(form, catalog_keys, changes):
    for f in form["fields"]:
        if f["field_id"] == "table" and f["control"] == "text":
            f["control"] = "reference"
            f["reference_kind"] = "table"
            changes.append("table picker")
        if f["field_id"] == "parent" and f["control"] == "text":
            kind = "schema" if "schemas" in catalog_keys else "database"
            f["control"] = "reference"
            f["reference_kind"] = kind
            if f.get("label", "").lower().startswith("parent"):
                f["label"] = "Schema" if kind == "schema" else "Database"
            changes.append(f"parent picker ({kind})")
        if f["control"] == "grid" and len(f.get("columns", [])) == 1 and f["columns"][0]["field_id"] == "value":
            # a one-column "value" grid is the drafter's rendering of a plain string list
            f["item_kind"] = "string"
            column = f["columns"][0]
            if f["field_id"] == "columns":
                column["label"] = "Column"
                column["control"] = "reference"
                column["reference_kind"] = "column"
                column.pop("option_values_path", None)
                changes.append("index columns as an ordered column list")
            else:
                changes.append(f"{f['field_id']} as a string list")


def sqlite_variants(form, changes):
    if form["engine"] != "sqlite" or form["family"] != "table":
        return
    fields = form["fields"]
    variant = next((f for f in fields if f["field_id"] == "variant"), None)
    if variant is None:
        return
    variant.setdefault("default", "default")
    variant["label"] = "Table kind"
    for option in variant.get("options", []):
        option["label"] = {"default": "Ordinary", "virtual": "Virtual (module)", "fts": "Full-text search"}.get(option["value"], option["label"])
    kept = []
    seen_module = set()
    for f in fields:
        if f["field_id"] == "columns" and f["control"] == "keyvalue":
            continue  # replaced by module_columns below
        if f["field_id"] in ("module", "module_options"):
            key = f["field_id"]
            if key in seen_module:
                continue
            seen_module.add(key)
            f["visible_when"] = {"field": "variant", "in": ["virtual", "fts"]}
            f.pop("group", None)
            f["tab"] = "Engine"
        if f["field_id"] == "columns" and f["control"] == "grid":
            f["visible_when"] = {"field": "variant", "equals": "default"}
        kept.append(f)
    if not any(f["field_id"] == "module_columns" for f in kept):
        kept.insert(next(i for i, f in enumerate(kept) if f["field_id"] == "columns") + 1,
                    field("module_columns", "Module columns", "grid", tab="Columns", backend_field_id="columns",
                          visible_when={"field": "variant", "in": ["virtual", "fts"]},
                          columns=[field("name", "Name", "text", required=True),
                                   field("unindexed", "Unindexed (FTS5)", "boolean")],
                          help="FTS and spatial column names; geopoly lists auxiliary columns."))
        changes.append("virtual/FTS variants get a module_columns grid")
    form["fields"] = kept
    form["gaps"] = [g for g in form.get("gaps", []) if ".columns" not in g["concept"]]


COLUMN_RECORD_KEYS = {"type": ("data_type", False), "primary_key": ("primary_key_position", True)}


def column_record_keys(form, changes):
    """Pre-fill keys for the standard column grid from the inspected record."""
    for f in form["fields"]:
        if f["field_id"] != "columns" or f["control"] != "grid":
            continue
        for column in f.get("columns", []):
            spec = COLUMN_RECORD_KEYS.get(column["field_id"])
            if spec and "record_key" not in column:
                column["record_key"], truthy = spec
                if truthy:
                    column["record_truthy"] = True
                changes.append("column grid record keys")


def duckdb_acknowledgements(form, changes):
    if form["engine"] != "duckdb":
        return
    for f in form["fields"]:
        if f["field_id"] in ("complete_definition_confirmed", "metadata_reset_acknowledged"):
            if f.get("tab") != "Options":
                f["tab"] = "Options"
                f["group"] = "Replace confirmation"
                f["help"] = (f.get("help") or "") + " Required by the provider before it replaces the definition."
                changes.append("DuckDB replace acknowledgements grouped under Options")


def review(engine, write):
    folder = DESCRIPTORS / engine
    options = json.loads((folder / "options.json").read_text()) if (folder / "options.json").exists() else {}
    catalog_keys = set(options.get("catalog", {}))
    report = []
    for path in sorted((folder / "forms").glob("*.form.json")):
        form = json.loads(path.read_text())
        if form.get("status") == "complete":
            continue
        before = copy.deepcopy(form)
        changes = []
        split_constraints(form, changes)
        trigger_events(form, changes)
        references(form, catalog_keys, changes)
        sqlite_variants(form, changes)
        duckdb_acknowledgements(form, changes)
        column_record_keys(form, changes)
        if form != before:
            form["notes"] = (form.get("notes", "") + " Reviewed by tools/review_ui_descriptors.py: " + "; ".join(sorted(set(changes))) + ".").strip()
            report.append(f"{path.name}: {', '.join(sorted(set(changes)))}")
            if write:
                path.write_text(json.dumps(form, indent=2, ensure_ascii=False) + "\n")
    print(f"{engine}:\n  " + ("\n  ".join(report) if report else "no changes"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", action="append")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for engine in args.engine or ENGINES:
        review(engine, args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
