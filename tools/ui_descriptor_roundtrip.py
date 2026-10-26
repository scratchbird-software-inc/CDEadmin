#!/usr/bin/env python3
"""Round-trip helpers for UI descriptor forms (README step 8).

A form reaches ``complete`` only after a draft entered through its own fields
has been planned, applied and re-inspected against the tested engine. This
module gives tests the two pieces that path needs without any UI:

* ``backend_draft(form, draft, mode, baseline)`` — the Python twin of the
  shell's ``toBackendDraft``: maps UI field ids onto provider field ids
  (``backend_field_id``, dotted and ``list[kind=X]`` forms), honours
  ``modes`` and ``visible_when``, and turns an alter-mode Columns grid diff
  into add/drop/rename lists.
* ``resolved_form(engine, family)`` — the form merged with its family
  skeleton, as the service serves it.

Keep this in step with web/pgadmin/static/js/cdeadmin_ui/objects/descriptors.js;
the Jest suite and these tests must agree on the same drafts.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "web"))
if "pgadmin" not in sys.modules:
    package = ModuleType("pgadmin")
    package.__path__ = [str(REPO / "web" / "pgadmin")]
    sys.modules["pgadmin"] = package

from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService  # noqa: E402

_BRACKET = re.compile(r"^([a-z0-9_]+)\[([a-z0-9_]+)=([^\]]+)\]$", re.I)
_SERVICE = UIDescriptorService()


def resolved_form(engine: str, family: str) -> dict:
    return _SERVICE.engine(engine)["forms"][family]


def field_visible(field: dict, draft: dict) -> bool:
    rule = field.get("visible_when")
    if not rule or not rule.get("field"):
        return True
    value = draft.get(rule["field"])
    if "equals" in rule:
        return value == rule["equals"]
    if isinstance(rule.get("in"), list):
        return value in rule["in"]
    if "truthy" in rule:
        return bool(value) == bool(rule["truthy"])
    return True


def active_fields(fields, mode="create", draft=None):
    draft = draft or {}
    return [f for f in fields if (not f.get("modes") or mode in f["modes"]) and field_visible(f, draft)]


def _strip(row):
    if isinstance(row, dict):
        return {k: v for k, v in row.items() if k != "_id" and v not in (None, "")}
    return row


def diff_columns(before, after):
    def key(row, index):
        return row.get("_id") if isinstance(row, dict) and row.get("_id") else f"{(row or {}).get('name', '')}#{index}"
    before_by_key = {key(row, i): row for i, row in enumerate(before or [])}
    after_keys = {key(row, i) for i, row in enumerate(after or [])}
    add, rename = [], []
    for i, row in enumerate(after or []):
        previous = before_by_key.get(key(row, i))
        if previous is None:
            add.append(_strip(row))
        elif previous.get("name") != row.get("name") and row.get("name"):
            rename.append({"from": previous["name"], "to": row["name"]})
    drop = [row.get("name") for i, row in enumerate(before or []) if key(row, i) not in after_keys]
    return {"add_columns": add, "drop_columns": drop, "rename_columns": rename}


def backend_draft(form: dict, draft: dict, mode: str = "create", baseline: dict | None = None) -> dict:
    out: dict = {}
    for tab in form.get("tabs", []):
        for field in active_fields(tab.get("fields", []), mode, draft):
            fid = field["field_id"]
            if fid not in draft or field.get("ui_only"):
                continue
            value = draft[fid]
            if mode == "alter" and field.get("control") == "grid" and fid == "columns" and baseline is not None:
                diff = diff_columns(baseline.get("columns") or [], value or [])
                out.update({k: v for k, v in diff.items() if v})
                continue
            if mode == "alter" and baseline is not None and \
                    json.dumps(value, sort_keys=True, default=str) == json.dumps(baseline.get(fid), sort_keys=True, default=str):
                continue  # unchanged fields are not part of the ALTER set, required or not
            if field.get("wrap_list") and not isinstance(value, list):
                value = [value] if value not in (None, "") else []
            target = field.get("backend_field_id") or fid
            match = _BRACKET.match(target)
            if match:
                list_name, key, discriminator = match.groups()
                out.setdefault(list_name, []).extend({key: discriminator, **_strip(row)} for row in (value or []))
            elif "." in target:
                node = out
                parts = target.split(".")
                for part in parts[:-1]:
                    node = node.setdefault(part, {})
                node[parts[-1]] = value
            elif field.get("control") == "grid" and field.get("item_kind") == "string":
                column = (field.get("columns") or [{"field_id": "value"}])[0]["field_id"]
                out[target] = [row.get(column) if isinstance(row, dict) else row for row in (value or [])
                               if (row.get(column) if isinstance(row, dict) else row) not in (None, "")]
            else:
                out[target] = [_strip(row) for row in value] if isinstance(value, list) else value
    return out


_MISSING = object()


def _read_path(record, path):
    node = record
    for part in path.split("."):
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return _MISSING
    return node


def is_child_of(row, resource):
    return (row.get("parent_resource_id") == resource.get("resource_id") or
            (row.get("native") or {}).get("navigator_parent_resource_id") == resource.get("resource_id") or
            list(row.get("display_path") or [])[:-1] == list(resource.get("display_path") or []))


def record_from_resource(form: dict, resource: dict, resources=()) -> dict:
    """The editor record: native facts plus record_children rows (twin of the host)."""
    native = resource.get("native") or {}
    record = {**native, "name": native.get("name", resource.get("display_name")),
              "display_name": resource.get("display_name"), "resource_id": resource.get("resource_id"),
              "resource_kind": resource.get("resource_kind")}
    for field_id, rule in (form.get("record_children") or {}).items():
        record[field_id] = [{"name": row.get("display_name"), **(row.get("native") or {})} for row in resources
                            if row.get("resource_kind") == rule["resource_kind"] and is_child_of(row, resource)]
    return record


def record_value(field: dict, record: dict):
    """The record value that pre-fills a field/grid column, or _MISSING.

    Order: record_derive rule, record_key (dotted allowed), field_id.
    """
    derive = field.get("record_derive")
    if derive:
        for case in derive.get("cases", []):
            found = _read_path(record, case["key"])
            if "equals" in case:
                if found is not _MISSING and found == case["equals"]:
                    return case["value"]
            elif "matches" in case:
                if isinstance(found, str) and re.search(case["matches"], found, re.S | re.I):
                    return case["value"]
            elif bool(found is not _MISSING and _truthy(found)) == bool(case.get("truthy", True)):
                return case["value"]
        return derive.get("default", _MISSING)
    value = _MISSING
    if field.get("record_key"):
        value = _read_path(record, field["record_key"])
    if value is _MISSING:
        value = _read_path(record, field["field_id"]) if field["field_id"] in record else _MISSING
    if value is _MISSING:
        return value
    if field.get("record_filter") and isinstance(value, list):
        rule = field["record_filter"]
        value = [row for row in value if isinstance(row, dict) and _read_path(row, rule["key"]) == rule["equals"]]
    if field.get("record_pluck") and isinstance(value, list):
        value = [row.get(field["record_pluck"]) if isinstance(row, dict) else row for row in value]
    if field.get("record_pattern") and isinstance(value, str):
        match = re.search(field["record_pattern"], value, re.S | re.I)
        value = match.group(1) if match else value
    if field.get("control") == "multiselect" and isinstance(value, str):
        value = [value] if value else []
    return _truthy(value) if field.get("record_truthy") else value


def _truthy(value):
    """Record truthiness: catalog flags arrive as "0"/"1" strings too."""
    return value not in (None, "", 0, "0", False, "false", "FALSE")


def record_draft(form: dict, record: dict, mode: str = "alter") -> dict:
    """Pre-fill a draft from an inspected native record (the editor's initialDraft)."""
    draft = {}
    for tab in form.get("tabs", []):
        for field in tab.get("fields", []):
            if field.get("modes") and mode not in field["modes"]:
                continue
            value = record_value(field, record)
            if value is _MISSING:
                if field.get("default") is not None:
                    draft[field["field_id"]] = field["default"]
                elif field.get("control") == "grid":
                    draft[field["field_id"]] = []
                continue
            if field.get("control") == "grid" and isinstance(value, list):
                rows = []
                for index, row in enumerate(value):
                    if not isinstance(row, dict):
                        column = (field.get("columns") or [{"field_id": "value"}])[0]["field_id"]
                        rows.append({column: row, "_id": str(index)} if field.get("item_kind") == "string" else row)
                        continue
                    out = dict(row)
                    for column in field.get("columns", []):
                        found = record_value(column, row)
                        if found is not _MISSING:
                            out[column["field_id"]] = found
                    out.setdefault("_id", str(index))
                    rows.append(out)
                value = rows
            draft[field["field_id"]] = value
    return draft


def form_field_ids(form: dict) -> set:
    return {f["field_id"] for tab in form.get("tabs", []) for f in tab.get("fields", [])}


__all__ = ("backend_draft", "diff_columns", "resolved_form", "active_fields", "field_visible", "form_field_ids", "record_draft", "record_value", "record_from_resource", "is_child_of", "operation_draft", "engine_operations")


def operation_draft(operation: dict, values: dict | None = None, confirmation: str | None = None) -> dict:
    """The OperationDialog's draft: field defaults plus the user's values (twin
    of initialValues); a typed-name confirmation travels as ``confirmation``."""
    draft = {}
    if operation.get("confirmation") == "typed_name" and confirmation:
        draft["confirmation"] = confirmation
    for field in operation.get("fields", []):
        if field.get("default") is not None:
            draft[field["field_id"]] = field["default"]
        elif field.get("control") == "boolean":
            draft[field["field_id"]] = False
        elif field.get("control") == "grid":
            draft[field["field_id"]] = []
    for key, value in (values or {}).items():
        if value is not None:
            draft[key] = value
    return draft


def engine_operations(engine: str) -> dict:
    return {op["operation_id"] + "@" + op["resource_kind"]: op
            for op in _SERVICE.engine(engine)["operations"]}
