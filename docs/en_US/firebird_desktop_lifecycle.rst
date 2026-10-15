Firebird desktop and lifecycle
==============================

FB-COMP-13–17 have engine-specific workflows and Linux native qualification.
Form validation remains human-owned. Windows/macOS feature qualification remains
with the platform teams; the native development environment qualification does
not qualify these desktop tools on those hosts.

Docker provisioning — FB-COMP-13
--------------------------------

The Firebird connector-root menu opens SR-F-001368. The local Electron host
selects the Docker executable and context. Preparation displays the actual
context endpoint, daemon identity, immutable official Firebird 5.0.4 image,
container name, published SQL/event ports, database filename and persistent
storage. It may pull the image but does not create resources. Browser-only
clients cannot run Docker on the application server.

Creation requires the reviewed configuration, a separately entered bootstrap
SYSDBA password and explicit confirmation. The daemon and image are checked
again. Storage is either a new named volume or a selected empty local directory;
directory mounts require a Unix-socket context and a matching canonical path,
device/inode and empty contents. Existing resources are preserved. The password
travels in the child environment, without command arguments or receipt storage.
Docker administrators can read the resulting container environment, and the
qualified image reapplies the bootstrap password at restart.

Credential-free receipts persist before each mutation. A consumed review cannot
be replayed, including after restart. Partial and lost-response outcomes retain
resource names and the last phase for inspection. Running is a Docker observation;
Firebird authentication and database readiness require separate verification.
Registration is an explicit handoff to the existing native registration form.

External ISQL — FB-COMP-14
---------------------------

The registered TCP database menu opens SR-F-001366. The server returns an
owner-scoped connection description without credentials; the Electron desktop
selects a local Firebird 5 ISQL executable and a Konsole or xterm terminal. The
launcher checks the executable version and uses argument arrays without a shell.
The user explicitly supplies the independent attachment's password, username,
role, charset and client dialect. Passwords replace inherited Firebird identity
variables in the child environment and are not saved or put in arguments.

The displayed database address is explicitly TCP. Embedded or server-local paths
cannot be reinterpreted as desktop files. Only the application's current same-
origin top frame may use the desktop bridge. The launch receipt reports process
creation; native authentication, SQL execution and transaction decisions belong
to ISQL. Browser-only clients cannot start a terminal on the application server.

Registration clone/move — FB-COMP-15
-------------------------------------

SR-F-001369 changes local registration metadata. Clone creates a new inactive
identity; move preserves the identity under a selected same-owner Firebird server
and leaves it inactive. Neither operation opens, copies, creates or drops the
native database. Name collisions are refused. Both endpoint configuration guards
must admit the operation without rerouting or finalizing pending work.

The catalog exposes source and destination configuration generations. Transfer
must carry both reviewed generations; a later configuration change refuses the
request. Conditional writes also serialize competing transfers. Switching the
selected registration invalidates the previous review and its asynchronous
responses; an old completion cannot refresh or label the new selection.

The source-credential option takes an independent saved encrypted password,
username, role and charset snapshot. Missing saved passwords remain missing;
process-only passwords are not persisted. The destination option inherits its
endpoint credentials, including role and charset, rather than retaining source
identity overrides. Native database options remain attached to the registration.
Passwords remain excluded from catalogs, previews and responses, and participate
in existing credential clearing and key rotation. Connection verification after
transfer is a separate explicit action and does not assert a file exists remotely.

Recreate empty — FB-COMP-16
----------------------------

The database shortcut reuses drop SR-F-000027 followed by create SR-F-000026.
An approved server creation root must already exist before destructive work.
The original database's filename is retained for the separate creation review.

Handoff requires a successful native drop for the exact selected registration,
a completed local registration-removal receipt and a returned catalog in which
that registration is absent. Missing evidence, a different identity or failed
cleanup blocks creation. Native success and local cleanup are reported separately.
The drop cannot be repeated by this workflow after dispatch. A lost response or
uncertain outcome requires inspection rather than automatic retry.

