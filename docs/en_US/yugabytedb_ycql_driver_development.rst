YugabyteDB YCQL native driver contract
====================================

The admitted profile is YugabyteDB 2025.2.2.2, YCQL protocol v4 and
cassandra-driver 3.30.1. YCQL is distinct from YSQL. Table-configured distributed
transactions, conditional mutations and native transaction/batch statements
retain YCQL semantics; no SQL COMMIT/ROLLBACK session controls are invented.

Execution returns a retained operation before awaiting its first response.
One operation owns a session until its terminal observation. Native paging
continues until exhaustion or an explicit local stop; the query driver must
not silently truncate results at 10,000 records. At most two browser pages
are queued, with 256-row/1 MiB targets (one larger cell may exceed the target).
Native frame/result memory is outside that queue bound. Each page identifies
its ordinal and row offset. Column keys are ordinals, preserving repeated
labels; dictionary row factories must not collapse duplicate projections.

Exact integer, decimal, binary, UUID, inet and temporal parameter envelopes
use native prepared binary bindings. Text interpolation can narrow decimal
literals before storage and is not admitted for parameterized execution.
Positional question marks and legacy %s / %(name)s placeholders are accepted;
translation skips quoted identifiers, strings and comments. Collection values retain their native
structure. Large integers and nonfinite floats are tagged at the JSON boundary;
map keys are represented as typed key/value pairs rather than coerced to
strings. Decimal, binary, temporal, UUID, UDT, tuple and set values retain
explicit representations. Raw browser-unsafe integer parameters are rejected.

No driver retry after uncertain dispatch or speculative execution is admitted.
The native driver may reprepare after an explicit UNPREPARED rejection, which
confirms the rejected execution did not run; this is distinct from replaying
an uncertain mutation.
Topology discovery and connection establishment may reconnect, but must not
replay a dispatched mutation. Native validation/permission errors are reported
without query/credential text. Timeout, connection loss and unknown execution
errors retain uncertain outcome and block session reuse until close. Conditional
mutation applied indicators are native results, never inferred successes.

Protocol v4 has no server query cancellation command. Cancel stops local
result delivery and further paging, while the original dispatched request
continues to its native response or timeout. A local stop does not establish
server cancellation, transaction rollback, or absence of mutation effects.
Close waits for operation ownership to end, then shuts down both native session
and cluster. Failed cleanup retains ownership for retry. Closed clients refuse
new sessions. Failed profile verification follows the same owned cleanup path.

The production provider retains the existing YCQL catalog, structured native
forms, administration, tracing and version API verification. SQL-only and
Cassandra-only features are not added. Linux native qualification and portable
source-bound gates support the Windows/macOS teams; their native packaging and
UX acceptance still require their own runs.

Platform execution
------------------

Run ``python tools/cdeadmin_yugabytedb_ycql_driver_platform_gate.py --route ROUTE
--evidence OUTSIDE_REPOSITORY`` with the packaged Python and cassandra-driver
3.30.1. The explicit route identifies the YCQL host/port and its version API
host/port. The gate creates a random keyspace, creates and drops its own table,
then drops the empty keyspace as required by YCQL. It checks more than 10,000
rows and may take several minutes. Use --password-prompt for password routes;
credentials are leased in memory and must not appear in the route JSON.

Use system-ca TLS with tls_check_hostname true and an explicit trusted CA for
TLS qualification. The optional --reply-loss requires a separate uncompressed
plaintext loopback fixture. Its native protocol decoder withholds an observed
mutation success, verifies the row independently, and counts original dispatches.
Local cancellation stops delivery only. CSV and other tabular exports use
ordinal column keys while preserving duplicate display labels.
