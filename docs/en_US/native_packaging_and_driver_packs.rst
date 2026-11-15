.. _native_packaging_and_driver_packs:

***********************************************
Native executables and per-engine driver packs
***********************************************

Status: 13 November 2026
========================

Owner direction, 2026-11-13: ScratchRobin distributes as small, optimised,
platform-specific native executables paired with signed, platform-specific
per-engine driver packs (``.srpack``), rather than shipping a general-purpose
Python virtual environment, pip/wheel tooling, external vendor CLI distributions
or every engine's client libraries in the base download.

Locked owner decisions (2026-11-13)
-----------------------------------

1. **Share underlying driver packs unless native functionality would be lost.**
   Wire-compatible engines share a single binary driver pack when the shared
   driver preserves full native protocol, type and attribute support. Where a
   shared driver would drop engine-specific fidelity—notably MariaDB's patched
   ``mariadb`` C connector (exact temporals and native types) versus MySQL's
   patched ``mysql-connector-python`` (MySQL 9.7 query attributes)—each keeps
   its own driver pack. Multi-protocol engines (such as YugabyteDB spanning
   YSQL and YCQL) resolve multiple shared packs automatically.
2. **Do not bundle external vendor CLI utilities.**
   ScratchRobin does not ship vendor command-line distributions (``pg_dump``,
   ``pg_restore``, ``psql``, ``mysqlsh``, ``mysqlbinlog``, ``mysql``,
   ``mariadb-dump``, ``mariadb-binlog``, ``mariadb-upgrade``, ``gbak``,
   ``nbackup``, ``gfix``, ``isql``, ``fdbcli``, ``fdbbackup``, ``cqlsh``,
   ``ycqlsh``, ``nodetool``, ``sstableloader``) in Core or in driver packs.
   Administrative, backup/restore, binlog and scripting workflows execute
   natively inside ScratchRobin over engine wire protocols, C libraries and
   service APIs. Users who want standalone external CLIs use the engine's own
   installer; ScratchRobin keeps optional host binary path overrides for
   passthrough use only.
3. **Two-tier native Python compilation (PyInstaller for iteration, Nuitka for
   releases).**
   Both tiers use directory-mode builds (``--onedir`` / ``--standalone``, never
   slow ``--onefile`` ``/tmp`` self-extractors) against the same custom CPython
   3.14 ``libpython`` + tracked SQLite 3.53.0 build, static module manifest and
   ``.srpack`` ABI contract:

   * **Fast iteration and PR CI:** ``PyInstaller --onedir`` validates frozen
     imports, packaged templates/catalogs, desktop sidecar startup and dynamic
     ``.srpack`` loading in under a minute.
   * **Release and nightly qualification:** ``Nuitka --standalone --lto=yes``
     compiles ScratchRobin's Python backend and server-side DDN layout/tiling
     libraries into native C/machine code while exporting standard
     ``libpython3.14`` C-API symbols for ``.srpack`` extension modules.

4. **Complete and qualify inside Electron before migrating the desktop shell to
   Tauri v2.**
   Keep the existing Electron runtime while delivering the dependency split,
   native CLI replacements, ``zstd`` asset/catalog packs, ``.srpack`` manager,
   and PyInstaller/Nuitka frozen ``scratchrobin-core`` executables. Migrate the
   desktop UI shell from Electron to Tauri v2 (OS WebView: WebView2, WebKitGTK,
   WKWebView) only after Phases 1–3 are proven and qualified in Electron.

Target platforms and SKUs
=========================

Each release builds six single-architecture platform targets across two SKUs:

* **Targets:** ``linux-x86_64`` (``manylinux_2_28``, ``-march=x86-64
  -mtune=generic`` so older Xeon and virtualised ``kvm64`` hosts never trap on
  ``SIGILL``), ``linux-aarch64`` (``manylinux_2_28``), ``windows-x86_64`` (MSVC
  v143), ``windows-arm64`` (MSVC ARM64), ``macos-arm64``
  (``MACOSX_DEPLOYMENT_TARGET=13.0``) and ``macos-x86_64``
  (``MACOSX_DEPLOYMENT_TARGET=13.0``). macOS artefacts are single-architecture
  per download, never fat ``universal2`` binaries.
* **SKUs:**

  * **Desktop** (``scratchrobin-<platform>-<arch>``): desktop UI shell +
    ``scratchrobin-core`` local server + ``assets.pack.zst`` (target ``~28 MiB``
    compressed download after Phase 4 Tauri migration; ``~66–83 MiB`` on disk).
  * **Server / Remote Dashboard Viewer**
    (``scratchrobin-server-<platform>-<arch>``): ``scratchrobin-core`` +
    ``assets.pack.zst`` only (target ``~23 MiB`` compressed download), serving
    Web Mode and the display-only remote BI dashboard viewer mode.

