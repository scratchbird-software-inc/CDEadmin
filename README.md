# ScratchRobin CDE Admin

**ScratchRobin** (short name **Robin**; repository and code namespace `CDEadmin`) is a multi-engine, multi-model **Convergent Data Engine (CDE) administrator** and visual design studio for ScratchBird and independently operated database engines. It unifies native database administration, SQL and non-SQL query workspaces, schema comparison, ETL/CDC, data lineage, replication topology, tracing, and Diagram-Design-Notation (`ddn-next-1`) designers for ERD/data modelling, dimensional cubes, BI questions/dashboards, and screen meshes.

- **Current Version**: `0.325-alpha` ([web/version.py](web/version.py) · [product_identity.json](web/pgadmin/cdeadmin/product/product_identity.json)) — pre-release; **24 engine connector roots / 27 provider profiles** in active qualification ([Status Matrix](docs/en_US/implementation_status.rst)).
- **Provenance & Licence**: ScratchRobin is an independent hard fork of pgAdmin 4 9.17, distributed under the PostgreSQL Licence ([LICENSE](LICENSE) · [NOTICE](NOTICE) · [Hard-Fork Policy](docs/en_US/cdeadmin_hard_fork.rst)). It is not affiliated with or endorsed by the pgAdmin Development Team.
- **Links**: [User Wiki](wiki/Home.md) · [Open-Source Site Source](website/index.html) · [ScratchRobin Product Page](https://scratchbird.ca/robin)

---

## Quick Start & Setup

- **AI-Agent Automated Setup (Linux, Windows PowerShell/WSL2, macOS):**
  Point your AI coding agent at **[docs/AI_AGENT_TEST_ENVIRONMENT_SETUP.md](docs/AI_AGENT_TEST_ENVIRONMENT_SETUP.md)**. It contains OS/version detection rules (`apt`/`dnf`/`pacman`, `glibc` checks, Windows PowerShell 5.1 & 7+, WSL2 vs Native x64, macOS Apple Silicon & Intel), all **29 pinned Docker images**, the full **users, roles, and passwords** catalog, test-database seeding, and ready-to-generate `start_robin` (Electron + Web Browser) and per-engine (`start | stop | status`) launcher scripts.
- **Step-by-Step Developer Guides:**
  [docs/DEVELOPER_SETUP.md](docs/DEVELOPER_SETUP.md) · [Linux / WSL2 / VM Guide](tools/development/README.md) · [Native Windows & macOS Guide](tools/development/NATIVE.md)

```bash
# Minimal Linux / WSL2 (x86_64) build & check — clone both sibling repositories:
git clone https://github.com/scratchbird-software-inc/CDEadmin.git
git clone https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git
cd CDEadmin
bash tools/development/dev.sh doctor
bash tools/development/dev.sh python && bash tools/development/dev.sh frontend && bash tools/development/dev.sh clients
make verify
```

---

## Supported Engines & Core Capabilities

- **Relational & Analytical SQL**: PostgreSQL, Firebird (network & embedded), MySQL, MariaDB, SQLite, DuckDB, ClickHouse, Dolt, XTDB, and ScratchBird (native roadmap; legacy-protocol interfaces run through their native engine providers).
- **Distributed SQL**: CockroachDB, TiDB, Vitess, YugabyteDB (YSQL & YCQL).
- **Key-Value, Wide-Column & Ledger**: Redis, Apache Cassandra, FoundationDB, TiKV, Apache Ignite, immudb.
- **Document, Graph, Search, Vector & Time-Series**: MongoDB, Neo4j, OpenSearch (native & SQL/PPL), Milvus, InfluxDB.
- **Unified Workspaces**: DDN-powered ERD & Data Modelling, Cube Designer, BI Questions & Dashboards, Screen Mesh Designer, Schema Comparison, Visual Administration, ETL & CDC Designers, Data Lineage, Data Quality, Replication Topology, Distributed Tracing, Data Discovery, and Governed AI Drafting.

---

## Documentation Map

| Topic | Documentation |
| :--- | :--- |
| **AI Test Environment, Docker Images & Engine Passwords** | [docs/AI_AGENT_TEST_ENVIRONMENT_SETUP.md](docs/AI_AGENT_TEST_ENVIRONMENT_SETUP.md) |
| **Developer Onboarding & Test Database Creation** | [docs/DEVELOPER_SETUP.md](docs/DEVELOPER_SETUP.md) |
| **Platform Setup (Linux/WSL2 vs Native Windows/macOS)** | [tools/development/README.md](tools/development/README.md) · [tools/development/NATIVE.md](tools/development/NATIVE.md) |
| **Reference Demo Estate & Per-Engine Lifecycle** | [tools/reference_engine_demos/README.md](tools/reference_engine_demos/README.md) |
| **Product, Provider & Security Architecture** | [docs/en_US/cdeadmin_architecture.rst](docs/en_US/cdeadmin_architecture.rst) |
| **UI Shell, Themes & Component Standards** | [web/pgadmin/static/js/cdeadmin_ui/ARCHITECTURE.md](web/pgadmin/static/js/cdeadmin_ui/ARCHITECTURE.md) |
| **DDN Integration & Native Schema Roundtrip** | [docs/en_US/ddn_adopted_runtime.rst](docs/en_US/ddn_adopted_runtime.rst) · [docs/en_US/ddn_database_roundtrip.rst](docs/en_US/ddn_database_roundtrip.rst) |
| **Implementation & Qualification Status Matrix** | [docs/en_US/implementation_status.rst](docs/en_US/implementation_status.rst) |
| **Python 3.14+ Runtime Policy** | [docs/en_US/python_runtime_policy.rst](docs/en_US/python_runtime_policy.rst) |
| **Security & Vulnerability Reporting** | [SECURITY.md](SECURITY.md) |
| **User Wiki & Building Sphinx HTML Docs (`make docs`)** | [wiki/Home.md](wiki/Home.md) · [docs/en_US/index.rst](docs/en_US/index.rst) |

---

## Repository Layout & Branch Policy

- `web/` — Python/Flask server, React frontend, and tests (`web/CDEadmin.py` is the canonical launcher).
- `web/pgadmin/cdeadmin/` — ScratchRobin provider adapters, UI descriptors, workspaces, and identity contracts.
- `runtime/` — Electron desktop application shell (`corepack yarn start`).
- `docs/` — Developer onboarding, AI setup playbook, architecture specs, and Sphinx documentation.
- `tools/` — Development launchers (`dev.sh`, `native.py`), DDN refresh (`refresh_ddn.py`), demo estate, and verification gates.
- `pkg/` — Platform packaging inputs (not yet approved for release signing).

**Shared Branch & Build Gate**: `master` is the shared development branch (`gh-pages` is kept separate for static site output). Always refresh the public [Diagram-Design-Notation](https://github.com/scratchbird-software-inc/Diagram-Design-Notation) (`ddn-next-1`) capture before direct Webpack, pytest, or Jest runs via `bash tools/development/dev.sh ddn` (`dev.sh frontend` and `native.py` run this automatically).

---

## Product identity and compatibility names

User-facing surfaces identify the product as **ScratchRobin** (**Robin**) or **CDEadmin** with engine-neutral artwork; engine names appear only where describing that specific engine. Legacy internal symbols (`pgadmin` Python/JS namespaces, `web/pgAdmin4.py`, and selected `PGADMIN_` runtime variables) remain temporarily for extension and state compatibility; new code uses `CDEadmin`, `cdeadmin`, or `CDEADMIN_`. Verify identity compliance after UI, runtime, packaging, or documentation edits with:

```bash
python3 tools/cdeadmin_product_identity.py --source .
```

---

## Licence and Attribution

ScratchRobin retains and modifies code from pgAdmin 4 (Copyright (C) 2013–2026, The pgAdmin Development Team) under the **PostgreSQL Licence**, and consumes standalone open `ddn-next-1` from [Diagram-Design-Notation](https://github.com/scratchbird-software-inc/Diagram-Design-Notation). Keep upstream copyright headers in inherited files; see [LICENSE](LICENSE) and [NOTICE](NOTICE) for full attribution. Report all ScratchRobin issues and security findings through ScratchRobin's own channels ([SECURITY.md](SECURITY.md)), never to upstream pgAdmin contacts.
