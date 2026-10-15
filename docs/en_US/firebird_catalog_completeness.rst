Firebird catalog completeness
*****************************

Scope
=====

The native Firebird 5.0.4 network and embedded catalogs enumerate attachment-visible
objects, including system objects. Completeness is scoped to the current native
principal and database. It does not mean every database or security principal on
a server is visible. A successful empty result establishes only that no rows were
visible in that observation. An unavailable optional catalog is unknown, not absent.

The supported catalog categories are tables, views, columns, indexes, constraints,
domains, sequences, triggers, procedures, functions, external functions, BLOB
filters, packages, exceptions, roles, character sets, collations, users,
publications, effective configuration, local/global authentication mappings,
privileges, shadows and storage files. Service operations and metric definitions
are capabilities rather than native catalog objects; their navigator reachability
is checked separately along with the native resources.

Implicit engine-generated ``RDB$FIELDS`` rows are represented through column and
routine type metadata rather than standalone user-domain entries. Named user
domains and native system domains are listed. Array dimensions, computed/default
expressions, native types, constraints, owners, comments, routines and dependencies
retain their existing native metadata and reconstruction behavior. Catalog source
and description BLOBs are materialized before closing or reusing their cursor.
The catalog remains documentary observation; reading it does not apply DDL.

Identity and navigation
=======================

Resource IDs escape native delimiters. Routine identities include their package;
user identities include both username and user-management plugin. Same-named
accounts from different plugins are distinct even though database privileges are
name-based. Selected-user ALTER/DROP commands use the inspected management plugin,
and cannot redirect to a different plugin through a draft. User catalog metadata
includes plugin, first/middle/last names, native active/admin flags and description;
passwords and hashes are never selected.

Duplicate structural catalog identities fail explicitly instead of overwriting
an earlier object. System packages expand through Firebird's own navigator rules.
Child discovery checks native owner IDs, so a sequence with the same name as a
relation does not acquire that relation's columns. MON$ metric definitions appear
beneath their actual monitoring relations. A metric definition is marked
``definition_only`` and does not imply that its current value was sampled.

Publication metadata includes owner, system flag, active state, auto-enable setting
and table membership. Table membership lists are observational projections of
native replication settings; the existing ``publication_enabled`` workflow owns
supported changes. No custom-publication creation workflow is inferred.

Coverage and consumers
=======================

The database resource includes ``catalog_coverage`` with an explicit schema,
attachment visibility, observed/partial state, unavailable sections and counts
for all supported categories, including visible zero counts. The record never
asserts server-wide completeness or that an independent inventory audit has run
for this particular user/database refresh. ``coverage_complete`` expresses whether
all queried catalog sections were available in that attachment.

Structural failures, including relation enumeration and publication memberships,
block the catalog instead of returning partial structural metadata. Optional
security/configuration failures retain safe diagnostics and warnings. Authentication
mapping and database-creation-authority failures participate in coverage too.
DDN export preserves partial coverage, and metadata search returns coverage and
warnings so an unsuccessful search cannot imply inaccessible metadata is absent.
Embedded SEC$USERS enumeration is unavailable in the qualified local fixture and
is explicitly marked partial; network-only security administration is not tested
by silently redirecting an embedded connection to the network.

Native qualification
====================

Run the native inventory gate with CPython 3.14 and firebird-driver 1.10.11::

    python tools/cdeadmin_firebird_catalog_completeness_gate.py \
      --runtime-root /path/to/existing/firebird-5.0.4 \
      --evidence /path/outside/repository/new-evidence-directory

On Linux, set ``LD_LIBRARY_PATH`` to that runtime's ``lib`` directory. The gate
stages private writable runtime configuration, security database, locks and
fixtures. It fingerprints the source runtime, owns its loopback server, and
removes owned state after retaining results. It does not modify an installed
server or the supplied runtime.

The gate compares multisets of raw native identity rows against provider resources
for all 25 categories, then walks the actual navigator. Its fixtures include
quoted delimiter names, an array domain, computed/identity columns, foreign keys,
expression indexes, same-named standalone/package routines, user and system
objects, collation, external function/filter declarations, mapping, shadow and
difference-file metadata. Declared external modules are not loaded or executed.
Captures cover a privileged network attachment, a restricted network account and
a distinct embedded database. Native user attributes and plugin-bound ALTER/DROP
are checked against the engine. Each catalog section and driver information field
also receives native failed-read injection through the observation gate, followed
by a recovery check.

Linux qualification is separate from Windows/macOS platform-team evidence and
from human form validation. This catalog gate does not close persistent monitoring
history's independent ScratchBird runtime acceptance obligation.
