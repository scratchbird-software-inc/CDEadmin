DuckDB engine functional completion
==================================

The native target is DuckDB 1.5.2 and PyArrow 25.0.1. This contract supplements
``duckdb_driver_development.rst``, the shared SQL editor, compact forms, navigation
and DDN roundtrip contracts. Native driver qualification alone does not establish
completion of management workflows.

DUCK-COMP-01: Native catalog and administration
  Preserve database/catalog, schema and object identity, including attached
  catalogs, temporary objects, columns, constraints, indexes, sequences, native
  types, scalar/table macros, functions, extensions and secret descriptors.
  The registered primary file's schemas are direct children of its database
  tree node. Attached-catalog schemas retain their attached-database parent.
  Navigator ownership must make actual schema descendants reachable, including
  indexes, sequences, types and views; a catalog capture without tree routes
  does not qualify object management.
  Resource IDs encode native path segments unambiguously; punctuation in names
  is not an identity delimiter. Distinct native constraint indexes remain
  distinct even when their reported names coincide. IDs are opaque; refresh
  discovery after activation rather than reusing a cached older identity format.
  Do not silently overwrite same-name native function overloads. A function or
  macro group retains every observed overload, its native function type,
  parameter names/types, return type, definition, examples and stability.
  A group exposes common fields only when all overloads agree; selecting one
  group must never silently select an arbitrary overload as its definition.
  Catalog capture presents overloads in a stable signature-and-definition
  order so repeated captures of unchanged native objects do not generate
  order-only design differences.
  For user-defined types, capture DuckDB's catalog-resolved type expression
  with an exact qualified ``typeof(NULL::type)`` query. This preserves STRUCT
  fields, UNION alternatives and alias targets that ``duckdb_types()`` names
  only by broad logical category. The resolved expression describes current
  native semantics; it is not proof of the author's original DDL spelling.
  Attachments are session-owned native objects, not remote authenticated servers.
  Do not offer unsupported server accounts, roles, triggers, procedures,
  replication, savepoints, or MySQL-style administrative executables.
  Never expose secret values, encryption keys or confidential attachment options.
  Database options use an explicit safe metadata allowlist; foreign attachment
  connection strings are omitted. Disclose omitted metadata without returning it.

DUCK-COMP-02: Embedded connection and transaction ownership
  Bind explorer connections, editor sessions and target selectors to the exact
  registered file/root and native catalog. Retain original DuckDB connections;
  cursor() creates another session and cannot substitute for their transaction.
  Respect read-only routes, native file locking, attachment lifetimes and native
  multi-database write restrictions. Preserve unknown outcomes and never replay
  native work. A COMMIT of an aborted transaction is reported as native rollback.
  Autocommit controls must reflect actual admitted DuckDB session policy, not
  imitate another driver's behavior. Refresh transactions when policy permits;
  pending interactive work must never be committed by monitoring or discovery.

DUCK-COMP-03: Shared SQL editor and native language
  Use the shared compact editor with engine-labelled connections, native parse
  validation, contextual completion, parameters, retained script execution,
  files, persistent optional owner/target/language-scoped history, result paging,
  cancellation, transaction controls, diagnostics and physical/profiling plans.
  Preserve native Arrow exact and nested values, duplicate column identities and
  ordered result sets. The SQL result grid must display each returned value in
  its corresponding ordinal column, including rows encoded as arrays by the
  native driver; a nonempty buffered result must not render blank cells.
  Result admission binds positional driver values to unique native column keys,
  not display names, so repeated output names remain distinct.
  Report preparation, dispatch and fetch measurements only
  for the scope actually measured. EXPLAIN ANALYZE executes native work.
  Source checking on a retained DuckDB session uses the pinned 1.5.2 native
  parse-only API. It returns native statement boundaries and grammar status
  without executing SQL. Parse errors are scrubbed because native diagnostics
  may echo source literals. This check does not establish semantic validity,
  permissions or side-effect safety; those remain execution-time concerns.
  Query metrics report native parsing time, client dispatch/reader setup time,
  and local fetch/encode time with a buffered-row count. The displayed total
  execution interval starts at dispatch and ends after native iteration and
  local buffering; it can include consumer backpressure. No plan is inferred
  from an ordinary execution. An explicit EXPLAIN result is shown as result
  data, and EXPLAIN ANALYZE may perform the work being profiled.
  A normal Run request admits exactly one user-authored SQL statement,
  including explicit EXPLAIN requests. Empty requests or a second SQL
  statement after a native-tokenized semicolon fail before dispatch and have
  no SQL effects. Native IMPORT DATABASE may expand that one command into
  several internal statements; this is not a second user-authored command.
  Multi-statement work
  uses the retained script coordinator: it reviews native boundaries, sends
  one statement at a time on the same session, observes each terminal result,
  stops on error or unknown outcome, and never automatically replays a
  submitted statement. An error plus blocked session is an unknown outcome.
  Editor preparation of a selection, current statement or remaining source
  from the cursor uses those same native parser boundaries without execution.
  A prepared multi-statement result enters retained script review; it is not
  passed to the ordinary single-statement Run path.
  Visible native catalog resources supply qualified catalog/schema/relation and
  column completions in the shared editor. Identifier insertion quotes and
  escapes exact native names. This page-scoped completion never claims a
  truncated or inaccessible catalog is empty or complete.

