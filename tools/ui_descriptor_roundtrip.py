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
            if fid not in draft:
                continue
            value = draft[fid]
            if mode == "alter" and field.get("control") == "grid" and fid == "columns" and baseline is not None:
                diff = diff_columns(baseline.get("columns") or [], value or [])
                out.update({k: v for k, v in diff.items() if v})
                continue
            if mode == "alter" and baseline is not None and not field.get("required") and \
                    json.dumps(value, sort_keys=True, default=str) == json.dumps(baseline.get(fid), sort_keys=True, default=str):
                continue
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


def record_draft(form: dict, record: dict, mode: str = "alter") -> dict:
    """Pre-fill a draft from an inspected native record (the editor's initialDraft)."""
    draft = {}
    for tab in form.get("tabs", []):
        for field in tab.get("fields", []):
            if field.get("modes") and mode not in field["modes"]:
                continue
            key = field.get("record_key") if field.get("record_key") in record else field["field_id"]
            if key not in record:
                if field.get("default") is not None:
                    draft[field["field_id"]] = field["default"]
                elif field.get("control") == "grid":
                    draft[field["field_id"]] = []
                continue
            value = record[key]
            if field.get("control") == "grid" and isinstance(value, list):
                rows = []
                for index, row in enumerate(value):
                    if not isinstance(row, dict):
                        column = (field.get("columns") or [{"field_id": "value"}])[0]["field_id"]
                        rows.append({column: row, "_id": str(index)} if field.get("item_kind") == "string" else row)
                        continue
                    out = dict(row)
                    for column in field.get("columns", []):
                        source = column.get("record_key") if column.get("record_key") in row else column["field_id"]
                        if source in row:
                            out[column["field_id"]] = bool(row[source]) if column.get("record_truthy") else row[source]
                    out.setdefault("_id", str(index))
                    rows.append(out)
                value = rows
            elif field.get("record_truthy"):
                value = bool(value)
            draft[field["field_id"]] = value
    return draft


def form_field_ids(form: dict) -> set:
    return {f["field_id"] for tab in form.get("tabs", []) for f in tab.get("fields", [])}


__all__ = ("backend_draft", "diff_columns", "resolved_form", "active_fields", "field_visible", "form_field_ids", "record_draft")
