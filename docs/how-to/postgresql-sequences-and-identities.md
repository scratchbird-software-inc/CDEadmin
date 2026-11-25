# How to Create, Alter, Restart, Comment, and Drop PostgreSQL Sequences & Identity Columns

This guide walks step-by-step through managing PostgreSQL 18.3 **Sequences** (`CREATE SEQUENCE`, `ALTER SEQUENCE`, `RESTART`, `OWNED BY`, `UNLOGGED`, `COMMENT ON SEQUENCE`, `GRANT`, `SECURITY LABEL`, and `DROP SEQUENCE`) using ScratchRobin's **Sequence Editor (`SR-F-020064`)**, as well as SQL-standard **`GENERATED {ALWAYS | BY DEFAULT} AS IDENTITY`** columns.

---

## Capabilities Covered

1. **Typed Integer Sequences (`AS smallint | integer | bigint`)**:
   - Choosing 16-bit (`smallint`), 32-bit (`integer`), or 64-bit (`bigint`, default) sequence arithmetic bounds.
2. **Custom Increment, Bounds, Pre-Allocation Cache, Cycling & Persistence**:
   - Positive or negative `INCREMENT BY`, explicit `START WITH` / `MINVALUE` / `MAXVALUE`, per-session `CACHE`, `CYCLE`, and crash-unlogged `UNLOGGED` sequences (`pg_class.relpersistence = 'u'`).
3. **Column Dependency Ownership (`OWNED BY schema.table.column`)**:
   - Binding a sequence's lifecycle to a specific table column so dropping the column or table automatically drops the sequence.
4. **Non-Advancing Live Inspection & Online `ALTER SEQUENCE` (`Edit...`)**:
   - Reading `Current / last value` from `pg_catalog.pg_sequences` **without** advancing the sequence, restarting to an explicit value (`RESTART WITH <n>`) or back to `START WITH` (`Restart at initial START value?`), changing data type, toggling `LOGGED` / `UNLOGGED`, updating `COMMENT ON SEQUENCE`, and managing `USAGE` / `SELECT` / `UPDATE` privileges and `SECURITY LABEL`s.
5. **Safe Destructive Removal (`Drop...`)**:
   - Reviewing `DROP SEQUENCE ... [CASCADE | RESTRICT]` with typed-name confirmation and Planned Statement Impact.

---

## Step 1: Open Create Sequence from Data Navigator

1. Expand `PostgreSQL -> <server> -> <database> -> Schemas -> <schema>` (for example, `seq_showcase`).
2. Right-click **`Sequences`** (or right-click `<schema>` and choose **`Create -> Sequence...`**) and click **`Create Sequence...`**.

![Opening Create Sequence from the PostgreSQL schema Sequences folder in Data Navigator](images/sequences/pg-seq-01-navigator-create-menu.png)

---

## Step 2: Configure General Identity, Integer Type & Comment

On the **`General`** tab of **Create sequence (`SR-F-020064`)**:

1. Set **Name** to `seq_invoice_number`.
2. Verify **Schema** is pre-filled with `seq_showcase` (and optionally set **Owner**).
3. Select **Data type** = `bigint` (`smallint` bounds to `±32,767`; `integer` bounds to `±2,147,483,647`; `bigint` bounds to `±9,223,372,036,854,775,807`).
4. Enter a **Comment** (`Fiscal invoice allocation sequence`), which emits `COMMENT ON SEQUENCE` in the same transaction.

![Configuring PostgreSQL sequence name, schema, bigint data type, and comment](images/sequences/pg-seq-02-create-general-and-type.png)

---

## Step 3: Configure Increment, Start, Min/Max Bounds, Cache, Cycle & Ownership

Switch to the **`Options`** tab:

1. Set **Increment** = `10` (negative increments such as `-1` create descending sequences).
2. Set **Start** = `1000`, **Minimum** = `1000`, and **Maximum** = `9999990`.
3. Set **Cache** = `20` (each backend pre-allocates 20 values in shared memory for high-concurrency throughput).
4. Leave **Cycle sequence?** unchecked so exhaustion raises an explicit overflow error rather than wrapping around, and leave **Unlogged?** unchecked so WAL recovery preserves sequence progression across crash recovery.
5. Optionally choose **Owned by table** and **Owned by column** (`OWNED BY`) if the sequence belongs exclusively to one table column.