Core executable requirements
============================

1. **Build-time module and blueprint manifest (``_frozen_manifest.py``).**
   Frozen builds do not walk filesystem directories with
   ``werkzeug.utils.find_modules()`` or ``os.walk()``. A build-time generator
   emits ``web/pgadmin/_frozen_manifest.py`` covering all blueprints, browser
   modules and dynamic registries; test generators and ``web/regression/`` are
   excluded unless ``PGADMIN_TESTING_MODE == '1'``.
2. **Seekable Zstandard asset and catalog pack (``AssetResolver``).**
   SQL/Jinja2 templates, ``ui_descriptors``, compiled ``.mo`` translations (with
   source ``.po`` files omitted), and the refreshed DDN ``current/`` snapshot
   are served from ``assets.pack.zst`` via CPython 3.14's standard-library
   ``compression.zstd`` module and a custom Jinja2 ``FrozenPackLoader``.
   Lightweight ``provider_manifest.json`` and connection descriptors stay in
   Core so all 24 engines remain visible before their pack is installed; large
   engine metric and codec JSON catalogs ship compressed inside each pack's
   ``catalogs.zst``.
3. **Core runtime baseline and dependency boundary.**
   Core embeds the custom CPython 3.14 runtime whose ``_sqlite3`` dynamically
   links the tracked **SQLite 3.53.0** library (compiled with
   ``ENABLE_SESSION``, ``ENABLE_PREUPDATE_HOOK``, ``ENABLE_CARRAY``,
   ``ENABLE_DBPAGE_VTAB``, ``ENABLE_DBSTAT_VTAB``, ``ENABLE_FTS5``,
   ``ENABLE_RTREE``, ``ENABLE_GEOPOLY``, ``ENABLE_MATH_FUNCTIONS`` and
   ``ENABLE_PERCENTILE``) plus its native C helper libraries, supporting
   ``cdeadmin.db``, ``designs.db`` and out-of-the-box SQLite administration
   with zero pack downloads. Pure-Python HTTP/JSONL analytical providers
   (ClickHouse, InfluxDB 3, OpenSearch and OpenSearch SQL/PPL) and the
   pure-Python ScratchBird (``SBsql``) SDK also reside in Core. Reference-only
   CI verification libraries (``clickhouse-connect``, ``influxdb3-python``,
   ``opensearch-py``, ``pytest``, ``selenium``) live strictly in qualification
   requirement files and are never bundled.

Native replacements for external vendor CLIs
============================================

