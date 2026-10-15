Firebird dashboards and collectors (FB-COMP-18/19)
*************************************************

Implementation
==============

The Firebird engine, registered-endpoint and database dashboards use the paired
DDN runtime as passive viewers. The authorized context-menu editor uses the DDN
unified tool. Saving a draft, publishing a saved revision, viewing observations
and starting a collection policy remain separate operations. Publication never
starts a collector, changes its credentials or applies native SQL.

Published layouts include fixed database/service metrics and registered endpoint,
database, aggregate and finding bindings. Endpoint and database bindings use
registration IDs, including encoded target IDs, rather than display names or
list positions. Reordering registrations cannot bind another database's values
to a saved widget. A removed or unavailable identity becomes unavailable. All
contained views validate through the current public DDN runtime. The viewer's
read-only view selector reaches additional compositions and detail views and
retains its selection across sample refreshes.

The editor seeds a new draft from an authorized observation snapshot so the
native binding identities are available. Sampled values are replaced with
unavailable placeholders before the draft is supplied to the editor or a saved
revision is published. Published revisions remain independent of later drafts.
Live values are rebound only from the current authorized observation, using the
public DDN replaceData API. Native integer/decimal strings stay exact. Source
labels and appearance remain definitions, not historical measurements.

The binding contract is ``firebird-observations-v1`` in the exact module
``scratchrobin.firebird.monitoring``. It admits one dashboard.ddn source file,
one observations data block, string-valued value/unit/rate fields and at most
4096 admitted records within the 512 KiB source limit. Dynamic identities name
only known observation families; they cannot request SQL, credentials, routes
or filesystem access. Imports and external data resolution are not part of this
publication contract. Excessive or invalid definitions fail as a whole. Layout
validation retains its bounded memory/time/concurrency limits. Monitoring HTTP
responses, including authorization failures, use Cache-Control: no-store.

Network collection and authentication
====================================

A network policy admits a dedicated native username/password and optional role,
or explicit reuse of the selected registration's credentials. The worker seals
its password under the configured worker key; it never borrows an interactive
connection or Flask login lease. Responses expose authentication mode, account,
role and admitted policy values, never the password. Native authentication and
monitoring privileges determine availability and visible scope.

Policy-enabled collection continues without a viewer. Each database sample owns
one short read-only native monitoring transaction, ends it before the next sample
and excludes its own attachment from user activity detail. Service observations
use independent native Services API handles. Periodic activity does not read SQL
BLOBs, account personal attributes or logs. Existing bounded, separately
authorized detail operations remain available on demand.

Stop revokes the grant and requires confirmed native release. An unconfirmed
release remains owned and blocks replacement; retrying Stop can finish cleanup.
Only then can another account or policy be started. A failed native login produces
an unavailable sample and cannot refresh an availability heartbeat. Reconnect
changes the source epoch and establishes a new rate baseline. Expiry and current
owner/route/generation/target revocation stop collection and release its native
source; values obtained after revocation are not published.

Embedded collection
===================

Embedded Firebird admits registered database-file collection with explicit
embedded_runtime and filesystem permissions. The collector uses the embedded
provider's own client/profile and validates the registered filesystem root and
contained file before connection and during reauthorization. It still owns a
separate attachment and fresh read-only monitoring transaction.

Engine13 authorizes local file access rather than checking a network password.
The policy therefore reports local-file authentication and refuses supplied
monitoring passwords or a wire-encryption requirement. A worker encryption key
is not required when no credential is delegated. Single-process admission, a
collector lock, lease and current scope authorization remain required. File
collection never switches to a network attachment.

The embedded endpoint dashboard aggregates observations of its registered files.
It explicitly states that no remote server Services API observation exists.
Server collection, server log/path operations and network service tasks are not
advertised for embedded endpoints. Database monitoring and dashboard editing
remain reachable from their native context menus. Native optional catalogs,
including unavailable embedded security account inventory, remain unavailable
rather than becoming successful empty observations.

Persistence and acceptance boundaries
=====================================

Versioned dashboard definitions/bindings use the existing owner/endpoint/target
project-asset repository. Recent samples and policy grants remain process-local.
Restart requires explicit admission of a new collection lease; multiple web
processes are not a distributed collector scheduler. ScratchBird remains the
intended persistent observation store, with independent source/destination
transactions and failure reporting. Both network and embedded file policies can
opt into that existing history pipeline; see :doc:`monitoring_history`.

Native history acceptance still requires a serving ScratchBird destination and
the separate history gate. Its previously reported engine startup failure is
owned by the engine team. Collector and dashboard qualification does not replace
that gate or imply a successful historical write. Windows/macOS qualification
belongs to the platform teams. Form validation belongs to the human team.

Qualification
=============

Use the admitted Firebird 5.0.4 runtime and the project's native-driver Python
environment. Refresh the paired DDN runtime/tool before each validation run,
as required by AGENTS.md. On Linux::

    LD_LIBRARY_PATH=/path/to/firebird/lib python \
      tools/cdeadmin_firebird_dashboard_collectors_gate.py \
      --runtime-root /path/to/firebird \
      --evidence /outside/repository/qualification

The gate uses independently staged configuration, security database, loopback
server and temporary databases. Each scenario runs in its own process. It checks
source-runtime fingerprints and owned process/state cleanup. Credentials and
native diagnostic text are excluded from retained failure receipts.

The network scenario qualifies restricted native visibility, independent native
transactions, request/compiled-plan/call-stack inspection, metadata/page inventory,
Services API observations, account/path/log detail, wrong-password failure,
background sampling and revocation. Host scenarios qualify native role-based
network collection and local-file embedded collection, two samples without a
viewer, preserved interactive transactions, coalescing, native reconnect/rate
epoch reset, release failure/retry, expiry, reconfiguration and revoked-scope
cleanup. Captured native samples also pass through the shipping engine/server/
database DDN adapters, publication redaction, exact live rebinding and rendering
of every generated view. Unit/consumer checks additionally cover immutable asset
revisions, stale publication conflicts, registered identity reordering/removal,
all-view validation and passive view navigation.