DUCK-COMP-04: Data and file workflows
  Implement native row editing with qualified identity, paging, commit/rollback,
  exact values, import/export and reusable test-data recipes. Provide reviewed
  native COPY, EXPORT/IMPORT DATABASE, attachment, checkpoint and maintenance
  workflows. Do not claim EXPORT is a physical backup, or that SQL rollback
  removes files written externally. Validate registered filesystem ownership
  without claiming that authorized arbitrary SQL/extensions are sandboxed.
  The database administration form requires an absolute directory under the
  registered filesystem root for native EXPORT/IMPORT DATABASE. EXPORT offers
  PARQUET or CSV and requires a new or empty destination. IMPORT requires an
  existing export with schema.sql and load.sql and targets the active file;
  it does not replace that file. Refuse export control-file symlinks that
  escape the reviewed import directory. Checkpoint, force checkpoint, vacuum
  and analyze expose only their native supported options.
  Native test-data recipes are scoped to one registered file and fresh catalog
  capture, bounded to 32 tables, 5000 rows, a 4 MiB recipe and 1 MiB generated
  SQL. Generation validates 1.5.2 native statement boundaries and performs no
  writes. The shared Query Tool owns execution, transaction outcome and effects.
  Native table COPY planning is similarly nonexecuting. It captures the exact
  registered-file table identity, requires a contained regular source file for
  import or an absent destination under the registered root for export, quotes
  the full catalog/schema/table and path, and emits one parsed native CSV or
  PARQUET statement. Import is a database write; export creates an external
  file that SQL rollback cannot promise to remove. Execution remains in the
  shared Query Tool with its explicit transaction controls.
  ATTACH/DETACH planning is session-scoped and nonexecuting. An ATTACH script
  accepts only an existing DuckDB file under the registered root, an explicit
  alias and read-only choice; a read-only primary route cannot attach a
  writable file. DETACH targets an explicit nonprimary alias. The script must
  run on the chosen retained connection, since an independent connection
  cannot observe or change another session's attachments. Never advertise
  these aliases as separately authenticated remote servers.

