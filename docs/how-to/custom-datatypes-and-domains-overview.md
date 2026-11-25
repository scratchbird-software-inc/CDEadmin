# Core Six Custom Datatypes, Domains, and Constraint Variations Overview

ScratchRobin surfaces custom datatypes and reusable SQL domains natively per database engine — exposing full enterprise editors where the engine provides schema- or database-level custom types, and intentionally omitting stub menus on engines that enforce types strictly at the column/table level.

---

## 1. Core Six Engine Support Matrix

| Engine (Reference Version) | Reusable Domains (`CREATE DOMAIN`) | Custom Types (`CREATE TYPE`) | Alter & Drop Lifecycle | Navigator Location | ScratchRobin Descriptor Form |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL (`18.3`)** | **Supported** (`AS base_type`, `COLLATE`, `DEFAULT`, `NOT NULL`, multiple named `CHECK` constraints, `NOT VALID` + `VALIDATE CONSTRAINT`, array base types, `OWNER`, `COMMENT`, `GRANT USAGE`, `SECURITY LABEL`) | **Supported** (`COMPOSITE`, `ENUM`, `RANGE` + `MULTIRANGE`, `EXTERNAL` base types, `SHELL` types) | **`Edit...`** (`RENAME TO`, `SET SCHEMA`, `OWNER TO`, `SET/DROP DEFAULT`, `SET/DROP NOT NULL`, `ADD/DROP/VALIDATE/RENAME CONSTRAINT`, `ADD/RENAME VALUE`, `ADD/ALTER/DROP/RENAME ATTRIBUTE`) + **`Drop...`** (`OperationDialog` with `CASCADE` + typed-name confirmation + Planned Statement Impact) | `<database> -> Schemas -> <schema> -> Domains` and `Types` (also right-click `<schema> -> Create`) | `SR-F-020068` (`ui_descriptors/postgresql/forms/type.form.json`) |
| **Firebird (`5.0.4`)** | **Supported** (scalar types, `NUMERIC`/`DECIMAL`/`INT128`/`DECFLOAT`, `CHARACTER SET`, `COLLATE`, multi-dimensional array bounds `[l:u]`, `BLOB SUB_TYPE TEXT/BINARY SEGMENT SIZE`, `DEFAULT`, `NOT NULL`, `CHECK (VALUE ...)`, `COMMENT ON DOMAIN`, DDL privileges `GRANT CREATE/ALTER ANY/DROP ANY DOMAIN`) | *N/A* (Firebird uses Domains for reusable scalar, array, and BLOB definitions) | **`Edit...`** (`ALTER DOMAIN ... TO new_name`, `TYPE`, `SET/DROP DEFAULT`, `SET/DROP NOT NULL`, atomic `DROP CONSTRAINT` + `ADD [CONSTRAINT name] CHECK (...)`, `COMMENT ON DOMAIN ... IS NULL`) + **`Drop...`** (`OperationDialog` with typed-name confirmation + Planned Statement Impact) | `<database> -> programming -> domains` (also right-click `<database>` or `programming -> Create`) | `SR-F-020036` (`ui_descriptors/firebird/forms/type.form.json`) |
| **DuckDB (`1.5.2`)** | *N/A* (DuckDB does not implement `CREATE DOMAIN`; value predicates bind via `ENUM`, fixed `ARRAY[N]`, and column `CHECK` constraints) | **Supported** (`ALIAS` scalar/list/nested, `ENUM`, `STRUCT`, `UNION`, fixed-length `ARRAY` `T[N]`, `MAP(K, V)`, `TEMPORARY` + `COMMENT ON TYPE`) | **`Inspect...`** (read-only catalog inspector unpacking `ENUM`, `STRUCT`, `UNION`, `ARRAY`, and `MAP` definitions) + **`CREATE OR REPLACE TYPE`** (`Replace existing type` option) + **`Drop...`** (`OperationDialog` with `CASCADE` + typed-name confirmation + Planned Statement Impact) | `<database> -> Schemas -> <schema> -> Types` (also right-click `<schema> -> Create`) | `SR-F-020026` (`ui_descriptors/duckdb/forms/type.form.json`) |
| **MySQL (`9.7.0`)** | *Not supported by engine* (`ERROR 1064`) | *Not supported by engine* (`ERROR 1064`) | Column-level `ALTER TABLE ... MODIFY COLUMN` / `DROP CHECK` | Intentionally omitted (`ui_descriptors/mysql/omitted_families.json`); inline `ENUM(...)`, `SET(...)`, and `CHECK (...)` live in the Table/Column editor (`SR-F-020055`) | Column/Table Editor |
| **MariaDB (`12.2.2`)** | *Not supported by engine* (`ERROR 1064`) | *Not supported at schema level* (built-in type plugins `UUID`, `INET4`, `INET6` + inline `ENUM`/`SET`) | Column-level `ALTER TABLE ... MODIFY COLUMN` / `DROP CONSTRAINT` | Intentionally omitted (`ui_descriptors/mariadb/omitted_families.json`); plugin types and `CHECK` constraints live in the Table/Column editor (`SR-F-020045`) | Column/Table Editor |
| **SQLite (`3.53.x`)** | *Not supported by engine* | *Not supported by engine* | Table rebuild / `ALTER TABLE` | Intentionally omitted (`ui_descriptors/sqlite/omitted_families.json`); `STRICT` table typing + column/table `CHECK` constraints live in the Table editor (`SR-F-020079`) | Column/Table Editor |

