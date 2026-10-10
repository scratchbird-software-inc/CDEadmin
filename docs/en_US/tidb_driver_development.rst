TiDB native driver contract
===========================

The admitted TiDB profile is 8.5.6. Connector/Python supplies MySQL transport;
The pure implementation is the default; an explicit Boolean use_pure selects
the installed connector implementation without silent fallback.
TiDB owns transaction, consistency, DDL, retry and cluster semantics. Sharing
transport/value conversion does not enable MySQL Shell, stored routines,
triggers, or other unsupported MySQL administration features.

A retained connection has one execution owner until the result is observed.
Ordered native result sets use exact raw text/binary conversion and ordinal
column identity, with two queued browser pages and 256-row/1 MiB page targets.
A single large cell may exceed the byte target. Parameters use the existing
exact MySQL-wire envelopes. Neither driver connection loss nor a failed commit
causes reconnection or statement replay. A decoded TiDB conflict/deadlock is
reported with its native code and explicit retry indication; unknown outcomes
block reuse until close. Native server retry policy remains TiDB-owned.

Optional catalog errors must not roll back pending user work. TiDB statement
errors for missing, unsupported or permission-restricted optional catalogs may
be skipped without a client rollback; transaction/conflict/transport errors
propagate. Administration and transaction control share execution ownership.

Cancellation uses TiDB's KILL TIDB QUERY and the retained connection ID, with
origin process identity observed through TiDB's server/process catalogs. The
all-zero compatibility server_uuid is not a usable server identity. Cancellation
refuses when exact live origin identity cannot be verified; ordinary execution
remains available without catalog privileges. A cancellation request is separate
from the original query's terminal outcome and never establishes rollback.

Pools remain provider-owned and credential/configuration-specific. Reset uses
native rollback and COM_RESET_CONNECTION; unknown connections are discarded.
Failed native cleanup retains ownership for retry. TLS verification follows the
explicit route and is never weakened to run plaintext fault injection.

Portable qualification exercises real TiDB 8.5.6 with PD/TiKV, exact values,
streaming, optimistic conflicts, decisions, cancellation, metadata, pool reset,
TLS/authentication and lost COMMIT confirmation. A single-node test topology is
not production cluster/failover qualification. Windows/macOS packaging and UX
acceptance require receiving-team native runs.

Platform execution
------------------

Run ``python tools/cdeadmin_tidb_driver_platform_gate.py --route ROUTE --evidence
OUTSIDE_REPOSITORY`` with the packaged Python and mysql-connector-python. Supply
an explicit server route without database or password; the gate prompts for
credentials and creates/drops a random owned database. Use --no-password only
for an explicitly passwordless owned fixture. Run once with use_pure true and
once with false when the platform includes the C extension. The optional
--reply-loss requires explicit plaintext loopback and does not alter TLS routes.
Exact integer/decimal envelopes use encoding/data; binary uses encoding=base64
and data, with optional verified byte_length. Preserve the emitted source hashes
and cleanup status with each platform's receipt.
