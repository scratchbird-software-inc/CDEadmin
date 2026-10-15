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

The explorer has **24 connector roots** (engine groupings) and **27 provider
profiles** (exact implementations). YugabyteDB YSQL and YCQL are different
profiles under one root; OpenSearch native and SQL/PPL are likewise different
profiles under one root; Firebird network and embedded are also separate
profiles. The old ``25 engines`` repository description does not
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
     - All 128 declared network administration tasks qualified through 24 native gates
     - Close the remaining Firebird acceptance backlog and browser/platform review
   * - Firebird Embedded
     - Separate local-file profile reusing native Firebird SQL administration; Linux Engine13 attachment evidence
     - Requalify backend/profile activation on the supported Python runtime and complete applicable platform acceptance
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

The subsequent Python policy migration raised the minimum to 3.14. A Linux
CPython 3.14.8 interpreter linked to the SQLite provider's exact 3.53.0
library passed the same 1,496 selected Python tests (and 174 subtests). The
portable SQLite exact-runtime gate also completed with no failures. The
newer standard Python 3.15 and free-threaded builds have dependency gaps;
their precise intake state is in :doc:`python_runtime_policy`. This does not
retroactively qualify all live providers or platform packages on Python 3.14.

In a later 14 October working-tree check, the SQLite 3.53.0 catalog navigator
reached all 90 non-root resources after its collapsed-database ownership fix;
the DuckDB 1.5.2 navigator reached all 1,013. Both audits still require an
independent native inventory comparison before catalog completeness can be
claimed. A disposable Firebird 5.0.4 Engine13 runtime passed the embedded
contract and profile-activation gate, and an isolated loopback Firebird 5.0.4
server passed provider activation, retained-session script, configuration,
query-plan, streaming, and two-server recovery gates; the embedded runtime
passed its recovery gate. The provider activation pass followed a correction
to Firebird trigger ALTER/DROP SQL identity and the live verifier's native
drafts. A separate generic dialect-task run exercised 51 tasks successfully
but left 77 declared task IDs unexercised, so it did not pass full dialect
qualification.
These checks used Python 3.12 because the prior Python 3.14 environment was
unavailable. Evidence lives
outside this repository under the corresponding working-tree revision and
does not qualify the full Firebird acceptance list.

The same working tree passed the exact SQLite 3.53.0 and DuckDB 1.5.2
relational-provider live gates: each reported all eight provider categories,
native editor operations, graphical object activation, and temporary-file
cleanup as passed. The SQLite check found and corrected a ``DROP TRIGGER``
compiler path that had included the trigger's navigator table parent as an SQL
qualifier. The verifier was also corrected to wait for SQLite's asynchronous
fault result and to use the native SQLite DROP draft shape. These are Linux
Python 3.12 observations, so supported-runtime and platform gates remain open.
Selected DDN/design tests (29), shared relational tests (108), and the seven
profiles' SQL-history/monitoring tests with MariaDB dashboard definitions
(246) also passed on that runtime. These selected tests are bounded source
checks, not complete native workflow qualification.

After Docker Desktop became available, seeded exact PostgreSQL 18.3, Firebird
5.0.4, MySQL 9.7.0 and MariaDB 12.2.2 runtimes verified. MySQL and MariaDB
provider activation gates passed all eight categories and native editor
operations using exact client tools in the external work area; MariaDB used
the pinned connector patch. PostgreSQL's real-application catalog gate
verified its exact driver and database/schema/table reads, while the native
driver gate passed 95 checks including DDN catalog capture, two-database
isolation and lost-reply handling. Privileged catalog navigator audits reached
all non-root resources for Firebird (2,443), MySQL (940) and MariaDB (1,375)
with no suppressed catalog-query errors. The lower-privilege MySQL and MariaDB
demo accounts reported permission-denied native catalog sections as partial
coverage. Independent native inventory comparison remains required.