---

## 2. Constraint Variations Covered Across the Manuals

Each per-engine manual walks through creating, previewing SQL, applying, inspecting, altering, and testing live data against every supported constraint pattern:

1. **Nullability & Defaults**:
   - Mandatory (`NOT NULL`) with static literals (`0.00`, `'NORMAL'`) and runtime context functions (`CURRENT_TIMESTAMP`, `'{}'::text[]`).
   - Nullable domains with explicit null-tolerant `CHECK` predicates (`VALUE IS NULL OR ...` in Firebird vs SQL-standard unknown-passes-check semantics).
2. **Numeric Range & Precision Bounds**:
   - Fixed scale (`NUMERIC(5,2)`, `DECIMAL(18,4)`) combined with inclusive/exclusive range checks (`VALUE BETWEEN 0.00 AND 100.00`, multiple named `chk_min` / `chk_max` constraints in PostgreSQL).
3. **String Format, Character Set, Collation & Regex Constraints**:
   - POSIX regular expressions in PostgreSQL (`VALUE ~* '^[A-Za-z0-9._%+-]+@...'` with `COLLATE "C"`),
   - SQL-standard `SIMILAR TO` patterns in Firebird 5 (`CHARACTER SET UTF8` + `COLLATE UNICODE_CI_AI`),
   - Closed-set membership (`ENUM` dictionary types in PostgreSQL & DuckDB; `CHECK (VALUE IN (...))` in Firebird).
4. **Deferred Validation & Online Constraint Rollout (PostgreSQL)**:
   - Adding a `CHECK` constraint marked **`NOT VALID`** so existing legacy rows remain readable/writable while all new writes are checked immediately, followed by online `ALTER DOMAIN ... VALIDATE CONSTRAINT ...`.
5. **Composite, Tagged Union, Range & Array Structural Constraints**:
   - **PostgreSQL**: `COMPOSITE` types (`monetary_amount_t`), `RANGE` + automatic `MULTIRANGE` types (`validity_period_range`), and `ARRAY` domains (`cardinality(VALUE) <= 5 AND array_position(VALUE, NULL) IS NULL`).
   - **Firebird 5**: Multi-dimensional `ARRAY` domains (`NUMERIC(14,2)[1:4]`) and `BLOB SUB_TYPE TEXT SEGMENT SIZE 80` length-checked domains.
   - **DuckDB**: `STRUCT` composite types with member-level `CHECK` predicates (`length(destination.country_iso) = 2`), `UNION` tagged disjoint types (`union_tag(...)`), and fixed-size `ARRAY` aliases (`DOUBLE[4]`).

---

## 3. Step-by-Step Engine Manuals (With Live Screenshots)

- [PostgreSQL Domains & Custom Types How-To](postgresql-domains-and-custom-types.md)
- [Firebird 5 Domains & Constraint Variations How-To](firebird-domains-and-constraints.md)
- [DuckDB Custom Types (`ENUM`, `STRUCT`, `UNION`, `ALIAS` / `ARRAY`) & Constraints How-To](duckdb-custom-types-and-constraints.md)

---

## 4. Reference Patterns for Engines Without Standalone Custom Types

When modelling portable schemas targeting **MySQL 9.7**, **MariaDB 12.2**, or **SQLite 3.53** (or converting from PostgreSQL / Firebird / DuckDB in ScratchRobin's ERD & Data Modelling tool):

- **MySQL 9.7**: Use inline `ENUM('draft', 'confirmed', ...)` or `SET(...)` on the column together with named `CONSTRAINT chk_... CHECK (...) ENFORCED` table/column checks.
- **MariaDB 12.2**: Use native `UUID`, `INET4`, `INET6`, and `JSON` column types alongside inline `ENUM(...)` and named `CONSTRAINT chk_... CHECK (...)` clauses.
- **SQLite 3.53**: Enable **`STRICT`** table mode (`INT`, `INTEGER`, `REAL`, `TEXT`, `BLOB`, `ANY`) so SQLite enforces storage classes instead of type affinity, paired with `NOT NULL`, `DEFAULT`, and `CHECK (...)` constraints.
