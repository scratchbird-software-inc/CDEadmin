.. _implementation_status:

*********************
Implementation status
*********************

Status date and scope
=====================

14 October 2026. ScratchRobin CDE Admin remains **0.1.0-dev**. This page
describes source and local verification; it is not a production-readiness or
release approval. The pushed source baseline before this consolidation was
``ac0e766c4``. PostgreSQL, SQLite and shared-interface changes are part of the
consolidation tree described here only after their commit is pushed. The
resulting Git revision identifies the precise source; earlier receipts must
not be applied to a later revision by implication.

The explorer has **24 connector roots** (engine groupings) and **26 provider
profiles** (exact implementations). YugabyteDB YSQL and YCQL are different
profiles under one root; OpenSearch native and SQL/PPL are likewise different
profiles under one root. The old ``25 engines`` repository description does not
match either defined count and should not be used as a completion claim.

Status vocabulary
=================

``Native work`` means feature code, forms or adapters exist in the source.
``Provider baseline`` means a provider manifest and an exact driver/capability
surface exist; it does not imply complete management-console parity. ``Local
evidence`` means a specified test or live qualification completed against the
stated revision and runtime. ``CI-qualified`` would require a successful
GitHub run for that same revision. ``Release-approved`` would additionally
require the final platform, legal, security, packaging and UX gates. No profile
is designated release-approved here. A manifest's ``experimental`` or
``implemented`` value is a code-registration state, not a release verdict.

Per-profile source inventory
============================

The table describes the source tree, including the active consolidation change
set. It does not upgrade an exact provider's manifest gate or stand in for its
live evidence. Details and qualifications belong to the linked engine contracts
and test outputs.

.. list-table::
   :header-rows: 1
   :widths: 23 35 42

   * - Profile
     - Source state
     - Qualification still required
   * - PostgreSQL
     - Native administration and shared editor work; substantial current change set
     - Requalify exact PostgreSQL 18 workflows, forms and live engine paths
   * - Firebird
     - Native administration, FlameRobin comparison workflows and DDN integration
     - Close the remaining Firebird acceptance backlog and browser/platform review
   * - MySQL
     - Native administration, monitoring, SQL history and DDN review workflows
     - Complete exact-version end-to-end and browser acceptance
   * - MariaDB
     - Separate native catalog, history, monitoring and DDN workflows
     - Complete separate exact-version end-to-end and browser acceptance
   * - DuckDB
     - Registered-file catalog, native administration and DDN work
     - Complete manual UI, file-mode and platform acceptance
   * - SQLite
     - Native file, catalog, editor, monitoring and DDN change set
     - Local tests pass; complete manual UI/platform review
   * - Apache Ignite
     - Provider baseline and recorded exact-contract evidence
     - Full native-console and platform acceptance
   * - Apache Cassandra
     - Provider baseline and recorded native-dialect/object evidence
     - Full native-console and platform acceptance
   * - ClickHouse
     - Provider baseline
     - Full native-console and platform acceptance
   * - CockroachDB
     - Provider baseline and recorded semantic/control-plane evidence
     - Full native-console and platform acceptance
   * - Dolt
     - Provider baseline and recorded semantic/control-plane evidence
     - Full native-console and platform acceptance
   * - FoundationDB
     - Provider baseline and recorded exact-contract evidence
     - Full native-console and platform acceptance
   * - immudb
     - Provider baseline and recorded object/control-plane evidence
     - Full native-console and platform acceptance
   * - InfluxDB
     - Provider baseline
     - Full native-console and platform acceptance
   * - Milvus
     - Provider baseline
     - Full native-console and platform acceptance
   * - MongoDB
     - Provider baseline
     - Full native-console and platform acceptance
   * - Neo4j
     - Provider baseline
     - Full native-console and platform acceptance
   * - OpenSearch native
     - Provider baseline
     - Full native-console and platform acceptance
   * - OpenSearch SQL/PPL
     - Separate query-language provider baseline
     - Full exact-language and platform acceptance
   * - Redis
     - Provider baseline
     - Full native-console and platform acceptance
   * - TiDB
     - Provider baseline and recorded semantic/control-plane evidence
     - Full native-console and platform acceptance
   * - TiKV
     - Provider baseline and recorded exact-contract evidence
     - Full native-console and platform acceptance
   * - Vitess
     - Provider baseline and recorded semantic/control-plane evidence
     - Full native-console and platform acceptance
   * - XTDB
     - Provider baseline
     - Full native-console and platform acceptance
   * - YugabyteDB YSQL
     - Separate SQL provider baseline and recorded control-plane evidence
     - Full exact-dialect and platform acceptance
   * - YugabyteDB YCQL
     - Separate CQL provider baseline and recorded object/security evidence
     - Full exact-dialect and platform acceptance

Local verification and CI
=========================

Local tests and driver gates must be tied to the source revision, dependency
versions and retained logs. Earlier receipts do not automatically qualify a
later working tree. The consolidation tree passed 1,496 selected Python tests
covering PostgreSQL, SQLite, DuckDB and affected shared services, plus 486
changed/affected JavaScript tests in 26 suites. Its production webpack bundle
compiled. These are local source/consumer checks, not proof of every live native
workflow or platform form. The SQLite 3.53.0 local driver gate passed with its
exact runtime; PostgreSQL's broad local tests passed with the declared pglast
8.5 parser, while remaining exact-runtime live qualification is tracked in its
provider manifest. The consumed DDN snapshot was revision
``a08ccb297c477d668a7d287ab50d26ef3d5dd580``. Raw local run logs are
retained outside the implementation repository. Existing provider manifests
record bounded evidence for other profiles, not a common end-to-end pass.

At the 14 October inspection, the GitHub Actions runs associated with the
latest pushed commit ended in ``startup_failure`` with no jobs in the sampled
run. That is an infrastructure/startup observation, neither a passing nor a
failing application test. The cause needs independent investigation and a new
successful run before any current revision is called CI-qualified.

Current-run exclusions and open gates
=====================================

Persistent monitoring history in ScratchBird and the ScratchBird connection
are deferred. Windows/macOS implementation and UX qualification belong to
their platform teams. Persistent SQL history, saved DDN designs, dashboard
definitions and recipes remain in scope. Native ScratchBird management is
planned after reference-engine browser completion.

Remaining release gates include exhaustive browser interaction and accessible
state review, authentication/security mode matrices, large-result behavior,
independent exact-engine live tests, packaging/signing/update infrastructure,
and legal, security and release-engineering approval. A listed engine receives
only the capabilities of its exact provider and selected runtime; common forms
do not add features absent from the native engine.
