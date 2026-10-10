Vitess native driver contract
=============================

Vitess 23.0.3 owns keyspace/shard routing, transaction mode, tablet selection,
VSchema, distributed decisions and online DDL. The retained driver shares only
MySQL-wire transport, exact encoding/data bindings and result conversion with
other engines. Existing Vitess catalog, administration and control-plane forms
remain engine-specific. Unsupported MySQL administration is not enabled.

One operation owns a connection until its terminal result is observed. Ordered
result sets use ordinal column identity, 256-row/1 MiB page targets and a queue
of two pages; a single oversized cell can exceed the byte target. Native error
codes are preserved without logging SQL or credentials. Neither a lost query
reply nor a lost COMMIT reply triggers driver replay or reconnection. An unknown
outcome quarantines the session until close. A VTGate error packet may carry a
tablet/RPC failure after dispatch; only explicit statement rejection codes are
classified as known errors. Failed transaction commands remain uncertain. VTGate's own internal retry policy
is separate from driver replay; transaction mode is never silently promoted to
TWOPC or changed to SINGLE. Optional catalog reads do not roll back user work.

Cancellation aborts the retained transport socket, never a connection selected
by an unverified gateway-local numeric ID. The receipt explicitly requires close
and reports an unknown outcome, not server cancellation or transaction rollback.
This works through a load balancer without targeting a different VTGate process.
Connector/Python's pure implementation supplies the admitted socket boundary;
other implementations refuse cancellation if that boundary is unavailable.
Users can issue native KILL through their separately verified administrative
route. A broken connection alone cannot establish a distributed decision.

VTGate 23.0.3 COM_RESET_CONNECTION releases native transaction resources but does
not establish full isolation of all gateway session options and user variables.
Accordingly, pool capacity/configuration isolation remains enforced, but each
released Vitess lease discards its physical connection. No session is recycled
based only on a successful reset acknowledgement. Failed close retains ownership.

The portable driver gate requires an explicitly owned existing unsharded keyspace; it
creates and removes only uniquely named test tables. It qualifies values,
streaming, commit/rollback, retained metadata, socket cancellation, fresh leases,
and optional lost-commit confirmation against a native VTGate/tablet topology.
TLS/authentication follows the explicit route and is never weakened for a fault
fixture. MySQL TLS and the separately routed identity HTTP endpoint have distinct
verification policies. Windows/macOS receiving teams must run the gate using
their packaged dependencies before platform acceptance. Driver qualification is
not qualification of production sharding, backup, reparenting or failover.

Platform execution
------------------

Run ``python tools/cdeadmin_vitess_driver_platform_gate.py --route ROUTE
--evidence OUTSIDE_REPOSITORY`` with Connector/Python 26.7.0. The JSON route
identifies a disposable unsharded keyspace and its VTGate SQL and identity HTTP
endpoints, but contains no password. Credentials are prompted; --no-password is
only for an explicitly passwordless owned fixture. Set use_pure true for the
qualified cancellation path. TLS routes specify ssl_ca, ssl_verify_cert and
ssl_verify_identity. The optional --reply-loss uses plaintext loopback only and
does not change the route's security policy. Preserve source hashes and cleanup
status with each platform receipt. Separate sharded qualification must verify
native transaction mode, routing and observations at each target shard.
