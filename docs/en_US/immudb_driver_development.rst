immudb native driver contract
=============================

immudb 1.11.0 is verified through both its PostgreSQL-wire identity and native
REST server information. SQL transport uses psycopg 3.3.4 ClientCursor text
binding; native immudb SQL, key/value, document, revision and proof administration
remain separate admitted surfaces. PostgreSQL wire does not imply PostgreSQL
storage, reset, catalog or transaction semantics.

One operation owns a retained session until terminal observation. Query workers
return ordered result sets in 256-row/1 MiB target pages with two queued pages;
native buffering is separate and one oversized value may exceed the target.
Columns retain ordinal identity. Integers outside the JavaScript safe range and
binary values use explicit lossless envelopes. SQL binary parameters are native
hex literals quoted by a dedicated psycopg dumper: PostgreSQL bytea literal text
must not be stored as the blob's contents. No query or uncertain decision is
reconnected or replayed automatically.

Native BEGIN, COMMIT and ROLLBACK responses remain engine-owned observations.
The original command tag is retained. Any failed transaction command quarantines
the session until close; a broken connection is not proof of rollback. Catalog
reads use an independent session so optional PostgreSQL-compatibility catalog
fallbacks cannot roll back a user's pending work. Explicit administration using
a retained SQL session shares its ownership guard.

Cancellation aborts only the retained socket, reports uncertainty and requires
session close. Physical pooled connections are discarded at release; generic
DISCARD ALL is not assumed to reset immudb state. Failed cleanup retains ownership
for retry. Native REST mutations are not retried. Proof responses remain native
evidence; a returned proof alone is not a claim of independent verification
against a trusted external anchor.

TLS policies for SQL and REST are explicit and independent. Neither transport
is downgraded after verification failure. Portable qualification creates only
uniquely named owned SQL tables and a key, verifies rollback/commit and exact blob values,
checks native proof/state access, streaming, pool disposal and reply-loss, and
removes its owned tables and tombstones its owned key. Native append-only
history of these fixture mutations remains until engine retention removes it. Platform teams run the gate with their packaged
libraries before declaring Windows/macOS native acceptance.

Run ``python tools/cdeadmin_immudb_driver_platform_gate.py --route ROUTE.json
--evidence OUTSIDE_REPOSITORY``. The gate prompts for credentials and requires
an owned writable namespace. Set ``database``, ``user``, SQL ``host``/``port`` and
REST ``web_host``/``web_port``. Use ``autocommit: true`` for gate setup; explicit
native BEGIN still retains pending work until the user's decision. SQL TLS uses
libpq ``sslmode: verify-full`` and ``sslrootcert``; REST independently uses
``web_tls_mode: verify-full`` and ``web_ca_file``. ``--reply-loss`` is limited to
an explicitly plaintext loopback fixture. Credentials must not be put in route
files. Preserve native configured row and transaction-size limits; the driver
does not turn a server refusal into a truncated successful result.

Qualified TLS packaging uses psycopg 3.3.4's Python implementation with libpq
16.13. The tested immudb 1.11.0 server rejects libpq 18.6's PostgreSQL ALPN offer
with ``no application protocol``. That is a native handshake incompatibility;
there is no plaintext fallback or certificate-check bypass. Ship the qualified
libpq runtime (``PSYCOPG_IMPL=python`` when selecting it explicitly) and rerun the
native gate for each packaged platform. A different client/server combination
requires its own TLS receipt. Libpq's ALPN status is documented at
https://www.postgresql.org/docs/18/libpq-status.html.

The native fixture also requires a correctly configured server trust store for
its internal SQL-to-gRPC authentication path. In the tested server, certificate
and key flags alone did not populate that internal trust; ``--auto-cert`` with
the supplied certificate did. This is server provisioning, not client TLS
verification. Fixture receipts record both endpoint and dependency versions.
