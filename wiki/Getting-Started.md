# Getting started

ScratchRobin is under development. Use a disposable database for initial
evaluation and check the [implementation status](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/implementation_status.rst)
before depending on an engine workflow.

## Install a development copy

The [platform development and demo guide](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/tools/development/README.md)
is the maintained source for Windows, macOS and Linux prerequisites, builds,
sample engines and start/stop commands. The root
[README](https://github.com/scratchbird-software-inc/CDEadmin#readme) gives the
short Python, Node, Yarn and launcher sequence. Native client libraries and
server versions depend on the selected provider; follow its exact driver guide
rather than substituting a similar engine.

## Register and open a connection

1. In Data Explorer, choose the engine root and register its endpoint. A
   connection to the same host on another port is a separate endpoint.
2. Supply the provider's native connection fields and verify the endpoint.
   File-backed engines register database files rather than a remote server.
3. Open the database from its context menu. The explorer should reveal internals
   only after a successful connection; the shared SQL editor lists active
   connections by engine, endpoint and database/file.
4. Use the selected object's context menu for its native properties,
   administration and data actions. The form reference identifies reused forms.

Credentials are scoped to their connection. Monitoring may use a separate
account and collector connection; turning on a dashboard does not authorize it
to borrow an interactive SQL transaction. Do not paste credentials into SQL
history, bug reports or shared design assets.

## First safe checks

Open the database dashboard, inspect an object, then run a read-only query in
the shared editor. Check the connection label, result-row limit and autocommit
setting before any write. A result page shows buffered rows and only the native
timings or plans that the provider actually reports. See
[engine workflows](Engine-Workflows) for engine-specific differences.
