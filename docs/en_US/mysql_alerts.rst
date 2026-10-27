MySQL alert policies
====================

Open **Availability → Configure monitoring collection** on a MySQL server or
registered database. Add rules before starting collection. Each rule has a
native metric, a greater-than threshold, a continuous duration, severity,
missing-observation behavior and an optional notification route. Stop and
release collection before changing its rules or credentials. Dedicated sealed
collector credentials and the existing single-process worker admission apply.
Collection and delivery continue when this screen and all dashboards are closed.

The eleven metrics cover running threads, connection utilization, oldest InnoDB
transaction, native lock waits, aborted connections and slow-query rates,
disk-temporary-table and buffer-pool-read ratios, replication errors/stopped
services and collector availability. These are server measurements even when
collection is configured on a database. Ratios use observed native counters;
the temporary-table ratio does not cover every TempTable overflow mechanism.
Replication findings describe configured receivers, coordinators and workers;
they do not infer replication lag or regard an absent channel as healthy.
Observing ``information_schema.innodb_trx`` requires native ``PROCESS``;
Performance Schema sources require their native access and instrumentation.
Denied and permission-filtered observations do not establish complete instance
coverage. The collector does not grant itself additional privileges.

Pending rules require consecutive observations in one collector/server epoch.
A reconnect, reset, denied/stale/truncated metric, absent denominator or long
collection gap breaks duration continuity. Missing observations become unknown
by default and retain unresolved incidents. A rule can explicitly alert on
missing data after its configured duration. A successful below-threshold native
observation resolves an active incident. Values, source identity, observation
time and an actionable diagnostic suggestion accompany findings. No rule runs
remediation SQL.

Silence controls suppress notification delivery while collection and evidence
continue. Expiry or explicit unsilencing produces one notification on the next
firing observation. Pending queued deliveries are checked again for silence,
grant expiry, owner/registration changes and the admitted route. A transport
already in flight can complete after a silence or stop request.

Dashboards display findings through DDN observation bindings; collection policy
administration remains in its separate screen. Published bindings contain no
retained telemetry and receive unavailable values when current evidence is lost.

Configured notifications
------------------------

Administrators configure authenticated TLS SMTP profiles through
``CDEADMIN_REPORT_DELIVERY_PROFILES`` (see :doc:`report_delivery`) and fixed
owner-authorized destinations through ``CDEADMIN_MYSQL_ALERT_ROUTES``::

    CDEADMIN_MYSQL_ALERT_ROUTES = {
        'operations': {
            'label': 'Database operations',
            'owner_ids': [1],
            'profile_id': 'operations-smtp',
            'target': {'recipients': ['operations@example.com']},
        },
    }

The referenced SMTP profile must admit JSON and allow every configured
recipient. The policy screen exposes route labels to admitted owners. It does
not expose SMTP credentials or allow a browser to supply a transport address or
recipient. Select a route and start collection to authorize event delivery.
Changing an admitted route requires a fresh collector policy admission.

A dedicated worker has a 64-item queue; collection does not wait for SMTP.
Each transition sends a bounded JSON attachment using the existing durable,
idempotent delivery occurrence service. The policy screen shows queued,
delivering, delivered, suppressed, failed or outcome-unknown receipts.
Unknown transport outcomes are not retried automatically. Queue exhaustion and
authorization failures remain explicit failed deliveries. Configured delivery
occurrence retention follows the existing report-delivery settings.

Alert state, rules, silences and the last 100 transitions belong to the current
collector process and lease; starting a new policy creates a new evaluation
baseline. Persistent monitoring samples use the existing optional ScratchBird
integration. Its qualification remains owner-deferred and is separate from
alert delivery occurrence records in the application database. Windows/macOS
acceptance remains with the platform teams.
