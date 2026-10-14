# SQL history and saved work

The shared SQL editor binds each session to an active engine, endpoint and
database/file. Its language profile, transaction controls, statement splitting,
source validation, plans and result metrics follow that exact binding. Verify
the connection label before running or saving a script. Autocommit disables
manual Commit/Rollback only when the native connection is actually in that
state; explicit transactions retain their native behavior.

SQL history can retain owner-, endpoint-, database- and language-scoped source
when enabled. Mark sensitive statements to omit their source. History provides
search and reload, but reloading text does not execute it; review the current
connection and transaction before Run. Saved files and DDN designs are separate
assets with their own scopes and revisions.

Persisted SQL history, dashboard definitions and test-data recipes are in the
current implementation scope. The deferred persistent monitoring history is a
different data stream. Query-result buffers are bounded pages, not durable
backups or proof that an unobserved write succeeded.

For scripts and native language details, see
[native dialect tooling](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/native_dialect_tooling.rst)
and the selected provider's driver guide.
