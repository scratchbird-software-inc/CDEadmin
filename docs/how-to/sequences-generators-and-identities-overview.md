# Core Six Sequences, Generators, and Identity Identifiers Overview

ScratchRobin provides dedicated, dialect-verified graphical editors and lifecycle dialogs for standalone **Sequences / Generators** on every Core Six engine that implements catalog sequence objects (**PostgreSQL 18.3**, **Firebird 5.0.4**, **MariaDB 12.2.2**, and **DuckDB 1.5.2**), alongside first-class **Identity / Auto-Increment Identifier** support on **MySQL 9.7.0**, **SQLite 3.53.x**, **PostgreSQL**, and **Firebird**.

> [!IMPORTANT]
> Engines that do **not** implement standalone `CREATE SEQUENCE` catalog objects (**MySQL 9.7** and **SQLite 3.53**) intentionally omit a stub `Sequences` tree folder (`ui_descriptors/mysql/omitted_families.json` and `ui_descriptors/sqlite/omitted_families.json`) and instead expose native `AUTO_INCREMENT` and `INTEGER PRIMARY KEY AUTOINCREMENT` controls directly inside their Table and Column editors.

---

## 1. Core Six Engine Capability Matrix

| Engine (Reference Version) | Standalone `CREATE SEQUENCE` / `GENERATOR` | Column Identity / Auto-Increment | Alter / Restart (`Edit...`) | Comment (`COMMENT`) | Drop (`Drop...`) | Descriptor Form |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL (`18.3`)** | **Supported** (`AS smallint\|integer\|bigint`, `INCREMENT BY`, `MINVALUE`/`NO MINVALUE`, `MAXVALUE`/`NO MAXVALUE`, `START WITH`, `CACHE`, `CYCLE`, `UNLOGGED`, `OWNED BY tbl.col`) | **`GENERATED {ALWAYS \| BY DEFAULT} AS IDENTITY`** (plus legacy `smallserial` / `serial` / `bigserial`) | **`ALTER SEQUENCE`** (`RENAME TO`, `SET SCHEMA`, `OWNER TO`, `AS <type>`, `INCREMENT`, `MINVALUE`, `MAXVALUE`, `START`, `RESTART [WITH n]`, `CACHE`, `[NO] CYCLE`, `SET LOGGED/UNLOGGED`, `OWNED BY`, `GRANT USAGE/SELECT/UPDATE`, `SECURITY LABEL`) | `COMMENT ON SEQUENCE ... IS '...' \| NULL` (inline on Create & Edit) | `DROP SEQUENCE ... [CASCADE \| RESTRICT]` (`OperationDialog`) | `SR-F-020064` (`ui_descriptors/postgresql/forms/sequence.form.json`) |
| **Firebird (`5.0.4`)** | **Supported** (`CREATE SEQUENCE` / `CREATE GENERATOR`, signed 64-bit `BIGINT` counter, `START WITH`, `INCREMENT BY`) | **`GENERATED {ALWAYS \| BY DEFAULT} AS IDENTITY (START WITH n INCREMENT BY k)`** (`ALTER COLUMN ... RESTART [WITH n]`) | **`ALTER SEQUENCE`** (`RESTART` to initial start, `RESTART WITH <n>`, `INCREMENT BY <k>`, `GRANT/REVOKE USAGE`) | `COMMENT ON SEQUENCE ... IS '...' \| NULL` (`RDB$DESCRIPTION`, inline on Create & Edit + `Remove comment`) | `DROP SEQUENCE ...` (`OperationDialog`, refuses unsupported `CASCADE`) | `SR-F-020032` (`ui_descriptors/firebird/forms/sequence.form.json`) |
| **MariaDB (`12.2.2`)** | **Supported** (`CREATE [OR REPLACE] [TEMPORARY] SEQUENCE [IF NOT EXISTS]`, `AS TINYINT..BIGINT [UNSIGNED]`, `START WITH`, `INCREMENT BY`, `MINVALUE`/`NO MINVALUE`, `MAXVALUE`/`NO MAXVALUE`, `CACHE`/`NOCACHE`, `CYCLE`/`NOCYCLE`) | **`AUTO_INCREMENT`** on integer primary/indexed columns (`ALTER TABLE ... AUTO_INCREMENT = n`) | **`ALTER SEQUENCE`** (`AS <type>`, `RESTART`, `RESTART WITH <n>` with typed-name guard, `START WITH`, `INCREMENT BY`, `MINVALUE`/`NO MINVALUE`, `MAXVALUE`/`NO MAXVALUE`, `CACHE`, `CYCLE`/`NOCYCLE`) | `CREATE SEQUENCE ... COMMENT = '...'` and `ALTER TABLE <seq> COMMENT = '...'` (MariaDB stores sequences as special sequence tables) | `DROP [TEMPORARY] SEQUENCE [IF EXISTS] ...` (`OperationDialog`) | `SR-F-020047` (`ui_descriptors/mariadb/forms/sequence.form.json`) |
| **DuckDB (`1.5.2`)** | **Supported** (`CREATE [OR REPLACE] [TEMPORARY] SEQUENCE [IF NOT EXISTS]`, `START WITH`, `INCREMENT BY`, `MINVALUE`/`NO MINVALUE`, `MAXVALUE`/`NO MAXVALUE`, `CYCLE`/`NO CYCLE`) | Column **`DEFAULT nextval('seq_name')`** (tracked in `duckdb_dependencies()`) | Comment-only edits run non-destructive `COMMENT ON SEQUENCE`; parameter edits compile guarded **`CREATE OR REPLACE SEQUENCE`** (requires explicit state-reset confirmation and preserves comments) | `COMMENT ON SEQUENCE ... IS '...' \| NULL` (inline on Create & Edit + `Clear comment`) | `DROP SEQUENCE ... [CASCADE]` (`OperationDialog`) | `SR-F-020023` (`ui_descriptors/duckdb/forms/sequence.form.json`) |
| **MySQL (`9.7.0`)** | *Not supported by engine* (`ERROR 1064`) | **`AUTO_INCREMENT`** (`TINYINT`..`BIGINT [UNSIGNED]`, table `AUTO_INCREMENT = n`, `@@auto_increment_increment`, `LAST_INSERT_ID()`, plus `DEFAULT (UUID_TO_BIN(UUID(), 1))`) | `ALTER TABLE <tbl> AUTO_INCREMENT = <n>` and `MODIFY COLUMN ... AUTO_INCREMENT` | Column `COMMENT '...'` and Table `COMMENT = '...'` | Column/Table `DROP` | `SR-F-020055` (`ui_descriptors/mysql/forms/table.form.json`) |
| **SQLite (`3.53.x`)** | *Not supported by engine* | **`INTEGER PRIMARY KEY`** (`rowid` alias) and **`INTEGER PRIMARY KEY AUTOINCREMENT`** (monotonic high-water mark persisted in `sqlite_sequence`) | Inspect/seed `sqlite_sequence` (`UPDATE sqlite_sequence SET seq = <n> WHERE name = '<tbl>'`) or table `rebuild` (`SR-F-030864`) | Preserved inline `--` SQL comments in `sqlite_master.sql` | Table `DROP` | `SR-F-020079` (`ui_descriptors/sqlite/forms/table.form.json`) |

