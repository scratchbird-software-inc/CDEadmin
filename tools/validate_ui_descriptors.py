#!/usr/bin/env python3
"""Validate CDEadmin UI descriptors and report UI-unification lint counts.

Owning design: docs/en_US/ui_unified_design.rst (section 8, "Gates that fail
the build"). This script is the build gate for the descriptor layer under
web/pgadmin/cdeadmin/ui_descriptors/:

  * every descriptor file validates against its JSON Schema (a small built-in
    checker covers the subset of JSON Schema the schemas use; no dependency);
  * every engine form's tabs are a subset of its family skeleton, in skeleton
    order, and a form with status "complete" carries every tab the skeleton
    marks required unless the form lists it under omitted_tabs with a reason;
  * no form or operation field uses a control outside the allowed set (there
    is no "json" control);
  * labels do not carry provenance phrasing ("exact native ... reference");
  * every kind in capabilities.json that names a form points at a file that
    exists and edits that kind;
  * engine folders contain no unexpected files.

It also prints the repository lint counts the migration tracker records
(docs/en_US/ui_unification_status.rst): raw json controls in provider form
code, direct @mui imports in provider/dialog/cdeadmin_ui code, engine-literal
branches in shared UI code, and hand-written engine panels. Those counts are
reported, not enforced, until the phase that retires them is reached; pass
--enforce-counts with a JSON file of maximums to fail when a count grows.

Exit status 1 on any descriptor error; 0 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESCRIPTORS = REPO / "web" / "pgadmin" / "cdeadmin" / "ui_descriptors"
BETA_ENGINES = ("postgresql", "mysql", "mariadb", "firebird", "duckdb", "sqlite",
                # Owner direction 2026-10-30: the parity engines join beta as
                # their descriptor folders land.
                "dolt", "tidb", "vitess", "cockroachdb", "yugabytedb",
                "immudb", "xtdb")
FAMILIES = ("table", "view", "index", "routine", "trigger", "sequence", "type",
            "role", "database", "server")
FORBIDDEN_LABEL = re.compile(r"\bexact native\b|\bnative .* reference\b", re.I)
ENGINE_FILES = {"capabilities.json", "operations.json", "navigator.json",
                "omitted_families.json", "options.json", "tools.json", "security.json",
                "README.md"}
IGNORED_FOLDERS = {"forms", "__pycache__"}


# --------------------------------------------------------------------------
# Minimal JSON Schema checker (subset: type, enum, const, required,
# properties, additionalProperties, items, minItems, pattern, $ref within the
# loaded schema set, anyOf-free).
# --------------------------------------------------------------------------
class SchemaSet:
    def __init__(self, folder: Path):
        self.schemas = {}
        for path in sorted(folder.glob("*.json")):
            doc = json.loads(path.read_text())
            self.schemas[path.name] = doc
            if "$id" in doc:
                self.schemas[doc["$id"]] = doc

    def resolve(self, ref: str, current: dict) -> dict:
        if ref.startswith("#/"):
            node = current
        else:
            name, _, frag = ref.partition("#")
            node = self.schemas[name]
            ref = "#" + frag if frag else "#"
            current = node
        for part in ref.lstrip("#/").split("/"):
            if part:
                node = node[part]
        return node

    def check(self, value, schema: dict, root: dict, path: str, errors: list):
        if "$ref" in schema:
            target_root = root
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                target_root = self.schemas[ref.partition("#")[0]]
            self.check(value, self.resolve(ref, root), target_root, path, errors)
            return
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected {schema['const']!r}")
            return
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} not one of {schema['enum']}")
            return
        expected = schema.get("type")
        if expected:
            ok = {
                "object": isinstance(value, dict),
                "array": isinstance(value, list),
                "string": isinstance(value, str),
                "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "boolean": isinstance(value, bool),
            }[expected]
            if not ok:
                errors.append(f"{path}: expected {expected}")
                return
        if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"{path}: missing required {key!r}")
            props = schema.get("properties", {})
            extra = schema.get("additionalProperties", True)
            for key, item in value.items():
                if key in props:
                    self.check(item, props[key], root, f"{path}.{key}", errors)
                elif extra is False:
                    errors.append(f"{path}: unexpected key {key!r}")
                elif isinstance(extra, dict):
                    self.check(item, extra, root, f"{path}.{key}", errors)
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: needs at least {schema['minItems']} items")
            if "items" in schema:
                for index, item in enumerate(value):
                    self.check(item, schema["items"], root, f"{path}[{index}]", errors)


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}")


def walk_fields(fields, prefix=""):
    for field in fields or []:
        yield prefix + field.get("field_id", "?"), field
        yield from walk_fields(field.get("columns"), prefix + field.get("field_id", "?") + ".")


# --------------------------------------------------------------------------
# Descriptor validation
# --------------------------------------------------------------------------
def check_security_descriptor(engine, engine_dir, caps, schemas, errors):
    """Validate security.json and resolve every reference it makes (Decision 21).

    The file only names kinds, form fields and option keys that other
    descriptors own, so each name must resolve in this engine's own folder.
    """
    rel = f"{engine}/security.json"
    doc = load(engine_dir / "security.json")
    schemas.check(doc, schemas.schemas["security.schema.json"], schemas.schemas["security.schema.json"], rel, errors)
    if doc.get("engine") != engine:
        errors.append(f"{rel}: engine {doc.get('engine')!r} does not match its folder")
    kinds = {k["resource_kind"]: k for k in caps.get("kinds", [])}
    principals = doc.get("principals", [])
    if not principals:
        if not doc.get("reason"):
            errors.append(f"{rel}: an empty principals list needs a reason")
        for extra in ("membership", "grants"):
            if extra in doc:
                errors.append(f"{rel}: {extra} is declared but the engine has no principals")
        return
    if "status" not in doc:
        errors.append(f"{rel}: status (draft or complete) is required when principals are declared")
    options = load(engine_dir / "options.json") if (engine_dir / "options.json").exists() else {}
    dialect = options.get("dialect", {})
    seen = set()
    for principal in principals:
        kind = principal.get("kind")
        if kind in seen:
            errors.append(f"{rel}: principal kind {kind!r} is listed twice")
        seen.add(kind)
        entry = kinds.get(kind)
        if entry is None:
            errors.append(f"{rel}: principal kind {kind!r} is not in capabilities.json")
            continue
        if entry.get("family") != "role":
            errors.append(f"{rel}: principal kind {kind!r} belongs to family {entry.get('family')!r}, not 'role'")
        form_rel = entry.get("form")
        if not form_rel or not (engine_dir / form_rel).exists():
            errors.append(f"{rel}: principal kind {kind!r} has no editor form")
            continue
        fields = dict(walk_fields(load(engine_dir / form_rel).get("fields")))
        for fid in principal.get("identity", []):
            if fid not in fields:
                errors.append(f"{rel}: {kind} identity field {fid!r} is not in {form_rel}")
        variant = principal.get("variant")
        if variant:
            field = fields.get(variant["field_id"])
            values = {o.get("value") for o in (field or {}).get("options", [])}
            if field is None:
                errors.append(f"{rel}: {kind} variant field {variant['field_id']!r} is not in {form_rel}")
            elif variant["value"] not in values:
                errors.append(f"{rel}: {kind} variant value {variant['value']!r} is not an option of {variant['field_id']}")
    for principal in principals:
        target = (principal.get("roster") or {}).get("merged_into")
        if target is not None and (target not in seen or target == principal.get("kind")):
            errors.append(f"{rel}: {principal.get('kind')} roster is merged into {target!r}, which is not another declared principal")
        elif target is not None and any((p.get("roster") or {}).get("merged_into") for p in principals if p.get("kind") == target):
            errors.append(f"{rel}: {principal.get('kind')} roster is merged into {target!r}, which is itself merged")
        elif target is not None and next(p for p in principals if p.get("kind") == target).get("scope") != principal.get("scope"):
            errors.append(f"{rel}: {principal.get('kind')} roster is merged into {target!r} of another scope")
    membership = doc.get("membership")
    if membership and membership["kind"] not in seen:
        errors.append(f"{rel}: membership kind {membership['kind']!r} is not a declared principal")
    grants = doc.get("grants") or {}
    for key in ("grant_kind", "default_privileges"):
        if key in grants and grants[key] not in kinds:
            errors.append(f"{rel}: grants.{key} {grants[key]!r} is not in capabilities.json")
    grant_kind = kinds.get(grants.get("grant_kind"))
    if grant_kind is not None:
        ops = {o.get("operation_id") for o in grant_kind.get("operations", [])}
        for needed in ("grant", "revoke"):
            if needed not in ops:
                errors.append(f"{rel}: grant kind {grants['grant_kind']!r} declares no {needed} operation")
    dialog = grants.get("dialog")
    if dialog and grant_kind is not None:
        for op_id in ("grant", "revoke"):
            op = next((x for x in grant_kind.get("operations", []) if x.get("operation_id") == op_id), None)
            have = {f.get("field_id") for f in (op or {}).get("fields", [])}
            row = dialog.get("row") or {}
            wanted = [dialog.get("object_type"), dialog.get("object"), *dialog.get("qualifiers", []),
                      *(dialog.get("fixed") or {}), *(dialog.get("object_by_kind") or {}).values(),
                      row.get("grantee_kind_field"), row.get("grantee_field"), row.get("privileges_field"),
                      *[(row.get("grantee_grid") or {}).get("field")]]
            for field in wanted:
                if field and have and field not in have:
                    errors.append(f"{rel}: grants.dialog names field {field!r}, which the {op_id} operation does not declare")
    for key in ("system_privileges", "object_privileges", "grantable_kinds"):
        if key in grants and grants[key] not in dialect:
            errors.append(f"{rel}: grants.{key} reads dialect.{grants[key]} which options.json does not define")
    object_privileges = dialect.get(grants.get("object_privileges"), {})
    if grants and "status" not in grants:
        errors.append(f"{rel}: grants.status (draft or complete) is required when grants are declared")
    listing = grants.get("listing")
    if listing:
        ways = [key for key in ("object_field", "object_fields", "kinds") if listing.get(key)]
        if not ways:
            errors.append(f"{rel}: grants.listing needs object_field, object_fields or kinds")
        if len(ways) > 1:
            errors.append(f"{rel}: grants.listing declares both {' and '.join(ways)}")
        if listing.get("kinds") and not listing.get("scope_field"):
            errors.append(f"{rel}: grants.listing kinds needs scope_field")
        grantable_kinds = dialect.get(grants.get("grantable_kinds"), [])
        for kind_name in (listing.get("kinds") or {}):
            if kind_name not in grantable_kinds:
                errors.append(f"{rel}: grants.listing kind {kind_name!r} is not in grantable_kinds")
        membership_doc = doc.get("membership") or {}
        for key in ("listing", "member_of_listing"):
            if key in membership_doc and "native_field" not in membership_doc[key]:
                errors.append(f"{rel}: membership.{key} needs native_field")
        grantable = {name for names in object_privileges.values() for name in names}
        for code, name in (listing.get("privilege_codes") or {}).items():
            if name not in grantable:
                errors.append(f"{rel}: listing code {code!r} means {name!r}, which object_privileges does not list")
    for object_kind, privileges in (grants.get("column_privileges") or {}).items():
        allowed = set(object_privileges.get(object_kind, []))
        if object_kind not in object_privileges:
            errors.append(f"{rel}: column_privileges names object kind {object_kind!r} that object_privileges does not list")
        for privilege in privileges:
            if privilege not in allowed:
                errors.append(f"{rel}: column_privileges {object_kind}.{privilege} is not a grantable privilege")



def validate_descriptors(strict_pending: bool) -> tuple[list[str], dict]:
    errors: list[str] = []
    schemas = SchemaSet(DESCRIPTORS / "schema")
    summary = {"engines": {}, "families": []}
    form_refs_path = (
        REPO
        / "web"
        / "pgadmin"
        / "static"
        / "js"
        / "cdeadmin_ui"
        / "navigation"
        / "formReferences.json"
    )
    registered_form_refs = {
        entry["reference"]
        for entry in load(form_refs_path).get("forms", {}).values()
        if isinstance(entry, dict) and entry.get("reference")
    }
    seen_descriptor_form_refs: dict[str, str] = {}

    families = {}
    for path in sorted((DESCRIPTORS / "families").glob("*.family.json")):
        doc = load(path)
        schemas.check(doc, schemas.schemas["family.schema.json"], schemas.schemas["family.schema.json"],
                      str(path.relative_to(REPO)), errors)
        families[doc.get("family")] = doc
        summary["families"].append(doc.get("family"))
    for family in FAMILIES + ("engine_object",):
        if family not in families:
            errors.append(f"families/{family}.family.json is missing")

    for engine_dir in sorted(p for p in DESCRIPTORS.iterdir() if p.is_dir() and p.name not in ("schema", "families")
                             and not p.name.startswith("__") and (p / "capabilities.json").exists()):
        engine = engine_dir.name
        report = {"forms": {}, "operations": 0, "kinds": 0, "json_like_fields": 0}
        summary["engines"][engine] = report
        for stray in engine_dir.iterdir():
            if stray.is_file() and stray.name not in ENGINE_FILES:
                errors.append(f"{engine}: unexpected file {stray.name}")
            if stray.is_dir() and stray.name not in IGNORED_FOLDERS:
                errors.append(f"{engine}: unexpected folder {stray.name}")

        caps = load(engine_dir / "capabilities.json")
        schemas.check(caps, schemas.schemas["capabilities.schema.json"], schemas.schemas["capabilities.schema.json"],
                      f"{engine}/capabilities.json", errors)
        kinds_by_form = {}
        for kind in caps.get("kinds", []):
            report["kinds"] += 1
            form = kind.get("form")
            if form:
                kinds_by_form.setdefault(form, []).append(kind)
                if not (engine_dir / form).exists():
                    errors.append(f"{engine}/capabilities.json: kind {kind['resource_kind']} names missing {form}")

        ops = load(engine_dir / "operations.json")
        schemas.check(ops, schemas.schemas["operations.schema.json"], schemas.schemas["operations.schema.json"],
                      f"{engine}/operations.json", errors)
        known_kinds = {k["resource_kind"] for k in caps.get("kinds", [])}
        for op in ops.get("operations", []):
            report["operations"] += 1
            if op.get("resource_kind") not in known_kinds:
                errors.append(f"{engine}/operations.json: {op['operation_id']} targets unknown kind {op.get('resource_kind')!r}")
            if re.search(r"\b(mysql|mariadb|firebird|postgresql|duckdb|sqlite)\b", op.get("title", ""), re.I):
                errors.append(f"{engine}/operations.json: {op['operation_id']} label names the engine: {op['title']!r}")
            for fid, field in walk_fields(op.get("fields")):
                if FORBIDDEN_LABEL.search(field.get("label", "")):
                    errors.append(f"{engine}/operations.json: {op['operation_id']}.{fid} label uses provenance phrasing")

        if (engine_dir / "options.json").exists():
            options = load(engine_dir / "options.json")
            schemas.check(options, schemas.schemas["options.schema.json"], schemas.schemas["options.schema.json"],
                          f"{engine}/options.json", errors)
            # every option_values_path a form uses must have a source
            dialect_keys = set(options.get("dialect", {}))
            catalog_keys = set(options.get("catalog", {}))
            for form_path in sorted((engine_dir / "forms").glob("*.form.json")):
                for fid, field in walk_fields(load(form_path).get("fields")):
                    path = field.get("option_values_path") or []
                    if len(path) >= 2 and path[0] == "dialect" and path[1] not in dialect_keys:
                        errors.append(f"{engine}/forms/{form_path.name}: {fid} reads dialect.{path[1]} which options.json does not define")
                    if len(path) >= 2 and path[0] == "catalog" and path[1] not in catalog_keys:
                        errors.append(f"{engine}/forms/{form_path.name}: {fid} reads catalog.{path[1]} which options.json does not define")
        if (engine_dir / "tools.json").exists():
            tools_doc = load(engine_dir / "tools.json")
            schemas.check(tools_doc, schemas.schemas["tools.schema.json"], schemas.schemas["tools.schema.json"],
                          f"{engine}/tools.json", errors)
            seen_commands = set()
            for tool in tools_doc.get("tools", []):
                if tool["command_id"] in seen_commands:
                    errors.append(f"{engine}/tools.json: duplicate command_id {tool['command_id']!r}")
                seen_commands.add(tool["command_id"])
        if (engine_dir / "security.json").exists():
            check_security_descriptor(engine, engine_dir, caps, schemas, errors)
        nav = load(engine_dir / "navigator.json")
        schemas.check(nav, schemas.schemas["navigator.schema.json"], schemas.schemas["navigator.schema.json"],
                      f"{engine}/navigator.json", errors)

        omitted = set()
        if (engine_dir / "omitted_families.json").exists():
            omitted = {row["family"] for row in load(engine_dir / "omitted_families.json").get("omitted", [])}

        for form_path in sorted((engine_dir / "forms").glob("*.form.json")):
            rel = f"{engine}/forms/{form_path.name}"
            doc = load(form_path)
            schemas.check(doc, schemas.schemas["form.schema.json"], schemas.schemas["form.schema.json"], rel, errors)
            fref = doc.get("form_reference")
            if not fref:
                errors.append(
                    f"{rel}: missing required form_reference (SR-F registry)"
                )
            elif fref not in registered_form_refs:
                errors.append(
                    f"{rel}: form_reference {fref!r} is not in "
                    "formReferences.json"
                )
            elif fref in seen_descriptor_form_refs:
                errors.append(
                    f"{rel}: duplicate form_reference {fref!r} already used "
                    f"by {seen_descriptor_form_refs[fref]}"
                )
            else:
                seen_descriptor_form_refs[fref] = rel
            family = doc.get("family")
            if family == "engine_object":
                # Owner direction 2026-10-29 (decision 15): one form per kind.
                kinds = doc.get("resource_kinds") or []
                if len(kinds) != 1:
                    errors.append(
                        f"{rel}: an engine-object form edits exactly one "
                        "resource kind")
                key = f"engine_object:{kinds[0]}" if kinds else family
            else:
                key = family
            if key in report["forms"]:
                # The descriptor service serves one form per family (engine objects per kind);
                # a second form would silently replace the first. Variants share one form.
                errors.append(f"{rel}: a second {key!r} form; one form serves every variant of a family")
            report["forms"][key] = doc.get("status")
            skeleton = families.get(family)
            if not skeleton:
                errors.append(f"{rel}: unknown family {family!r}")
                continue
            if family in omitted:
                errors.append(f"{rel}: family is listed in omitted_families.json; delete one of them")
            skeleton_tabs = [t["tab"] for t in skeleton["tabs"]]
            required_tabs = [t["tab"] for t in skeleton["tabs"] if t.get("required")]
            used_tabs = []
            for fid, field in walk_fields(doc.get("fields")):
                tab = field.get("tab")
                if "." not in fid and tab is None:
                    errors.append(f"{rel}: field {fid} has no tab")
                if tab and tab not in skeleton_tabs:
                    errors.append(f"{rel}: field {fid} uses tab {tab!r} not in the {family} skeleton {skeleton_tabs}")
                if tab and tab not in used_tabs:
                    used_tabs.append(tab)
                if FORBIDDEN_LABEL.search(field.get("label", "")):
                    errors.append(f"{rel}: field {fid} label uses provenance phrasing: {field['label']!r}")
                if field.get("control") == "code" and not field.get("language"):
                    errors.append(f"{rel}: code field {fid} needs a language")
                if field.get("control") == "grid" and not field.get("columns"):
                    errors.append(f"{rel}: grid field {fid} needs columns")
            order = [skeleton_tabs.index(t) for t in used_tabs]
            if order != sorted(order):
                errors.append(f"{rel}: tabs appear out of skeleton order: {used_tabs}")
            omitted_tabs = {row["tab"] for row in doc.get("omitted_tabs", [])}
            if doc.get("status") == "complete" or (strict_pending and doc.get("status") == "draft"):
                for tab in required_tabs:
                    if tab in ("SQL",):
                        continue  # rendered by the shell from the provider plan
                    if tab not in used_tabs and tab not in omitted_tabs:
                        errors.append(f"{rel}: status {doc['status']} but required tab {tab!r} has no fields and is not in omitted_tabs")
            variant = next((field for field in doc.get("fields", []) if field.get("field_id") == "variant"), None)
            offered = {option.get("value") for option in (variant or {}).get("options", [])}
            for kind in kinds_by_form.get(f"forms/{form_path.name}", []):
                if kind["resource_kind"] not in doc.get("resource_kinds", []):
                    errors.append(f"{rel}: capabilities.json routes kind {kind['resource_kind']} here but resource_kinds does not list it")
                # The editor fixes a kind's declared variant (ProviderObjectEditorHost); one the
                # form does not offer would open the form on no variant's fields.
                if kind.get("variant") and variant is not None and kind["variant"] not in offered:
                    errors.append(f"{rel}: kind {kind['resource_kind']} declares variant {kind['variant']!r} "
                                  f"but the form's variant select offers {sorted(offered)}")
        for family in FAMILIES:
            has_kind = any(k["family"] == family for k in caps.get("kinds", []))
            if has_kind and family not in report["forms"] and family not in omitted:
                errors.append(f"{engine}: kinds use family {family} but forms/{family}.form.json is missing")
    return errors, summary


# --------------------------------------------------------------------------
# Repository lint counts (reported; enforced through --enforce-counts)
# --------------------------------------------------------------------------
def count_matches(paths, pattern: re.Pattern) -> tuple[int, Counter]:
    total, per_file = 0, Counter()
    for path in paths:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        found = len(pattern.findall(text))
        if found:
            total += found
            per_file[str(path.relative_to(REPO))] = found
    return total, per_file


def lint_counts() -> dict:
    web = REPO / "web" / "pgadmin"
    providers = list((web / "cdeadmin" / "providers").rglob("*.py"))
    ui_dirs = [web / "static" / "js" / "Dialogs", web / "static" / "js" / "cdeadmin_ui",
               web / "browser" / "static" / "js", web / "browser" / "server_groups" / "servers" / "static" / "js"]
    ui_files = [p for d in ui_dirs for p in d.rglob("*") if p.suffix in (".js", ".jsx", ".ts", ".tsx")]
    json_controls, json_files = count_matches(providers, re.compile(r"['\"]json['\"]\s*[,)]"))
    mui_imports, mui_files = count_matches(ui_files, re.compile(r"from\s+['\"]@mui/"))
    engine_branches, branch_files = count_matches(
        ui_files, re.compile(r"(?:engine_id|profile_id|languageProfile|cde_engine_id|cde_profile_id)\s*===?\s*['\"]"))
    # Decision 21 (2026-11-25): the ``engine`` / ``engineId`` props and
    # ``isMysql*``-style helpers are engine branches too; the pattern above
    # only sees ``engine_id`` / ``profile_id`` style identifiers.
    prop_branches, prop_files = count_matches(
        ui_files,
        re.compile(
            r"(?<![A-Za-z_.])(?:engine|engineId)\s*[!=]==?\s*['\"]"
            r"|\[(?:\s*['\"][a-z0-9_]+['\"]\s*,?)+\]\.includes\(\s*(?:engine|engineId)\s*\)"
            r"|\bconst\s+is(?:Mysql|MysqlFamily|UnifiedRoleEngine|Firebird|Postgres\w*)\b"))
    security_prop_branches = sum(
        n for name, n in prop_files.items() if "/cdeadmin_ui/security/" in name)
    context_menu = web / "cdeadmin" / "context_menu.py"
    menu_branches, _menu_files = count_matches(
        [context_menu], re.compile(r"\bengine_id\s*(?:==|in)\s*[\('\"]")) if context_menu.exists() else (0, Counter())
    dialogs = web / "static" / "js" / "Dialogs"
    panels = sorted(p.name for p in dialogs.glob("*.jsx")
                    if re.match(r"(Firebird|MySQL|MariaDB|DuckDB|SQLite|Postgresql)", p.name))
    shared = {
        "ProviderWorkspaceContent.jsx": len((dialogs / "ProviderWorkspaceContent.jsx").read_text().splitlines())
        if (dialogs / "ProviderWorkspaceContent.jsx").exists() else 0,
        "relational_admin.py": len((web / "cdeadmin" / "providers" / "relational_admin.py").read_text().splitlines())
        if (web / "cdeadmin" / "providers" / "relational_admin.py").exists() else 0,
    }
    return {
        "json_controls_in_provider_forms": json_controls,
        "json_controls_top_files": json_files.most_common(8),
        "mui_imports_in_ui_code": mui_imports,
        "mui_imports_top_files": mui_files.most_common(8),
        "engine_literal_branches_in_ui_code": engine_branches,
        "engine_branch_top_files": branch_files.most_common(8),
        "engine_prop_branches_in_ui_code": prop_branches,
        "engine_prop_branch_top_files": prop_files.most_common(8),
        "security_ui_engine_branches": security_prop_branches,
        "engine_panels_in_dialogs": len(panels),
        "engine_branches_in_context_menu": menu_branches,
        "shared_monolith_lines": shared,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict-pending", action="store_true",
                        help="also require draft forms to carry every required tab")
    parser.add_argument("--counts", action="store_true", help="print repository lint counts")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--enforce-counts", type=Path, metavar="MAXIMUMS.json",
                        help="fail when any lint count exceeds the maximum recorded in this file")
    args = parser.parse_args()

    errors, summary = validate_descriptors(args.strict_pending)
    counts = lint_counts() if (args.counts or args.enforce_counts) else None
    if args.enforce_counts:
        maxima = json.loads(args.enforce_counts.read_text())
        for key, limit in maxima.items():
            if isinstance(counts.get(key), int) and counts[key] > limit:
                errors.append(f"lint count {key}={counts[key]} exceeds recorded maximum {limit}")

    if args.json:
        print(json.dumps({"errors": errors, "summary": summary, "counts": counts}, indent=2))
    else:
        for engine, report in summary["engines"].items():
            forms = ", ".join(f"{k}:{v}" for k, v in sorted(report["forms"].items())) or "-"
            print(f"{engine:11s} kinds={report['kinds']:3d} operations={report['operations']:3d}  forms[{forms}]")
        if counts:
            print("\nlint counts (recorded in docs/en_US/ui_unification_status.rst):")
            for key in ("json_controls_in_provider_forms", "mui_imports_in_ui_code",
                        "engine_literal_branches_in_ui_code",
                        "engine_prop_branches_in_ui_code",
                        "security_ui_engine_branches", "engine_panels_in_dialogs",
                        "engine_branches_in_context_menu"):
                print(f"  {key:40s} {counts[key]}")
            for key, lines in counts["shared_monolith_lines"].items():
                print(f"  {key:40s} {lines} lines")
        if errors:
            print(f"\n{len(errors)} descriptor error(s):", file=sys.stderr)
            for line in errors:
                print("  " + line, file=sys.stderr)
        else:
            print("\nui descriptors: OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
