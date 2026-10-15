# Troubleshooting

**The engine root appears but database objects do not.** Check that the exact
endpoint and database/file are connected. A registered target may be visible
before its native internals can be discovered. Use the endpoint's verification
and connection actions; do not infer a successful attachment from a saved name.

**The SQL editor has no active connection.** Open a database from the explorer,
then select its engine-labelled connection in the shared editor. An editor tab
can survive a disconnect; its old text does not imply a live session.

**A dashboard says unavailable.** Inspect the monitoring policy, collector
credentials, selected target, lease and last completed sample. Monitoring uses
an independent connection; it cannot observe a separate `:memory:` SQLite
database as though it were the user's session. A heartbeat is not proof of a
successful SQL transaction.

**A schema change is blocked.** Read the plan's exact native dependency or
capability reason. Save a baseline, recapture the live catalog, and review
explicit deletion intent. Do not bypass a refused native rebuild by editing
the diagram alone.

**An operation times out or disconnects.** Check whether the result is unknown
before retrying. A failed network response does not prove a native write rolled
back. Inspect the provider receipt or rediscover the database; do not replay a
potentially completed operation without its documented recovery path.

**A GitHub workflow did not start.** A run marked `startup_failure` without jobs
does not contain application test results. Inspect repository Actions settings,
runner availability and the run's startup diagnostics before changing test
code. Keep local source/test revision and logs separate from CI claims.

When filing a problem, include the form reference, provider/profile and native
version, exact action, sanitized diagnostics, source revision and whether the
outcome is known. Exclude passwords, connection secrets and sensitive SQL.
