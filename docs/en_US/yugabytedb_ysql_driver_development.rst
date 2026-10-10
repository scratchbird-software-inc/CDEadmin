YugabyteDB YSQL native driver contract
====================================

The admitted YSQL profile is YugabyteDB 2025.2.2.2. The PostgreSQL wire protocol
supplies transport and native text representation; YugabyteDB supplies the
transaction, consistency, catalog, topology and retry behavior. YCQL is a
separate provider and is not exposed through YSQL sessions.

YSQL and CockroachDB explicitly admit the same retained PostgreSQL-wire
mechanics: one connection owner, bounded ordered browser pages, exact scalar
bindings and text values, ordinal column identities, native backend-key
cancellation, savepoint-isolated optional metadata, configuration-specific pools
and reset on return. These mechanics do not enable PostgreSQL-only features.
The shared boundary is an implementation detail; each provider retains its
own exact runtime identity, language, forms, metadata and control plane.

A native 40001 requires an explicit caller decision to retry the transaction;
no query, mutation or decision is automatically replayed. An ambiguous 40003,
connection loss or unclassified transport failure quarantines the retained
session. COMMIT and ROLLBACK expose the native completion tag and transaction
status. Socket failure cannot determine a distributed transaction's outcome.
Cancellation transport failure is separate from the original query's native
completion. Neither cancellation nor metadata failure invents a rollback.
Optional metadata may skip only native missing, unsupported or permission
errors after verified savepoint recovery; serialization and recovery failures
propagate. Native YSQL savepoints and isolation levels remain user-selectable
through native SQL/connection policy, without a client retry helper.

Pools cannot share a connection across changed credentials, TLS options or
pool policies. A returned connection rolls back pending work, performs native
DISCARD ALL and resets driver transaction defaults. Implicit prepared statement
caching is disabled across resets. Failed resets discard the connection;
failed release retains ownership for cleanup retry. No uncertain connection is
returned live to a pool. Existing retained sessions never reconnect on failure.

The portable gate must qualify exact values, multiple result sets, paging,
parameter bindings, cancellation, metadata isolation, real concurrent-write
serialization conflict, lost COMMIT reply, pooled reset/reuse, TLS and native
release against the exact YSQL version. Linux qualification does not establish
native Windows/macOS packaging or UX acceptance; those teams execute the same
source-bound gate with their interpreter and dependencies.

Platform execution
------------------

Install psycopg and psycopg_pool with the project's packaged interpreter. Run
``python tools/cdeadmin_yugabytedb_ysql_driver_platform_gate.py --route ROUTE
--evidence OUTSIDE_REPOSITORY`` against an explicit server route JSON. Omit
database and password; the gate creates and removes its own random database
and prompts for the password. Certificate authentication uses --no-password
and explicit sslrootcert/sslcert/sslkey. The account needs CREATE DATABASE.
A concurrent update under YSQL REPEATABLE READ exercises native snapshot
serialization failure; SERIALIZABLE reads can instead block a competing write
and are not used to manufacture this test outcome.

Use verify-full for TLS qualification. The optional --reply-loss requires an
explicit plaintext loopback fixture, independently checks the committed row
and never downgrades a TLS route. Preserve source hashes, native versions,
cleanup result and the platform runtime with the resulting receipt.
