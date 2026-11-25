# How to Create, Alter, Restart, Comment, and Drop Firebird 5 Generators, Sequences & Identity Columns

In Firebird 5.0, SQL-standard **Sequences** (`CREATE SEQUENCE`, `ALTER SEQUENCE`, `NEXT VALUE FOR`) and classic InterBase/FlameRobin **Generators** (`CREATE GENERATOR`, `SET GENERATOR`, `GEN_ID`) are **the exact same catalog object** in `RDB$GENERATORS`: every user sequence/generator is a lock-free, non-transactional signed 64-bit (`BIGINT`) atomic counter.

This guide walks through creating, inspecting, restarting, commenting, granting `USAGE`, and dropping Firebird 5 sequences/generators in ScratchRobin's **Sequence Editor (`SR-F-020032`)**, alongside table-column **`GENERATED {ALWAYS | BY DEFAULT} AS IDENTITY`** identifiers.

---

## Firebird 5 Sequence & Generator Rules Verified Against Engine Semantics

1. **64-Bit Signed Range & Non-Transactional Atomicity**:
   - Every Firebird Dialects 3 sequence is 64-bit signed (`-9,223,372,036,854,775,808` to `9,223,372,036,854,775,807`). Advancing a sequence via `NEXT VALUE FOR` or `GEN_ID(seq, step)` is immediate and never rolls back when an enclosing DML transaction rolls back.
2. **Engine-Accurate Clause Scope (No Fake Clauses)**:
   - Firebird 5 does **not** support `MINVALUE`, `MAXVALUE`, `CACHE`, or `CYCLE` on `CREATE/ALTER SEQUENCE`; ScratchRobin intentionally omits those unsupported fields rather than rendering dead controls.
3. **`START WITH` vs `RESTART WITH` (`RDB$INITIAL_VALUE` Semantics)**:
   - Firebird stores the initial `START WITH` value in `RDB$GENERATORS.RDB$INITIAL_VALUE`.
   - `ALTER SEQUENCE <name> RESTART` resets the generator so the **next** `NEXT VALUE FOR` returns `RDB$INITIAL_VALUE` (`Restart at original start`).
   - `ALTER SEQUENCE <name> RESTART WITH <N>` sets the generator so the **next** `NEXT VALUE FOR` returns `<N>` (unlike legacy `SET GENERATOR <name> TO <N>`, which set the *current* value so the next `NEXT VALUE FOR` returned `N + increment`!).
4. **Live Non-Advancing Inspection (`GEN_ID(seq, 0)`)**:
   - Opening **`Edit...`** inspects the live counter (`Current generator value`) via `GEN_ID(<seq>, 0)` without advancing the sequence.

---

## Step 1: Open Create Sequence from `programming -> sequences`

1. Expand `Firebird -> <server> -> <database.fdb> -> programming` in **Data Navigator**.
2. Right-click **`sequences`** (or right-click `programming` / `<database.fdb>` and choose **`Create -> Sequence...`**) and click **`Create Sequence...`**.

![Opening Create Sequence under Firebird programming -> sequences in Data Navigator](images/sequences/fb-seq-01-navigator-generators-create.png)

---

## Step 2: Configure Generator Start Value, Step Increment & `RDB$DESCRIPTION` Comment

On **Create sequence (`SR-F-020032`)**:

1. Set **Name** to `GEN_LEDGER_ENTRY`.
2. Set **Start value** = `10000` (accepts full signed 64-bit integer text) and **Increment by** = `5` (any non-zero 32-bit signed integer).
3. Enter **Comment** = `General ledger batch sequence` (stored in `RDB$GENERATORS.RDB$DESCRIPTION` via `COMMENT ON SEQUENCE`).
4. Switch to **`SQL`** to verify the two-statement native Firebird 5 plan and click **`Apply`**:

```sql
CREATE SEQUENCE "GEN_LEDGER_ENTRY" START WITH 10000 INCREMENT BY 5;
COMMENT ON SEQUENCE "GEN_LEDGER_ENTRY" IS 'General ledger batch sequence'
```

![Creating a Firebird 5 sequence/generator with START WITH, INCREMENT BY, and COMMENT ON SEQUENCE](images/sequences/fb-seq-02-create-generator-form-and-sql.png)

