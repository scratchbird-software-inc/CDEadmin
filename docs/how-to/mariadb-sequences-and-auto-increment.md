# How to Create, Alter, Restart, Comment, and Drop MariaDB 12.2 Sequences & `AUTO_INCREMENT`

Unlike MySQL, **MariaDB 12.2** provides full first-class SQL **Sequences** (`CREATE SEQUENCE`, `ALTER SEQUENCE`, `NEXT VALUE FOR` / `NEXTVAL()`, `PREVIOUS VALUE FOR` / `LASTVAL()`, `SETVAL()`) stored as transactional storage-engine sequence tables (`TABLE_TYPE = 'SEQUENCE'`) **in addition to** classic column `AUTO_INCREMENT`.

This guide walks step-by-step through creating, inspecting, restarting, commenting, and dropping MariaDB sequences using ScratchRobin's **Sequence Editor (`SR-F-020047`)**, and combining sequences with `AUTO_INCREMENT` in SQL Studio.

---

## MariaDB 12.2 Sequence Capabilities Covered

1. **Signed & Unsigned Integer Storage Types (`AS TINYINT..BIGINT [UNSIGNED]`)**:
   - Choose `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, or `BIGINT` with optional **`UNSIGNED`** (`0` up to `18,446,744,073,709,551,615`).
2. **Creation Modifiers (`OR REPLACE`, `TEMPORARY`, `IF NOT EXISTS`)**:
   - Mutually guarded `CREATE OR REPLACE SEQUENCE` and `CREATE SEQUENCE IF NOT EXISTS`, plus session-scoped `CREATE TEMPORARY SEQUENCE`.
3. **Bounds, Pre-Allocation Cache (`CACHE` / `NOCACHE`) & Cycling (`CYCLE` / `NOCYCLE`)**:
   - Explicit `MINVALUE` / `NO MINVALUE`, `MAXVALUE` / `NO MAXVALUE`, `CACHE <n>` (setting `0` emits `NOCACHE`), and `CYCLE` / `NOCYCLE`.
4. **Sequence Comments on Both Create & Alter**:
   - MariaDB accepts `COMMENT = '...'` inside `CREATE SEQUENCE`, whereas `ALTER SEQUENCE` does not accept `COMMENT = '...'` directly — because MariaDB implements sequences as sequence tables, ScratchRobin automatically compiles `ALTER TABLE <db>.<seq> COMMENT = '...'` alongside `ALTER SEQUENCE` when updating comments in **`Edit...`**!
5. **Non-Advancing Live Value Inspection & Confirmation-Guarded `RESTART`**:
   - **`Edit...`** reads `SELECT next_not_cached_value, cycle_count FROM <seq>` without advancing the sequence, and guards `RESTART` / `RESTART WITH <n>` behind an exact sequence-name confirmation field.

---

## Step 1: Open Create Sequence from Data Navigator

1. Expand `MariaDB -> <server> -> <database>` (for example, `cdeadmin_demo`).
2. Right-click **`Sequences`** (or right-click `<database>` and choose **`Create -> Sequence...`**) and click **`Create Sequence...`**.

![Opening Create Sequence under a MariaDB 12.2 database in Data Navigator](images/sequences/mdb-seq-01-navigator-sequences-create.png)

---

## Step 2: Configure Unsigned Integer Type, Bounds, Cache, Cycle & Comment

1. On the **`General`** tab of **Create sequence (`SR-F-020047`)**:
   - Set **Name** = `seq_order_ticket` and **Database** = `cdeadmin_demo`.
   - Select **Integer type** = `BIGINT` and enable **Unsigned** (`AS BIGINT UNSIGNED`).
   - Enter **Comment** = `Unsigned 64-bit order ticket generator`.
2. On the **`Options`** tab:
   - Set **Start with** = `100000`, **Increment by** = `1`, **Minimum bound** = `Explicit value` (`100000`), **Maximum bound** = `Native type default`, **Cache** = `50` (enter `0` for `NOCACHE`), and **Cycle** = `NOCYCLE`.

![Configuring MariaDB 12.2 BIGINT UNSIGNED sequence bounds, cache, NOCYCLE, and comment](images/sequences/mdb-seq-02-create-sequence-general-and-bounds.png)

---

## Step 3: Preview Native MariaDB Sequence DDL & Apply

Switch to the **`SQL`** tab to inspect the generated MariaDB 12.2 statement and click **`Apply`**:

```sql
CREATE SEQUENCE `cdeadmin_demo`.`seq_order_ticket`
  AS BIGINT UNSIGNED
  START WITH 100000
  INCREMENT BY 1
  CACHE 50
  MINVALUE 100000
  NOCYCLE
  COMMENT = 'Unsigned 64-bit order ticket generator'
