#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Create, seed, apply DDL to, and register isolated developer test databases."""

from __future__ import annotations

import argparse
import builtins
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPOSITORY = ROOT.parents[1]
DATA = ROOT / "data"
RUNTIME = ROOT / "runtime"
PASSWORD = "CDEadminDemo-2026!"

IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")

PROTECTED_DEMO_DATABASES = frozenset({
    "cdeadmin_demo",
    "cdeadmin-work-orders",
    "test_keyspace",
    "lookup_keyspace",
    "postgres",
    "template0",
    "template1",
    "mysql",
    "information_schema",
    "performance_schema",
    "sys",
    "system",
    "system_auth",
    "system_schema",
    "defaultdb",
    "yugabyte",
    "neo4j",
    "defaultdb",
    "admin",
    "local",
    "config",
})

SUPPORTED_CREATE_ENGINES = (
    "sqlite",
    "duckdb",
    "firebird",
    "postgresql",
    "cockroachdb",
    "yugabytedb",
    "mysql",
    "mariadb",
    "dolt",
    "tidb",
    "clickhouse",
    "mongodb",
    "cassandra",
    "yugabytedb_ycql",
    "opensearch",
    "influxdb",
)


def validate_database_name(name, *, allow_protected=False):
    if not isinstance(name, str) or not IDENTIFIER_RE.match(name):
        raise ValueError(
            f"invalid test database name {name!r}: must match "
            "^[A-Za-z][A-Za-z0-9_]{0,62}$"
        )
    if not allow_protected and name.lower() in PROTECTED_DEMO_DATABASES:
        raise ValueError(
            f"{name!r} is a protected system or canonical demo database; "
            "choose an isolated test database name (e.g. dev_feature_test)"
        )
    return name


def split_sql_statements(sql_text):
    statements = []
    for chunk in sql_text.split(";"):
        cleaned = "\n".join(
            line for line in chunk.splitlines()
            if not line.lstrip().startswith("--")
        ).strip()
        if cleaned:
            statements.append(cleaned)
    return statements


def target_descriptor(engine, name):
    validate_database_name(name)
    if engine == "sqlite":
        return {
            "engine": engine,
            "database": str((DATA / f"{name}.sqlite").resolve()),
            "display_name": f"{name}.sqlite",
            "kind": "embedded_file",
        }
    if engine == "duckdb":
        return {
            "engine": engine,
            "database": str((DATA / f"{name}.duckdb").resolve()),
            "display_name": f"{name}.duckdb",
            "kind": "embedded_file",
        }
    if engine == "firebird":
        return {
            "engine": engine,
            "database": f"/var/lib/firebird/data/{name}.fdb",
            "display_name": f"{name}.fdb",
            "kind": "container_file",
        }
    return {
        "engine": engine,
        "database": name,
        "display_name": name,
        "kind": "network_catalog",
    }


def _seed_relational_rows(cursor, paramstyle, schema_prefix=""):
    from seed_demo import ASSETS, CUSTOMERS, WORK_ORDERS

    placeholder = "%s" if paramstyle == "format" else "?"
    tuple4 = f"({','.join([placeholder] * 4)})"
    tuple5 = f"({','.join([placeholder] * 5)})"
    tuple6 = f"({','.join([placeholder] * 6)})"

    for table in ("work_orders", "assets", "customers"):
        cursor.execute(f"DELETE FROM {schema_prefix}{table}")
    cursor.executemany(
        f"INSERT INTO {schema_prefix}customers VALUES {tuple4}",
        CUSTOMERS,
    )
    cursor.executemany(
        f"INSERT INTO {schema_prefix}assets VALUES {tuple5}",
        ASSETS,
    )
    cursor.executemany(
        f"INSERT INTO {schema_prefix}work_orders "
        "(work_order_id,asset_id,technician,summary,status,priority) "
        f"VALUES {tuple6}",
        WORK_ORDERS,
    )


def _create_sqlite(name, *, seed=False, sql_statements=(), drop_existing=False):
    from seed_demo import relational_ddl

    DATA.mkdir(parents=True, exist_ok=True)
    path = (DATA / f"{name}.sqlite").resolve()
    if path.exists() and drop_existing:
        path.unlink()

    reference_cli = RUNTIME / "sqlite-3.53.0/bin/sqlite3"
    if reference_cli.is_file():
        subprocess.run(
            [str(reference_cli), str(path), "PRAGMA user_version=35300;"],
            check=True,
        )

    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if seed:
            cursor.execute("DROP VIEW IF EXISTS open_work_orders")
            for ddl in relational_ddl("sqlite"):
                try:
                    cursor.execute(ddl)
                except sqlite3.OperationalError as exc:
                    if "already exists" not in str(exc).lower():
                        raise
            _seed_relational_rows(cursor, "qmark")
        for statement in sql_statements:
            cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()
    return {"engine": "sqlite", "database": str(path), "seeded": bool(seed)}