The user explicitly opens creation, reviews its plan and confirms it separately.
Closing after drop leaves the database absent. Creation failure does not restore
it. The replacement has a new native database and registration identity; no
schema or data is preserved. A successful creation allocates a fresh registration
even when another alias already points to the filename. Existing aliases survive;
a display-name collision reports local follow-up failure without repeating native
creation. Deleting an inactive alias also invalidates reviewed generations.
Successful registration changes refresh the owning navigator branch.

Native events — FB-COMP-17
---------------------------

SR-F-001363 owns a dedicated authenticated native attachment and event collector.
Subscriptions accept 1–15 unique event names of at most 127 UTF-8 bytes. Counts
are cumulative decimal strings without JavaScript integer rounding. Notifications
are observed at native commit; rolled-back POST_EVENT operations do not deliver.
The latest 1000 observed increases can be exported as JSON Lines. Observation
timestamps are not commit timestamps or durable event history.

Polling renews the 120-second lease. Short diagnostic reads release their native
transactions immediately. Stop, expiry, failed heartbeat and a stopped native
callback thread release the collector and attachment, reporting confirmed release
or cleanup uncertainty. Failed worker startup also retains a pollable receipt
when attachment cleanup fails. Native errors are represented by type, without
private exception text.

Reconnect is explicit after confirmed release and starts a new identity and
observation interval. Disconnected intervals cannot be replayed. A lost start
response blocks another start in that form; idle expiry is the fallback for the
unknown subscription. Switching databases releases a late start or poll through
its original endpoint and target. Old counts, errors and file imports cannot
replace the new database's state. Closing also requests owned cleanup.

Subscriptions are process-local and require request affinity. Network events
require a reachable Firebird auxiliary port in addition to SQL connectivity.
Neither a failed socket nor a launched terminal proves native attachment release.

Qualification
---------------

Native Firebird 5.0.4 acceptance covers embedded and TCP event commit/rollback,
explicit reconnect, lease expiry and release; network attachment termination
additionally verifies delivery gaps and truthful cleanup outcomes. Docker
qualification uses both new named volumes and empty bind directories, including
SQL authentication and actual delivery over the configured published event port.
A deliberately lost container-create response retains the created resources,
refuses replay and does not automatically start or delete them.

The real ISQL/Konsole launch runs in an isolated virtual display. Keyboard input
and a separate native observer prove uncommitted invisibility, explicit commit,
rollback and detach. Process arguments contain no password. Native recreation
proves file absence after drop, an empty replacement, overwrite refusal and final
drop. Persisted registration clone/move qualification proves stable identities,
inactive results, no native opens during transfer, and preserved native data on
separate verification. Backend and UI regressions cover generation conflicts,
credential isolation, stale responses and withheld destructive handoffs.

Reproduction helpers are ``tools/firebird_desktop_native.mjs``,
``tools/firebird_events_native.py``, ``tools/firebird_registration_native.py`` and
``tools/firebird_recreate_native.py``. They require explicitly owned fixtures.
The desktop helper accepts ``docker`` or ``isql``, a credential-free input JSON
path and a receipt output path; the fixture password is supplied in
``CDEADMIN_NATIVE_FIXTURE_PASSWORD``. The Docker fixture orchestrator verifies
ownership labels before removing its own containers and volumes.

Preserved run receipts and logs live outside the repository under
``/home/dcalford/Sandbox/ChatGPT_Codex_1_Workarea/firebird-desktop-lifecycle-20261015``.
``native-current/native-receipt.json`` records all 13 native checks and resource
cleanup. Earlier terminal automation failures remain in the failure inventory;
they are superseded by the complete native run, not relabeled as successes.
DDN freshness is checked before each validation batch, and frontend assets are
rebuilt after broad acceptance.