```

![Reviewing MariaDB CREATE SEQUENCE AS BIGINT UNSIGNED DDL preview](images/sequences/mdb-seq-03-create-sql-preview.png)

---

## Step 4: Inspect Uncached Position, Restart & Edit Comment (`Edit...`)

Right-click `seq_order_ticket` under **`Sequences`** and select **`Edit...`**:

1. On **`Options`**, inspect **Next uncached value** (`100000` before allocation, or the next uncached block boundary) read directly from the sequence table without consuming values.
2. To restart the sequence at `200000`:
   - Enter **Restart with** = `200000` and type `seq_order_ticket` in **Exact sequence name to confirm restart**.
3. Update **Comment** on **`General`** — ScratchRobin compiles both `ALTER SEQUENCE \`cdeadmin_demo\`.\`seq_order_ticket\` RESTART WITH 200000` and `ALTER TABLE \`cdeadmin_demo\`.\`seq_order_ticket\` COMMENT = '...'` cleanly!

> [!NOTE]
> MariaDB forbids combining `ALTER SEQUENCE ... AS <new_type>` with other `ALTER SEQUENCE` options in a single statement. ScratchRobin enforces this rule up front so type changes and parameter/restart changes are applied cleanly without runtime syntax errors.

![Restarting a MariaDB 12.2 sequence and updating its comment in the Sequence Editor](images/sequences/mdb-seq-04-alter-restart-and-comment.png)

---

## Step 5: Drop a MariaDB Sequence (`Drop...` Confirmation Modal)

1. Right-click an obsolete sequence (`seq_legacy_batch`) under **`Sequences`** and click **`Drop...`**.
2. Enter `seq_legacy_batch` in **Type the object name to confirm**, click **`Preview`** to inspect the Planned Statement Impact and `DROP SEQUENCE \`cdeadmin_demo\`.\`seq_legacy_batch\``, and click **`Run`**.

![Dropping a MariaDB sequence via OperationDialog with typed confirmation](images/sequences/mdb-seq-05-drop-sequence-operation-dialog.png)

---

## Step 6: Live Verification — `NEXT VALUE FOR`, `PREVIOUS VALUE FOR`, and `AUTO_INCREMENT`

Open the MariaDB query workspace (`Right-click cdeadmin_demo -> Open database query workspace...`) to exercise `DEFAULT (NEXT VALUE FOR ...)`, `PREVIOUS VALUE FOR`, and `AUTO_INCREMENT` together:

```sql
CREATE TABLE ticket_dispatches (
  row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  ticket_no BIGINT UNSIGNED NOT NULL DEFAULT (NEXT VALUE FOR seq_order_ticket) UNIQUE,
  channel VARCHAR(32) NOT NULL
) ENGINE=InnoDB;

INSERT INTO ticket_dispatches (channel) VALUES ('WEB-PORTAL'), ('API-GATEWAY');

SELECT
  row_id,
  ticket_no,
  channel,
  PREVIOUS VALUE FOR seq_order_ticket AS session_last_seq
FROM ticket_dispatches
ORDER BY row_id;
```

![Executing MariaDB 12.2 NEXT VALUE FOR, PREVIOUS VALUE FOR, and AUTO_INCREMENT together in SQL Studio](images/sequences/mdb-seq-06-live-nextval-lastval-and-auto-increment.png)
