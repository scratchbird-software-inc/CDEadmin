# ScratchRobin documentation

ScratchRobin CDE Admin is a multi-engine database administration and development
environment. It is currently **0.1.0-dev** and is not approved for production
release. An engine appears in the explorer when its provider is registered;
this does not mean every native workflow has completed end-to-end qualification.

Start with [installation and a first connection](Getting-Started), then use the
[engine workflow guide](Engine-Workflows) for the selected database. The shared
SQL editor, object explorer and forms adapt to the exact provider and connection.
They should not show another engine's unsupported features.

- [Schema diagrams and reviewed changes](Schema-Review)
- [Dashboards and monitoring](Dashboards-and-Monitoring)
- [SQL history and saved work](SQL-History-and-Saved-Work)
- [Troubleshooting](Troubleshooting)
- [Development and qualification](Development-and-Qualification)

The [dated implementation matrix](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/implementation_status.rst)
separates source, local verification, CI and release approval. The
[open-source site](https://scratchbird-software-inc.github.io/CDEadmin/) and
[commercial product page](https://scratchbird.ca/robin) serve different
purposes; neither changes a provider's qualification state.

ScratchRobin is an independent hard fork of pgAdmin 4 9.17, not affiliated
with or endorsed by the pgAdmin Development Team. See the repository
[LICENSE](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/LICENSE)
and [NOTICE](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/NOTICE).