DUCK-COMP-05: DDN catalog, data and design exchange
  Capture native catalog and selected data into DDN views using the sister
  project's public tools. Preserve catalog-qualified names, native types,
  defaults, expressions, constraints, indexes, sequences, macros and dependency
  evidence. Retain exact native DDL where available; explicitly report metadata
  which DuckDB cannot reconstruct. Read DDN for native creation and three-way
  baseline/desired/live diff, with explicit deletion intent, native nonexecuting
  validation and reviewed apply receipts. A view filter never authorizes drops.
  Distinguish temporary/session definitions from persisted file contents.
  Catalog capture uses its own connection and transaction, bounded to 20,000
  native/expanded facts, 8 MiB and 30 seconds. Overflow or interruption returns
  no partial successful capture. A known missing registered file is refused
  before connection creation. Independent capture of :memory: is refused.
  Selected relation data uses a separate registered-file connection and native
  read transaction, exact catalog/schema/table-or-view identity, 1–6,000 rows,
  a 4 MiB value budget and 30-second deadline. A full request exceeding its
  row budget fails; a sample records truncation. Attached session-only catalogs
  are not independently captured. Values use the driver's exact Arrow encoding,
  and no capture borrows or commits an interactive transaction.
  Separate native sequence observations from resumable sequence state; discovery
  must not call nextval. Preserve native file effects and uncertain apply state.
  Versioned DDN design drafts use the shared project asset repository, scoped to
  the owner, exact endpoint and registered file target. Keep the capture used as
  the design baseline with each revision, permit source merge through the paired
  public DDN workflow, and treat an edited design as documentary until native
  plan review and application are separately qualified.
  Three-way design preview compares a saved baseline and edited DDN with a
  fresh native capture. Only explicit, exactly qualified DuckDB CREATE objects,
  exact-name index CREATE on a qualified table, nullable native column ADD,
  explicit DROP intent, view replacement, isolated column alterations including
  STRUCT field addition or removal, native
  enum extension, reviewed full type replacement, reviewed sequence replacement,
  single-overload scalar or
  table macro replacement and complete macro overload replacement,
  exact-identity table/view/column rename, explicit primary-key addition and
  isolated native object comments are previewed
  through the 1.5.2 native parser. A column addition requires an observed persistent
  parent table and a native type; unsupported column constraints block review.
  View columns remain navigable but cannot enter table-column create, alter,
  rename or drop reviews; these column mutations require an observed native
  table parent, except columns included in a new table's CREATE statement.
  DuckDB's supported column-comment operation remains available for view columns.
  One-field column default or nullability alterations require explicit change
  intent and an otherwise unchanged baseline definition. An explicit column
  type alteration may change only native type-derived metadata, with an
  optional separately reviewed ``USING`` expression; it does not infer a
  conversion or alter constraints. After commit, rediscovery must verify the
  requested native type, even when its canonical spelling differs and review
  is consequently marked unverified. A separate ``alter-column-properties``
  intent may combine two or three changes among type, default and nullability
  on one observed column. It uses only the already qualified native ALTER
  statements, each parsed and reviewed in order. An existing default that
  changes is dropped before type conversion; a new default follows it; SET
  NOT NULL is last. The batch
  runs in one native transaction and verifies all three final column facts
  after commit. Any conversion, default or nullability failure rolls back the
  batch. Changes to other column metadata or constraints remain blocked.
  Each isolated alteration is one parsed native statement and one review.
  A top-level field may be added to an observed ``STRUCT`` column through a
  separate ``add-field`` review. The desired native type must be the observed
  structure with exactly that one named field and native type appended; no
  other column property may change. The reviewed statement uses DuckDB's
  ``ALTER TABLE ... ADD COLUMN struct_column.field`` grammar, and fresh
  discovery must match the complete resulting native column type. A top-level
  field removal requires an explicit ``drop-field``
  intent naming one observed field and an unchanged remaining type. At least
  one field must remain. DuckDB's ``ALTER TABLE ... DROP COLUMN
  struct_column.field RESTRICT`` is reviewed as one statement and the complete
  resulting native type is checked after commit.
  Nested ``STRUCT`` paths may use ``add-nested-field`` or
  ``drop-nested-field`` with a complete simple-identifier path inside the
  column. Each path segment must name an observed nested ``STRUCT`` field;
  the desired type must equal exactly the old type with that one terminal
  field added or removed. Existing nested values must survive native execution,
  and fresh discovery verifies the whole column type. A nested parent cannot
  be emptied by removal. Combined field edits remain blocked.
  An enum extension requires an observed native ENUM, preserves every existing
  label in order and appends distinct new labels. It uses one reviewed native
  ``CREATE OR REPLACE TYPE``. DuckDB does not retarget columns that already
  reference the prior type definition; any such column conversion requires a
  separate reviewed column alteration. An enum extension with an unchanged
  native comment replays it after ``CREATE OR REPLACE TYPE`` in the same
  transaction and verifies it after commit; native tags still block replacement.
  A view replacement replays unchanged view and column comments in the same
  native transaction after ``CREATE OR REPLACE VIEW``; a changed comment,
  a missing commented column in the desired model or any native tags block
  review. A view replacement and a separate child-column comment edit cannot
  share one review. Native execution rolls back if the submitted replacement SQL no
  longer exposes a commented column despite its desired model. After a
  committed view creation or replacement, compare
  the preserved comments and the native
  catalog's parsed view-query tokens and explicit column aliases with the
  submitted definition. A changed
  object name or merely different definition is insufficient verification;
  canonical spelling differences may leave a successful commit explicitly
  unverified, and must not trigger automatic replay. A macro replacement requires exactly
  one observed scalar or table overload, unchanged macro kind, parameters and
  metadata, an explicit new bounded definition, and an affirmative
  ``parameters_without_defaults_confirmed`` review assertion. DuckDB 1.5.2
  ``duckdb_functions()`` does not expose macro parameter default expressions;
  names and types alone cannot prove that reconstruction preserves optional
  arguments. A reviewer must independently verify the original signature has
  no defaults before the plan may synthesize a replacement statement. A
  single-overload scalar macro replacement with an unchanged native comment
  replays that comment in the same transaction and verifies it after commit.
  A complete scalar overload-group replacement likewise replays a common,
  unchanged comment on every overload and verifies it after commit. DuckDB
  1.5.2 does not admit ``COMMENT ON MACRO`` for table macros. Native tags
  remain blocked because ``CREATE OR REPLACE`` clears them.
  Table replacement uses
  ``CREATE OR REPLACE MACRO ... AS TABLE``; scalar replacement omits ``TABLE``.
  A distinct ``replace-macro`` intent may replace a complete overload group or
  change its signatures only when the reviewer supplies the exact fully
  qualified ``CREATE OR REPLACE MACRO`` source and explicitly confirms it is
  the complete desired signature set. DuckDB cannot expose existing parameter
  defaults, so this source is a deliberate whole-group replacement rather than
  an inferred preservation of hidden defaults. The plan accepts one bounded
  native CREATE statement, requires a consistent desired scalar or table kind,
  checks every declared desired overload's parameters and definition, and
  refuses an existing comment that replacement would erase. Application verifies
  the complete observed overload signature and definition set after commit.
  Desired definitions must use DuckDB's catalog-normalized expression form;
  a parsed statement alone cannot prove that the desired capture will match.
  Both replacement paths preserve uncertain outcomes without automatic replay.
  DuckDB ``CREATE OR REPLACE SEQUENCE`` recreates the generator and resets its
  value. A ``replace-sequence`` design intent therefore requires a complete,
  exactly qualified native statement and an explicit ``reset_state_confirmed``
  assertion. Review changes only observed start, minimum, maximum, increment
  and cycle options. An unchanged sequence comment is replayed in the same
  transaction and verified after commit; native tags still block replacement.
  An automatic ownership dependency
  observed on the current native catalog also blocks replacement before
  dispatch; this observation does not assert that ownership survives a file
  reopen. Application rechecks the old
  definition in its transaction, dispatches the replacement and any comment
  replay once each, and verifies
  the new option values after commit. Native dependency checks govern
  replacement; do not use ``CASCADE`` or silently detach dependents. DuckDB
  1.5.2 preserves a simple table default referencing a replaced sequence;
  other dependency failures roll back the reviewed transaction. The historic
  generator position cannot be
  reconstructed from metadata and is never represented as retained design.
  DuckDB 1.5.2 parses and executes ``ALTER SEQUENCE ... OWNED BY``, but in the
  pinned runtime the ownership dependency disappears after closing and
  reopening the database file, including after ``CHECKPOINT``. Dropping the
  former owner then leaves the sequence. ScratchRobin must not advertise this
  as a durable DDN or administration change; sequence-owner edits remain
  blocked pending a later version's reopen-and-drop qualification. A dependency
  seen only in the applying connection is not persistence proof.
  A ``replace-type`` intent requires a complete, exactly qualified native
  ``CREATE OR REPLACE TYPE`` statement and an explicit whole-definition
  confirmation. The edited design must declare the complete resolved type,
  broad logical category, labels and native size it expects; changing other
  metadata in the same review is blocked. An unchanged type comment is
  replayed after replacement in the same transaction and verified after
  commit; native tags still block replacement. After commit,
  capture the type again and compare its resolved definition and reported
  metadata. Replacing a named type does not imply that columns already using
  the old type are converted; those columns require separate reviewed changes.
  A rename requires the baseline source resource ID, unchanged native
  definition, unchanged parent, an absent target identity and an explicit old
  name confirmation. The plan binds both source and destination IDs, dispatches
  one native ``ALTER`` and verifies that the source disappeared and the
  destination appeared. Child resource identities generated from a renamed
  parent path must be refreshed in the design before further native changes.
  Table, view, column, sequence, type, macro and index comments may be set or
  cleared through one parsed ``COMMENT ON`` statement when the only edited
  native field is the comment. DuckDB 1.5.2 cannot comment on schemas; those
  edits remain blocked. The resulting comment is verified by fresh discovery.
  A primary key may be added to an existing table only by explicit intent
  naming one or more distinct observed columns when the baseline has no
  primary key. No other table edit is bundled with this operation. DuckDB
  checks existing data and nullability during native execution; a failure
  rolls back the reviewed transaction. Fresh discovery must observe the key
  and the exact ordered key columns. Dropping or changing a primary key is
  unavailable through DuckDB 1.5.2 ``ALTER TABLE``. A separate
  ``rebuild-drop-primary-key`` intent may remove the sole key and its implicit
  NOT NULL constraints when the reviewer explicitly accepts that all former
  key columns become nullable. It requires no other CHECK, UNIQUE or foreign
  key on the table, unchanged non-nullability column facts, and the same
  dependency, data-copy, index and comment safeguards as the admitted staged
  constraint rebuild. Before copying rows, the staged table's exact native
  column names, types, defaults and nullability and absence of constraints
  must match the reviewed desired model. Changed key identity, retention of
  explicit NOT NULL remains blocked. A separate
  ``rebuild-retarget-primary-key`` intent may replace the sole primary key
  with a different ordered set of existing columns. The old and new tables
  may contain only the respective key and its implicit NOT NULL constraints.
  Columns leaving the key become nullable; newly keyed columns become NOT
  NULL. All other column facts stay fixed. Before copying rows, the staged
  table's columns and exact ordered primary-key and implicit NOT NULL facts
  must match the reviewed desired model. DuckDB checks old rows against the
  new key during the copy; a duplicate or NULL rolls back the transaction.
  The same dependency, sequence-default, index, comment and rediscovery
  safeguards as key removal apply. Explicit NOT NULL retention, an unchanged
  key and general primary-key rebuilds remain blocked.
  ``CREATE OR REPLACE TABLE`` is not a safe substitute for a general table
  migration: it clears rows, indexes and comments. It can leave a dependent
  view reporting ``is_bound = true`` while a query against that view fails to
  bind. Native rollback restores the original table, but a successful commit
  does not preserve these facts. General whole-table replacement remains
  blocked; a separate migration must preserve data and dependent metadata.
  An isolated ``rebuild-column-order`` intent may reorder two or more existing
  columns without adding, dropping, renaming, converting or changing any
  column property or constraint. It binds the complete old and desired native
  column sets, their unchanged definitions and explicit final ordinals. The
  staged table copies every row by named columns, checks both row-multiset
  directions, replays unchanged independent indexes and comments, and verifies
  the final column order and child rows after commit. The ordinary dependent
  view and macro binding checks apply; a changed ``SELECT *`` projection must
  roll the transaction back. Foreign-key edges, generated columns, native tags
  and unaccounted sequence ownership remain blockers.
  A narrow CHECK or UNIQUE constraint migration may be admitted when all observed columns
  remain identical and no tag or foreign-key edge needs preservation.
  A bounded set of unchanged, persistent user views in the same catalog may
  coexist with the rebuild. Their exact catalog definitions and child columns
  are bound into the review. The apply transaction binds every view with
  native DESCRIBE before staging and again after the table swap; any failure
  or changed projection rolls back. Fresh post-commit discovery must retain
  each view definition and column facts, and native DESCRIBE must still bind
  to the same projection. Temporary views, attached catalogs, missing desired
  view rows and unqualified view bindings remain blockers. Independent
  scalar or table macro groups with one to eight complete unchanged overloads,
  each with at most eight observed positional parameters, in the same catalog
  may also coexist when every overload has a distinct parameter count. Each
  arity is bound with native DESCRIBE using NULL placeholders before and after
  the swap, with exact projection equality, and the full catalog definition
  is checked again after commit. If placeholders cannot bind, application
  refuses before dispatch. Same-arity overloads, variadic, changed or
  unbindable macros remain blockers.
  Independent
  sequences may coexist with the table, including a sequence referenced by
  an unchanged column default: the explicit-column
  data copy must not advance it. Before the old table is dropped, the
  transaction compares the native sequence dependency identities of the old
  and staged tables; a direct ``nextval`` default also requires an observed
  dependency. Any mismatch rolls back. A sequence with an observed automatic
  ownership dependency still blocks the rebuild; dropping its owner may
  otherwise delete the sequence. DuckDB 1.5.2 may accept ``OWNED BY`` for
  a sequence already referenced by the table default without exposing an
  automatic dependency; the native ``DROP ... RESTRICT`` must then refuse
  the swap and roll the whole transaction back. The reviewer supplies a complete
  CREATE TABLE definition and explicitly confirms the corresponding isolated
  constraint rebuild. The CHECK intent changes only CHECK constraints and may
  retain an unchanged, complete UNIQUE constraint set on that same table;
  its complete inline or table-level native definitions must survive staging
  and rediscovery. The UNIQUE intent accepts CHECK and UNIQUE constraints. An unchanged primary
  key and its implicit NOT NULL constraint may be retained only when their
  complete native definitions and child catalog facts are unchanged. Primary
  key creation remains outside this migration; the isolated key-removal and
  retargeting intents above are separate. An
  isolated ``rebuild-foreign-keys`` intent may add, remove or replace the
  complete outgoing foreign-key set of one child table. It retains unchanged
  CHECK, primary-key, NOT NULL and independent UNIQUE facts, and uses the same staged copy,
  index/comment replay and exact post-commit child verification. The
  referenced parent tables must be observed in the same catalog and schema,
  differ from the child, and have unchanged semantic definitions bound into
  the review receipt. Global native constraint ordinals can shift when the
  child is recreated and are excluded from that parent comparison. No other
  table may have a foreign key in this first native
  subset; this also excludes inbound references to the child. An unchanged
  UNIQUE set must match the reviewed child catalog before the staged copy or
  old-table drop; changed or omitted UNIQUE definitions roll back.
  A separate ``rebuild-check-with-inbound-child`` intent may rebuild CHECK
  constraints on a parent referenced by an unchanged child table
  when that simple-name child has exactly one outgoing foreign key to the parent,
  plain unchanged columns and no unadmitted defaults,
  unsupported secondary constraints or sequence ownership. Up to two unchanged
  table-level child CHECK constraints and two unchanged UNIQUE constraints
  may accompany that parent-directed foreign key. One unchanged child primary key
  and its native NOT NULL facts, or explicit unchanged NOT NULL column facts,
  may also survive both stages. A UNIQUE constraint may use
  native inline or table-level syntax; the intermediate child definition must
  retain their exact native body,
  and both stages verify their catalog text and columns before any child drop.
  The child may also have up to eight unchanged foreign keys to other unchanged
  same-schema parents. Each referenced parent's semantic definition is bound
  into the review and checked after commit. The intermediate definition removes
  only the key to the rebuilt parent; native staging must retain and verify
  every other edge before dropping its predecessor. More outgoing keys or
  changed referenced parents remain blocked.
  Each child may also carry up to eight unchanged plain, nonunique independent
  indexes, subject to the 512-statement isolated-rebuild review budget. Their exact observed
  native definitions are replayed after the final child swap
  in the same transaction, with its catalog identity bound into the receipt and
  checked again after commit. Unchanged table, column and admitted index
  comments may be replayed after that final swap, in the same reviewed
  transaction, and their exact catalog facts must survive rediscovery.
  A missing child object row, changed comment or replay failure blocks or
  rolls back the review. DuckDB assigns a new native index OID during
  replay; that transient OID is not part of retained design identity. Index
  native tags and child indexes beyond the review budget remain blocked in this bounded
  subset.
  The captured file has no user views or
  macros in this first inbound subset. The reviewer
  supplies the complete intermediate child CREATE TABLE definition without
  the foreign key. The one-time receipt binds the parent, child, their
  columns and constraint children, and both complete CREATE definitions.
  In one transaction the child is copied to a constraint-free stage and
  swapped; the parent is rebuilt under the ordinary row, index, comment and
  dependency checks; then the child is copied into a second stage carrying
  its original foreign key and swapped again. Each stage must match reviewed
  native columns and constraint facts and preserve row multisets before its
  predecessor is dropped. Any failure rolls back both tables; fresh discovery
  verifies both table definitions, rows and the restored foreign key. More
  complex inbound graphs remain blocked. The companion
  ``rebuild-check-with-inbound-children`` intent accepts two to thirty-two distinct
  qualifying children, each with its own complete intermediate definition.
  The parent may also retain an independent unchanged UNIQUE constraint set;
  staging verifies its exact native columns and definition before copying rows
  or dropping the old parent. All child foreign keys are detached before the
  parent swap, then each child
  is restored and independently row-checked within the same transaction and
  receipt. A partial child set, overlapping child identities or a batch above
  the statement budget is refused before dispatch. A child's unchanged numeric,
  string, boolean or NULL literal defaults, or bounded constant expressions
  composed only of those literals, parentheses, arithmetic operators and string
  concatenation, may survive both stages. The complete native CREATE definitions
  must parse, and explicit column-list copies never evaluate the defaults.
  A direct ``nextval('name')`` or ``nextval('schema.name')`` default may also
  survive when each staging table has exactly the original child's observed
  native sequence dependencies before its predecessor is dropped, at least one
  dependency exists, and no sequence has observed ownership of the child.
  DuckDB 1.5.2 may fail to expose an ``OWNED BY`` dependency through an
  independent catalog capture; in that case native ``DROP ... RESTRICT`` must
  refuse the child swap and roll back the entire transaction.
  The explicit copy must not advance the sequence; fresh rows retain its
  native default after final rediscovery. Other function calls, identifiers,
  casts and sequence expressions remain blocked pending dependency and
  side-effect qualification.
  Each stage's native default facts must match the reviewed child columns
  before the old child is dropped.
  An unchanged virtual generated child column may survive both stages under
  the same simple-expression whitelist as the parent constraint rebuild.
  Both copies name only base columns, while each stage compares the complete
  row multiset including recomputed generated values. Function or sequence
  expressions in generated child columns remain pre-dispatch blockers.
  Native staging validates existing rows against new references before the
  original child is dropped; a failure rolls back. Unchanged independent indexes are
  replayed after the table swap. Existing column defaults must remain
  identical in the reviewed native CREATE TABLE body and catalog; the data
  copy names every column explicitly, so it never evaluates those defaults.
  An unchanged virtual generated column may accompany a constraint rebuild
  when its native expression contains only observed base-column references,
  constants, parentheses and arithmetic or concatenation operators. Copy only
  the base columns; DuckDB recomputes the generated values in staging, and the
  complete row-multiset comparison must prove the resulting values match before
  the original table is dropped. Function calls, sequence use, casts, generated
  references to other generated columns and expressions outside this admitted
  subset block review because staging might invoke side effects or change values.
  A deterministic staging table receives every old row in the same native
  transaction; both EXCEPT ALL directions must be empty before the original
  table is dropped and the staging table renamed. The same transaction must
  then recreate each observed independent index and its comment, and restore
  the table and column comments from the exact reviewed catalog. Native tags
  still block the rebuild. Any failed constraint, copy or metadata replay
  rolls back the original table and data. Fresh rediscovery and
  row-count, constraint, index and comment checks after commit can leave a committed result
  unverified, never automatically replayed. Other rebuilds remain blocked.
  An index's native identity includes its table, but DuckDB CREATE INDEX names
  the index without catalog qualification; DROP INDEX qualifies the index by
  catalog and schema. The reviewed target must match both forms exactly.
  After a committed table or index creation, compare the submitted native
  definition body with the newly captured DuckDB SQL using strict parser
  tokens. Target qualification and trailing separators may differ, but a
  different column, constraint or index expression leaves the one-time commit
  explicitly unverified. A form that cannot be compared is also unverified;
  successful creation by name alone is insufficient and never triggers replay.
  After creating a named type, compare its submitted native type expression
  after ``AS`` with the catalog-resolved type expression. A canonical rewrite
  that cannot be proven equal leaves the committed result unverified; the
  creation is not replayed.
  Sequence creation admits only the native 1.5.2 numeric START, INCREMENT,
  MINVALUE, MAXVALUE and CYCLE options in one exactly qualified statement.
  Preview derives DuckDB's positive/negative increment defaults and refuses
  duplicate or unrecognized clauses, including OWNED BY. After commit, compare
  every effective generator option with fresh native catalog metadata; matching
  the sequence name alone is insufficient. This does not reconstruct current
  generator position or claim ownership durability.
  A committed single-overload macro creation is verified against the complete
  observed scalar/table kind, plain parameter names and native definition
  tokens. Creation with parameter defaults or several overloads may still use
  its exact reviewed native statement, but stays explicitly unverified until
  its complete signature and body can be reconstructed from discovery. The
  catalog does not expose parameter default expressions. No creation is
  replayed to resolve an unverified receipt.
  A committed column addition is verified against its requested native type,
  nullable state and default as well as its identity. Canonical spelling
  differences leave the committed result unverified without automatic replay.
  Other native edits are blockers. Missing desired rows are
  ignored rather than treated as deletion. A plan rejects an unchanged row
  whose object kind, path, name, system
  classification or resource ID has been changed under its existing key;
  such a row cannot silently pass through beside a valid operation. Up to 32
  native statements may be reviewed together when their identities and dependencies
  are unambiguous. One isolated table rebuild may use up to 512 native statements
  under the same one-time receipt and transaction; longer programs are refused
  before dispatch. Create schemas before their tables and tables before their
  indexes; apply added columns before indexes on those columns. Drop children
  before their parents. A new table's columns belong in its one CREATE TABLE
  statement, and cannot also be added as separate operations. Rename remains
  a single-operation review until descendant identities are recaptured.
  Reject conflicting create/drop actions under one parent, unresolved targets
  and an aggregate source above 1 MiB. The durable owner/file-bound receipt
  binds the exact ordered statement list and affected baseline/desired rows.
  Application opens its own connection, begins one DuckDB transaction,
  verifies the registered file identity and rechecks the live baseline in that
  transaction, dispatches each native statement once in dependency order,
  commits once and rediscovers every target. A failed/uncertain commit is never
  replayed automatically. The limited admitted operation set does not complete
  the full native DDN adapter obligation.

