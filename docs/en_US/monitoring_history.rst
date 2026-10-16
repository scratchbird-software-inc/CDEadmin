Persistent monitoring history
=============================

Firebird network/embedded database-file collectors and MySQL/MariaDB server/database
collectors can opt into a native
ScratchBird archive with
``history_enabled: true`` in the monitoring policy. Collection remains independent
of viewers and user connections. The destination connection and transaction are
owned by the archive writer. The source is never committed or rolled back by it.
The in-memory dashboard still describes current collection; archived observations
are opened separately through **Persistent history** in the display-only viewer.
The existing DDN trend renderer displays both original and downsampled samples.

Deployment
----------

Install the official ScratchBird Python native DB-API driver from the engine
release matching your deployed ScratchBird runtime. No alternate SQL database is
used when the driver, schema or destination is unavailable. Configure the following
in the application's server configuration (not a browser request)::

    CDEADMIN_MONITORING_HISTORY = {
        'enabled': True,
        'namespace': 'unique-installation-id',
        'connection': {
            'host': 'history.example.org', 'port': 3092,
            'database': 'monitoring', 'user': 'monitoring_writer',
            'sslmode': 'verify-full', 'sslrootcert': '/etc/cdeadmin/history-ca.pem',
            'connect_timeout': 5, 'socket_timeout': 10,
        },
        'password_env': 'CDEADMIN_HISTORY_PASSWORD',
        'raw_days': 7, 'rollup_days': 90, 'bucket_seconds': 300,
    }

Use a dedicated destination database. The operator provisions its account with
SELECT/INSERT/UPDATE/DELETE privileges on the archive tables; schema initialization
requires CREATE privileges. Use a separate installation namespace and the existing
single-process collector ownership lock. Multiple independent writer processes
must not share a namespace: rollup updates are serialized by that owner process.
The password is resolved at connection time, allowing environment secret rotation
without persisting the value in policies or records. Do not put a password or DSN
in the connection configuration. Native transport settings are the driver's own
settings; deploy verified TLS for a remote destination.

Write the same history dictionary as JSON to an operator-owned configuration file,
without a password, then run with the application environment and native driver::

    python tools/cdeadmin_monitoring_history.py initialize --config /etc/cdeadmin/history.json

Initialization is explicit and intended once per dedicated database. It creates
``cde_monitor_history``, its scope index and a version table. Initialization is
never performed by a viewer GET or collector startup. An unconfirmed initialization
must be inspected at the destination before rerunning; there is no automatic
schema repair or migration. Unsupported versions fail closed.

Schedule maintenance independently of collection, for example every hour using
the deployment's scheduler::

    python tools/cdeadmin_monitoring_history.py maintain --config /etc/cdeadmin/history.json

Collection also prunes expired records at most once per minute when writing.
Queries enforce retention even before physical cleanup. Physical removal without
active collectors requires the scheduled maintenance command. Backups are subject
to the destination operator's own retention and deletion policy.

Records and downsampling
------------------------

Records retain owner, installation, engine, endpoint and target identity, policy
revision, hashed route/generation revision, source epoch, coverage revision,
observation timestamp and separate ingestion timestamp. Passive metadata groups
are retained with metric groups. Exact integers and decimal strings stay exact.
Explicit SQL inspection, credential resolution and native log detail responses
never enter this pipeline. The archive excludes credential, SQL text and context
variable fields from passive collector output and bounds each sample to 2 MiB.

Each observed sample and its rollup update share one destination transaction.
Repeated identical sample IDs are idempotent; conflicting reuse is refused.
Rollups separate policy, route, metadata revision, source epoch, rate epoch, coverage and availability
status. They retain observation count, first/last observation time and exact
minimum/maximum/count for numeric scalar fields. They use the latest observation
as their display representative; they neither sum cumulative counters nor invent
transaction TPS. Downsampled rate plots explicitly show gaps. Exact summaries
and source provenance can be expanded below the historical trend viewer.

A bucket is not evidence of continuous collection. Missing observations, unavailable
sources, expired grants and history write failures are not interpolated. Subsequent
confirmed writes include the count of preceding unconfirmed observations. A failed
commit reply is unconfirmed even if the destination committed; the writer never
replays that sample automatically. Live sampling continues, with separate
``history_storage`` status, latest sample identity, phase and failure count.
Source observation and destination ingestion are not a distributed transaction.

Query interface
---------------

Authenticated ``GET /cdeadmin/api/monitoring/firebird/<server-id>/history`` and
``GET /cdeadmin/api/monitoring/mysql/<server-id>/history`` take
``target_id`` for a registered database, required timezone-aware ISO ``start`` and
``end`` timestamps, ``tier=raw|rollup``, ``limit`` (1–720) and optional returned
``after`` cursor. Windows are bounded by configured rollup retention. Pages are further capped at 32 records and 8 MiB; follow the returned cursor
even when fewer than the requested number of samples is returned. Results
are ordered by observation time and stable record identity; pages are independent
reads, not a database snapshot spanning requests. New late ingestions may require
reloading the window. Results include retention cutoffs and provenance.

Owner/endpoint/target admission is checked before and after destination I/O.
Read access works when the collector is disabled and never starts a source
connection or acquires collector ownership. Unauthorized or changed scopes expose
no samples. Responses are not cached. The archive API does not accept destination
credentials, SQL, table names or browser-supplied routes. It exposes no dashboard
layout mutation controls.

Qualification
-------------

The unit contract suite uses an explicitly labeled SQLite SQL double to verify
application behavior; this is not a product fallback or native ScratchBird proof.
Native qualification additionally requires a serving ScratchBird server/listener,
the matching native Python driver, and restart/retention/isolation checks against
that destination. Platform teams own Windows/macOS evidence. The current supplied
Linux runtime's startup failure must be resolved before native completion is claimed.

Run native qualification against an isolated destination using::

    python tools/cdeadmin_monitoring_history_gate.py --config /etc/cdeadmin/history.json

Add ``--initialize`` only for a new dedicated database without archive tables.
The gate uses a fresh private namespace, verifies native commits, restart reads,
exact values, idempotency, owner isolation, epoch boundaries, pagination and
retention, and expires its own records. It never changes another namespace.
An engine process restart is a separate deployment durability acceptance check.
