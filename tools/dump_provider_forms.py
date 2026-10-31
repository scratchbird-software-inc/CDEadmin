#!/usr/bin/env python3
"""Dump the effective visual-administration forms a provider sends to the UI.

Runs each relational provider's ``visual_admin_catalog`` adaptation over the
portfolio catalog, exactly as ``ProviderVisualAdministration._catalog`` does,
and writes one JSON document per engine with every resource kind, operation,
and the form fields (control, required, options, array/object editors) the
browser would receive. This is the source material for populating
``web/pgadmin/cdeadmin/ui_descriptors/<engine>/`` (see its README.md).

Usage:
    python3 tools/dump_provider_forms.py --out /tmp/forms [--engine firebird]

The dump is read-only: no database connection is opened.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "web"))
if "pgadmin" not in sys.modules:
    # Import the provider packages without the Flask application module,
    # the same way the tools/*_gate.py scripts do.
    package = ModuleType("pgadmin")
    package.__path__ = [str(REPO / "web" / "pgadmin")]
    sys.modules["pgadmin"] = package

from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine  # noqa: E402
from pgadmin.cdeadmin.visual_admin.experience import enrich_engine_experience  # noqa: E402


def administrations():
    """Return engine_id -> RelationalAdministration for the relational providers."""
    found = {}
    from pgadmin.cdeadmin.providers.mysql_family import provider as mysql
    found["mysql"] = mysql.MYSQL_ADMINISTRATION
    found["mariadb"] = mysql.MARIADB_ADMINISTRATION
    from pgadmin.cdeadmin.providers.firebird import provider as firebird
    found["firebird"] = firebird.ADMINISTRATION
    from pgadmin.cdeadmin.providers.sqlite import provider as sqlite
    found["sqlite"] = sqlite.ADMINISTRATION
    from pgadmin.cdeadmin.providers.duckdb import provider as duckdb
    found["duckdb"] = duckdb.ADMINISTRATION
    # MySQL-wire engines brought to full parity (owner direction 2026-10-29).
    from pgadmin.cdeadmin.providers.dolt import provider as dolt
    found["dolt"] = dolt.ADMINISTRATION
    from pgadmin.cdeadmin.providers.tidb import provider as tidb
    found["tidb"] = tidb.ADMINISTRATION
    from pgadmin.cdeadmin.providers.vitess import provider as vitess
    found["vitess"] = vitess.ADMINISTRATION
    # PostgreSQL-wire engines brought to full parity (same direction).
    from pgadmin.cdeadmin.providers.cockroachdb import provider as cockroachdb
    found["cockroachdb"] = cockroachdb.ADMINISTRATION
    from pgadmin.cdeadmin.providers.yugabytedb import provider as yugabytedb
    found["yugabytedb"] = yugabytedb.ADMINISTRATION
    from pgadmin.cdeadmin.providers.immudb import provider as immudb
    found["immudb"] = immudb.ADMINISTRATION
    # XTDB has no relational administration: its client adapts the catalog.
    found["xtdb"] = ClientCatalog("xtdb")
    return found


class ClientCatalog:
    """A client-adapted catalog, keeping the operations the client runs."""

    def __init__(self, engine_id):
        from pgadmin.cdeadmin.providers.xtdb.client import XTDBClient
        self.client = {"xtdb": XTDBClient}[engine_id]()

    def catalog(self, catalog):
        adapted = self.client.visual_admin_catalog(catalog)
        for resource in adapted.get("objects", []):
            resource["operations"] = [
                operation for operation in resource.get("operations", [])
                if self.client.supports_admin_operation(
                    resource["resource_kind"], operation["operation_id"])]
        return adapted


def compact_field(field):
    keep = {}
    for key in ("field_id", "label", "control", "required", "help", "help_text", "default",
                "options", "option_values_path", "visible_when", "initial_value_path",
                "array_editor", "object_editor", "sensitive", "placeholder", "min", "max"):
        if key in field and field[key] not in (None, "", [], {}):
            keep[key] = field[key]
    if "array_editor" in keep:
        editor = keep["array_editor"]
        if isinstance(editor, dict) and "fields" in editor:
            keep["array_editor"] = {**editor, "fields": [compact_field(f) for f in editor["fields"]]}
    if "object_editor" in keep:
        editor = keep["object_editor"]
        if isinstance(editor, dict) and "fields" in editor:
            keep["object_editor"] = {**editor, "fields": [compact_field(f) for f in editor["fields"]]}
    return keep


def dump_engine(engine_id, administration):
    base = catalog_for_engine(engine_id)
    adapted = administration.catalog(copy.deepcopy(base))
    catalog = enrich_engine_experience(adapted)
    out = {"engine": engine_id, "kinds": []}
    for resource in catalog.get("objects", []):
        kind = {
            "resource_kind": resource["resource_kind"],
            "title": resource.get("title"),
            "navigator": resource.get("navigator"),
            "editor": resource.get("editor"),
            "parent_kinds": resource.get("parent_kinds"),
            "operations": [],
        }
        for operation in resource.get("operations", []):
            form = operation.get("form") or {}
            kind["operations"].append({
                "operation_id": operation["operation_id"],
                "title": operation.get("title"),
                "mutation_class": operation.get("mutation_class"),
                "target_required": operation.get("target_required"),
                "confirmation_required": operation.get("confirmation_required"),
                "workspace_scope": operation.get("workspace_scope"),
                "form_id": form.get("form_id"),
                "form_title": form.get("title"),
                "fields": [compact_field(f) for f in form.get("fields", [])],
            })
        out["kinds"].append(kind)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--engine", action="append")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    admins = administrations()
    for engine_id, administration in admins.items():
        if args.engine and engine_id not in args.engine:
            continue
        doc = dump_engine(engine_id, administration)
        path = args.out / f"{engine_id}.forms.json"
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str))
        kinds = len(doc["kinds"])
        ops = sum(len(k["operations"]) for k in doc["kinds"])
        fields = sum(len(o["fields"]) for k in doc["kinds"] for o in k["operations"])
        print(f"{engine_id:9s} kinds={kinds:3d} operations={ops:4d} fields={fields:5d} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
