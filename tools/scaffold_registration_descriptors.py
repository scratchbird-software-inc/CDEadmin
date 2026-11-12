#!/usr/bin/env python3
"""Scaffold the minimal ui_descriptors/<engine>/ package for an engine whose
only descriptor is its Server registration form.

Owner direction 2026-11-11: every engine registers and edits its endpoints
through the descriptor registration host (ServerRegistrationHost), which
needs a bundle for the engine with a complete ``server`` form. Engines whose
objects are administered through their provider workspace rather than the
family forms get a package that declares the server kind only, lists the
nine object families as omitted with that reason, and an empty navigator
group and operations list. The server form itself comes from
tools/draft_server_descriptors.py.

Usage: python3 tools/scaffold_registration_descriptors.py [--write]
       [--engine x ...]
"""
from __future__ import annotations

import argparse
import json
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

ENGINES = ("apache_ignite", "cassandra", "clickhouse", "foundationdb",
           "influxdb", "milvus", "mongodb", "neo4j", "opensearch", "redis",
           "tikv")
PACKAGE_OF = {"opensearch_sql_ppl": "opensearch"}
FAMILIES = ("table", "view", "index", "routine", "trigger", "sequence",
            "type", "role", "database")
REASON = ("Administered through the engine's provider workspace and "
          "operations, not a family form; the package exists so registration "
          "goes through the descriptor registration host (owner direction "
          "2026-11-11).")


def versions():
    pilots = DESCRIPTORS.parent / "providers" / "actual_engine_pilots.json"
    record = json.loads(pilots.read_text())
    return {row["engine_id"]: row["exact_profile"] for row in record["pilots"]}


def scaffold(engine, profiles, version):
    return {
        "capabilities.json": {
            "schema": "cdeadmin.ui-capabilities.v1", "engine": engine,
            "profiles": [p["profile_id"] for p in profiles],
            "beta_tier": "basic",
            "version_range": {"minimum": version, "tested": [version]},
            "kinds": [{
                "resource_kind": "server", "family": "server",
                "form": "forms/server.form.json",
                "operations": [{"operation_id": "inspect", "tier": 1,
                                "mutation_class": "read"}]}],
        },
        "navigator.json": {
            "schema": "cdeadmin.ui-navigator.v1", "engine": engine,
            "sort": "alphabetical",
            "groups": [{"group_id": "server", "title": "Server",
                        "kinds": ["server"], "order": 1}]},
        "operations.json": {"schema": "cdeadmin.ui-operations.v1",
                            "engine": engine, "operations": []},
        "omitted_families.json": {
            "engine": engine,
            "omitted": [{"family": family, "reason": REASON}
                        for family in FAMILIES]},
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--engine", action="append")
    args = parser.parse_args()
    selected = tuple(args.engine) if args.engine else ENGINES
    by_engine = {}
    for profile in registration_profiles():
        package = PACKAGE_OF.get(profile["engine_id"], profile["engine_id"])
        if package in selected:
            by_engine.setdefault(package, []).append(profile)
    pinned = versions()
    for engine, profiles in by_engine.items():
        folder = DESCRIPTORS / engine
        files = scaffold(engine, profiles, pinned.get(engine, "0"))
        for name, document in files.items():
            path = folder / name
            if path.exists():
                print(f"{engine}: {name} exists, left alone")
                continue
            print(f"{engine}: {name}")
            if args.write:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "forms").mkdir(exist_ok=True)
                path.write_text(
                    json.dumps(document, indent=2, ensure_ascii=False)
                    + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
