Native language and script tooling contract
==========================================

Status and scope
----------------

The six required SQL engines also follow :doc:`six_engine_completion`, which
records the current editor gaps and full product acceptance obligations.

This contract defines required ScratchRobin language-tool behavior. It does not
certify current full-language implementation. Engine inventories, keyword lists,
wire compatibility, successful native execution and individual administration
form tests do not establish full statement or script syntax coverage.

The statement editor, completion, validation, formatting, script framing,
metadata/DDL extraction and execution must share one resolved language context.
No engine may silently inherit another engine's language because it uses the
same network protocol. Non-SQL engines require native command or API schemas,
not a fabricated SQL dialect.

Language identity
-----------------

The resolved context includes engine, provider, interface, endpoint, observed
server version, database/namespace, native language, compatibility mode, query
engine, installed extensions, session syntax settings and grammar revision.
Firebird additionally distinguishes database, attachment and statement dialect.
Dolt includes branch/ref. YSQL and YCQL retain their separate endpoints.

A generic family label or combined language label is not a validation identity.
Language switching must select the native endpoint and refresh session-bound
syntax/completion state. It must not silently change a running operation or
an existing transaction. Switching behavior follows the provider's session and
transaction contract, with an explicit outcome when switching is unavailable.

Current compatibility routing
-----------------------------

InfluxDB recognizes the exact query aliases ``sql`` / ``influxdb3-sql`` and
``influxql`` / ``influxdb3-influxql``. OpenSearch recognizes ``sql`` /
``opensearch-sql`` and ``ppl`` / ``opensearch-ppl``. These exact aliases select
the named language even when the connection default selects the other language.
Case folding is permitted; substring matching and unrelated profile IDs are
rejected before a native query is sent.

Existing combined profiles ``influxdb3-sql-influxql`` and
``opensearch-sql-ppl`` preserve their explicit connection defaults for backward
compatibility. An absent language retains that default. These combined profiles
are not full editor dialect identities; separate end-to-end studio contributions
and session bindings remain required. Invalid defaults and non-string language
values are rejected. These dispatch checks do not parse the query.

Validation authority and completeness
-------------------------------------

Every language surface needs separately recorded evidence for:

* Versioned grammar or native API schema, lexical rules, quoting and reserved
  words, expressions, statements, procedural bodies and supported extensions.
* Editor tokenization and diagnostics with exact source ranges, Unicode offsets,
  incomplete-edit handling, cancellation and document-generation checks.
* Syntax validation distinct from catalog binding, authorization, type checking,
  feature availability and execution-time errors.
* Script framing, client directives, includes, variable expansion, parameters,
  embedded bodies, data payloads and native stop/error behavior.
* Native positive/negative acceptance cases and cross-language rejection cases.
  Inventory counts alone cannot satisfy this acceptance.

Validation reports identify their authority: local grammar, native parse/prepare,
API-schema validation, limited classification, or unavailable. Unknown or
unverified syntax is not reported as either valid or invalid. Executing a query
and rolling it back is not syntax validation. Native prepare/explain paths may
only be used when the exact statement class and provider contract establish
that the validation request has no execution side effects.

The UI displays the selected language/version/mode and distinguishes a local
syntax result from native acceptance. A plain text input or MIME declaration
must not be described as a language-aware validator. Full-source execution may
remain available under its own permissions without claiming successful preflight
validation. A user override must not change an unsupported grammar into a
qualified one.

Script boundaries
-----------------

Semicolon splitting is insufficient. Each language adapter owns string/comment
rules, quoted identifiers, dollar-quoted bodies, compound statements, delimiters,
batch blocks, native client commands and data framing. Client commands are never
sent blindly as server statements. Dangerous local client commands and includes
require an explicit supported command policy; file/credential access is not
inherited from ordinary SQL execution.

A script plan records source spans, native statements versus client directives,
parameter scopes, execution order, transaction boundaries, error policy and
results. It preserves the provider's outcome semantics. Network loss does not
justify automatic replay of an uncertain write. Multi-statement support in a
driver is not proof of a complete native client-script interpreter.

Completion and formatting
-------------------------

Completion uses the same selected dialect and permission-filtered catalog
snapshot. Functions, operators, overloads, types and keywords are versioned.
Mode/catalog changes invalidate incompatible caches. User identifiers are not
rewritten using rules from a different engine. Formatting preserves comments,
quoting, literals, client directives and embedded-language boundaries. Unsupported
syntax is preserved rather than reformatted with an unrelated grammar.

Metadata extraction and generated statements
--------------------------------------------

The extraction manifest records language identity and required modes/extensions.
Generated administration SQL keeps its provider-owned dialect independently of
an editor override. A script containing multiple language contexts has explicit
boundaries and adapter selection; the implementation may reject such a script
rather than guess. An exported API/configuration document is not advertised as
replayable SQL.

Qualification and release gate
------------------------------

Qualification is per engine/version/interface/language/mode, never inherited
from a whole engine or transport. Required tests include nested quotes/comments,
Unicode, body delimiters, identifiers, expression and DDL families, invalid native
forms, neighboring-engine syntax, version changes, mode changes, stale replies,
read-only validation and native error positions. Test both parse acceptance and
rejection; verify script boundaries and parameter handling independently.