The 14 October working tree was then qualified on an isolated CPython 3.14.8
build linked to SQLite 3.53.0. SQLite, DuckDB, Firebird network, MySQL and
MariaDB each passed the eight-category native provider activation gate with
graphical object activation and no operation failures. PostgreSQL passed its
95-check native driver, DDN catalog, two-database and lost-reply gate; its
real-application catalog gate passed as well. Firebird Embedded passed a fresh
Engine13 native contract and activation gate, and its generated dialect and
metrics contracts were rebound to that receipt. These are bounded Linux
backend checks, not full native inventory or browser/platform acceptance.
The Python 3.14 catalog walk reached all visible resources for SQLite (90),
DuckDB (1,013), Firebird (2,443), privileged MySQL (940) and privileged
MariaDB (2,059) without query failures. The MySQL and MariaDB demo accounts
remained permission-limited and marked inaccessible catalog sections as
partial coverage. All catalog audits still require independent native
inventory comparison.
The dedicated Python 3.14 dialect run covered every declared SQLite (32)
and DuckDB (35) task. MySQL exercised 55 of 105 and MariaDB 63 of 88 in
their generic native verifier; the remaining task IDs include server,
replication, partition and specialized object operations. Their separate
qualification gates must be reconciled before full dialect completion is
claimed.

Firebird network task qualification subsequently passed all 128 declared tasks
through the consolidated network-task gate on Python 3.14.8, driver 1.10.11 and
the exact 5.0.4 runtime. All 24 native component gates passed, with no missing
task IDs and unchanged implementation and DDN snapshots. Specialized receipts
close the 77 tasks absent from the generic verifier. The role-membership gate
checks USER/ROLE members, default status, delegation, partial revocation and
native permission outcomes. The administrator-mapping gate now verifies that
a failed task preserves caller-owned pending work instead of requiring an
implicit transaction rollback. The affected Python selection passed 85 tests.
This closes declared network administration task coverage; the broader Firebird
functional checklist, native catalog completeness and platform acceptance
remain separate open obligations.

The subsequent Firebird catalog-completeness gate independently compares raw
native identity multisets for all 25 supported categories in privileged network,
restricted network and embedded captures. It now walks every returned non-root
resource, including system package members and MON$ metric definitions. Same-named
accounts retain plugin-qualified identities; user attributes, publication settings
and table membership are recorded. Optional security gaps propagate through DDN
export and metadata search. See :doc:`firebird_catalog_completeness` for the
current-attachment scope, embedded SEC$USERS limitation, qualification command
and platform boundaries. This supersedes the earlier Firebird inventory-audit
qualification gap; other engines' independent inventory checks remain separate.

At the 14 October inspection, the GitHub Actions runs associated with the
latest pushed commit ended in ``startup_failure`` with no jobs in the sampled
run. That is an infrastructure/startup observation, neither a passing nor a
failing application test. The cause needs independent investigation and a new
successful run before any current revision is called CI-qualified.

Current-run scope and open gates
================================

The owner's newer direction brings persistent monitoring history and its
ScratchBird connection into this completion scope. Native ScratchBird
management, persistent SQL history, saved DDN designs, dashboard definitions
and recipes therefore remain open backend obligations. Form validation is
assigned to the human team. Windows/macOS implementation and qualification
require evidence from the platform teams before a cross-platform completion
claim.

Remaining release gates include exhaustive browser interaction and accessible
state review, authentication/security mode matrices, large-result behavior,
independent exact-engine live tests, packaging/signing/update infrastructure,
and legal, security and release-engineering approval. A listed engine receives
only the capabilities of its exact provider and selected runtime; common forms
do not add features absent from the native engine.


Firebird DDN exchange and migration
===================================

FB-COMP-03/09 now includes admitted workspace imports and complete view
validation, native graphical column handoff, stored dialect 1 planning, static
exact-value data DDN export/import, native SQL restoration and durable unknown
commit outcomes. The dedicated owned-fixture gate covers network and embedded
attachments on Linux Firebird 5.0.4. See :doc:`ddn_database_roundtrip` for the
contracts; platform-team and human-form evidence remain separate acceptance
requirements.


Firebird dashboards and collectors
===================================

FB-COMP-18/19 now includes registered-identity dashboard detail publication,
read-only navigation across DDN views, exact authorized live rebinding,
file-authorized embedded collection and native network account/role lifecycle
qualification. Source sampling remains independent of viewers and interactive
transactions. See :doc:`firebird_dashboard_collectors` for native gates and
process limits. Native ScratchBird historical-store acceptance remains open;
Linux collector evidence does not qualify Windows/macOS or human form validation.