---

## 2. Step-by-Step Engine Manuals (With Live Screenshots)

- [PostgreSQL 18.3 Sequences & Identity Columns How-To](postgresql-sequences-and-identities.md)
- [Firebird 5.0.4 Generators, Sequences & Identity Columns How-To](firebird-generators-sequences-and-identities.md)
- [MariaDB 12.2.2 Sequences & `AUTO_INCREMENT` How-To](mariadb-sequences-and-auto-increment.md)
- [DuckDB 1.5.2 Sequences & Default Identifiers How-To](duckdb-sequences-and-constraints.md)

---

## 3. Identifier Workflows on Engines Without Standalone Sequences (`MySQL 9.7` & `SQLite 3.53`)

### A. MySQL 9.7 — `AUTO_INCREMENT`, Custom Seed Values & Ordered Binary UUIDs

MySQL 9.7 manages surrogate numeric identifiers at the table and column level rather than through `CREATE SEQUENCE`:

1. **Table / Column Editor (`SR-F-020055`)**:
   - Mark the integer key column (`BIGINT UNSIGNED`, `INT UNSIGNED`, etc.) **`NOT NULL`**, **`PRIMARY KEY`**, and **`AUTO_INCREMENT`**, and optionally set the table's initial **`Auto-increment`** seed on the `Options` / `MySQL` tab.
