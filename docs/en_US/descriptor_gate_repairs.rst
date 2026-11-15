Descriptor and family gate failure repair
=========================================

Missing stable references
-------------------------

Assigned append-only registry identities to existing connector registration
forms. No field, backend mapping or native connection behaviour changes.

* apache_ignite: SR-F-030042
* cassandra: SR-F-030043
* clickhouse: SR-F-030044
* foundationdb: SR-F-030045
* influxdb: SR-F-030046
* milvus: SR-F-030047
* mongodb: SR-F-030048
* neo4j: SR-F-030049
* opensearch: SR-F-030050
* redis: SR-F-030051
* tikv: SR-F-030052

PostgreSQL metadata
-------------------

Removed notes from schema locations which do not allow them, preserving their
prior text below as historical implementation commentary. These notes are not
native implementation or acceptance evidence. No kind, operation or navigator
group was removed. Both partition Comment fields use the already-supported
plain-text code control, preserving multiline string values and backend IDs.

operator: M5 review (2026-11-11): declared so the provider tree lists the operator kind the provider already edits natively (native_admin._operator_admin); the form is the provider-native one from preserved_surface.adapt_catalog.

pgagent-job: M5 review (2026-11-11): declared so the provider tree lists the operator kind the provider already edits natively (native_admin._operator_admin); the form is the provider-native one from preserved_surface.adapt_catalog.

navigator: Owner direction 2026-11-08 (PostgreSQL onto the provider tree, M2): groups follow the YugabyteDB navigator, which is PostgreSQL-derived, with the kinds YugabyteDB lacks added (text search, foreign data wrappers, languages, subscriptions, casts, conversions, operators). Kinds not yet declared in capabilities.json are listed so the tree order is settled before their forms arrive (M3-M5). The provider tree today groups by the visual-admin declarations; this descriptor is served in the engine bundle for consumers of cdeadmin.ui-navigator.v1.


Shared changes applied after owner confirmation
-------------------------------------------

The final two validator failures were a schema missing the already-used
initial_value_path field (PostgreSQL partition prefill) and a UI engine-branch
count of 113 exceeding the existing ceiling of 111. Do not remove prefill or
raise that ceiling. The applied repair adds a strictly typed nonempty path
declaration and uses database_tool_tabs from the endpoint's matched descriptor
bundle for the existing test-data and large-object workspace tools. Native
requests still authorize independently. The active backend now supplies this
navigation metadata without an engine-specific dispatch branch.

All 63 recorded family render failures stopped at the same missing-control
assertion. The shared Select primitive dropped inputProps, including the
descriptor's data-cdeadmin-qa-key and aria-describedby. This was a real attribute
forwarding defect, not 63 separate missing database implementations. The
applied primitive fix forwards the attributes to the combobox trigger and
links internal helper text while preserving an external description. Tests
verify selection callbacks, disabled state, field identity and accessible
descriptions; the original family assertions remain intact.

Proposal qualification: zero descriptor-validator errors, all 171 selected
JavaScript tests passing, and engine branches 113 -> 111. JSON controls remain
301, MUI imports 212 and engine panels 113. Backend metadata/registration tests
pass 88 cases (11 skipped); workspace/builder/partition regressions pass 62
cases (12 skipped, plus 25 passing subtests). Those backend runs overlap;
their counts are not a combined unique-test total.

The owner confirmed application of the shared UI/schema patch. The Select
attribute/description fix, typed prefill schema, descriptor-driven tool guards
and focused regression tests are now in the active project. The exact applied
patch and hashes remain in ui-gate-repair-proposal.patch and
ui-gate-repair-proposal.json under
/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/.
Post-application verification is recorded separately from the earlier proposal
runs; human presentation and native Windows/macOS acceptance remain separate.

Post-application checks passed
------------------------------

The active patch passes make ui-descriptors-check: zero validator errors and
136 backend descriptor tests passed (66 skipped for unavailable native test
environments). All 171 selected JavaScript tests pass, including the original
63 failing render cases and the new Select attribute/description tests. The
workspace, SQL builder and PostgreSQL partition regression run passes 62 tests
(12 skipped, plus 25 passing subtests). No lint ceiling or existing render
assertion was relaxed.

The snapshot capture now includes untracked frontend regression tests, so the
new Select test is included in the immutable verification input. The first
post-application run passed the existing 168 JavaScript tests but could not
load that omitted new file; correcting the capture and rerunning all five
suites produced the clean 171-test result.

Publication integration
-----------------------

The published navigator, Firebird authentication and registration changes were
merged without removing their commits or UX. Overlapping Select changes were
reconciled into one inputProps binding, one helper identity and one composed
accessible description, retaining the incoming checkbox and placeholder fixes.
The new connection-prompt principal suggestion reads the canonical server
form's username default through registration profile metadata rather than an
engine-specific UI comparison. Declared principal and private-registration
credential checks pass.

Firebird embedded source bindings changed with the published navigation code.
Fresh Engine13 qualification passed against an owned runtime copy with source
runtime unchanged, and both embedded contracts were regenerated from that real
receipt. Final integration checks pass: 1,136 backend regression tests (65
skipped), 189 affected integration tests (23 skipped), the descriptor gate
(137 passed, 66 skipped), and 247 JavaScript tests. Native Windows/macOS and
owner-deferred ScratchBird history qualification are not claimed.