.. list-table::
   :header-rows: 1
   :widths: 22 26 52

   * - Subsystem
     - Retired bundled CLI
     - Native ScratchRobin implementation
   * - SQLite AST schema rewriter
     - ``sqlite3`` CLI (``CDEADMIN_SQLITE_BINARY`` in
       ``sqlite_native_rebind.py``)
     - Isolated native helper (``cdeadmin_sqlite_rebind`` / internal child mode
       of ``scratchrobin-core``) invoking
       ``sqlite3_test_control(SQLITE_TESTCTRL_INTERNAL_FUNCTIONS, 1)`` directly
       against Core's tracked ``libsqlite3`` 3.53.0.
   * - Firebird 5.0
     - ``gbak``, ``nbackup``, ``gfix``, ``fbsvcmgr``, ``isql`` and
       ``runtime/src/js/firebirdIsql.js``
     - ``libfbclient`` Services API (``isc_service_attach`` / ``IMaster``) for
       logical backup, restore, incremental ``nbackup``, sweep, validation and
       trace/user administration; ``cdeadmin/providers/firebird/scripts.py``
       and ``script_cursor.py`` for multi-statement/``SET TERM`` script
       execution.
   * - PostgreSQL
     - ``pg_dump``, ``pg_restore``, ``psql``
     - Native ``ddn_database_roundtrip`` DDL discovery/generation + ``psycopg``
       streaming ``COPY TO STDOUT`` / ``COPY FROM STDIN`` + native script
       execution (retaining ``DEFAULT_BINARY_PATHS`` as an optional user
       override).
   * - MySQL & MariaDB
     - ``mysqlsh`` (+ private OpenSSL), ``mysqlbinlog``, ``mysql``,
       ``mariadb-dump``, ``mariadb-binlog``, ``mariadb-upgrade``
     - Native wire-protocol schema/data export, binlog event stream decoding
       and replay, and ``_cdeadmin_*`` native physical/recovery C workers.
   * - FoundationDB
     - ``fdbcli``, ``fdbbackup``, ``fdbrestore``
     - ``libfdb_c`` C API over ``\xff\xff/status/json``,
       ``\xff\xff/management/*`` and transactional key-range streaming.
   * - Apache Cassandra & YugabyteDB YCQL
     - ``cqlsh``, ``ycqlsh``, ``nodetool``, ``sstableloader``
     - Native ``cassandra-driver`` CQL execution, ``COPY`` streaming and
       ``system_views.*`` / ``system_schema.*`` inspection.
   * - TiKV
     - *(None — first-party bridge retained)*
     - ``cdeadmin-tikv-helper`` compiled from
       ``web/pgadmin/cdeadmin/providers/tikv/go_helper`` is ScratchRobin's own
       first-party Go gRPC/PD adapter and ships inside the ``tikv`` pack.

Driver pack format, OS loader rules and 24-engine matrix
========================================================

Pack format and verification
----------------------------

Each pack archive
(``driver-pack-<pack_id>-<version>-<platform>-<arch>-cp314_abi<N>.srpack``) is a
Zstandard tarball containing ``manifest.json``, a detached Ed25519 signature
(``manifest.sig``), ``pylib/``, ``native/lib/``, ``catalogs.zst`` and
third-party ``LICENSES.txt``. ``PackManager`` verifies SHA-256 digests and the
Ed25519 signature before atomic extraction under
``DATA_DIR/driver_packs/<abi_epoch>/<pack_id>/``, supporting both one-click
HTTPS installation from **Settings › Database Engines** and offline ``.srpack``
file import for air-gapped environments.

OS dynamic linker and signing invariants
----------------------------------------

* **Linux (``ld-linux.so``):** Mutating ``LD_LIBRARY_PATH`` in Python after
  process startup does not affect transitive shared-library resolution. Every
  ``.so`` and helper inside a Linux ``.srpack`` must set
  ``RPATH``/``RUNPATH`` to ``$ORIGIN:$ORIGIN/../native/lib`` via ``patchelf``
  at build time.
* **macOS (``dyld`` and Hardened Runtime):** ``pkg/mac/entitlements.plist.in``
  enforces ``com.apple.security.cs.disable-library-validation = false`` and
  ``com.apple.security.cs.allow-dyld-environment-variables = false``. Every
  Mach-O ``.so`` and ``.dylib`` in a macOS ``.srpack`` must rewrite library
  references to ``@loader_path/../native/lib`` via ``install_name_tool`` **and**
  be signed with the exact same Apple Developer Team ID (``%TEAMID%``) as
  ``scratchrobin-core``.
* **Windows (``LoadLibraryEx`` and Authenticode):** ``PackManager`` registers
  ``pack_root / 'native/lib'`` with ``os.add_dll_directory()`` before importing
  compiled ``.pyd`` extensions or ``ctypes.WinDLL`` targets, and all ``.pyd``,
  ``.dll`` and helper ``.exe`` binaries are Authenticode-signed.

13-pack matrix covering all 24 engines
--------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 18 28 40 14

   * - Pack ID
     - Engines served
     - Native / Python contents
     - Est. download
   * - *(Core built-in)*
     - SQLite, ClickHouse, InfluxDB 3, OpenSearch (Query DSL + SQL/PPL),
       ScratchBird (``SBsql``)
     - Tracked ``libsqlite3`` 3.53.0 + 5 C helpers; HTTP/JSONL
       ``analytic_stream`` drivers; pure-Python ``scratchbird`` SDK
     - ``0 MiB``
   * - ``pg-wire``
     - PostgreSQL, CockroachDB, YugabyteDB (YSQL), immudb, XTDB
     - ``psycopg[c]==3.3.4`` (``libpq``), ``psycopg_pool``, patched
       ``pglast==8.5`` (``libpg_query``), ``lz4``, family catalogs
     - ``~5.8 MiB``
   * - ``mysql-wire``
     - MySQL, TiDB, Vitess, Dolt
     - Patched ``mysql-connector-python==26.7.0`` (MySQL 9.7 C API query
       attributes), ``_cdeadmin_*`` C workers, family catalogs
     - ``~4.4 MiB``
   * - ``mariadb``
     - MariaDB
     - Patched ``mariadb==1.1.14`` (exact temporals/types),
       ``mariadb-connector-c`` 3.4.8 (``libmariadb``), ``_cdeadmin_*`` C
       workers, MariaDB catalog
     - ``~1.9 MiB``
   * - ``firebird``
     - Firebird 5.0 (Network & Embedded)
     - ``firebird-driver==1.10.11``, ``libfbclient`` 5.0.4, ``plugins/libSrp``,
       ``plugins/libEngine13``, ``libtomcrypt``, ``firebird.msg``,
       ``plugins.conf``, codec catalog
     - ``~6.1 MiB``
   * - ``duckdb``
     - DuckDB
     - ``duckdb==1.5.2`` (``_duckdb`` C++ extension) + DuckDB catalog
     - ``~16.2 MiB``
   * - ``arrow-analytics`` *(optional)*
     - Arrow/Parquet import & DuckDB Arrow bridge
     - Trimmed ``pyarrow==25.0.1`` (core + ``libarrow`` + ``libparquet`` + IPC)
     - ``~12.5 MiB``
   * - ``cassandra-wire``
     - Apache Cassandra, YugabyteDB (YCQL)
     - ``cassandra-driver==3.30.1`` Cython extensions, ``lz4``,
       ``python-snappy``, ``pyasyncore`` (Win32), Cassandra/YCQL catalogs
     - ``~2.6 MiB``
   * - ``mongodb``
     - MongoDB
     - ``pymongo==4.17.0`` (``_bson``, ``_cmessage``), ``pymongo-auth-aws``,
       ``dnspython``
     - ``~1.2 MiB``
   * - ``redis``
     - Redis
     - ``redis==6.4.0``, ``hiredis`` C extension
     - ``~0.5 MiB``
   * - ``neo4j``
     - Neo4j
     - ``neo4j==6.3.0``, ``pytz`` (+ optional Rust Bolt extension)
     - ``~0.6 MiB``
   * - ``milvus``
     - Milvus
     - ``pymilvus==2.6.5``, ``grpcio`` (``cygrpc``), ``protobuf``, ``ujson``
     - ``~5.9 MiB``
   * - ``foundationdb``
     - FoundationDB
     - ``foundationdb==7.3.77`` + ``libfdb_c`` 7.3.77
     - ``~2.1 MiB``
   * - ``tikv``
     - TiKV
     - First-party ``cdeadmin-tikv-helper`` Go gRPC client adapter
     - ``~5.2 MiB``
   * - ``apache-ignite``
     - Apache Ignite
     - ``pyignite==0.6.1`` (+ C binary-protocol extension)
     - ``~0.4 MiB``
   * - ``enterprise-auth-cloud`` *(optional)*
     - Kerberos/LDAP auth, Cloud deployment wizards, PDF export
     - ``gssapi``/``krb5``, ``ldap3``, ``reportlab``, ``boto3``, ``azure-*``,
       ``google-api-python-client`` (zstd discovery docs)
     - ``~14.0 MiB``

Build pipeline and phased execution order
=========================================

Every frozen build and pack build preserves the mandatory DDN intake freshness
gate (``tools/refresh_ddn.py`` against the public ``Diagram-Design-Notation``
repository) as **Stage 1** before frontend bundling (Stage 2,
``NODE_ENV=production`` without shipped sourcemaps), asset/catalog zstd packing
(Stage 3), custom CPython 3.14 + SQLite 3.53.0 compilation and Core freezing
(Stage 4A/4B), per-pack wheelhouse assembly and RPATH/signing (Stage 4C/5), and
zero-pack + live-pack smoke verification (Stage 6). Intermediate staging trees
are built outside the repository and removed once verified artifacts are
published.

Implementation proceeds in four sequential phases:

1. **Phase 1 (Electron + dev venv):** Native replacements for external vendor
   CLIs, ``requirements/core.txt`` vs. pack split, ``AssetResolver`` (``zstd``
   catalogs), and ``PackManager`` + Settings UI.
2. **Phase 2 (Electron + PyInstaller ``--onedir``):** ``_frozen_manifest.py``,
   ``FrozenPackLoader``, fast-loop ``scratchrobin-core`` binary, ``.srpack``
   wheelhouse builder (``patchelf`` / ``install_name_tool`` /
   ``add_dll_directory``) and Electron sidecar integration.
3. **Phase 3 (Electron + Nuitka ``--standalone``):** Native C/LTO compilation
   for release targets alongside PyInstaller PR gates across all six OS/arch
   targets.
4. **Phase 4 (Tauri v2 + PyInstaller/Nuitka):** Replace the ``342 MiB``
   Electron desktop runtime with a ``~10 MiB`` Rust Tauri v2 shell after Phases
   1–3 are fully qualified in Electron.