2. **Advancing or Resetting the Counter (`ALTER TABLE ... AUTO_INCREMENT = N`)**:
   - Raise the next generated identifier at any time with `ALTER TABLE orders AUTO_INCREMENT = 50000;` (InnoDB persists the counter in the redo-protected data dictionary across restarts in MySQL 8.0+/9.7).
3. **Time-Ordered Binary UUIDs (`UUID_TO_BIN(UUID(), 1)`)**:
   - For distributed multi-writer identifiers without sequence contention, MySQL 9.7 supports expression defaults (`BINARY(16) DEFAULT (UUID_TO_BIN(UUID(), 1)) PRIMARY KEY`), rearranging timestamp bits first for B-tree locality.

```sql
CREATE TABLE mysql_id_orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'Monotonic InnoDB auto-increment key',
  public_uuid BINARY(16) NOT NULL DEFAULT (UUID_TO_BIN(UUID(), 1)) UNIQUE COMMENT 'Time-swapped binary UUID',
  customer_ref VARCHAR(64) NOT NULL
) ENGINE=InnoDB AUTO_INCREMENT=50000 COMMENT='MySQL 9.7 identity showcase';

INSERT INTO mysql_id_orders (customer_ref) VALUES ('ACME-NORTH'), ('ACME-SOUTH');
ALTER TABLE mysql_id_orders AUTO_INCREMENT = 60000;
INSERT INTO mysql_id_orders (customer_ref) VALUES ('ACME-WEST');

SELECT order_id, BIN_TO_UUID(public_uuid, 1) AS uuid_text, customer_ref, LAST_INSERT_ID() AS last_id
FROM mysql_id_orders ORDER BY order_id;
```

![Executing MySQL 9.7 AUTO_INCREMENT seeding, LAST_INSERT_ID(), and UUID_TO_BIN identifiers in SQL Studio](images/sequences/mysql-id-01-live-auto-increment-and-uuid-identifiers.png)

---

### B. SQLite 3.53 — `INTEGER PRIMARY KEY` vs `AUTOINCREMENT` & `sqlite_sequence`

SQLite provides two distinct integer identifier mechanisms inside **Create / Edit Table (`SR-F-020079`)**:

1. **`INTEGER PRIMARY KEY` (Fast `rowid` Alias — Recommended Default)**:
   - Maps directly to SQLite's internal 64-bit signed B-tree `rowid`. Picks `MAX(rowid) + 1` in $O(\log N)$ time without extra table writes; deleted tail IDs can be reused.
2. **`INTEGER PRIMARY KEY AUTOINCREMENT` (Strict Monotonic Never-Reuse)**:
   - Creates and updates SQLite's internal `sqlite_sequence(name, seq)` catalog table so a previously allocated ID is **never** reused even after deleting the highest row (raises `SQLITE_FULL` if `9223372036854775807` is reached).
   - Works cleanly inside `STRICT` tables (`id INTEGER PRIMARY KEY AUTOINCREMENT`).
3. **Inspecting or Advancing the High-Water Mark**:
   - Query `SELECT name, seq FROM sqlite_sequence;` to inspect the current value without advancing it, or run `UPDATE sqlite_sequence SET seq = 10000 WHERE name = 'ledger_entries';` to advance the next generated key to `10001`.

```sql
CREATE TABLE ledger_entries (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_code TEXT NOT NULL CHECK (length(account_code) >= 3),
  amount_cents INTEGER NOT NULL
) STRICT;

INSERT INTO ledger_entries (account_code, amount_cents) VALUES ('AR-100', 12500), ('AP-200', -4200);
UPDATE sqlite_sequence SET seq = 9000 WHERE name = 'ledger_entries';
INSERT INTO ledger_entries (account_code, amount_cents) VALUES ('REV-300', 88000);

SELECT e.entry_id, e.account_code, e.amount_cents, s.seq AS high_water_mark
FROM ledger_entries e CROSS JOIN sqlite_sequence s WHERE s.name = 'ledger_entries'
ORDER BY e.entry_id;
```

![Executing SQLite 3.53 STRICT table AUTOINCREMENT and sqlite_sequence seeding in SQL Studio](images/sequences/sqlite-id-01-live-autoincrement-sqlite-sequence.png)
