#!/usr/bin/env python3
"""Draft ui_descriptors/<engine>/forms/server.form.json from registration contracts.

Server registration forms do not come from the visual-administration catalog;
they come from providers/form_contracts.py (``server.define`` per profile).
This script reads those contracts for the beta engines and writes a draft
Server family form per engine, grouping fields onto the canonical tabs
(Connection, Authentication, SSL/TLS, Advanced, Engine, Tags). Profiles of one
engine (firebird-native, firebird-embedded) share one form behind a
``profile`` select. PostgreSQL's registration is legacy_preserved and is
transcribed by tools/draft_postgresql_descriptors.py instead; it is skipped
here. Re-run after a provider manifest changes its connection fields.

Usage: python3 tools/draft_server_descriptors.py [--write]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
DESCRIPTORS = REPO / "web" / "pgadmin" / "cdeadmin" / "ui_descriptors"
sys.path.insert(0, str(REPO / "web"))
if "pgadmin" not in sys.modules:
    package = ModuleType("pgadmin")
    package.__path__ = [str(REPO / "web" / "pgadmin")]
    sys.modules["pgadmin"] = package

from pgadmin.cdeadmin.endpoints.profiles import registration_profiles  # noqa: E402

ENGINES = ("mysql", "mariadb", "firebird", "duckdb", "sqlite",
           # Owner direction 2026-10-30: the parity engines are beta engines too.
           "dolt", "tidb", "vitess", "cockroachdb", "yugabytedb", "immudb", "xtdb")
# Registration keys of the servers API (web/pgadmin/browser/server_groups/servers) that are
# not provider contract fields. Everything else travels as cde_route_<id> / cde_secret_<id>.
GENERIC = {"name": "name", "host": "host", "port": "port", "username": "username", "password": "password",
           "save_password": "save_password", "database": "db", "connect_now": "connect_now", "bgcolor": "bgcolor",
           "fgcolor": "fgcolor", "comment": "comment", "tags": "tags"}
JSON_CONTROLS = {
    "attached_databases": {"control": "grid", "columns": [
        {"field_id": "name", "label": "Alias", "control": "text", "required": True},
        {"field_id": "database", "label": "Database file", "control": "file", "required": True}]},
    "config": {"control": "keyvalue", "help": "Connection configuration options passed to the engine as named scalar values."},
    # MySQL-wire JSON fields (Dolt, TiDB, Vitess): the typed controls of the MySQL server form. The
    # legacy JSON field sent '' when empty, which leaves the route key unset; empty_as_null keeps that
    # (the connector refuses an empty failover list; design open decision 20).
    "failover": {"empty_as_null": True, "label": "Failover endpoints", "control": "grid", "help": "Targets inherit connection settings unless overridden. Each protected password reference is scoped to this endpoint and owner. Provider-owned target pools are independent; native priority order and random choice among equal priorities apply.", "columns": [{"field_id": "host", "label": "Host", "control": "text"}, {"field_id": "port", "label": "Port", "control": "number", "min": 1, "max": 65535}, {"field_id": "unix_socket", "label": "Unix socket", "control": "text"}, {"field_id": "user", "label": "User", "control": "text"}, {"field_id": "database", "label": "Database", "control": "text"}, {"field_id": "priority", "label": "Priority", "control": "number", "min": 0, "max": 100}, {"field_id": "credential_reference_id", "label": "Password reference", "control": "reference", "reference_kind": "secret-reference"}, {"field_id": "credential_kind", "label": "Credential kind", "control": "select", "options": [{"value": "database_password", "label": "Registration password"}, {"value": "password", "label": "Protected account password"}]}, {"field_id": "pool_name", "label": "Pool name", "control": "text"}, {"field_id": "pool_size", "label": "Pool size", "control": "number", "min": 1, "max": 32}, {"field_id": "pool_reset_session", "label": "Reset session", "control": "boolean", "default": True}]},
    "tls_versions": {"empty_as_null": True, "label": "TLS versions", "control": "multiselect", "help": "", "options": [{"value": "TLSv1.2", "label": "TLSv1.2"}, {"value": "TLSv1.3", "label": "TLSv1.3"}]},
    "tls_ciphersuites": {"empty_as_null": True, "label": "TLS cipher suites", "control": "grid", "help": "", "item_kind": "string", "columns": [{"field_id": "value", "label": "Cipher suite", "control": "text"}]},
    "conn_attrs": {"empty_as_null": True, "label": "Connection attributes", "control": "keyvalue", "help": ""},
}
TITLE = {"mysql": "MySQL", "mariadb": "MariaDB", "firebird": "Firebird", "duckdb": "DuckDB", "sqlite": "SQLite",
         "dolt": "Dolt", "tidb": "TiDB", "vitess": "Vitess", "cockroachdb": "CockroachDB", "yugabytedb": "YugabyteDB",
         "immudb": "immudb", "xtdb": "XTDB"}
ORDER = ["Connection", "Authentication", "SSL/TLS", "Advanced", "Engine", "Tags"]
CONTROLS = {"text", "number", "boolean", "select", "multiselect", "radio", "password", "secret-reference",
            "code", "grid", "keyvalue", "privileges", "reference", "file"}
RULES = [
    (r"^(name|host|port|database|file|alias|read_only|connect_now|colour|service_expected_database|database_create_root|uri_mode|protocol)$", "Connection", None),
    (r"^(username|user|password|save_password|auth_plugin_list|trusted_auth|auth_plugin|role|key_data|client_library|use_pure)$", "Authentication", None),
    (r"ssl|tls|cert|cipher|wire_crypt|wire_compression|wire_config|ca_", "SSL/TLS", None),
    (r"^(timeout|dummy_packet_interval|statement_timeout_ms|session_idle_timeout_seconds|connect_timeout|tool_workspace|tool_timeout|allow_local_infile|allow_local_infile_in_path|busy_timeout|journal_mode)$", "Advanced", "Timeouts and utilities"),
    (r"^(charset|session_time_zone|no_linger|attachment_cache|parallel_workers|no_gc|no_db_triggers|dbkey_scope)", "Advanced", "Attachment"),
    (r"^transaction_", "Advanced", "Transaction defaults"),
    (r"decfloat|^trap_", "Advanced", "DECFLOAT"),
]


# Contract groups of the parity engines' registration fields (owner direction 2026-10-30).
# Shared wire options go to the canonical tabs; any other group is engine-specific and
# stays on the Engine tab under its own name.
GROUP_TABS = {
    "MySQL-wire authentication": ("Authentication", None), "PostgreSQL-wire authentication": ("Authentication", None),
    "XTDB authentication": ("Authentication", None), "CQL authentication": ("Authentication", None),
    "MySQL-wire TLS": ("SSL/TLS", None), "PostgreSQL-wire TLS": ("SSL/TLS", None), "XTDB TLS": ("SSL/TLS", None),
    "CQL TLS": ("SSL/TLS", None), "YugabyteDB YCQL TLS": ("SSL/TLS", None),
    "YugabyteDB identity verification": ("SSL/TLS", None),
    "MySQL-wire connection": ("Advanced", "Network"), "PostgreSQL-wire network": ("Advanced", "Network"),
    "XTDB network": ("Advanced", "Network"), "XTDB database": ("Connection", None),
    "XTDB timeouts": ("Advanced", "Timeouts"), "YugabyteDB YCQL timeouts": ("Advanced", "Timeouts"),
    "MySQL-wire session": ("Advanced", "Session"), "PostgreSQL-wire session": ("Advanced", "Session"),
    "XTDB session": ("Advanced", "Session"), "XTDB transactions": ("Advanced", "Session"),
    "YugabyteDB YCQL session": ("Advanced", "Session"), "YugabyteDB YCQL consistency": ("Advanced", "Session"),
    "CQL session and retry policy": ("Advanced", "Session"), "YugabyteDB YCQL protocol": ("Advanced", "Session"),
    "MySQL-wire pool": ("Advanced", "Connection pool"), "PostgreSQL-wire pool": ("Advanced", "Connection pool"),
    "XTDB pool": ("Advanced", "Connection pool"),
    "CQL topology and routing": ("Advanced", "Topology"), "YugabyteDB YCQL topology": ("Advanced", "Topology"),
}
PARITY_ENGINES = {"dolt", "tidb", "vitess", "cockroachdb", "yugabytedb", "immudb", "xtdb"}
# Contract fields a form does not offer, with the evidence; each becomes a gap of the form.
CONN_ATTRS = ("Not offered: any connection attribute makes the connection fail ('B' format requires "
              "0 <= number <= 255): the provider adds its own observer attribute to every MySQL "
              "Connector/Python connection, and the extra attribute exceeds the connector's limit. Live on "
              "the pinned demos, 2026-11-04; the legacy dialog sends it through the same path.")
COMPRESS = "Not offered: with protocol compression the connection hangs on the pinned {} demo (live, 2026-11-04)."
UNSUPPORTED = {
    ("dolt", "conn_attrs"): CONN_ATTRS, ("tidb", "conn_attrs"): CONN_ATTRS, ("vitess", "conn_attrs"): CONN_ATTRS,
    ("dolt", "compress"): COMPRESS.format("Dolt 1.86.6"), ("vitess", "compress"): COMPRESS.format("Vitess 23.0.3"),
}


def tab_group(field_id, contract_group=None, engine=None):
    for pattern, tab, group in RULES:
        if re.search(pattern, field_id):
            # The pattern rules were tuned for the first six engines; for a parity engine they
            # keep only the core connection and credential fields, and its contract group decides
            # the rest (an engine tool's TLS or timeout fields stay with that tool).
            if engine in PARITY_ENGINES and contract_group and tab not in ("Connection", "Authentication"):
                break
            return tab, group
    if engine in PARITY_ENGINES and contract_group:
        return GROUP_TABS.get(contract_group, ("Engine", contract_group))
    return "Engine", None


def draft(engine, profiles):
    fields, seen, gaps = [], set(), []
    contract_database = None
    for profile in profiles:
        pid = profile["profile_id"]
        for field in profile["form_contract"]["server"]["forms"]["define"].get("fields", []):
            fid = field["field_id"]
            if fid in seen:
                continue
            if (engine, fid) in UNSUPPORTED:
                seen.add(fid)
                gaps.append({"concept": f"server.{fid}", "reason": UNSUPPORTED[(engine, fid)]})
                continue
            if fid == "database" and profile.get("route_kind") == "network":
                # The servers API writes its generic database (db) into the route on create and
                # on every edit, overwriting a contract database field (XTDB). Use the generic
                # field and keep the contract's wording, default and requirement.
                contract_database = field
                continue
            seen.add(fid)
            tab, group = tab_group(fid, field.get("group"), engine)
            out = {"field_id": fid, "label": field.get("label") or fid, "tab": tab, "control": field.get("control", "text")}
            if out["control"] == "multiline":
                out["control"], out["language"] = "code", "text"
            if out["control"] == "json" and fid in JSON_CONTROLS:
                out.update(JSON_CONTROLS[fid])
            if out["control"] not in CONTROLS:
                gaps.append({"concept": f"server.{fid}", "reason": f"provider control {out['control']!r} needs a typed control"})
                out["control"] = "text"
            contract_ids = {f["field_id"] for f in profile.get("connection_fields", [])}
            secret_ids = {f["field_id"] for f in profile.get("secret_fields", [])}
            if fid in contract_ids:
                out["backend_field_id"] = f"cde_route_{fid}"
            elif fid in secret_ids:
                out["backend_field_id"] = f"cde_secret_{fid}"
            else:
                out["backend_field_id"] = GENERIC.get(fid, fid)
            if group:
                out["group"] = group
            for key in ("required", "options", "default", "help"):
                if field.get(key) not in (None, "", []):
                    out[key] = field[key]
            if field.get("help_text") and "help" not in out:
                out["help"] = field["help_text"]
            if "minimum" in field:
                out["min"] = field["minimum"]
            if "maximum" in field:
                out["max"] = field["maximum"]
            visible = field.get("visible_when")
            if isinstance(visible, dict) and visible.get("field_id"):
                out["visible_when"] = {"field": visible["field_id"], **{k: visible[k] for k in ("equals", "in", "truthy") if k in visible}}
            others = {f["field_id"] for other in profiles if other is not profile
                      for f in other["form_contract"]["server"]["forms"]["define"].get("fields", [])}
            if len(profiles) > 1 and fid not in others and "visible_when" not in out:
                out["visible_when"] = {"field": "profile", "equals": pid}
            fields.append(out)
    embedded = all(p.get("route_kind") == "embedded_file" for p in profiles)
    network = all(p.get("route_kind") == "network" for p in profiles)
    database = {"field_id": "database", "tab": "Connection", "backend_field_id": "db",
                "label": "Database file" if embedded else "Maintenance database",
                "control": "file" if embedded else "text", "required": embedded,
                "help": ("Absolute path of the database file this profile opens; further files are registered as databases under it."
                         if embedded else "Database the profile connects to first; leave empty for the engine default.")}
    if not network and not embedded:  # mixed profiles (Firebird): file path for the embedded kind only
        database.update({"label": "Database file", "control": "file", "required": True,
                         "visible_when": {"field": "profile", "equals": next(p["profile_id"] for p in profiles if p.get("route_kind") == "embedded_file")}})
    if contract_database:
        database.update({key: contract_database[key] for key in ("label", "default", "required", "help")
                         if contract_database.get(key) not in (None, "", [])})
        if contract_database.get("help_text") and "help" not in contract_database:
            database["help"] = contract_database["help_text"]
    fields.append(database)
    fields.extend([
        {"field_id": "connect_now", "label": "Connect now", "tab": "Connection", "control": "boolean", "default": True, "backend_field_id": "connect_now"},
        {"field_id": "comment", "label": "Comments", "tab": "Connection", "control": "code", "language": "text", "backend_field_id": "comment"},
        {"field_id": "bgcolor", "label": "Background colour", "tab": "Tags", "control": "text", "backend_field_id": "bgcolor",
         "help": "Hex colour shown behind the server node; also tints the query tool."},
        {"field_id": "fgcolor", "label": "Foreground colour", "tab": "Tags", "control": "text", "backend_field_id": "fgcolor"},
        {"field_id": "tags", "label": "Tags", "tab": "Tags", "control": "grid", "backend_field_id": "tags", "columns": [
            {"field_id": "text", "label": "Tag", "control": "text", "required": True},
            {"field_id": "color", "label": "Colour", "control": "text"}]},
    ])
    if len(profiles) > 1:
        fields.insert(0, {"field_id": "profile", "label": "Connection kind", "tab": "Connection", "control": "select", "required": True,
                          "options": [{"value": p["profile_id"], "label": p["profile_id"].replace(f"{engine}-", "").capitalize()} for p in profiles]})
    fields.sort(key=lambda f: ORDER.index(f["tab"]))
    omitted = [] if not embedded else [
        {"tab": "Authentication", "reason": "embedded file engine: no credentials"},
        {"tab": "SSL/TLS", "reason": "embedded file engine: no network transport"}]
    return {
        "schema": "cdeadmin.ui-form.v1", "engine": engine, "family": "server", "resource_kinds": ["server"],
        "status": "draft", "engine_tab_title": TITLE[engine], "omitted_tabs": omitted, "gaps": gaps, "fields": fields,
        "notes": "Drafted by tools/draft_server_descriptors.py from providers/form_contracts.py server.define for "
                 + ", ".join(p["profile_id"] for p in profiles)
                 + ". Field ids are the registration contract's own; backend_field_id is the servers API key "
                   "(cde_route_<id> / cde_secret_<id> for contract fields). Review tab/group placement.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--engine", action="append", help="limit to these engines (default: all but mysql, owned by its stream)")
    args = parser.parse_args()
    selected = tuple(args.engine) if args.engine else tuple(e for e in ENGINES if e != "mysql")
    by_engine = {}
    for profile in registration_profiles():
        if profile["engine_id"] in selected:
            by_engine.setdefault(profile["engine_id"], []).append(profile)
    for engine, profiles in by_engine.items():
        form = draft(engine, profiles)
        path = DESCRIPTORS / engine / "forms" / "server.form.json"
        existing = json.loads(path.read_text()) if path.exists() else {}
        if existing.get("status") == "complete":
            print(f"{engine}: server form complete, left alone")
            continue
        counts = {tab: sum(1 for f in form["fields"] if f["tab"] == tab) for tab in ORDER}
        print(f"{engine}: {len(form['fields'])} fields {counts}")
        if args.write:
            path.write_text(json.dumps(form, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
