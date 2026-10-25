#!/usr/bin/env python3
"""Draft ui_descriptors/<engine>/forms/server.form.json from registration contracts.

Server registration forms do not come from the visual-administration catalog;
they come from providers/form_contracts.py (``server.define`` per profile).
This script reads those contracts for the six beta engines and writes a draft
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

ENGINES = ("mysql", "mariadb", "firebird", "duckdb", "sqlite")
TITLE = {"mysql": "MySQL", "mariadb": "MariaDB", "firebird": "Firebird", "duckdb": "DuckDB", "sqlite": "SQLite"}
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


def tab_group(field_id):
    for pattern, tab, group in RULES:
        if re.search(pattern, field_id):
            return tab, group
    return "Engine", None


def draft(engine, profiles):
    fields, seen, gaps = [], set(), []
    for profile in profiles:
        pid = profile["profile_id"]
        for field in profile["form_contract"]["server"]["forms"]["define"].get("fields", []):
            fid = field["field_id"]
            if fid in seen:
                continue
            seen.add(fid)
            tab, group = tab_group(fid)
            out = {"field_id": fid, "label": field.get("label") or fid, "tab": tab, "control": field.get("control", "text")}
            if out["control"] == "multiline":
                out["control"], out["language"] = "code", "text"
            if out["control"] not in CONTROLS:
                gaps.append({"concept": f"server.{fid}", "reason": f"provider control {out['control']!r} needs a typed control"})
                out["control"] = "text"
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
    if len(profiles) > 1:
        fields.insert(0, {"field_id": "profile", "label": "Connection kind", "tab": "Connection", "control": "select", "required": True,
                          "options": [{"value": p["profile_id"], "label": p["profile_id"].replace(f"{engine}-", "").capitalize()} for p in profiles]})
    fields.sort(key=lambda f: ORDER.index(f["tab"]))
    return {
        "schema": "cdeadmin.ui-form.v1", "engine": engine, "family": "server", "resource_kinds": ["server"],
        "status": "draft", "engine_tab_title": TITLE[engine], "omitted_tabs": [], "gaps": gaps, "fields": fields,
        "notes": "Drafted by tools/draft_server_descriptors.py from providers/form_contracts.py server.define for "
                 + ", ".join(p["profile_id"] for p in profiles)
                 + ". Field ids are the registration contract's own. Review tab/group placement.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    by_engine = {}
    for profile in registration_profiles():
        if profile["engine_id"] in ENGINES:
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
