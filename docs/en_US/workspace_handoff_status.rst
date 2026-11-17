Data and SQL workspace continuation
==================================

This is an in-progress development checkpoint, not full native-engine or human
presentation acceptance. It preserves the previously uncommitted data/SQL
workspace work for continuation on the shared development branch.

Implemented in the checkpoint
-----------------------------

* Shared adaptive record forms size fields from types, declared lengths and
  sampled values, and wrap compact cards without distributing unused height.
* Data and SQL result surfaces expose record/page navigation, row bookmarks,
  keyboard cell movement and focus restoration.
* Workspace tabs support human-readable titles and explicit renaming.
* The visual query builder resolves catalog objects through its host API,
  supports selectable-routine inputs/outputs, suggests FK joins and uses the
  shared DDN canvas for selection, joins, removal and pinned placement.
* Native result column metadata distinguishes primary keys from string column
  identifiers and exposes available field lengths.

Publication corrections
-----------------------

The UI refuses an object when native catalog resolution returns no object;
there is no production fallback that invents a node for test mocks. Firebird
executable-only metadata cannot be overridden by a SUSPEND token in source
text or comments. SQL conversion reports unmodeled filters, grouping, ordering
and limits as lossy, warning that regeneration can omit content. Identifier
quoting for new navigator drag payloads comes from the shared language-profile
descriptors rather than engine checks in the tree renderer.

SQL execution adapter correction
--------------------------------

The SQL surface calls the public retained-session execution API with explicit
session, source and bound-parameter arguments. It consumes the rendered table
under ``view_model`` and uses the declared record lookup keys, preserving
independent values when joined columns have repeated labels. The unit fixture
uses the real call signature so passing a whole payload as the session argument
cannot silently pass. An owned Linux Firebird 5.0.4 embedded API check executes
an ASSETS/CUSTOMERS join and reads every returned column, including independently
valued duplicate labels. This does not extend native qualification to the other
items below.

Continuation checklist
----------------------

* Qualify selectable-routine discovery and generated SQL on real supported
  engines, including Firebird network and embedded, native parameter/type
  metadata, quoted identifiers and duplicate names across schemas.
* Replace or extend the regex conversion with complete, engine-aware fidelity
  handling. The lossy guard is not a full SQL parser or a guarantee that every
  other expression is represented exactly.
* Expose catalog truncation/completeness and acquisition failures. The current
  acquisition is bounded to 25 pages of 500 resources and may cache an empty
  catalog after a discovery failure.
* Define bookmark semantics across refresh, reorder and result reexecution.
  Current bookmarks use row offsets in local React state, not durable primary
  key identities. Define persistence separately for bookmarks and renamed tabs.
* Exercise real pointer/keyboard interactions, canvas field-to-field join
  dragging, pinned routes, large catalogs and all shared DDN canvas consumers.
* Obtain human presentation acceptance and native Windows/macOS evidence from
  the owning teams. Mock-backed regression tests do not qualify those scopes.

This checkpoint does not close any engine audit item. ScratchBird history
qualification remains owner-deferred. The previously supplied desktop binary
is built from the earlier revision and does not gain these edits automatically.