def _create_duckdb(name, *, seed=False, sql_statements=(), drop_existing=False):
    import duckdb
    from seed_demo import ASSETS, CUSTOMERS, WORK_ORDERS

    DATA.mkdir(parents=True, exist_ok=True)
    path = (DATA / f"{name}.duckdb").resolve()
    if path.exists() and drop_existing:
        path.unlink()
        wal = Path(f"{path}.wal")
        if wal.exists():
            wal.unlink()

    connection = duckdb.connect(str(path))
    try:
        if seed:
            connection.execute("CREATE SCHEMA IF NOT EXISTS service")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS service.customers "
                "(customer_id INTEGER PRIMARY KEY, name VARCHAR, "
                "city VARCHAR, region VARCHAR)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS service.assets "
                "(asset_id INTEGER PRIMARY KEY, customer_id INTEGER, "
                "tag VARCHAR UNIQUE, asset_type VARCHAR, status VARCHAR)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS service.work_orders "
                "(work_order_id INTEGER PRIMARY KEY, asset_id INTEGER, "
                "technician VARCHAR, summary VARCHAR, status VARCHAR, "
                "priority INTEGER, "
                "created_at TIMESTAMP DEFAULT current_timestamp)"
            )
            for table in ("work_orders", "assets", "customers"):
                connection.execute(f"DELETE FROM service.{table}")
            connection.executemany(
                "INSERT INTO service.customers VALUES (?,?,?,?)", CUSTOMERS,
            )
            connection.executemany(
                "INSERT INTO service.assets VALUES (?,?,?,?,?)", ASSETS,
            )
            connection.executemany(
                "INSERT INTO service.work_orders "
                "(work_order_id,asset_id,technician,summary,status,priority) "
                "VALUES (?,?,?,?,?,?)",
                WORK_ORDERS,
            )
        for statement in sql_statements:
            connection.execute(statement)
    finally:
        connection.close()
    return {"engine": "duckdb", "database": str(path), "seeded": bool(seed)}


def _create_firebird(name, *, seed=False, sql_statements=(), drop_existing=False):
    from firebird.driver import connect, create_database
    from seed_demo import seed_firebird

    database_path = f"/var/lib/firebird/data/{name}.fdb"
    dsn = f"127.0.0.1/53050:{database_path}"
    if drop_existing:
        try:
            existing = connect(dsn, user="SYSDBA", password=PASSWORD)
            existing.drop_database()
        except Exception as exc:
            if "no such file" not in str(exc).lower() and (
                "not defined" not in str(exc).lower()
            ):
                raise

    if seed:
        seed_firebird(database_path=database_path)
    else:
        try:
            conn = connect(dsn, user="SYSDBA", password=PASSWORD)
        except Exception:
            conn = create_database(dsn, user="SYSDBA", password=PASSWORD)
        conn.close()

    if sql_statements:
        conn = connect(dsn, user="SYSDBA", password=PASSWORD)
        try:
            cur = conn.cursor()
            for statement in sql_statements:
                cur.execute(statement)
            conn.commit()
        finally:
            conn.close()
    return {"engine": "firebird", "database": database_path, "seeded": bool(seed)}


def _create_postgresql_family(
    engine, name, *, seed=False, sql_statements=(), drop_existing=False,
):
    import psycopg
    from seed_demo import relational_ddl

    admin_params = {
        "postgresql": dict(
            host="127.0.0.1", port=55432, user="cdeadmin_demo",
            password=PASSWORD, dbname="cdeadmin_demo",
        ),
        "cockroachdb": dict(
            host="127.0.0.1", port=56257, user="root",
            dbname="defaultdb", sslmode="disable",
        ),
        "yugabytedb": dict(
            host="127.0.0.1", port=55433, user="yugabyte",
            dbname="yugabyte",
        ),
    }[engine]

    admin = psycopg.connect(**admin_params, autocommit=True)
    try:
        if drop_existing:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,),
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        admin.close()

    target_params = dict(admin_params, dbname=name)
    conn = psycopg.connect(**target_params, autocommit=True)
    try:
        cur = conn.cursor()
        if seed:
            for ddl in relational_ddl(engine):
                cur.execute(ddl)
            _seed_relational_rows(cur, "format", schema_prefix="service.")
        for statement in sql_statements:
            cur.execute(statement)
        cur.close()
    finally:
        conn.close()
    return {"engine": engine, "database": name, "seeded": bool(seed)}


