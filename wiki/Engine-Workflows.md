# Engine workflows

The Data Explorer has 24 engine connector roots and 26 provider profiles.
YugabyteDB YSQL/YCQL and OpenSearch native/SQL-PPL are distinct protocol
profiles under their respective engine roots. A visible root is an inventory
entry, not proof of full release qualification.

Select the **exact** engine and endpoint before using the shared SQL editor.
Its language, object completion, plans, transaction controls and result grid
follow that connection. Native object trees, context menus and forms follow
the selected engine's supported objects and version; they are not a least-common-
denominator catalog.

| Engine family | Starting point | Important distinction |
| --- | --- | --- |
| Firebird | [Functional contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/firebird_functional_completion.rst) | MGA transactions, service operations and database-level triggers are native Firebird features. |
| PostgreSQL | [Functional contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/postgresql_functional_completion.rst) | Native schemas, OIDs, roles, privileges and version-specific object forms remain PostgreSQL-specific. |
| MySQL | [Functional contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/mysql_functional_completion.rst) | Database/schema equivalence and MySQL-native administration apply. |
| MariaDB | [Functional contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/mariadb_functional_completion.rst) | It has a separate provider and must be verified separately from MySQL. |
| DuckDB | [Functional contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/duckdb_functional_completion.rst) | Registered files, attached catalogs and session-owned attachments are not remote servers. |
| SQLite | [Functional contract](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/sqlite_functional_completion.rst) | A registered file is the database target; attached schemas are session-scoped. |

Other engines have provider-specific driver guides in
[`docs/en_US`](https://github.com/scratchbird-software-inc/CDEadmin/tree/master/docs/en_US).
Check the [dated status matrix](https://github.com/scratchbird-software-inc/CDEadmin/blob/master/docs/en_US/implementation_status.rst)
and the selected provider's capability gate before treating a menu action as
qualified. The native ScratchBird provider is deferred while reference-engine
browser work is completed.

For a row edit, first confirm that the grid has a proved native row identity;
a read-only view or a row without a stable key may browse but must not offer a
guessed update target. Backup, restore and schema changes use reviewed native
workflows with exact endpoint and database/file scope.
