#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Authoritative Docker image catalog and pre-pull tooling for demo fixtures."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


DOCKER_IMAGE_CATALOG = (
    {
        "image": "postgres:18.3",
        "engines": ("postgresql",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-postgresql",),
        "ports": ("127.0.0.1:55432->5432",),
        "purpose": "PostgreSQL 18.3 server fixture",
    },
    {
        "image": "firebirdsql/firebird:5.0.4",
        "engines": ("firebird",),
        "groups": ("bootstrap", "local", "core", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": ("cdeadmin-demo-firebird",),
        "ports": ("127.0.0.1:53050->3050",),
        "purpose": (
            "Firebird 5.0.4 server fixture and host libfbclient.so.5.0.4 "
            "client extraction"
        ),
    },
    {
        "image": "mysql:9.7.0",
        "engines": ("mysql",),
        "groups": ("bootstrap", "core", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": ("cdeadmin-demo-mysql",),
        "ports": ("127.0.0.1:53306->3306",),
        "purpose": (
            "MySQL 9.7.0 server fixture and MySQL Shell 9.7.0 + private "
            "OpenSSL 3.5.1 client extraction"
        ),
    },
    {
        "image": "mariadb:12.2.2",
        "engines": ("mariadb",),
        "groups": ("bootstrap", "core", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": ("cdeadmin-demo-mariadb",),
        "ports": ("127.0.0.1:53307->3306",),
        "purpose": (
            "MariaDB 12.2.2 row-binlog server fixture and mariadb/mariadb-dump/"
            "mariadb-upgrade/mariadb-binlog/mariadb-admin client extraction"
        ),
    },
    {
        "image": "redis:8.6.2",
        "engines": ("redis",),
        "groups": ("local", "core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-redis",),
        "ports": ("127.0.0.1:56379->6379",),
        "purpose": "Redis 8.6.2 AOF server fixture",
    },
    {
        "image": "mongo:8.2.6",
        "engines": ("mongodb",),
        "groups": ("local", "core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-mongodb",),
        "ports": ("127.0.0.1:57017->27017",),
        "purpose": "MongoDB 8.2.6 document server fixture",
    },
    {
        "image": "clickhouse/clickhouse-server:25.12.10.7",
        "engines": ("clickhouse",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-clickhouse",),
        "ports": ("127.0.0.1:58123->8123", "127.0.0.1:59001->9000"),
        "purpose": "ClickHouse 25.12.10.7 Keeper + ReplicatedMergeTree fixture",
    },
    {
        "image": "cockroachdb/cockroach:v26.1.3",
        "engines": ("cockroachdb",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-cockroachdb",),
        "ports": ("127.0.0.1:56257->26257", "127.0.0.1:58081->8080"),
        "purpose": "CockroachDB v26.1.3 single-node SQL + CLI wrapper fixture",
    },
    {
        "image": "dolthub/dolt-sql-server:1.86.6",
        "engines": ("dolt",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-dolt",),
        "ports": ("127.0.0.1:53308->3306",),
        "purpose": "Dolt 1.86.6 versioned SQL server fixture",
    },
    {
        "image": "codenotary/immudb:1.11.0",
        "engines": ("immudb",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-immudb",),
        "ports": (
            "127.0.0.1:53322->3322", "127.0.0.1:55435->5432",
            "127.0.0.1:58082->8080", "127.0.0.1:59497->9497",
        ),
        "purpose": "immudb 1.11.0 tamper-evident ledger/SQL server fixture",
    },
    {
        "image": "influxdb:3.9.0-core",
        "engines": ("influxdb",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-influxdb",),
        "ports": ("127.0.0.1:58181->8181",),
        "purpose": "InfluxDB 3.9.0 Core time-series server fixture",
    },
    {
        "image": "neo4j:2026.04.0-enterprise",
        "engines": ("neo4j",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-neo4j",),
        "ports": ("127.0.0.1:57474->7474", "127.0.0.1:57687->7687"),
        "purpose": "Neo4j 2026.04.0 graph server and admin CLI fixture",
    },
    {
        "image": "opensearchproject/opensearch:3.6.0",
        "engines": ("opensearch", "opensearch_sql_ppl"),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-opensearch",),
        "ports": ("127.0.0.1:59200->9200", "127.0.0.1:59600->9600"),
        "purpose": "OpenSearch 3.6.0 native + SQL/PPL shared deployment",
    },
    {
        "image": "ghcr.io/xtdb/xtdb:2.1.0",
        "engines": ("xtdb",),
        "groups": ("core", "all"),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-xtdb",),
        "ports": ("127.0.0.1:55434->5432", "127.0.0.1:58083->8080"),
        "purpose": "XTDB 2.1.0 bitemporal SQL/HTTP server fixture",
    },
    {
        "image": "apacheignite/ignite:2.17.0",
        "engines": ("apache_ignite",),
        "groups": ("bootstrap", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": (
            "cdeadmin-demo-apache-ignite",
            "cdeadmin-demo-apache-ignite-2",
        ),
        "ports": ("127.0.0.1:51080->10800", "127.0.0.1:58080->8080"),
        "purpose": (
            "Apache Ignite 2.17.0 two-node cluster and JAR compilation "
            "dependency extraction"
        ),
    },
    {
        "image": "cassandra:5.0.8",
        "engines": ("cassandra",),
        "groups": ("bootstrap", "local", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": (
            "cdeadmin-demo-cassandra",
            "cdeadmin-demo-cassandra-2",
            "cdeadmin-demo-cassandra-3",
        ),
        "ports": (
            "127.0.0.1..3:19042->19042",
            "127.0.0.1..3:17199->17199",
        ),
        "purpose": (
            "Apache Cassandra 5.0.8 three-node authenticated cluster and "
            "cqlsh/nodetool/sstableloader client extraction"
        ),
    },
    {
        "image": "foundationdb/foundationdb:7.3.77",
        "engines": ("foundationdb",),
        "groups": ("bootstrap", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": ("cdeadmin-demo-foundationdb",),
        "ports": ("127.0.0.1:54500..54503->54500..54503",),
        "purpose": (
            "FoundationDB 7.3.77 four-process server and "
            "fdbcli/fdbbackup/libfdb_c.so client extraction"
        ),
    },
    {
        "image": "yugabytedb/yugabyte:2025.2.2.2-b11",
        "engines": ("yugabytedb", "yugabytedb_ycql"),
        "groups": ("bootstrap", "all"),
        "bootstrap_client": True,
        "opt_in": False,
        "containers": ("cdeadmin-demo-yugabytedb",),
        "ports": (
            "127.0.0.1:55433->5433", "127.0.0.1:59042->9042",
            "127.0.0.1:57000->7000", "127.0.0.1:59000->9000",
        ),
        "purpose": (
            "YugabyteDB 2025.2.2.2 YSQL + authenticated YCQL server and "
            "ycqlsh client extraction"
        ),
    },
    {
        "image": "milvusdb/milvus:v2.6.5",
        "engines": ("milvus",),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-milvus",),
        "ports": ("127.0.0.1:59530->19530", "127.0.0.1:59091->9091"),
        "purpose": "Milvus v2.6.5 standalone vector database server",
    },
    {
        "image": "quay.io/coreos/etcd:v3.5.18",
        "engines": ("milvus",),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-milvus-etcd",),
        "ports": (),
        "purpose": "etcd v3.5.18 metadata backing store for Milvus",
    },
    {
        "image": "minio/minio:RELEASE.2024-12-18T13-15-44Z",
        "engines": ("milvus", "tidb_br"),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-milvus-minio", "cdeadmin-demo-tidb-minio"),
        "ports": (),
        "purpose": (
            "MinIO S3-compatible object store for Milvus and opt-in TiDB BR "
            "backups"
        ),
    },
    {
        "image": "pingcap/pd:v8.5.6",
        "engines": ("tikv", "tidb"),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-pd", "cdeadmin-demo-tidb-pd"),
        "ports": ("127.0.0.1:52379->2379",),
        "purpose": "PingCAP Placement Driver v8.5.6 for TiKV and TiDB stacks",
    },
    {
        "image": "pingcap/tikv:v8.5.6",
        "engines": ("tikv", "tidb"),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": (
            "cdeadmin-demo-tikv", "cdeadmin-demo-tikv-2",
            "cdeadmin-demo-tikv-3", "cdeadmin-demo-tikv-4",
            "cdeadmin-demo-tidb-store-1", "cdeadmin-demo-tidb-store-2",
            "cdeadmin-demo-tidb-store-3",
        ),
        "ports": ("<host-ip>:52016..52019->20160",),
        "purpose": (
            "PingCAP TiKV v8.5.6 four-store API-v2 cluster and three-store "
            "TiDB backing cluster"
        ),
    },
    {
        "image": "pingcap/tidb:v8.5.6",
        "engines": ("tidb",),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": ("cdeadmin-demo-tidb",),
        "ports": ("127.0.0.1:54000->4000", "127.0.0.1:51000->10080"),
        "purpose": "PingCAP TiDB v8.5.6 distributed SQL server",
    },
    {
        "image": "vitess/lite:v23.0.3",
        "engines": ("vitess",),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": (
            "cdeadmin-demo-vitess-vtgate-1",
            "cdeadmin-demo-vitess-vtctld-1",
            "cdeadmin-demo-vitess-vtorc-1",
            "cdeadmin-demo-vitess-vttablet101-1..302-1",
        ),
        "ports": ("127.0.0.1:15306->15306", "127.0.0.1:15000->8080"),
        "purpose": "Vitess v23.0.3 sharded MySQL cluster (Compose topology)",
    },
    {
        "image": "hashicorp/consul:2.0.3",
        "engines": ("vitess",),
        "groups": ("all",),
        "bootstrap_client": False,
        "opt_in": False,
        "containers": (
            "cdeadmin-demo-vitess-consul1-1",
            "cdeadmin-demo-vitess-consul2-1",
            "cdeadmin-demo-vitess-consul3-1",
        ),
        "ports": ("127.0.0.1:8500->8500",),
        "purpose": "Consul 2.0.3 three-node topology store for Vitess",
    },
    {
        "image": "pingcap/ticdc:v8.5.6",
        "engines": ("tidb_ticdc",),
        "groups": ("opt-in",),
        "bootstrap_client": False,
        "opt_in": True,
        "containers": ("cdeadmin-demo-tidb-ticdc",),
        "ports": ("127.0.0.1:58300->8300",),
        "purpose": "Opt-in TiCDC v8.5.6 changefeed server for TiDB",
    },
    {
        "image": "pingcap/br:v8.5.6",
        "engines": ("tidb_br",),
        "groups": ("opt-in",),
        "bootstrap_client": False,
        "opt_in": True,
        "containers": (),
        "ports": (),
        "purpose": "Opt-in PingCAP Backup & Restore (BR) v8.5.6 CLI image",
    },
    {
        "image": "pingcap/tiflash:v8.5.6",
        "engines": ("tidb_tiflash",),
        "groups": ("opt-in",),
        "bootstrap_client": False,
        "opt_in": True,
        "containers": ("cdeadmin-demo-tidb-tiflash",),
        "ports": (),
        "purpose": (
            "Opt-in TiFlash v8.5.6 columnar learner node (requires >= 12 GiB "
            "Docker memory)"
        ),
    },
)

GROUP_NAMES = ("all", "core", "bootstrap", "local", "opt-in")


def select_images(target="all", include_opt_in=False):
    """Return catalog entries matching a group name or engine identifier."""
    if target in ("sqlite", "duckdb", "embedded"):
        return ()
    selected = []
    for entry in DOCKER_IMAGE_CATALOG:
        if entry["opt_in"] and not include_opt_in and target not in (
            "opt-in", *entry["engines"]
        ):
            continue
        if (
            target in entry["groups"]
            or target in entry["engines"]
            or (target == "all" and include_opt_in and entry["opt_in"])
        ):
            selected.append(entry)
    if not selected:
        raise KeyError(f"unknown image target or engine: {target}")
    return tuple(selected)


def local_image_present(image):
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def inspect_catalog(target="all", include_opt_in=True):
    rows = []
    for entry in select_images(target, include_opt_in=include_opt_in):
        rows.append({
            "image": entry["image"],
            "engines": list(entry["engines"]),
            "groups": list(entry["groups"]),
            "bootstrap_client": entry["bootstrap_client"],
            "opt_in": entry["opt_in"],
            "containers": list(entry["containers"]),
            "ports": list(entry["ports"]),
            "purpose": entry["purpose"],
            "status": "present" if local_image_present(entry["image"]) else "missing",
        })
    return rows


def pull_images(target="all", include_opt_in=False, dry_run=False):
    entries = select_images(target, include_opt_in=include_opt_in)
    if not entries:
        print(f"No Docker images required for embedded target: {target}")
        return []
    pulled = []
    for entry in entries:
        image = entry["image"]
        command = ["docker", "pull", image]
        print("+", " ".join(command), flush=True)
        if not dry_run:
            subprocess.run(command, check=True)
        pulled.append(image)
    return pulled


def valid_targets():
    engines = sorted({
        engine
        for entry in DOCKER_IMAGE_CATALOG
        for engine in entry["engines"]
    })
    return (*GROUP_NAMES, "embedded", "sqlite", "duckdb", *engines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "images", help="Inspect required pinned Docker images and local state",
    )
    list_parser.add_argument(
        "target", nargs="?", default="all", choices=valid_targets(),
    )
    list_parser.add_argument("--json", action="store_true")

    pull_parser = subparsers.add_parser(
        "pull", help="Pull pinned Docker images for a group or single engine",
    )
    pull_parser.add_argument(
        "target", nargs="?", default="core", choices=valid_targets(),
    )
    pull_parser.add_argument(
        "--include-opt-in", action="store_true",
        help="Also pull opt-in TiDB TiCDC, BR and TiFlash images when target=all",
    )
    pull_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "images":
        rows = inspect_catalog(args.target, include_opt_in=True)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                flags = []
                if row["bootstrap_client"]:
                    flags.append("bootstrap-client")
                if row["opt_in"]:
                    flags.append("opt-in")
                suffix = f" [{', '.join(flags)}]" if flags else ""
                engines = ",".join(row["engines"])
                print(
                    f"{row['status']:7}  {row['image']:45}  "
                    f"engines={engines}{suffix}"
                )
        return 0
    pull_images(
        args.target,
        include_opt_in=args.include_opt_in,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