def _create_mysql_family(
    engine, name, *, seed=False, sql_statements=(), drop_existing=False,
):
    import mysql.connector
    from seed_demo import relational_ddl

    port, user, password = {
        "mysql": (53306, "root", PASSWORD),
        "mariadb": (53307, "root", PASSWORD),
        "dolt": (53308, "root", None),
        "tidb": (54000, "root", None),
    }[engine]

    def _connect(db_name=None):
        kwargs = dict(
            host="127.0.0.1", port=port, user=user,
            connection_timeout=10, autocommit=True,
        )
        if password:
            kwargs["password"] = password
        if db_name:
            kwargs["database"] = db_name
        return mysql.connector.connect(**kwargs)

    admin = _connect()
    try:
        cur = admin.cursor()
        if drop_existing:
            cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}`")
        if engine in ("mysql", "mariadb"):
            cur.execute(
                f"GRANT ALL PRIVILEGES ON `{name}`.* TO 'cdeadmin_demo'@'%'"
            )
        cur.close()
    finally:
        admin.close()

    conn = _connect(name)
    try:
        cur = conn.cursor()
        if seed:
            cur.execute("DROP VIEW IF EXISTS open_work_orders")
            for ddl in relational_ddl("mysql"):
                try:
                    cur.execute(ddl)
                except Exception as exc:
                    msg = str(exc).lower()
                    if "already exists" not in msg and "duplicate key" not in msg:
                        raise
            _seed_relational_rows(cur, "format")
        for statement in sql_statements:
            cur.execute(statement)
        cur.close()
    finally:
        conn.close()
    return {"engine": engine, "database": name, "seeded": bool(seed)}


def _clickhouse_exec(query, database=None):
    params = {"user": "cdeadmin_demo", "password": PASSWORD}
    if database:
        params["database"] = database
    url = "http://127.0.0.1:58123/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, data=query.encode("utf-8"), method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def _create_clickhouse(name, *, seed=False, sql_statements=(), drop_existing=False):
    from seed_demo import CUSTOMERS

    if drop_existing:
        _clickhouse_exec(f"DROP DATABASE IF EXISTS {name}")
    _clickhouse_exec(f"CREATE DATABASE IF NOT EXISTS {name}")
    if seed:
        _clickhouse_exec(
            f"CREATE TABLE IF NOT EXISTS {name}.customers ("
            "customer_id Int32, name String, city String, region String"
            ") ENGINE = MergeTree ORDER BY customer_id"
        )
        _clickhouse_exec(f"TRUNCATE TABLE {name}.customers")
        rows = ", ".join(
            f"({cid}, '{cname}', '{city}', '{region}')"
            for cid, cname, city, region in CUSTOMERS
        )
        _clickhouse_exec(f"INSERT INTO {name}.customers VALUES {rows}")
    for statement in sql_statements:
        _clickhouse_exec(statement, database=name)
    return {"engine": "clickhouse", "database": name, "seeded": bool(seed)}


def _create_mongodb(name, *, seed=False, drop_existing=False):
    from pymongo import MongoClient
    from seed_demo import CUSTOMERS, WORK_ORDERS

    client = MongoClient("mongodb://127.0.0.1:57017/", serverSelectionTimeoutMS=10000)
    try:
        if drop_existing:
            client.drop_database(name)
        db = client[name]
        if seed:
            db.customers.delete_many({})
            db.customers.insert_many([
                {"_id": cid, "name": cname, "city": city, "region": region}
                for cid, cname, city, region in CUSTOMERS
            ])
            db.work_orders.delete_many({})
            db.work_orders.insert_many([
                {
                    "_id": wid, "asset_id": aid, "technician": tech,
                    "summary": summary, "status": status, "priority": prio,
                }
                for wid, aid, tech, summary, status, prio in WORK_ORDERS
            ])
        elif "metadata" not in db.list_collection_names():
            db.create_collection("metadata")
    finally:
        client.close()
    return {"engine": "mongodb", "database": name, "seeded": bool(seed)}


def _create_cql_keyspace(
    engine, name, *, seed=False, sql_statements=(), drop_existing=False,
):
    from cassandra.auth import PlainTextAuthProvider
    from cassandra.cluster import Cluster
    from seed_demo import CUSTOMERS

    port = 19042 if engine == "cassandra" else 59042
    auth = PlainTextAuthProvider(username="cassandra", password=PASSWORD)
    cluster = Cluster(["127.0.0.1"], port=port, auth_provider=auth)
    session = cluster.connect()
    try:
        if drop_existing:
            session.execute(f'DROP KEYSPACE IF EXISTS "{name}"')
        session.execute(
            f'CREATE KEYSPACE IF NOT EXISTS "{name}" '
            "WITH replication = {'class': 'SimpleStrategy', "
            "'replication_factor': 1}"
        )
        session.set_keyspace(name)
        if seed:
            session.execute(
                "CREATE TABLE IF NOT EXISTS customers ("
                "customer_id int PRIMARY KEY, name text, city text, region text)"
            )
            for cid, cname, city, region in CUSTOMERS:
                session.execute(
                    "INSERT INTO customers (customer_id, name, city, region) "
                    "VALUES (%s, %s, %s, %s)",
                    (cid, cname, city, region),
                )
        for statement in sql_statements:
            session.execute(statement)
    finally:
        cluster.shutdown()
    return {"engine": engine, "database": name, "seeded": bool(seed)}


def _create_opensearch(name, *, seed=False, drop_existing=False):
    from seed_demo import WORK_ORDERS

    index_name = name.lower()
    base_url = f"http://127.0.0.1:59200/{index_name}"
    if drop_existing:
        req = urllib.request.Request(base_url, method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
    put_req = urllib.request.Request(
        base_url,
        data=b'{"settings":{"number_of_shards":1,"number_of_replicas":0}}',
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        urllib.request.urlopen(put_req, timeout=10).close()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        if "resource_already_exists_exception" not in body:
            raise
    if seed:
        for wid, aid, tech, summary, status, prio in WORK_ORDERS:
            doc = json.dumps({
                "work_order_id": wid, "asset_id": aid,
                "technician": tech, "summary": summary,
                "status": status, "priority": prio,
            }).encode("utf-8")
            doc_req = urllib.request.Request(
                f"{base_url}/_doc/{wid}?refresh=true",
                data=doc,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            urllib.request.urlopen(doc_req, timeout=10).close()
    return {"engine": "opensearch", "database": index_name, "seeded": bool(seed)}


def _create_influxdb(name, *, seed=False):
    line = (
        "work_orders,status=open,technician=Ada priority=3i 1730000000000000000\n"
        if seed else
        "test_database_init,db=" + name + " ready=1i 1730000000000000000\n"
    )
    url = (
        "http://127.0.0.1:58181/api/v3/write_lp?"
        + urllib.parse.urlencode({"db": name, "precision": "nanosecond"})
    )
    req = urllib.request.Request(
        url, data=line.encode("utf-8"), method="POST",
    )
    urllib.request.urlopen(req, timeout=10).close()
    return {"engine": "influxdb", "database": name, "seeded": bool(seed)}


def register_database_target_for_user(engine, descriptor, user_email):
    """Add an EndpointDatabaseTarget to an existing user's engine profile."""
    web_dir = REPOSITORY / "web"
    if str(web_dir) not in sys.path:
        sys.path.insert(0, str(web_dir))
    import config  # noqa: E402
    builtins.SERVER_MODE = None

    from pgadmin import create_app
    app = create_app(config.APP_NAME + "-create-test-db")
    with app.app_context():
        from pgadmin.cdeadmin.endpoints import registration_profiles
        from pgadmin.model import (
            db, EndpointDatabaseTarget, Server, User,
        )
        from register_demo_profiles import PROFILE_OVERRIDES

        sqlite_db = Path(config.SQLITE_PATH)
        if sqlite_db.is_file():
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            backup_path = sqlite_db.with_name(
                f"{sqlite_db.name}.create-db-{timestamp}.bak"
            )
            with sqlite3.connect(sqlite_db) as src, sqlite3.connect(
                backup_path
            ) as dst:
                src.backup(dst)

        user = User.query.filter_by(email=user_email).first()
        if user is None:
            raise RuntimeError(f"CDEadmin user does not exist: {user_email}")

        profile_id = PROFILE_OVERRIDES.get(
            engine, f"{engine.replace('_', '-')}-native"
        )
        registrations = {p["profile_id"]: p for p in registration_profiles()}
        if profile_id not in registrations:
            raise RuntimeError(f"no registration profile for {engine}")

        matching_server = None
        for server in Server.query.filter_by(user_id=user.id).all():
            ep = getattr(server, "endpoint_profile", None)
            if ep is not None and ep.profile_id == profile_id:
                matching_server = server
                break
        if matching_server is None:
            raise RuntimeError(
                f"no registered {engine} server found for {user_email}; "
                f"run `bash tools/development/dev.sh register --user "
                f"{user_email}` first"
            )

        endpoint = matching_server.endpoint_profile
        database_value = descriptor["database"]
        existing = next(
            (
                t for t in endpoint.database_targets
                if t.database == database_value
            ),
            None,
        )
        if existing is None:
            existing = EndpointDatabaseTarget(
                id=str(uuid.uuid4()),
                endpoint_id=endpoint.id,
                display_name=descriptor["display_name"],
                database=database_value,
                configuration="{}",
                active=True,
            )
            db.session.add(existing)
        else:
            existing.display_name = descriptor["display_name"]
            existing.active = True
        endpoint.profile_generation = str(uuid.uuid4())
        db.session.commit()
        return {
            "registered_user": user_email,
            "endpoint_id": endpoint.id,
            "target_id": existing.id,
        }