Publish the grammar/schema revision, reference provenance, representative and
production-family coverage, unsupported extensions, native test identity and
residual gaps. Only verified surfaces may be marked complete. Engine/version
updates or changes to syntax settings require affected-consumer requalification.

Required language surfaces
--------------------------

The following is a coverage obligation, not a list of currently implemented
editors. Optional native query engines, extensions and client interpreters are
shown only when installed and admitted. Compatibility modes do not imply feature
parity with the original vendor language.

.. list-table:: Native language coverage
   :header-rows: 1
   :widths: 15 30 55

   * - Engine
     - Language surface
     - Required selection context
   * - firebird
     - Firebird DSQL
     - Client dialect 1/2/3; database dialect 1/3; dialect 2 is transitional, not a database format
   * - firebird
     - Firebird PSQL
     - Routine, trigger and EXECUTE BLOCK bodies; server version and external-engine admission
   * - firebird
     - Firebird isql-style scripts
     - SET TERM and admitted client commands; not server SQL
   * - mysql
     - MySQL SQL
     - Exact version/storage engine; sql_mode including ANSI_QUOTES and NO_BACKSLASH_ESCAPES
   * - mysql
     - MySQL stored-program bodies
     - Compound statements, handlers, labels and native language extensions
   * - mysql
     - MySQL client scripts
     - DELIMITER and explicit supported client commands; not server statements
   * - mariadb
     - MariaDB SQL
     - Native version and sql_mode; independent from MySQL
   * - mariadb
     - MariaDB Oracle compatibility mode
     - Mode-dependent syntax/types/packages; not Oracle Database feature parity
   * - mariadb
     - MariaDB routine/package bodies
     - Default SQL/PSM versus Oracle-mode syntax, selected explicitly
   * - mariadb
     - MariaDB client scripts
     - DELIMITER and client directives; native sql_mode tracked
   * - postgresql
     - PostgreSQL SQL
     - Exact version; standard_conforming_strings; extensions
   * - postgresql
     - PL/pgSQL bodies
     - Dollar quoting and function/procedure blocks; installed languages are separate
   * - postgresql
     - psql scripts
     - Meta-commands, variables, includes and COPY stdin data framing are client syntax
   * - sqlite
     - SQLite SQL
     - Compile options, extensions, enabled features and connection settings
   * - sqlite
     - SQLite shell scripts
     - Dot commands must be routed to a qualified client-script adapter, never SQL
   * - duckdb
     - DuckDB SQL and macro bodies
     - Exact version; extensions; scalar/table macros
   * - duckdb
     - DuckDB shell scripts
     - CLI commands separate from engine SQL
   * - cockroachdb
     - CockroachDB SQL
     - Native version and feature gates; not full PostgreSQL
   * - cockroachdb
     - CockroachDB PL/pgSQL bodies
     - Native restricted routine/trigger grammar; not upstream PostgreSQL parity
   * - yugabytedb
     - YugabyteDB YSQL
     - YSQL endpoint and exact bundled PostgreSQL/Yugabyte grammar
   * - yugabytedb
     - YSQL procedural bodies
     - YSQL native supported routine/trigger grammar
   * - yugabytedb
     - YugabyteDB YCQL
     - Separate YCQL endpoint; not Cassandra feature parity
   * - dolt
     - Dolt SQL and stored-program bodies
     - Native version; branch/ref binding; Dolt procedures and table functions
   * - dolt
     - Dolt SQL client scripts
     - Batch command behavior must be qualified independently of MySQL CLI
   * - cassandra
     - Cassandra CQL
     - Server version; CQL BATCH is grammar, not naïve semicolon splitting
   * - cassandra
     - cqlsh scripts
     - COPY/SOURCE/DESCRIBE and client commands require exact client-version admission
   * - apache_ignite
     - Ignite H2-based SQL
     - Configured H2 query engine/version and Ignite DDL dispatch
   * - apache_ignite
     - Ignite Calcite SQL
     - Configured Calcite query engine/version; no H2 fallback
   * - apache_ignite
     - Ignite cache API
     - Typed request schemas and operations; no SQL grammar
   * - foundationdb
     - FoundationDB API
     - Selected API version, transaction/tenant context and typed requests; no SQL
   * - foundationdb
     - fdbcli commands
     - Administrative command grammar; not SDK JSON or SQL
   * - tikv
     - TiKV RawKV API
     - v1/v1ttl/v2 keyspace and API types
   * - tikv
     - TiKV transactional API
     - Transactional requests and context; no SQL
   * - tidb
     - TiDB SQL
     - Native TiDB grammar and sql_mode; reject unsupported MySQL routines/events/triggers
   * - vitess
     - Vitess SQL
     - VTGate/version/VSchema/sharding semantics; MySQL wire is not MySQL grammar parity
   * - vitess
     - Vitess administration API
     - Control-plane commands and schemas distinct from VTGate SQL
   * - redis
     - Redis commands / RESP
     - Server version and module command metadata; inline CLI syntax is distinct from RESP framing
   * - redis
     - Redis Lua scripts/functions
     - Installed scripting engine/version, key/argument contracts and permitted APIs
   * - mongodb
     - MongoDB query/aggregation API
     - BSON/Extended JSON representation, operators, stages and feature compatibility
   * - mongodb
     - mongosh JavaScript
     - Shell/runtime APIs and asynchronous behavior; JSON validity is not JavaScript or MQL validation
   * - milvus
     - Milvus query/search API
     - Typed request structure and vector/search parameter schemas
   * - milvus
     - Milvus filter expressions
     - Native Plan grammar; no generic SQL parser
   * - clickhouse
     - ClickHouse SQL
     - Native settings, table engines, functions and formats
   * - clickhouse
     - ClickHouse KQL
     - Configured dialect/build feature; ClickHouse subset, not universal Kusto
   * - clickhouse
     - ClickHouse PRQL
     - Configured dialect/build feature and bundled translator version
   * - clickhouse
     - ClickHouse client input
     - Multiquery framing and INSERT FORMAT payload boundaries
   * - influxdb
     - InfluxDB 3 SQL
     - Exact embedded query engine and InfluxDB supported statements/functions
   * - influxdb
     - InfluxDB 3 InfluxQL
     - Dedicated InfluxQL parser and endpoint; not SQL and not full InfluxDB 1.x
   * - influxdb
     - Influx line protocol
     - Ingestion framing, escaping and field/timestamp types; not SQL
   * - neo4j
     - Cypher 5
     - Explicit CYPHER version/default policy and native server admission
   * - neo4j
     - Cypher 25
     - Separate pinned parser and server version; installed procedures/functions
   * - neo4j
     - Cypher shell scripts
     - Shell directives, parameters and statement framing distinct from Cypher
   * - opensearch
     - OpenSearch Query DSL
     - JSON schema plus registered query/aggregation/analysis types
   * - opensearch
     - OpenSearch SQL
     - SQL plugin/version/planner configuration and supported language subset
   * - opensearch
     - OpenSearch PPL
     - Separate PPL grammar and endpoint; never guessed from source text
   * - opensearch
     - OpenSearch stored/inline scripts
     - Admitted script language, script context, sandbox and version; not Query DSL
   * - immudb
     - immudb SQL
     - Native version; PostgreSQL wire does not imply PostgreSQL grammar
   * - immudb
     - immudb key/value API
     - Versioned key operations and proof schemas
   * - immudb
     - immudb document API
     - Collection/document/query request schemas
   * - xtdb
     - XTDB SQL
     - Bitemporal syntax and native functions; not PostgreSQL SQL
   * - xtdb
     - XTQL
     - Native JSON/Clojure representation and distinct API transport
   * - scratchbird
     - ScratchBird native SQL/PSQL
     - Owning Core grammar and actual provider/parser registration
   * - scratchbird
     - ScratchBird registered compatibility dialects
     - Enumerate implemented parser profiles individually; do not infer all engines from the intended feature superset

