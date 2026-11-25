# How to Create DuckDB Custom Types (`ENUM`, `STRUCT`, `UNION`, `ALIAS` / `ARRAY`) and Constraints

This guide walks step-by-step through creating, inspecting, and constraining **DuckDB Custom Types** (`CREATE TYPE ... AS ...`) using ScratchRobin's **DuckDB Type Editor (`SR-F-020026`)** and SQL Studio.

---

## How DuckDB Custom Types & Constraints Work Together

DuckDB 1.5 provides rich analytical and nested custom types via `CREATE TYPE`, while intentionally omitting SQL-92 `CREATE DOMAIN`:

1. **Type-Layer Structural & Closed-Set Constraints (`CREATE TYPE`)**:
   - **`ENUM` (`ENUM ('draft', ...)`):** Enforces a closed set of allowed string literals natively via dictionary encoding — invalid strings fail immediately on cast or `INSERT`.
   - **`STRUCT` (`STRUCT(field1 T1, field2 T2, ...)`):** Enforces exact named member structure and nested field types.
   - **`UNION` (`UNION(tag1 T1, tag2 T2, ...)`):** Enforces a closed set of explicitly tagged disjoint type alternatives (`union_tag(...)`).
   - **`ALIAS` (`DECIMAL(18,4)`, `DOUBLE[4]`, `VARCHAR[]`, `MAP(VARCHAR, INTEGER)`):** Enforces numeric precision/scale, fixed-size `ARRAY` cardinality (`DOUBLE[4]` rejects 3- or 5-element arrays at the type layer!), or key-value map typing.
2. **Value-Predicate Constraints (`CHECK`, `NOT NULL`, `DEFAULT` on Columns/Tables)**:
   - Numeric bounds (`CHECK (amount >= 0)`), nested `STRUCT` field rules (`CHECK (length(destination.country_iso) = 2)`), and `UNION` tag rules bind on columns using your custom types.

---

## Step 1: Open Create Type from Data Navigator

1. Open **Data Navigator**, expand `DuckDB -> <server> -> <database.duckdb> -> Schemas -> <schema>` (for example, `main`).
2. Right-click **`Types`** (or right-click `<schema>` and choose **`Create -> Type...`**) and click **`Create Type...`**.
   - ScratchRobin pre-populates **`Schema`** with the selected schema (`main`).

![Opening Create Type under DuckDB Schemas -> main -> Types](images/custom-types/ddb-01-navigator-types-create-menu.png)

---

## Step 2: Create a Closed-Set `ENUM` Type (`order_stage_t`)

1. On **`General`**, set:
   - **Name**: `order_stage_t`
   - **Schema**: `main`
   - **Type kind**: `Enum (Closed-Set Values)`
   - **Comment**: `Closed-set fulfillment lifecycle enforced at the dictionary type layer`
2. Switch to **`Constraints`** and add allowed literals in the **Enum values** grid (`draft`, `confirmed`, `dispatched`, `settled`, `void`).
3. Click **`Apply`** (compiles `CREATE TYPE "main"."order_stage_t" AS ENUM ('draft', 'confirmed', 'dispatched', 'settled', 'void')` + `COMMENT ON TYPE`).

![Defining closed-set Enum literals for a DuckDB ENUM custom type](images/custom-types/ddb-02-type-enum-values-grid.png)

---

## Step 3: Create a Composite `STRUCT` Type (`shipping_address_t`)

