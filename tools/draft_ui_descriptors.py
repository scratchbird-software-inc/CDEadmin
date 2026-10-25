#!/usr/bin/env python3
"""Draft ui_descriptors for an engine from its effective provider forms.

Reads the dump produced by ``tools/dump_provider_forms.py`` and writes a first
draft of ``ui_descriptors/<engine>/forms/<family>.form.json``,
``operations.json`` and ``capabilities.json`` with every field id, label,
option list and visibility rule taken from the provider, so plan/validate/apply
keep receiving the names they already accept. The draft does three mechanical
things the design requires and nothing more:

* places each field on a canonical tab of its family (by field id; unknown
  fields land on the Engine tab, never dropped);
* replaces the ``json`` control: an array editor becomes a ``grid`` with the
  editor's fields as columns, an object editor becomes a one-row grid, and a
  bare JSON box becomes ``keyvalue`` and is recorded under ``gaps`` as
  "typed_from_json" so an engine stream finishes typing it;
* classifies non-lifecycle operations as tier 2 or 3 and gives them a menu
  category.

Forms come out as ``status: draft``. Human/agent review per engine is still
required before ``complete`` (README step 7). The script is idempotent and
overwrites only the files it generates; ``navigator.json`` and
``omitted_families.json`` are left alone.

Usage:
    python3 tools/dump_provider_forms.py --out /tmp/forms
    python3 tools/draft_ui_descriptors.py --forms /tmp/forms --engine firebird [--write]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESCRIPTORS = REPO / "web" / "pgadmin" / "cdeadmin" / "ui_descriptors"

LIFECYCLE = {"inspect", "create", "alter", "drop", "rename", "comment", "insert", "update", "delete",
             "truncate", "grant", "revoke", "create_or_alter", "recreate", "define", "connect", "edit", "remove"}
TIER3_WORDS = re.compile(r"backup|restore|dump|replay|clone|export_database|import_database|shutdown|bring_online|"
                         r"upgrade|validate_database|repair_database|sweep|statistics|fixup|recover|archive", re.I)
MENU = [
    (re.compile(r"backup|restore|dump|export_database|import_database|clone|archive|replay", re.I), "backup_restore"),
    (re.compile(r"replica|replication|binlog|binary_log|gtid|slave|master|channel|group", re.I), "replication"),
    (re.compile(r"grant|revoke|privilege|password|mapping|admin_|security|secret|keyring|master_key|tls|masking|user", re.I), "security"),
    (re.compile(r"check|verify|validate|integrity|statistics|inspect|limbo|explain|diagnos|histogram|checksum|analyze", re.I), "diagnostics"),
    (re.compile(r".", re.I), "maintenance"),
]
ENGINE_TITLE = {"postgresql": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB", "firebird": "Firebird",
                "duckdb": "DuckDB", "sqlite": "SQLite"}
# field id (regex) -> tab, evaluated in order, per family. Unmatched -> Engine.
GENERAL = r"^(name|parent|database|schema|owner|comment|description|if_not_exists|or_replace|temporary|table_type|"\
          r"on_commit|external_file|materialized|table|routine_kind|returns|language|scope|timing|events|active|"\
          r"position|granularity|when|columns_of|start|increment|minimum|maximum|cycle|cache|current|current_value|"\
          r"restart|restart_initial|type_kind|base_type|data_type|length|precision|scale|default|not_null|host|"\
          r"role_kind|password|plugin|auth_method|authentication_mode|authentication_string|valid_until|"\
          r"password_expiration|password_expiration_days|account_lock|connection_limit|first_name|middle_name|"\
          r"last_name|database_path|template|unique|where|condition|message|clear_description|clear_comment|"\
          r"definer_user|definer_host|schedule|enabled|status|completion|time_zone|preserve|character_set_name)$"
TAB_RULES = {
    "table": [(GENERAL, "General"), (r"^columns$", "Columns"), (r"constraint|primary_key|foreign_key|unique_|check", "Constraints"),
              (r"partition", "Partitions"), (r"^(tablespace|fillfactor|character_set|collation|sql_security|row_format)$", "Options"),
              (r"privilege|grant", "Security")],
    "view": [(GENERAL, "General"), (r"^(query|definition|body|declaration)$", "Definition"), (r"^columns$", "Columns"),
             (r"^(check_option|security_barrier|security_invoker|sql_security|algorithm|with_data|definer)$", "Options"),
             (r"privilege|grant", "Security")],
    "index": [(GENERAL, "General"), (r"^(columns|expression|direction|include_columns)$", "General"),
              (r"^(method|index_kind|include|fillfactor|concurrent|tablespace|using)$", "Options")],
    "routine": [(GENERAL, "General"), (r"^(parameters|return_parameters|arguments|argument)", "Parameters"),
                (r"^(body|header|definition|declaration|source|expression|specification)$", "Definition"),
                (r"^(sql_security|deterministic|data_access|volatility|strict|parallel|cost|rows|leakproof|security|"
                 r"table_macro|return_type|return_mode|return_data_type|return_length|return_mechanism)$", "Options"),
                (r"privilege|grant", "Security")],
    "trigger": [(GENERAL, "General"), (r"^(body|definition|declaration|function|tfunction|arguments)$", "Definition"),
                (r"^(deferrable|constraint_trigger|initially_deferred)$", "Options")],
    "sequence": [(GENERAL, "General"), (r"^(start|increment|minimum|maximum|cycle|cache|restart|current)", "General"),
                 (r"privilege|grant", "Security")],
    "type": [(GENERAL, "General"), (r"^(check|constraints|drop_constraint|enum_values|fields|members)$", "Constraints" ),
             (r"privilege|grant", "Security")],
    "role": [(GENERAL, "General"), (r"^(max_|tls_|x509)", "General"), (r"^(members|member|member_kind|default_role|admin_option|admin_option_only|grantor|is_default|mode)$", "Membership"),
             (r"privilege|system_privileges|administrator|admin_role|ddl_|object_type|object_name|principal|grantees|grant_option|update_columns|reference_columns", "Privileges")],
    "database": [(GENERAL, "General"), (r"^(character_set|default_charset|encoding|collation|default_collation|locale|page_size|sql_dialect|read_only|encryption|tablespace|"
                 r"forced_writes|reserve_space|stored_page_buffers|sweep_interval|linger_seconds|drop_linger|default_sql_security|journal_mode|synchronous|auto_vacuum|"
                 r"application_id|user_version|datconnlimit|is_template|datallowconn)$", "Options"),
                 (r"^(config|variables|parameters)$", "Parameters"), (r"privilege|grant", "Security")],
    "server": [(r"^(name|group|host|port|database|file|alias|read_only|connect_now|colour|service|protocol|uri_mode)$", "Connection"),
               (r"^(user|username|password|save_password|auth|role|tunnel|ssh|wire_crypt|plugin|key_data|client_library)", "Authentication"),
               (r"ssl|tls|cert|cipher|ca_", "SSL/TLS"),
               (r"timeout|tool_|workspace|allow_local_infile|use_pure|busy|journal|decfloat|transaction|parallel|page_cache|charset|session|time_zone|config", "Advanced")],
}
TAB_ORDER = {}
for _fam in TAB_RULES:
    TAB_ORDER[_fam] = json.loads((DESCRIPTORS / "families" / f"{_fam}.family.json").read_text())
TAB_ORDER = {fam: [t["tab"] for t in doc["tabs"]] for fam, doc in TAB_ORDER.items()}
BODY_IDS = re.compile(r"^(body|query|definition|declaration|source|expression|header|specification|sql|script|statement|check|condition|when|sql_text|ddl)$")
DERIVED_ALTER = {"add_columns", "drop_columns", "rename_columns", "alter_columns"}
ROLE_GROUPS = [(re.compile(r"^max_"), "Limits"), (re.compile(r"^(tls_|x509)"), "TLS"), (re.compile(r"password|auth|plugin|account_lock"), "Authentication")]


def tab_for(family, field_id):
    for pattern, tab in TAB_RULES.get(family, []):
        if re.search(pattern, field_id):
            if tab in TAB_ORDER[family]:
                return tab
    return "Engine" if "Engine" in TAB_ORDER[family] else TAB_ORDER[family][0]


def convert_control(field, gaps, context):
    control = field.get("control")
    out = {}
    if control == "json":
        editor = field.get("array_editor") or field.get("object_editor")
        if editor and editor.get("fields"):
            out["control"] = "grid"
            out["columns"] = [convert_field(f, None, gaps, context, nested=True) for f in editor["fields"]]
            if field.get("object_editor"):
                out["help"] = (field.get("help") or "") + " (single record)"
        elif editor and editor.get("item_kind") in ("string", "text", "identifier"):
            out["control"] = "multiselect" if field.get("options") else "grid"
            if out["control"] == "grid":
                out["columns"] = [{"field_id": "value", "label": field.get("label", "Value"), "control": "text", "required": True}]
        else:
            out["control"] = "keyvalue"
            gaps.append({"concept": f"{context}.{field['field_id']}", "reason": "typed_from_json: provider accepts a JSON value with no editor; give it a typed control or grid", "tracking": "ui-unification"})
    elif control == "multiline":
        out["control"] = "code" if BODY_IDS.search(field["field_id"]) else "text"
        if out["control"] == "code":
            out["language"] = "sql"
    elif control == "code":
        out["control"] = "code"
        out["language"] = field.get("language", "sql")
    elif control in ("text", "number", "boolean", "select", "multiselect", "password", "secret-reference"):
        out["control"] = control
    else:
        out["control"] = "text"
        gaps.append({"concept": f"{context}.{field['field_id']}", "reason": f"unknown provider control {control!r}"})
    return out


def convert_field(field, tab, gaps, context, nested=False, modes=None):
    out = {"field_id": field["field_id"], "label": field.get("label") or field["field_id"].replace("_", " ").capitalize()}
    if tab:
        out["tab"] = tab
    out.update(convert_control(field, gaps, context))
    for key in ("required", "default", "options", "option_values_path", "placeholder", "min", "max"):
        if key in field and field[key] not in (None, ""):
            out[key] = field[key]
    helptext = field.get("help") or field.get("help_text")
    if helptext:
        out["help"] = helptext if "help" not in out else out["help"]
    vw = field.get("visible_when")
    if isinstance(vw, dict) and vw.get("field_id"):
        conv = {"field": vw["field_id"]}
        for key in ("equals", "in", "truthy"):
            if key in vw:
                conv[key] = vw[key]
        out["visible_when"] = conv
    if modes:
        out["modes"] = modes
    if re.search(r"\bexact native\b|\bnative .* reference\b", out["label"], re.I):
        out["label"] = re.sub(r"(?i)exact native\s*", "", out["label"]).strip().capitalize()
    return out


def draft_family_form(engine, family, kinds, dump_kinds, existing):
    by_kind = {k["resource_kind"]: k for k in dump_kinds}
    fields, seen, gaps, notes = [], set(), [], []
    derived, variant_fields = set(), 0
    primary = kinds[0]["resource_kind"]
    for kind in kinds:
        dk = by_kind.get(kind["resource_kind"])
        if not dk:
            notes.append(f"{kind['resource_kind']}: not present in provider dump")
            continue
        ops = {o["operation_id"]: o for o in dk["operations"]}
        base = ops.get("create") or ops.get("define") or ops.get("create_or_alter")
        alter = ops.get("alter") or ops.get("edit")
        prefix = "" if kind["resource_kind"] == primary else f"{kind.get('variant') or kind['resource_kind']}."
        for op, modes in ((base, None), (alter, ["alter"])):
            if not op:
                continue
            for field in op["fields"]:
                fid = field["field_id"]
                if fid in ("confirmation", "new_name", "cascade"):
                    continue
                if fid in DERIVED_ALTER:
                    derived.add(fid)
                    continue
                converted = convert_field(field, tab_for(family, fid), gaps, f"{kind['resource_kind']}.{op['operation_id']}", modes=modes)
                if prefix:
                    variant = kind.get("variant")
                    same = [f for f in fields if f["field_id"] == fid and f["control"] == converted["control"] and
                            (f.get("visible_when", {}).get("field") != "variant" or f["visible_when"].get("equals") == variant)]
                    if same:
                        continue  # shared with the primary kind or already listed for this variant
                    converted["group"] = kind.get("variant", kind["resource_kind"]).replace("_", " ").capitalize()
                    if kind.get("variant"):
                        converted["visible_when"] = converted.get("visible_when") or {"field": "variant", "equals": kind["variant"]}
                    variant_fields += 1
                elif fid in seen:
                    continue
                seen.add(fid)
                if family == "role" and converted.get("tab") == "General":
                    for pattern, group in ROLE_GROUPS:
                        if pattern.search(fid):
                            converted["group"] = group
                            break
                fields.append(converted)
        if not base:
            notes.append(f"{kind['resource_kind']}: provider exposes no create form ({', '.join(sorted(ops))})")
    order = {t: i for i, t in enumerate(TAB_ORDER[family])}
    fields.sort(key=lambda f: order.get(f.get("tab"), 99))
    if derived:
        notes.append("Alter-mode column changes (" + ", ".join(sorted(derived)) + ") are produced from the Columns grid diff; they are not separate fields.")
    if variant_fields and any(k.get("variant") for k in kinds):
        fields.insert(0, {"field_id": "variant", "label": "Variant", "tab": TAB_ORDER[family][0], "control": "select",
                          "options": [{"value": k.get("variant") or "default", "label": (k.get("variant") or "default").replace("_", " ").capitalize()} for k in kinds]})
    form = {
        "schema": "cdeadmin.ui-form.v1", "engine": engine, "family": family,
        "resource_kinds": [k["resource_kind"] for k in kinds],
        "status": "draft" if fields else "pending",
        "engine_tab_title": ENGINE_TITLE.get(engine, engine),
        "omitted_tabs": existing.get("omitted_tabs", []), "gaps": gaps, "fields": fields,
        "notes": "Drafted by tools/draft_ui_descriptors.py from the provider's effective create/alter forms; field ids, "
                 "options and visibility are the provider's own. Review tab placement, finish typing any keyvalue field "
                 "listed under gaps, split combined constraint grids, then set status complete after a verified round trip."
                 + ((" " + " ".join(notes)) if notes else ""),
    }
    return form


def draft_operations(engine, caps, dump_kinds, existing):
    tier1 = {k["resource_kind"]: {o["operation_id"] for o in k["operations"]} for k in caps["kinds"]}
    out = []
    kept = {(o["resource_kind"], o["operation_id"]): o for o in existing.get("operations", [])}
    from collections import Counter
    title_counts = Counter((op.get("form_title") or op.get("title") or "") for dk in dump_kinds for op in dk["operations"])
    for dk in dump_kinds:
        for op in dk["operations"]:
            oid = op["operation_id"]
            if oid in LIFECYCLE or oid in tier1.get(dk["resource_kind"], set()) and oid in LIFECYCLE:
                continue
            if oid == "inspect":
                continue
            key = (dk["resource_kind"], oid)
            if key in kept and kept[key].get("status") == "complete":
                out.append(kept[key])
                continue
            gaps = []
            fields = [convert_field(f, None, gaps, f"{dk['resource_kind']}.{oid}") for f in op["fields"] if f["field_id"] != "confirmation"]
            tier = 3 if (op.get("workspace_scope") == "server_service" or TIER3_WORDS.search(oid)) else 2
            category = next(cat for pat, cat in MENU if pat.search(oid))
            title = (op.get("form_title") or op.get("title") or "")
            title = re.sub(r"(?i)\b(mysql|mariadb|firebird|postgresql|duckdb|sqlite)\b\s*", "", title)
            title = re.sub(r"(?i)\s*native partitioning$|\s+with\s+-?\S*\s*[\d.]+$", "", title).strip()
            if not title or title_counts[title] > 1 or title.lower().startswith(("run ", "manage ")):
                title = oid.replace("_", " ")
            entry = {
                "operation_id": oid, "resource_kind": dk["resource_kind"], "title": title[0].upper() + title[1:],
                "menu": {"category": category}, "tier": tier, "status": "draft",
                "confirmation": "typed_name" if op.get("mutation_class") == "destructive" else ("confirm" if op.get("confirmation_required") else "none"),
                "fields": fields,
            }
            if tier == 3:
                entry["execution_host"] = True
                entry["produces_log"] = True
            if gaps:
                entry["notes"] = "typed_from_json: " + ", ".join(g["concept"] for g in gaps)
            out.append(entry)
    overrides = {("extension", "execute"): "Install or load extension", ("database", "integrity_check"): "Integrity check",
                 ("database", "quick_check"): "Quick check", ("session", "terminate_query"): "Terminate running query",
                 ("session", "terminate_connection"): "Terminate connection"}
    from collections import Counter
    final = Counter(o["title"] for o in out)
    for o in out:
        key = (o["resource_kind"], o["operation_id"])
        if key in overrides:
            o["title"] = overrides[key]
        elif final[o["title"]] > 1:
            o["title"] = o["operation_id"].replace("_", " ").capitalize()
    return {"schema": "cdeadmin.ui-operations.v1", "engine": engine, "operations": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forms", type=Path, required=True, help="folder written by dump_provider_forms.py")
    parser.add_argument("--engine", action="append", required=True)
    parser.add_argument("--write", action="store_true", help="write files (default: report only)")
    args = parser.parse_args()
    for engine in args.engine:
        dump = json.loads((args.forms / f"{engine}.forms.json").read_text())
        folder = DESCRIPTORS / engine
        caps = json.loads((folder / "capabilities.json").read_text())
        # refresh tier-1 operation lists from the dump without losing families/variants
        dump_ops = {k["resource_kind"]: k["operations"] for k in dump["kinds"]}
        known = {k["resource_kind"] for k in caps["kinds"]}
        for dk in dump["kinds"]:
            if dk["resource_kind"] not in known:
                # Seed list missed a provider kind: add it as an Engine object so
                # nothing the backend exposes is left without a UI entry.
                caps["kinds"].append({"resource_kind": dk["resource_kind"], "family": "engine_object",
                                      "title": dk.get("title") or dk["resource_kind"], "operations": []})
        for kind in caps["kinds"]:
            ops = dump_ops.get(kind["resource_kind"])
            if ops is None:
                continue
            kind["operations"] = [{"operation_id": o["operation_id"], "tier": 1, "mutation_class": o.get("mutation_class") or "write"}
                                  for o in ops if o["operation_id"] in LIFECYCLE]
        families = {}
        for kind in caps["kinds"]:
            if kind["family"] not in ("engine_object", "server"):
                # server registration forms come from providers/form_contracts.py, not the catalog
                families.setdefault(kind["family"], []).append(kind)
        report = []
        for family, kinds in families.items():
            path = folder / "forms" / f"{family}.form.json"
            existing = json.loads(path.read_text()) if path.exists() else {}
            if existing.get("status") == "complete":
                report.append(f"{family}: complete, left alone")
                continue
            form = draft_family_form(engine, family, kinds, dump["kinds"], existing)
            report.append(f"{family}: {len(form['fields'])} fields, {len(form['gaps'])} gaps -> {form['status']}")
            if args.write:
                path.write_text(json.dumps(form, indent=2, ensure_ascii=False) + "\n")
        ops_path = folder / "operations.json"
        existing_ops = json.loads(ops_path.read_text()) if ops_path.exists() else {}
        ops = draft_operations(engine, caps, dump["kinds"], existing_ops)
        report.append(f"operations: {len(ops['operations'])} (tier3={sum(1 for o in ops['operations'] if o['tier']==3)})")
        if args.write:
            ops_path.write_text(json.dumps(ops, indent=2, ensure_ascii=False) + "\n")
            (folder / "capabilities.json").write_text(json.dumps(caps, indent=2, ensure_ascii=False) + "\n")
        print(engine + ":\n  " + "\n  ".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