DUCK-COMP-06: Native dashboards and monitoring
  Provide display-only DDN engine/embedded-instance/database dashboards with a
  separately authorized editor and published definitions. Use independently
  owned monitoring connections compatible with the native file's connection
  configuration. Observe loaded/installed extensions, attached file statistics,
  native memory/storage/configuration and availability without inventing remote
  server load, network authentication or global user-session metrics. Temporary
  objects and session settings on another connection are not globally visible.
  Configure sampling, bounded volatile retention, leases and optional heartbeat.
  A failed refresh cannot heartbeat. An independent :memory: connection is a
  different database; do not present it as monitoring the interactive instance.
  The collector is admitted only for a registered, existing file in its
  filesystem root. It has an independently owned connection and a scoped grant;
  neither a database password nor a current-user credential selector is used.
  The host requires single-process admission and a process lock. Each completed
  probe opens a native read transaction and rolls it back; failure retires that
  collector connection and cannot count as a heartbeat. The server dashboard
  aggregates registered file collectors, not a remote process. The engine
  dashboard lists owner-registered file targets and never deduplicates physical
  aliases. All metric bindings are validated against DuckDB-specific public DDN
  module and scope identifiers, with live values rebound after publication.
  Published definitions contain no sampled values. Trends expose only bounded
  volatile samples for the current process. Engine, server and database viewers
  remain display-only; dashboard editing is a separately authorized destination.

