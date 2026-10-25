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
Retrieving/exporting raw key material awaits Decision 10 and remains a beta gap.
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