Implemented editor and script boundary
-------------------------------------

Data Studio exposes ``source_validate`` using the retained session's exact
language binding. It returns positioned lexical or JSON diagnostics and never
executes source to validate it. ``grammar_valid`` remains unknown unless a
provider supplies a safe native validator; local acceptance is not full grammar,
API-schema, privilege or semantic certification. The optional provider port is
``validate_source_without_execution``; ordinary execution is not its fallback.

InfluxDB SQL/InfluxQL and OpenSearch SQL/PPL have separate language and session
contributions. A session records its exact language and rejects execution or
embedded command language overrides. Legacy combined contributions remain for
persisted callers; new editing should select the explicit language. Switching
languages closes the previous provider session before opening another.

Beyond the existing Firebird adapter, ``native_script_prepare`` frames bounded
SQL/CQL source into statements with offsets and a source hash. MySQL-family
DELIMITER, PostgreSQL-family dollar quoting, SQLite trigger bodies and CQL
batches have explicit framing. Unobserved backslash modes, embedded import data,
executable comments, syntax-changing session commands and unsupported client
commands are refused. InfluxQL, PPL and Cypher script framing remains unavailable;
these languages retain individual-query execution and lexical diagnostics.

``native_script_advance`` uses a retained plan ID and expected revision. Repeating
a revision observes the current plan without submitting again. Each native
statement must reach a provider-confirmed usable terminal result before the next
can start. Errors stop sequencing; unknown outcomes retain the session reservation.
Other queries and scripts cannot use a reserved session. Stop does not imply
cancel, commit or rollback. Discard is refused while an outcome is unresolved.
Confirmed provider session closure releases its in-memory plans.

Plans are bounded to 32, each source to 2 MiB and each script to 1000 statements.
They live in the owning application process, not durable recovery storage. A
worker restart or loss of the owning browser context requires native outcome
reconciliation; the application must not replay source automatically. HTTP retry
safety is scoped to a retained plan in that process. Parameterized script batches,
full native grammar validators, and additional client-language adapters require
further provider-specific work; they are not implied by lexical support.