---

## Step 3: Inspect Current Value, Restart Counter & Update Comment (`Edit...`)

Right-click `GEN_LEDGER_ENTRY` under **`sequences`** and choose **`Edit...`**:

1. Inspect the read-only **Current generator value** and **Owner** (`SYSDBA`) reported directly from `RDB$GENERATORS` without advancing the counter.
2. Enter **Next generated value** = `25000` (or check **Restart at original start** to emit `ALTER SEQUENCE "GEN_LEDGER_ENTRY" RESTART`).
3. Change **Increment by** = `10` and update **Comment** (or check **Remove comment** to emit `COMMENT ON SEQUENCE "GEN_LEDGER_ENTRY" IS NULL`).
4. Switch to **`SQL`** to review the generated Firebird 5 DDL and click **`Apply`**:

```sql
ALTER SEQUENCE "GEN_LEDGER_ENTRY" RESTART WITH 25000 INCREMENT BY 10;
COMMENT ON SEQUENCE "GEN_LEDGER_ENTRY" IS 'General ledger batch sequence — adjusted for Q4'
```

> [!TIP]
> To grant or revoke `USAGE` on a Firebird sequence/generator (`GRANT USAGE ON SEQUENCE "GEN_LEDGER_ENTRY" TO USER/ROLE/PROCEDURE/TRIGGER/PACKAGE ...`), use the object security controls or right-click privilege operations surfaced from `firebird/capabilities.json`.

![Altering a Firebird 5 sequence with RESTART WITH, INCREMENT BY, and updated RDB$DESCRIPTION comment](images/sequences/fb-seq-03-alter-restart-and-comment.png)

---

## Step 4: Drop a Sequence / Generator (`Drop...` Confirmation Modal)

1. Right-click an obsolete generator (`GEN_OBSOLETE`) under **`sequences`** and select **`Drop...`**.
2. Notice that Firebird does not support `DROP SEQUENCE ... CASCADE` — ScratchRobin hides unsupported cascade options and checks `RDB$DEPENDENCIES` so dependent triggers, procedures, or computed defaults are never silently broken.
3. Type `GEN_OBSOLETE` to confirm, click **`Preview`** to review `DROP SEQUENCE "GEN_OBSOLETE"`, and click **`Run`**.

![Dropping a Firebird 5 sequence/generator through the OperationDialog confirmation modal](images/sequences/fb-seq-04-drop-generator-operation-dialog.png)

---

## Step 5: Live Verification — `NEXT VALUE FOR`, `GEN_ID(..., 0)`, and Identity Columns

Open the Firebird SQL workspace (`Right-click <database.fdb> -> Open Firebird SQL editor`) to verify `NEXT VALUE FOR`, non-advancing `GEN_ID(..., 0)` inspection, and Firebird 5 **`GENERATED BY DEFAULT AS IDENTITY`** columns:

```sql
CREATE TABLE "LEDGER_POSTINGS" (
  "POSTING_ID" BIGINT GENERATED BY DEFAULT AS IDENTITY (START WITH 500 INCREMENT BY 2) PRIMARY KEY,
  "BATCH_SEQ" BIGINT DEFAULT NEXT VALUE FOR "GEN_LEDGER_ENTRY" NOT NULL,
  "NARRATIVE" VARCHAR(100) CHARACTER SET UTF8 NOT NULL
);

INSERT INTO "LEDGER_POSTINGS" ("NARRATIVE") VALUES ('Opening journal batch');
INSERT INTO "LEDGER_POSTINGS" ("NARRATIVE") VALUES ('Accrual adjustment batch');

SELECT
  "POSTING_ID",
  "BATCH_SEQ",
  "NARRATIVE",
  GEN_ID("GEN_LEDGER_ENTRY", 0) AS "CURRENT_GEN_VALUE"
FROM "LEDGER_POSTINGS"
ORDER BY "POSTING_ID";
```

![Executing Firebird 5 NEXT VALUE FOR, GEN_ID(..., 0), and GENERATED BY DEFAULT AS IDENTITY in SQL Studio](images/sequences/fb-seq-05-live-next-value-for-gen-id-and-identity.png)
