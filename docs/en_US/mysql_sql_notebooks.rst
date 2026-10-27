SQL notebooks and shared investigations
======================================

Open a native MySQL database SQL editor and choose **SQL notebook**. Create a
project from Project Explorer if needed, select it, and create a notebook with
**Add note** and **Add SQL cell**. Cells can be edited, reordered or removed.
Notes are plain inert text. **Save notebook revision** stores an optimistic,
versioned project asset; a concurrent save error preserves the current draft.
Multiple notebooks have distinct asset paths within the same project.

Connection and execution
------------------------

The notebook records only the engine, local endpoint identity and registered
database target identity. It stores no host route, user, password, credential
reference, session handle, parameter binding or query attribute. Use **Bind to
this SQL editor** to select the current connection explicitly. Rebinding clears
old snapshots. Another target cannot run a bound notebook without rebinding.

**Load cell in SQL editor** only loads text. Use the existing editor for native
completion, syntax diagnostics and editing; **Replace cell from SQL editor**
copies the edited text back. **Run selected SQL cell** explicitly executes that
one cell in the existing native session, with empty bindings and attributes.
Native transaction/autocommit controls, cancellation, diagnostics and results
remain in the SQL workspace. There is no automatic run-all action, implicit
commit, rollback, retry or inferred mutation outcome. A transport failure must
be reviewed in the native workspace before a deliberate repeat.

Retaining evidence
------------------

Results remain temporary until **Retain reviewed page snapshot** is selected.
Only a tabular displayed page whose executed SQL and connection match the
selected cell can be retained. Columns default to omitted; names suggesting
credentials default to redacted. Select **Retain value**, **Redact** or **Omit**
for each column. The snapshot contains at most 100 displayed rows and 128
selected columns, and records whether the displayed result was limited. Native
display strings preserve large integer, decimal and other typed presentations.
No full native result, cursor, session or provider extension is copied.

Changing SQL or rebinding clears its saved snapshot from the draft. Removing
evidence does not erase earlier immutable project revisions. Before granting
project access, review all assets and revisions that member will be able to
read. A shared viewer cannot edit project assets; database execution still
requires the recipient's independent native permissions.

Sharing and reopening
---------------------

Save the current draft, review notes, SQL literals and retained values, and
acknowledge the sharing review before **Export shareable notebook**. Export
reads exactly that saved revision and emits a strict, portable JSON document
with every local connection binding removed. Credential-like connection URLs,
password assignments, authentication SQL and private-key headers are rejected
at the storage boundary. Pattern detection cannot identify arbitrary secret or
business data: authors must review literals and selected values. Notebook files
are limited to 2 MiB; individual cells and snapshot values are also bounded.

**Import notebook** validates a portable draft and never executes its SQL. An
import has no authority to select a local connection; explicit binding is
required before execution. Imported notes and retained evidence remain visible
until changed or rebound. Opening a saved notebook from Project Explorer loads
the same asset editor without opening a database session. To execute it, open
the database SQL editor, choose **SQL notebook**, and load that project asset.

Earlier revisions can be loaded as drafts. They must be saved as a new current
revision before sharing; the current-head version is checked when saving.
Dirty drafts prevent notebook close and language changes. **Discard draft /
new notebook** explicitly abandons a draft. Project membership uses existing
owner-controlled project access and applies to all project assets and saved
revisions, not just the current notebook.

Qualification scope
-------------------

``tools/cdeadmin_mysql_notebook_qualification.py`` exercises native MySQL 9.7.0
with corrected Connector/Python 26.7.0 pure and C interfaces. It covers
authenticated revision persistence, inert opening/import/sharing of stored
mutation SQL, explicit execution, exact unsigned/Unicode results, redacted
snapshots, optimistic conflicts and independent pending transaction/savepoint
preservation. Its optional production desktop gate covers loading, execution,
retention/redaction, saved revision export, inert import and explicit rebinding.
Project permissions and malformed/credential-bearing document boundaries also
have focused application tests. This is Linux scope; Windows/macOS acceptance
belongs to the platform teams. ScratchBird history qualification remains
owner-deferred and is not run by this workflow.