1. Right-click **`Types -> Create Type...`**.
2. On **`General`**, set **Name** = `shipping_address_t`, **Schema** = `main`, and **Type kind** = `Struct (Composite Fields)`.
3. Switch to **`Constraints`** and add member fields in the **Struct/union fields** grid (each row offers a `ComboBox` with DuckDB's built-in scalar and nested types):
   - `street` — `VARCHAR`
   - `city` — `VARCHAR`
   - `country_iso` — `VARCHAR`
   - `postal_code` — `VARCHAR`
4. Click **`Apply`**.

![Defining composite member fields on a DuckDB STRUCT custom type](images/custom-types/ddb-03-type-struct-fields-grid.png)

---

## Step 4: Create a Tagged Disjoint `UNION` Type (`settlement_instrument_t`)

1. Right-click **`Types -> Create Type...`**.
2. Set **Name** = `settlement_instrument_t` and **Type kind** = `Union (Tagged Disjoint Alternatives)`.
3. On **`Constraints`**, add each tagged alternative in **Struct/union fields**:
   - `ach_routing` — `VARCHAR`
   - `wire_ref` — `BIGINT`
   - `credit_note` — `VARCHAR`
4. Click **`Apply`**. Every value stored in a `settlement_instrument_t` column is guaranteed to hold exactly one of those three typed alternatives.

![Defining tagged alternatives on a DuckDB UNION custom type](images/custom-types/ddb-04-type-union-alternatives-grid.png)

---

## Step 5: Create Fixed-Cardinality `ARRAY`, `MAP`, and Precision `ALIAS` Types (`kpi_quartiles_t`)

1. Right-click **`Types -> Create Type...`**.
2. Choose **Type kind** from any of DuckDB 1.5's six native forms (and optionally enable **Replace existing type** for `CREATE OR REPLACE TYPE` or **Temporary (session-scoped)** for `CREATE TEMPORARY TYPE`):
   - **`Array (Fixed-Length T[N])`**: set **Name** = `kpi_quartiles_t`, **Element type** = `DOUBLE`, and **Array length** = `4` (compiles `CREATE TYPE "main"."kpi_quartiles_t" AS DOUBLE[4]`, enforcing exact 4-element cardinality at the type layer!).
   - **`Map (Key-Value MAP(K, V))`**: set **Map key type** (e.g. `VARCHAR`) and **Map value type** (e.g. `INTEGER[]` or `DOUBLE`).
   - **`Alias (Scalar / List / Nested Expression)`**: set **Alias base type** (e.g. `DECIMAL(18,4)` or `VARCHAR[]`).
3. Switch to **`SQL`** to preview `CREATE TYPE "main"."kpi_quartiles_t" AS DOUBLE[4]` + `COMMENT ON TYPE`, and click **`Apply`**.
   - Double-clicking or right-clicking **`Inspect...`** on any created DuckDB type in **Data Navigator** opens the read-only inspector pre-populated with its resolved `ENUM` literals, `STRUCT`/`UNION` members, `ARRAY` element/length, or `MAP` key/value types!

![Previewing SQL for a fixed-length DOUBLE[4] DuckDB ARRAY alias type](images/custom-types/ddb-05-type-fixed-array-alias-sql.png)

---

## Step 6: Inspect & Replace Existing DuckDB Custom Types (`Inspect...` & `CREATE OR REPLACE TYPE`)

DuckDB does not implement `ALTER TYPE` in its SQL grammar — instead, existing types are inspected from `duckdb_types()` and updated when unreferenced via **`CREATE OR REPLACE TYPE`**:

1. **Inspecting an Existing Type (`Inspect...`)**:
   - Expand `Schemas -> <schema> -> Types` in **Data Navigator**, right-click any custom type (for example `shipping_address_t`), and click **`Inspect...`** (or double-click the node).
   - ScratchRobin unpacks the catalog definition from `duckdb_types()` and populates the read-only inspector with its `Schema`, `Type kind`, `Comment`, and structured `ENUM` literals, `STRUCT` / `UNION` member fields, `ARRAY` element/length, or `MAP` key/value types.
2. **Replacing an Unreferenced Type (`Replace existing type`)**:
   - Open **`Create Type...`**, enter the existing **Schema** and **Name**, check **`Replace existing type`** on **`General`**, update its definition, and click **`Apply`** — ScratchRobin emits `CREATE OR REPLACE TYPE "main"."<name>" AS ...`!

![Inspecting an existing DuckDB STRUCT custom type unpacked from duckdb_types()](images/custom-types/ddb-06-inspect-struct-type.png)

---

## Step 7: Drop DuckDB Custom Types Safely (`Drop...`)

1. Right-click the custom type under `Schemas -> <schema> -> Types` (for example `legacy_code_t`) and click **`Drop...`**.
2. In the modal **Drop Custom type Operation Dialog**:
   - Toggle **Include dependent objects** (`CASCADE`) if dependent objects should be dropped alongside the type, or leave unchecked (`RESTRICT` default) to block dropping types still referenced by tables or views.
   - Enter the exact type name in **`Type legacy_code_t to confirm`**.
   - Click **`Preview`** to review the **Planned Statement Impact** (`remove` / `destructive`) and **Provider plan** (`DROP TYPE "main"."legacy_code_t" CASCADE`).
3. Click **`Run`** to execute the drop and automatically refresh **Data Navigator**.

![Dropping a DuckDB custom type safely through OperationDialog with CASCADE, typed confirmation, and SQL preview](images/custom-types/ddb-07-drop-type-operation-dialog.png)

---

## Step 8: Combine DuckDB Custom Types with Column `CHECK`, `NOT NULL`, and `DEFAULT` Constraints

Open the **DuckDB SQL Editor** (`SQL + Data Split`) to verify how `ENUM`, `DECIMAL(18,4)` alias (`CREATE OR REPLACE TYPE`), `STRUCT` member predicates (`length(destination.country_iso) = 2`), `UNION` values (`union_value(...)` / `union_tag(...)`), and fixed `DOUBLE[4]` arrays work together on a live table:

![Live DuckDB execution combining ENUM, STRUCT, UNION, and fixed ARRAY custom types with CHECK constraints](images/custom-types/ddb-08-live-duckdb-custom-types-and-constraints-results.png)
