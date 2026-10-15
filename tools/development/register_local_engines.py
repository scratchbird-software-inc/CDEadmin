#!/usr/bin/env python3
"""Register standalone Firebird, MySQL, MariaDB, and DuckDB in CDEadmin."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import uuid
from pathlib import Path

REPOSITORY = Path("/cdeadmin")
if not (REPOSITORY / "web").is_dir():
    REPOSITORY = Path(__file__).resolve().parents[2]
WEB = REPOSITORY / "web"
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(WEB))

import config  # noqa: E402

DEMO_PASSWORD = "CDEadminDemo-2026!"
APP_PASSWORD = os.environ.get(
    "CDEADMIN_DEFAULT_PASSWORD", "CDEadminDev-2026!"
)
DUCKDB_FILE = "/cdeadmin/.devstate/application/cdeadmin_demo.duckdb"


def on_network(name):
    try:
        socket.getaddrinfo(name, 1)
    except socket.gaierror:
        return False
    return True


def profiles():
    firebird_host = "firebird" if on_network("firebird") else "127.0.0.1"
    mysql_host = "mysql" if on_network("mysql") else "127.0.0.1"
    mariadb_host = "mariadb" if on_network("mariadb") else "127.0.0.1"
    return (
        {
            "name": "Local Firebird (Docker)",
            "profile_id": "firebird-native",
            "host": firebird_host,
            "port": 3050 if firebird_host == "firebird" else 53050,
            "user": "SYSDBA",
            "password": DEMO_PASSWORD,
            "database": "/var/lib/firebird/data/cdeadmin_demo.fdb",
            "display_name": "cdeadmin_demo.fdb",
            "connector": "firebird",
            "route": {
                "database_create_root": "/var/lib/firebird/data",
                "charset": "UTF8",
                "wire_crypt": "Enabled",
                "auth_plugin_list": "Srp256,Srp,Legacy_Auth",
            },
            "form": {
                "cde_route_wire_crypt": "Enabled",
                "cde_route_database_create_root": "/var/lib/firebird/data",
                "cde_route_charset": "UTF8",
            },
        },
        {
            "name": "Local MySQL (Docker)",
            "profile_id": "mysql-native",
            "host": mysql_host,
            "port": 3306 if mysql_host == "mysql" else 53306,
            "user": "cdeadmin_demo",
            "password": DEMO_PASSWORD,
            "database": "cdeadmin_demo",
            "display_name": "cdeadmin_demo",
            "connector": "mysql",
            "route": {
                "ssl_disabled": False,
                "ssl_verify_cert": False,
                "ssl_verify_identity": False,
                "use_pure": True,
            },
            "form": {
                "cde_route_ssl_disabled": False,
                "cde_route_ssl_verify_cert": False,
                "cde_route_ssl_verify_identity": False,
                "cde_route_use_pure": True,
            },
        },
        {
            "name": "Local MariaDB (Docker)",
            "profile_id": "mariadb-native",
            "host": mariadb_host,
            "port": 3306 if mariadb_host == "mariadb" else 53307,
            "user": "cdeadmin_demo",
            "password": DEMO_PASSWORD,
            "database": "cdeadmin_demo",
            "display_name": "cdeadmin_demo",
            "connector": "mariadb",
            "route": {
                "ssl": False,
                "ssl_verify_cert": False,
            },
            "form": {
                "cde_route_ssl": False,
                "cde_route_ssl_verify_cert": False,
            },
        },
        {
            "name": "Local DuckDB",
            "profile_id": "duckdb-native",
            "host": None,
            "port": 1,
            "user": "embedded-process",
            "password": None,
            "database": DUCKDB_FILE,
            "display_name": "cdeadmin_demo.duckdb",
            "connector": "duckdb",
            "embedded": True,
            "route": {
                "database": DUCKDB_FILE,
                "filesystem_root": str(Path(DUCKDB_FILE).parent),
                "database_create_root": str(Path(DUCKDB_FILE).parent),
            },
            "form": {},
        },
    )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def enable_connector(db, user_id, engine_id):
    from pgadmin.model import Preferences, UserPreference

    preference = Preferences.query.filter_by(
        name=f"show_connector_{engine_id}"
    ).first()
    if preference is None:
        return
    current = UserPreference.query.filter_by(
        pid=preference.id, uid=user_id
    ).first()
    if current is None:
        db.session.add(UserPreference(
            pid=preference.id, uid=user_id, value="True"
        ))
    else:
        current.value = "True"


def register_one(db, user, group, item, registration, route):
    from pgadmin.model import (
        EndpointDatabaseTarget,
        EndpointProfile,
        Server,
    )
    from pgadmin.utils.crypto import encrypt

    server = Server.query.join(EndpointProfile).filter(
        Server.user_id == user.id,
        Server.name == item["name"],
        EndpointProfile.profile_id == registration["profile_id"],
    ).first()
    if server is None:
        server = Server.query.filter_by(
            user_id=user.id, name=item["name"]
        ).first()
    created = server is None
    embedded = item.get("embedded") is True
    password = None
    save_password = 0
    if item.get("password"):
        password = encrypt(item["password"], APP_PASSWORD)
        save_password = 1
    if created:
        server = Server(
            user_id=user.id,
            servergroup_id=group.id,
            name=item["name"],
            host=None if embedded else item["host"],
            port=item["port"],
            maintenance_db=None,
            username=item["user"],
            password=password,
            save_password=save_password,
            shared=False,
            use_ssh_tunnel=0,
            tunnel_port=22,
            tunnel_authentication=0,
            tunnel_prompt_password=0,
            tunnel_keep_alive=0,
            kerberos_conn=False,
            connection_params={},
            tags=[{"text": "local-dev-engine", "color": "#31708f"}],
            comment="Standalone local development engine",
        )
        server._cde_endpoint_registration = registration
        server._cde_endpoint_route_configuration = route
        db.session.add(server)
        db.session.flush()
    else:
        server.host = None if embedded else item["host"]
        server.port = item["port"]
        server.username = item["user"]
        server.password = password
        server.save_password = save_password

    db.session.flush()
    endpoint = EndpointProfile.query.filter_by(
        legacy_server_id=server.id
    ).one()
    stored_route = dict(route)
    if registration.get("route_kind") == "network":
        stored_route.pop("database", None)
    for model in endpoint.routes:
        model.configuration = json.dumps(
            stored_route, sort_keys=True, separators=(",", ":")
        )
    database = item["database"]
    target = next((
        row for row in endpoint.database_targets
        if row.database == database
    ), None)
    for row in endpoint.database_targets:
        row.active = False
    if target is None:
        db.session.add(EndpointDatabaseTarget(
            id=str(uuid.uuid4()),
            endpoint_id=endpoint.id,
            display_name=item["display_name"],
            database=database,
            configuration="{}",
            active=True,
        ))
    else:
        target.display_name = item["display_name"]
        target.active = True
    enable_connector(db, user.id, item["connector"])
    return {
        "name": item["name"],
        "server_id": server.id,
        "created": created,
        "host": item["host"],
        "port": item["port"],
        "database": item["display_name"],
    }


def main():
    args = parse_args()
    from pgadmin import create_app
    from pgadmin.cdeadmin.endpoints import (
        provider_route_options,
        registration_profile,
    )
    from pgadmin.model import ServerGroup, User, db

    app = create_app(config.APP_NAME + "-local-engine-registration")
    with app.app_context():
        email = args.user
        if not email:
            first = User.query.order_by(User.id).first()
            if first is None:
                raise SystemExit("CDEadmin has no users yet")
            email = first.email
        user = User.query.filter_by(email=email).first()
        if user is None:
            raise SystemExit(f"CDEadmin user not found: {email}")
        group = ServerGroup.query.filter_by(user_id=user.id).order_by(
            ServerGroup.id
        ).first()
        if group is None:
            group = ServerGroup(user_id=user.id, name="Servers")
            db.session.add(group)
            db.session.flush()

        results = []
        for item in profiles():
            registration = registration_profile(item["profile_id"])
            base = {
                "host": item["host"],
                "port": item["port"],
                "user": item["user"],
                "database": item["database"],
                "connection_timeout": 10,
            }
            if item.get("embedded"):
                base = dict(item["route"])
            else:
                base.update(item["route"])
            route = provider_route_options(
                registration, item["form"], base
            )
            results.append(register_one(
                db, user, group, item, registration, route
            ))

        if args.dry_run:
            db.session.rollback()
            print(json.dumps({"dry_run": True, "user": email, "engines": results}, indent=2))
            return 0
        db.session.commit()
        print(json.dumps({"user": email, "engines": results}, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
