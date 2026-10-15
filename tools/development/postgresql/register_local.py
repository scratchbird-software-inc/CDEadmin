#!/usr/bin/env python3
"""Register the standalone Docker PostgreSQL database in CDEadmin."""

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
    REPOSITORY = Path(__file__).resolve().parents[3]
WEB = REPOSITORY / "web"
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(WEB))

import config  # noqa: E402

DEMO_PASSWORD = "CDEadminDemo-2026!"
APP_PASSWORD = os.environ.get(
    "CDEADMIN_DEFAULT_PASSWORD", "CDEadminDev-2026!"
)


def postgres_endpoint():
    """Compose-network name from the web container, else the published host port."""
    try:
        socket.getaddrinfo("postgresql", 5432)
    except socket.gaierror:
        return "127.0.0.1", 55432
    return "postgresql", 5432


HOST, PORT = postgres_endpoint()
PROFILE = {
    "name": "Local PostgreSQL (Docker)",
    "engine": "postgresql",
    "host": HOST,
    "port": PORT,
    "database": "cdeadmin_demo",
    "user": "cdeadmin_demo",
    "password": DEMO_PASSWORD,
    "sslmode": "prefer",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user",
        default=None,
        help="CDEadmin account email (first user if omitted)",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    from pgadmin import create_app
    from pgadmin.cdeadmin.endpoints import (
        provider_route_options,
        registration_profile,
    )
    from pgadmin.model import (
        EndpointDatabaseTarget,
        EndpointProfile,
        Server,
        ServerGroup,
        User,
        db,
    )
    from pgadmin.utils.crypto import encrypt

    app = create_app(config.APP_NAME + "-local-postgresql-registration")
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

        registration = registration_profile("postgresql-native")
        route = provider_route_options(registration, {}, {
            "host": PROFILE["host"],
            "port": PROFILE["port"],
            "user": PROFILE["user"],
            "database": PROFILE["database"],
            "connection_timeout": 10,
            "sslmode": "prefer",
        })

        group = ServerGroup.query.filter_by(user_id=user.id).order_by(
            ServerGroup.id
        ).first()
        if group is None:
            group = ServerGroup(user_id=user.id, name="Servers")
            db.session.add(group)
            db.session.flush()

        server = Server.query.join(EndpointProfile).filter(
            Server.user_id == user.id,
            Server.name == PROFILE["name"],
            EndpointProfile.profile_id == registration["profile_id"],
        ).first()
        if server is None:
            server = Server.query.filter_by(
                user_id=user.id, name=PROFILE["name"]
            ).first()

        encrypted = encrypt(DEMO_PASSWORD, APP_PASSWORD)
        created = server is None
        if created:
            server = Server(
                user_id=user.id,
                servergroup_id=group.id,
                name=PROFILE["name"],
                host=PROFILE["host"],
                port=PROFILE["port"],
                maintenance_db=PROFILE["database"],
                username=PROFILE["user"],
                password=encrypted,
                save_password=1,
                shared=False,
                use_ssh_tunnel=0,
                tunnel_port=22,
                tunnel_authentication=0,
                tunnel_prompt_password=0,
                tunnel_keep_alive=0,
                kerberos_conn=False,
                connection_params={"sslmode": "prefer"},
                tags=[{"text": "local-docker-postgresql", "color": "#336791"}],
                comment="Standalone PostgreSQL container cdeadmin-postgresql",
            )
            server._cde_endpoint_registration = registration
            server._cde_endpoint_route_configuration = route
            db.session.add(server)
            db.session.flush()
        else:
            server.host = PROFILE["host"]
            server.port = PROFILE["port"]
            server.maintenance_db = PROFILE["database"]
            server.username = PROFILE["user"]
            server.password = encrypted
            server.save_password = 1
            server.connection_params = {"sslmode": "prefer"}

        db.session.flush()
        endpoint = EndpointProfile.query.filter_by(
            legacy_server_id=server.id
        ).one()
        stored_route = dict(route)
        stored_route.pop("database", None)
        for item in endpoint.routes:
            item.configuration = json.dumps(
                stored_route, sort_keys=True, separators=(",", ":")
            )
        database = PROFILE["database"]
        target = next((
            item for item in endpoint.database_targets
            if item.database == database
        ), None)
        for item in endpoint.database_targets:
            item.active = False
        if target is None:
            db.session.add(EndpointDatabaseTarget(
                id=str(uuid.uuid4()),
                endpoint_id=endpoint.id,
                display_name=database,
                database=database,
                configuration="{}",
                active=True,
            ))
        else:
            target.display_name = database
            target.active = True

        if args.dry_run:
            db.session.rollback()
            print(json.dumps({
                "dry_run": True,
                "user": email,
                "host": PROFILE["host"],
                "port": PROFILE["port"],
            }, indent=2))
            return 0

        db.session.commit()
        print(json.dumps({
            "user": email,
            "server_id": server.id,
            "created": created,
            "host": PROFILE["host"],
            "port": PROFILE["port"],
            "database": PROFILE["database"],
            "username": PROFILE["user"],
        }, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
