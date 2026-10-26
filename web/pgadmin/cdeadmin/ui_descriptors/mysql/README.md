# MySQL descriptor audit

Audited against the MySQL administration catalog at `815c9cb4b` and the current
provider plan/validate/apply contract. `capabilities.json` includes every catalog
operation, plus the profile's read-only character-set, collation and storage-engine
kinds. Server registration is not server DDL: the seeded server create/alter/drop
entries and replication-channel drop entry were removed because that catalog
does not admit them. Masking is marked post beta closed source. Library and
materialized-view metadata entries do not claim closed execution runtimes.
The tested version is 9.7.0; the descriptor does not admit untested versions.

The table descriptor is **draft**, scoped to accepted create fields. The shared
shell/render tests are owned by the front-end stream; this audit is not a UI
round-trip acceptance claim. The MySQL-specific legacy table field branch and
`mysql_table_options.fields()` were deleted. Shared generic forms used by other
engines were preserved.

Corrections to the worked example:

| Original binding/control | Finding and correction |
| --- | --- |
| `constraints[kind=primary_key]`, `constraints[kind=foreign_key]` | Underscores are not the backend's SQL kind values. Use `PRIMARY KEY` and `FOREIGN KEY`; also canonicalize `UNIQUE` and `CHECK`. |
| Foreign-key `references`, `referenced_columns` | Map to record keys `references_table`, `references_columns`. |
| Column `identity -> auto_increment` | The create record compiler does not read that field. Removed and recorded as a gap. |
| Column length, precision, scale, unsigned, character set, collation, computed/stored, comment | These separate record properties are ignored. The current compiler accepts a complete declaration in `type`; separate typed properties are gaps. |
| Columns unique/primary-key flags | These are accepted record fields and were missing. Added both. |
| Table `table_type` | The compiler emits `CREATE TABLE`; it ignores the drafted temporary variant. Gap. |
| `partition_by.strategy`, `partition_by.expression`, `add_partitions` grid | These name other operations, not table-create properties. Their drafts take `partition_clause`, `definitions` or `count`; record the grid integration gap under Decision 4/9. |
| Constraint `on_update`, `on_delete`, `enforced` | The create record compiler ignores them. Removed; separate enforcement operation and referential-action gaps are recorded. |
| Native integer options as number/boolean | The backend requires decimal strings, including values beyond JavaScript integer precision. Use text or selects with string `0`/`1`; `stats_sample_pages` also accepts `DEFAULT`. |
| `mysql_table_options.union` multiselect | Backend requires a list of identifier-path arrays, not selected strings. Record missing projection under Decision 9. |
| `alter_algorithm`, `alter_lock` | Not fields in the table-alter compiler; existing controlled-change workflow is separate. Gap. |
| `privilege.grant` | An operation address, not a table draft field. Record cross-operation grid dispatch gap. |
| Omitted Triggers tab | MySQL has triggers. Removed the false omission; catalog-backed/read-only tabs belong to the shared shell. |

Native option aliases are not duplicate controls: `table_checksum` is represented
by the `checksum` concept. Secondary attribute key/value objects are accepted; scalar/nested
attribute editing and explicit secondary-engine NULL need declared projections.
Every retained `backend_field_id` is exercised against the real plan compiler by
`tools/tests/test_mysql_ui_descriptors.py`; no field is declared merely because
the server grammar contains its keyword.

User-key operations use `operations.json` as the sole source of labels and fields:
install the native plugin/functions, inspect type/length, store text, generate,
and remove a key owned by `CURRENT_USER()`. They use the existing provider
plan/validate/apply contract and Security menu category. No new legacy form
function, panel, engine branch or raw JSON control is introduced. Native review
checks do not lock out other keyring writers or implement atomic compare-and-set.
Decision 10 is resolved for user keys: the owner selected metadata-only for beta.
Inspection returns type and byte length; raw-key retrieval/export is outside the
current beta scope and is not an implementation blocker or Enterprise deferral.
The operation descriptors remain **draft / unsurfaced by the unified shell** until
the front-end stream's operation-dialog and family-render acceptance is available.

## View migration

The View family is now **draft**. Name/database, query, algorithm, check option,
SQL security and separate definer user/host fields bind to the actual ordinary
view create/alter compiler. The engine-specific legacy field factory and its
shared `_form()` dispatch branch were deleted. MySQL does not allow triggers on
views, so that tab is omitted with its native reason. The metadata-only
materialized-view kind does not acquire ordinary-view DDL.