def create_test_database(
    engine,
    name,
    *,
    seed=False,
    sql_file=None,
    register_user=None,
    drop_existing=False,
    dry_run=False,
):
    if engine not in SUPPORTED_CREATE_ENGINES:
        raise ValueError(
            f"unsupported engine {engine!r}; choose from "
            f"{', '.join(SUPPORTED_CREATE_ENGINES)}"
        )
    descriptor = target_descriptor(engine, name)
    sql_statements = ()
    if sql_file is not None:
        sql_path = Path(sql_file).expanduser().resolve()
        if not sql_path.is_file():
            raise FileNotFoundError(f"SQL file not found: {sql_path}")
        sql_statements = tuple(
            split_sql_statements(sql_path.read_text(encoding="utf-8"))
        )

    plan = {
        **descriptor,
        "seed_field_service_fixture": bool(seed),
        "custom_sql_statements": len(sql_statements),
        "drop_existing": bool(drop_existing),
        "register_user": register_user,
        "dry_run": bool(dry_run),
    }
    if dry_run:
        return plan

    if engine == "sqlite":
        outcome = _create_sqlite(
            name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine == "duckdb":
        outcome = _create_duckdb(
            name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine == "firebird":
        outcome = _create_firebird(
            name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine in ("postgresql", "cockroachdb", "yugabytedb"):
        outcome = _create_postgresql_family(
            engine, name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine in ("mysql", "mariadb", "dolt", "tidb"):
        outcome = _create_mysql_family(
            engine, name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine == "clickhouse":
        outcome = _create_clickhouse(
            name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine == "mongodb":
        if sql_statements:
            raise ValueError("MongoDB does not accept --sql-file statements")
        outcome = _create_mongodb(
            name, seed=seed, drop_existing=drop_existing,
        )
    elif engine in ("cassandra", "yugabytedb_ycql"):
        outcome = _create_cql_keyspace(
            engine, name, seed=seed, sql_statements=sql_statements,
            drop_existing=drop_existing,
        )
    elif engine == "opensearch":
        if sql_statements:
            raise ValueError("OpenSearch does not accept --sql-file statements")
        outcome = _create_opensearch(
            name, seed=seed, drop_existing=drop_existing,
        )
    elif engine == "influxdb":
        if sql_statements:
            raise ValueError("InfluxDB does not accept --sql-file statements")
        outcome = _create_influxdb(name, seed=seed)
    else:
        raise ValueError(f"unsupported engine: {engine}")

    result = {**plan, **outcome}
    if register_user:
        registration_info = register_database_target_for_user(
            engine, descriptor, register_user,
        )
        result.update(registration_info)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", required=True, choices=SUPPORTED_CREATE_ENGINES,
        help="Target engine on which to create the isolated test database",
    )
    parser.add_argument(
        "--name", required=True,
        help="Isolated database/keyspace/index name (e.g. dev_schema_test)",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="Populate with the standard field-service sample tables/documents",
    )
    parser.add_argument(
        "--sql-file", type=Path,
        help="Optional DDL/SQL script applied after creating the test database",
    )
    parser.add_argument(
        "--register-user",
        help="Optional CDEadmin user email to register the new database target",
    )
    parser.add_argument(
        "--drop-existing", action="store_true",
        help="Drop and recreate the test database if it already exists "
             "(refused for protected/canonical demo databases)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the planned target and actions without modifying state",
    )
    args = parser.parse_args(argv)
    outcome = create_test_database(
        args.engine,
        args.name,
        seed=args.seed,
        sql_file=args.sql_file,
        register_user=args.register_user,
        drop_existing=args.drop_existing,
        dry_run=args.dry_run,
    )
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