DUCK-COMP-07: Contextual compact forms
  Give native tree entries meaningful engine-specific destinations and stable
  reusable form references. Use compact selectors, checkboxes, icon actions and
  navigable data grids. Preserve supported native functionality without adding
  features from other engines. Require review and exact target authorization
  for mutations; display native capability or configuration limits explicitly.
  DuckDB view rename uses native ``ALTER VIEW ... RENAME TO``. Its Alter form
  emits ``CREATE OR REPLACE VIEW`` from one reviewed SELECT/WITH query; the
  generic ``ALTER VIEW ... AS`` statement is not DuckDB syntax. A macro Alter
  form takes one exact fully qualified ``CREATE OR REPLACE MACRO`` statement,
  including every intended overload and default argument, rather than
  reconstructing one signature from incomplete catalog metadata. Both
  replacements require explicit whole-definition and comment/tag-reset
  acknowledgement, validate one native CREATE statement before dispatch,
  and show the reviewed statement. The DDN preservation path remains stricter
  and blocks a replacement that would silently discard metadata.
  The exact DuckDB 1.5.2 dialect contract must cover all 35 executable
  generated tasks, including view Alter and Rename; a missing task blocks the
  entire provider dialect gate and therefore all generated forms. Qualification
  consumes live parser and execution evidence from the current provider and
  retains the evidence digest with the contract.

DUCK-COMP-08: Qualification and cleanup
  Qualify native driver, catalog, structured administration, SQL, data, file,
  DDN and monitoring behavior with independent observations where applicable.
  Refresh DDN and qualify immutable captured inputs. Preserve failure inventory
  and evidence outside the repository. Clean up only owned disposable fixtures.
  Static forms and driver receipts alone do not prove full engine completion.

Current-run exclusions
----------------------

Persistent monitoring history and its ScratchBird backend remain deferred.
Windows/macOS development and platform UX qualification belong to their teams.
Persistent SQL history, design/dashboard definitions and recipes remain in scope.
