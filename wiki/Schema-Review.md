# Schema diagrams and reviewed changes

ScratchRobin reads authorized native metadata and selected data, maps it to
DDN/DDNA/DDNN workspaces, and stores versioned design assets. The separate DDN
runtime and unified Designer render and edit the diagrams. The database
provider remains responsible for native discovery, authorization, SQL planning,
execution and verification. See the
[roundtrip contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/ddn_database_roundtrip.rst).

1. Capture the exact database or object scope and inspect provenance and
   capture limits. A view filter or absent diagram node is not deletion intent.
2. Save the design revision before editing. Compare the saved baseline, desired
   design and freshly discovered live catalog.
3. Review each native statement, dependency, data-preservation decision and
   explicit deletion selection. Blocked transformations require manual native
   SQL in the shared editor; do not infer that a preview applied anything.
4. Apply only a provider-qualified plan with the owning connection and review
   token. Afterward, rediscover the native catalog and inspect the receipt.

An edited diagram never silently changes a database. Complex native schema
changes may be refused when rows, indexes, triggers, foreign keys or other
dependencies cannot be preserved safely. SQLite and DuckDB have bounded
rebuild contracts; their forms should explain an unsupported transformation
instead of guessing at it.

DDN diagrams are design exchange, not database backups. For recovery, use the
selected engine's native backup/restore workflow and verify the result.
