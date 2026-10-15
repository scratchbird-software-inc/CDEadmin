#!/usr/bin/env python3
"""Register the local Docker MongoDB demo in the running CDEadmin config DB."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
WEB = REPOSITORY / "web"
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(WEB))

import config  # noqa: E402

PROFILE = {
    "name": "Local MongoDB (Docker)",
    "host": "127.0.0.1",
    "port": 27017,
    "database": "cdeadmin_demo",
    "user": "demo",
    "auth_mechanism": "NONE",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user",
        default=config.DESKTOP_USER if hasattr(config, "DESKTOP_USER") else None,
        help="CDEadmin account email (desktop default if omitted)",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    from pgadmin import create_app
    from pgadmin.cdeadmin.endpoints import (
        provider_route_options,
        registration_profile,
        service_for_app,
    )
    from pgadmin.model import (
        EndpointDatabaseTarget,
        EndpointProfile,
        Preferences,
        Server,
        ServerGroup,
        User,
        UserPreference,
        db,
    )
    from tools.reference_engine_demos.register_demo_profiles import (
        retain_database_target,
        route_for,
    )

    app = create_app(config.APP_NAME + "-local-mongodb-registration")
    with app.app_context():
        email = args.user or User.query.order_by(User.id).first().email
        user = User.query.filter_by(email=email).first()
        if user is None:
            raise SystemExit(f"CDEadmin user not found: {email}")

        registration = registration_profile("mongodb-native")
        item = {**PROFILE, "engine": "mongodb"}
        route = route_for(
            item, PROFILE["host"], registration, provider_route_options
        )

        group = ServerGroup.query.filter_by(user_id=user.id).order_by(
            ServerGroup.id
        ).first()
        if group is None:
            group = ServerGroup(user_id=user.id, name="Connectors")
            db.session.add(group)
            db.session.flush()

        server = Server.query.join(EndpointProfile).filter(
            Server.user_id == user.id,
            Server.name == PROFILE["name"],
            EndpointProfile.profile_id == registration["profile_id"],
        ).first()

        if server is None:
            server = Server(
                user_id=user.id,
                servergroup_id=group.id,
                name=PROFILE["name"],
                host=PROFILE["host"],
                port=PROFILE["port"],
                maintenance_db=None,
                username=PROFILE["user"],
                save_password=0,
                shared=False,
                use_ssh_tunnel=0,
                tunnel_port=22,
                tunnel_authentication=0,
                tunnel_prompt_password=0,
                tunnel_keep_alive=0,
                kerberos_conn=False,
                connection_params={},
                tags=[{"text": "local-docker-mongodb", "color": "#13aa52"}],
                comment="Local MongoDB from docker-compose.mongodb.yml",
            )
            server._cde_endpoint_registration = registration
            server._cde_endpoint_route_configuration = route
            db.session.add(server)
            db.session.flush()
            created = True
        else:
            server.host = PROFILE["host"]
            server.port = PROFILE["port"]
            server.username = PROFILE["user"]
            created = False

        retain_database_target(
            db, EndpointDatabaseTarget, server, item, route, registration
        )

        preference = Preferences.query.filter_by(
            name="show_connector_mongodb"
        ).first()
        if preference is not None:
            current = UserPreference.query.filter_by(
                pid=preference.id, uid=user.id
            ).first()
            if current is None:
                db.session.add(UserPreference(
                    pid=preference.id, uid=user.id, value="True"
                ))
            else:
                current.value = "True"

        if args.dry_run:
            db.session.rollback()
            print(json.dumps({"dry_run": True, "user": email}, indent=2))
            return 0

        db.session.commit()
        target = next(
            (
                item for item in server.endpoint_profile.database_targets
                if item.active
            ),
            None,
        )
        # Verification is optional; some routes fail verify while still connecting.
        if target is not None:
            try:
                service_for_app(app).verify_server(
                    server, database_target_id=target.id
                )
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                print(
                    json.dumps({
                        "warning": "saved but not verified",
                        "detail": str(exc),
                    }),
                    file=sys.stderr,
                )
        print(json.dumps({
            "user": email,
            "server_id": server.id,
            "created": created,
            "database": PROFILE["database"],
            "collections": ["customers", "sales"],
        }, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