The compiler also accepts an ordered list of scalar column aliases. Decision 9
currently blocks expressing that list as a grid. The descriptor records the gap
and requires the shell to preserve existing aliases or withhold ALTER until the
projection exists; it must never silently erase an alias list. Privilege edits
remain separate operations pending the same cross-operation dispatch contract.
Backend binding tests exercise every declared field in both applicable modes.
No rendered round trip or unified shell acceptance is claimed.

## Index migration

The Index family is draft. Typed key-part records map `column` to backend `name`
and preserve native expressions, prefix lengths and order; legacy scalar lists
still work. Creation also exposes native kind/method, uniqueness, comments,
visibility, parser, key block size, algorithm/lock and secondary attributes.
Name editing binds the existing rename action. Visibility has a typed
Maintenance descriptor; the old index-change field branches are deleted.

The original Table draft also exposed primary `engine_attribute`. Source and
release qualification show that the required primary-engine capability flag has
no implementation in the audited Community profile; the field is removed from
both Table and Index and recorded outside beta. Secondary metadata uses a
different core path. Syntax/hooks and a debug simulation never qualify an
available primary engine implementation. The source/release limits are recorded
in `mysql_functional_completion.rst`. No shared schema or renderer was changed.

The Routine family is split into native capability-selected variants:
`routine.form.json` (Procedure), `routine-function.form.json` (Function) and
`routine-scheduled.form.json` (Event). No kind/operation picker is required.
Every field binds the existing native property or an explicit
`backend_field_id`; create/alter characteristic defaults remain separate.
Procedure parameters include native IN/OUT/INOUT modes; functions accept input
parameters. Native ALTER cannot replace the body/signature/determinism/definer.
The parser, native owned-connection execution and catalog observations are
backend contracts, not new UI branches. All three descriptors are draft;
Decision9 value/privilege dispatch and front-end render acceptance remain open.

The Trigger descriptor is draft (11fields/1gap). Native event selection is
single-valued; backend compatibility retains the old one-element events list.
Relative ordering belongs on Engine. Native MySQL has no enable/disable flag,
numeric position, INSTEAD OF or statement-level trigger. Native compiled review
and catalog facts cover the supported concepts without a new legacy form.
The remaining family replacement dispatch is Decision9, not an invented ALTER.

## User and Role migration

The User variant has 36 fields; Role has four. Native authentication/plugin,
TLS, password policies, limits, attributes, default roles and GPL socket MFA
bind the actual compiler. Whole secret-bearing factor grids are redacted at the
backend admission boundary. Native9.7 pure/C and authenticated APIs qualify
creation, policy editing, exact rename/drop, role membership/defaults and partial
initial-grant failures. Named-account role aliases are action views, never
attested creation origin. User listing preserves accounts used as roles.

The old MySQL role field factory and dispatch are deleted. The separate privilege
variant is draft with15fields and two typed Security operations; Decision9 grids and protected generated-password delivery remain
explicit gaps. Decision10 user-key export is owner-excluded from beta. No shared schema, family renderer or shell was changed. All
variants remain draft pending shared rendering and round trips.


The native privilege compiler preserves scoped column lists, dynamic privileges,
multiple exact account identities, proxy grants, global GRANT AS role modes and
native REVOKE options. The private review binds observed grants and the runtime
partial_revokes setting. Per-field tests reach the compiler, native pure/C tests
verify real allow/deny behavior, and authenticated APIs verify typed grant/revoke.
Decision9 still owns applying a privilege diff from another family editor.

## Database and Server migration

Database is complete for its declared fields (6 fields/1 gap). Its JSON is also the field source for the
existing endpoint and visual input contracts; the MySQL field tuples were
deleted. Native SHOW CREATE DATABASE supplies the full definition and read-only
state. Failed observation stays unavailable. The shared record projection
converts native YES/NO encryption into Y/N without an engine branch. Native
pure/C and authenticated APIs qualify create, prefill, alter, actual read-only
write refusal, preserved data and drop. The shared family-render suite plus the native descriptor/draft round trip
qualify those fields; human presentation and platform acceptance remain separate.
Database Security diffs remain the cross-operation part of Decision9.

