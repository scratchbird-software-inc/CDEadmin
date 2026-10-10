MongoDB driver contract
=======================

The default factory uses PyMongo 4.17.0 and the MongoDB 8.2.6 profile.
Each query session owns its MongoClient, ClientSession and single worker.
Only one result may be active. Explicit begin/commit/rollback and all Query
API operations run on that same session; administration retains its separate
native forms and connections. No application transaction callback is replayed.
PyMongo's documented retryable-write/commit protocol remains driver-owned.

JSON operations include find, aggregate, watch, command, insert_one,
insert_many, update_one, update_many, replace_one, delete_one, delete_many,
find_one_and_update, find_one_and_replace and find_one_and_delete. Documents,
filters and values accept canonical BSON Extended JSON. The command escape
hatch exposes native commands, but cannot supply session/transaction identity
or bypass the explicit transaction controls. Server authorization applies.

Find/aggregate results are paged until exhaustion, with no implicit 1,000 or
100,000 document truncation. Explicit limit/max_documents limits are honored.
Pages contain at most 256 documents, approximately 1 MiB, except that a single
legal BSON document may exceed that byte target. Change streams expose resume
tokens on each page, including empty heartbeat pages. Resume is explicit.
Canonical Extended JSON preserves binary, Int64, decimal, dates and ObjectId.

Local cancellation stops delivery; it does not prove rollback. Transport or
cursor errors quarantine the session, preserve an unknown outcome and require
explicit close/reconnect. Closing a session delegates native cleanup to
PyMongo; it never claims a successful transaction outcome. Native errors are
redacted, not converted into empty successful results. TLS/authentication,
replica-set/SRV/load-balanced routing, read/write concerns and optional native
retry settings retain the existing route and credential contracts.

Platform qualification
----------------------

Run tools/cdeadmin_mongodb_driver_platform_gate.py against a disposable
MongoDB 8.2.6 replica set with PyMongo 4.17.0 installed. Use an external evidence
directory. Windows/macOS teams run the same gate on their native platform;
Linux evidence does not qualify another platform. The gate uses a random
database and removes it after checking streaming, BSON and commit/rollback.
