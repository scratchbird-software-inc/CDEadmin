# How to Create, Alter, Comment, and Drop DuckDB 1.5.2 Sequences & Default Identifiers

DuckDB 1.5.2 provides schema-scoped 64-bit signed **Sequences** (`CREATE [OR REPLACE] [TEMPORARY] SEQUENCE [IF NOT EXISTS]`) with `nextval()` / `currval()` functions and `COMMENT ON SEQUENCE` metadata inspected via `duckdb_sequences()`.

This guide walks through creating, inspecting, commenting, replacing, and dropping DuckDB sequences using ScratchRobin's **Sequence Editor (`SR-F-020023`)**, and binding sequences to table columns via `DEFAULT nextval(...)`.

---

## DuckDB 1.5.2 Sequence Semantics Verified Against Engine Code

1. **Creation Clauses (`OR REPLACE`, `TEMPORARY`, `IF NOT EXISTS`, Bounds & `CYCLE`)**:
   - DuckDB supports `CREATE [OR REPLACE] [TEMPORARY] SEQUENCE [IF NOT EXISTS]`, `START WITH`, `INCREMENT BY` (positive or negative non-zero), `MINVALUE <n>` / `NO MINVALUE`, `MAXVALUE <n>` / `NO MAXVALUE`, and `CYCLE` / `NO CYCLE`.
   - DuckDB forbids combining `OR REPLACE` and `IF NOT EXISTS` in one statement; ScratchRobin's form mutually gates those toggles so invalid combinations cannot be constructed.
2. **Comment-Preserving Edits vs Parameter Replacement (`Edit...`)**:
   - DuckDB 1.5.2 has no in-place `ALTER SEQUENCE ... INCREMENT BY / RESTART WITH` grammar (`ALTER SEQUENCE` only supports `RENAME` and non-durable `OWNED BY`).
   - In ScratchRobin (`SR-F-020023`):
     - **Comment-only edits** compile a non-destructive `COMMENT ON SEQUENCE <schema>.<name> IS '...'` (or `NULL`), preserving `last_value` untouched!
     - **Parameter changes** (`start`, `increment`, `minimum`, `maximum`, `cycle`) require checking **`Confirm generator reset on parameter replacement`** on the **`DuckDB`** tab and compile `CREATE OR REPLACE SEQUENCE ...` followed automatically by `COMMENT ON SEQUENCE ...` so existing documentation comments are never lost!
3. **Non-Advancing Inspection (`duckdb_sequences()`)**:
   - Opening **`Edit...`** displays **Last generated value** directly from `duckdb_sequences().last_value` (`NULL` before first `nextval`) without advancing the sequence.

---

## Step 1: Create a DuckDB Sequence with Bounds & Comment

1. Expand `DuckDB -> <server> -> <database.duckdb> -> Schemas -> main` in **Data Navigator**.
2. Right-click **`Sequences`** (or right-click `main` and choose **`Create -> Sequence...`**) and click **`Create Sequence...`**.
3. Configure **Create sequence (`SR-F-020023`)**:
   - **Name**: `seq_batch_run`
   - **Schema**: `main`
   - **Start value**: `1000`
   - **Increment**: `10`
   - **No minimum bound (`NO MINVALUE`)**: **Checked**
   - **Maximum**: `900000`
   - **Cycle**: **Unchecked**
   - **Comment**: `Analytical batch run counter`
4. Switch to **`SQL`** to verify the two-statement native DuckDB plan and click **`Apply`**:

```sql
CREATE SEQUENCE "main"."seq_batch_run" START WITH 1000 INCREMENT BY 10 NO MINVALUE MAXVALUE 900000;
COMMENT ON SEQUENCE "main"."seq_batch_run" IS 'Analytical batch run counter'
```

![Creating a DuckDB 1.5.2 sequence with NO MINVALUE, MAXVALUE, and COMMENT ON SEQUENCE](images/sequences/ddb-seq-01-create-sequence-form-and-sql.png)

---

## Step 2: Inspect `last_value`, Edit Comment, or Replace Parameters (`Edit...`)

Right-click `seq_batch_run` under **`Sequences`** and select **`Edit...`**:

1. Inspect **Last generated value** (read-only from `duckdb_sequences()`).
2. To update only the **Comment** (or toggle **Clear comment**), edit **Comment** on **`General`** and click **`Apply`** — ScratchRobin runs `COMMENT ON SEQUENCE` without resetting the counter.
3. To re-seed or change step parameters (for example **Start value** = `5000`, **Increment** = `20`), switch to the **`DuckDB`** tab, enable **`Confirm generator reset on parameter replacement`**, verify on the **`SQL`** tab that ScratchRobin emits both `CREATE OR REPLACE SEQUENCE ...` and `COMMENT ON SEQUENCE ...` (preserving your comment!), and click **`Apply`**.

![Editing and replacing a DuckDB sequence while preserving its COMMENT ON SEQUENCE metadata](images/sequences/ddb-seq-02-alter-sequence-comment-and-replace.png)

---

## Step 3: Drop a DuckDB Sequence (`Drop...` Confirmation Modal)

1. Right-click an obsolete sequence (`seq_temp_stage`) under **`Sequences`** and click **`Drop...`**.
2. Toggle **Drop dependent objects (`CASCADE`)** if needed, enter `seq_temp_stage` to confirm, click **`Preview`** to inspect the Planned Statement Impact and `DROP SEQUENCE "main"."seq_temp_stage" CASCADE`, and click **`Run`**.

![Dropping a DuckDB sequence through OperationDialog with CASCADE and typed confirmation](images/sequences/ddb-seq-03-drop-sequence-operation-dialog.png)

---

## Step 4: Live Verification — `DEFAULT nextval()`, `currval()`, and `duckdb_sequences()`

Open the DuckDB SQL workspace (`Right-click <database.duckdb> -> Open DuckDB SQL editor`) to bind `seq_batch_run` to a table's primary key default and inspect `duckdb_sequences()` without advancing it:

```sql
CREATE TABLE pipeline_runs (
  run_id BIGINT DEFAULT nextval('main.seq_batch_run') PRIMARY KEY,
  pipeline_name VARCHAR NOT NULL,
  rows_processed BIGINT NOT NULL CHECK (rows_processed >= 0)
);

INSERT INTO pipeline_runs (pipeline_name, rows_processed) VALUES
  ('bronze_ingest', 125000),
  ('silver_transform', 124890),
  ('gold_rollup', 18400);

SELECT
  r.run_id,
  r.pipeline_name,
  r.rows_processed,
  currval('main.seq_batch_run') AS session_currval,
  s.last_value AS catalog_last_value,
  s.comment AS sequence_comment
FROM pipeline_runs r
CROSS JOIN (SELECT last_value, comment FROM duckdb_sequences() WHERE sequence_name = 'seq_batch_run') s
ORDER BY r.run_id;
```

![Executing DuckDB nextval, currval, and duckdb_sequences() metadata inspection in SQL Studio](images/sequences/ddb-seq-04-live-nextval-currval-default-results.png)