![Configuring PostgreSQL sequence increment, start, bounds, cache, cycle, and unlogged options](images/sequences/pg-seq-03-create-options-and-bounds.png)

---

## Step 4: Preview Multi-Statement PostgreSQL DDL & Apply

Switch to the **`SQL`** tab to verify the generated PostgreSQL 18 DDL before applying:

```sql
CREATE SEQUENCE "seq_showcase"."seq_invoice_number"
  AS bigint
  INCREMENT 10
  MINVALUE 1000
  MAXVALUE 9999990
  START 1000
  CACHE 20;
COMMENT ON SEQUENCE "seq_showcase"."seq_invoice_number" IS 'Fiscal invoice allocation sequence'
```

Click **`Apply`** to create the sequence and refresh `Sequences` in **Data Navigator**.

![Reviewing the generated PostgreSQL CREATE SEQUENCE and COMMENT ON SEQUENCE DDL](images/sequences/pg-seq-04-create-sql-preview.png)

---

## Step 5: Inspect Live Position & Alter / Restart (`Edit...`)

Right-click `seq_invoice_number` under **`Sequences`** and select **`Edit...`**:

1. Switch to **`Options`** — **Current / last value** displays the live `pg_catalog.pg_sequences.last_value` (`NULL` before first `nextval`, or the most recently allocated value) **without** consuming a sequence number.
2. To jump the counter forward (or backward within `MINVALUE`..`MAXVALUE`), enter **Restart** = `5000` (or toggle **Restart at initial START value?** to emit `ALTER SEQUENCE ... RESTART`).
3. Change **Increment** = `25` and update **Comment** on the **`General`** tab (or add ACL grants / revocations and `SECURITY LABEL`s on the **`Security`** tab).
4. Review the incremental diff on the **`SQL`** tab (`ALTER SEQUENCE "seq_showcase"."seq_invoice_number" INCREMENT 25 RESTART WITH 5000;` + `COMMENT ON SEQUENCE ...`) and click **`Apply`**.

![Altering a PostgreSQL sequence to restart at 5000, change increment, and update its comment](images/sequences/pg-seq-05-alter-restart-and-security.png)

---

## Step 6: Drop a Sequence Safely (`Drop...` Confirmation Modal)

To remove an obsolete sequence (`seq_temp_ticket`):

1. Right-click `seq_temp_ticket` under **`Sequences`** and choose **`Drop...`**.
2. In the **`Drop Sequence`** (`OperationDialog`) modal:
   - Toggle **Drop dependent objects (`CASCADE`)** if column defaults depend on the sequence (or leave unchecked to enforce PostgreSQL `RESTRICT` safety).
   - Type `seq_temp_ticket` into **Type the object name to confirm** and click **`Preview`** to inspect the Planned Statement Impact and `DROP SEQUENCE "seq_showcase"."seq_temp_ticket" CASCADE` statement.
3. Click **`Run`**.

![Dropping a PostgreSQL sequence with CASCADE and typed-name confirmation](images/sequences/pg-seq-06-drop-sequence-operation-dialog.png)

---

## Step 7: Live Verification — `nextval()`, `currval()`, and `GENERATED AS IDENTITY`

Open a query workspace (`Right-click cdeadmin_demo -> Open database query workspace...`) to verify both standalone sequences and SQL-standard identity columns (`GENERATED ALWAYS AS IDENTITY` vs `GENERATED BY DEFAULT AS IDENTITY`):

```sql
CREATE TABLE seq_showcase.invoices (
  internal_id bigint GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1) PRIMARY KEY,
  invoice_no bigint NOT NULL DEFAULT nextval('seq_showcase.seq_invoice_number') UNIQUE,
  customer_code text NOT NULL
);

ALTER SEQUENCE seq_showcase.seq_invoice_number OWNED BY seq_showcase.invoices.invoice_no;

INSERT INTO seq_showcase.invoices (customer_code) VALUES ('CUST-ALPHA'), ('CUST-BETA');

SELECT internal_id, invoice_no, customer_code, currval('seq_showcase.seq_invoice_number') AS session_currval
FROM seq_showcase.invoices ORDER BY internal_id;
```

![Executing PostgreSQL nextval, currval, OWNED BY, and GENERATED ALWAYS AS IDENTITY in SQL Studio](images/sequences/pg-seq-07-live-nextval-and-identity-results.png)