Server is draft (41 fields/4 gaps). Every field binds the expanded mysql-native
registration input contract. Arrays/objects use typed grids, multiselects and
key/value controls. No engine-specific server form factory existed to retire;
the shared profile-form builder remains a backend input contract. The existing
family host sends visual_admin DDL actions, so Decision11 records the required
registration dispatch. Server remains unsurfaced until that shared bridge lands.
Nested failover credentials/pools and optional closed-server runtimes are
recorded as gaps rather than exposed through ordinary text or JSON controls.

## Maintenance operations and navigation

The42 operation entries include29 migrated server/cache actions. Their existing
native field IDs/defaults are preserved; seven module `form()` factories and
their dispatches are removed. The input adapter reads the descriptor rather
than keeping another field list. LSN/cache numbers and binary XA identities
retain lossless text inputs. SDI paths and index lists are typed scalar grids.

Entries remain draft. Decision12 records the shared OperationDialog projection
gap: it currently submits grid records, while the native APIs require scalar
lists. SDI import and both table cache operations are explicitly unsurfaced
until that shared bridge lands. Backend projection tests/native cache round
trips do not qualify actual dialog behavior. No shared renderer is changed.

`navigator.json` covers the33 current catalog kinds with16 groups, semantic
icons and table/view child kinds. Its layout is draft/unsurfaced pending shared
tree consumption (Decision13), rather than another provider-specific tree.

The65 entries now include partition maintenance, CHECK enforcement, Group
Replication and privilege inspection (23 added). Group/CHECK form factories are
retired; the partition factory keeps only Tier1 drop confirmation. Capabilities
are parsed-identical after layout compaction. Declared prefill paths map back
to the existing catalog `initial_value_path` contract.

Native SQL partition definitions remain bounded grammar, not arbitrary actions.
COUNT/DEFINITIONS visibility and the reorganize scalar grid require shared
operation projection (Decision12); family grid dispatch remains Decision9.
Those workflows are explicitly unsurfaced. All entries stay draft: native
pure/C, authenticated API and three-member group qualifications verify projected
inputs and native effects, separately from actual dialog/presentation acceptance.

The76 entries include11 configuration/channel actions. Typed scalar inputs
preserve native bindings; backend-only admission retains AUTO and encoded
mapping APIs. Filter records and legacy pairs generate identical SQL. Selected
empty filters clear that family. All11 entries remain draft/unsurfaced under
Decision12. The server-operation factory and migrated action branches are
retired. Family/options JSON reindentation preserves parsed content and fields.

The84 operation entries include eight database maintenance/dump actions. Typed
histogram attributes/buckets and Shell partition/condition records adapt to the
existing native arrays/maps. Collection switches preserve absent versus empty.
All eight remain draft/unsurfaced under Decision12. The retired portfolio forms
are deleted; legacy browser gates refuse the empty fallback. Three dynamic row
workflows still need shared Data-editor integration and descriptors (Decision14).

Installed catalog facts retain all eleven plugin fields and five runtime
function fields. Server DDN carries these observations; usage counters are
volatile. Shared family acceptance and the independent inventory remain open.

Operation drafts require shared projection/render acceptance (Decision12).
Wide relay coordinates bind the target's ULONG_MAX metadata at review/apply.
Shared SQL tabs and form-reference allocation belong to the front-end shell.

Wide `SOURCE_RETRY_COUNT` uses the target's native unsigned-long ceiling, with
owned review/revalidation and exact decimal text. It remains part of the
unsurfaced channel create/alter source-option contract; native/API qualification
is not descriptor or dialog acceptance. Relay-only observations retain
`native_relay_position`; retry requests report `native_unsigned_long` for the
largest requested guarded integer. No retry-sequence outcome is inferred.

## Declared tool openers

`tools.json` owns 25 existing endpoint/database openers. Stable command/handler
IDs, native arguments, category/priority, owner/verification gates and offline
job access are retained; only user-facing labels are normalized. The retired
appenders are deleted from `context_menu.py`. Viewers, collection configuration
and the separate DDN editor remain independent.

Decision15 records why channel create/alter cannot yet have a valid descriptor:
`engine_object` has no shared family skeleton and operation dialogs admit only
tiers 2/3. Native source options need typed lifecycle fields with omission,
false/zero/empty and nullable-value semantics. Keep that gap explicit; do not
fabricate a family mapping or relabel lifecycle actions. The existing typed
channel operation descriptors and backend option contracts remain unchanged.
