##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Portable relational schema for the ScratchRobin design store (designs.db).

Owner decisions, 2026-11-10:
- A1: UUIDv7 identifiers for design, element, binding and resource_identity.
- A2: Separate ``designs.db`` in ``DATA_DIR``, portable SQL schema.
- A3: Layout stays inside ``ddn_text`` (no separate layout_text column).
- A4: ``asset_blob`` table in ``designs.db``, content-addressed by SHA-256,
  16 MiB cap, linked via ``design_asset``.
- A5: ``binding`` table is authoritative for state (valid/suspect/unknown);
  DDN carries the target reference.
- A6: Mark bindings ``suspect`` on target rename/drop until confirmed.
- A7: Keep every saved version (no automatic draft pruning).
- A8: BI alerts and embeds remain runtime tables outside the design store.
"""

from __future__ import annotations

DESIGN_KINDS = (
    'erd',
    'cube',
    'question',
    'dashboard',
    'screen',
    'screen_flow',
    'monitoring_dashboard',
)

SAVE_POINT_STATUSES = (
    'draft',
    'in_progress',
    'in_review',
    'accepted',
)

BINDING_STATES = (
    'valid',
    'suspect',
    'unknown',
)

TARGET_KINDS = (
    'resource',
    'element',
    'question',
    'measure',
    'dashboard',
    'collector',
)

GIT_SYNC_STATES = (
    'synced',
    'modified',
    'out_of_sync',
    'conflict',
)

MAX_BLOB_BYTES = 16 * 1024 * 1024  # 16 MiB (Owner decision A4)

PORTABLE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS design (
        id              TEXT PRIMARY KEY,
        kind            TEXT NOT NULL CHECK (
                            kind IN (
                                'erd', 'cube', 'question', 'dashboard',
                                'screen', 'screen_flow',
                                'monitoring_dashboard'
                            )
                        ),
        project_id      TEXT NOT NULL,
        key             TEXT NOT NULL,
        title           TEXT NOT NULL,
        active_version  INTEGER NULL,
        head_version    INTEGER NOT NULL CHECK (head_version >= 1),
        created_by      INTEGER NOT NULL,
        created_at      TEXT NOT NULL,
        updated_by      INTEGER NOT NULL,
        updated_at      TEXT NOT NULL,
        UNIQUE (project_id, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS design_version (
        design_id       TEXT NOT NULL
                        REFERENCES design(id) ON DELETE CASCADE,
        version         INTEGER NOT NULL CHECK (version >= 1),
        base_version    INTEGER NULL,
        status          TEXT NOT NULL CHECK (
                            status IN (
                                'draft', 'in_progress',
                                'in_review', 'accepted'
                            )
                        ),
        ddn_text        TEXT NOT NULL,
        ddn_sha256      TEXT NOT NULL,
        dialect_version TEXT NOT NULL DEFAULT 'ddn-next-1',
        note            TEXT NOT NULL DEFAULT '',
        actor_id        INTEGER NOT NULL,
        saved_at        TEXT NOT NULL,
        origin          TEXT NOT NULL DEFAULT 'local',
        loss_report     TEXT NULL,
        PRIMARY KEY (design_id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS acceptance (
        design_id       TEXT NOT NULL,
        version         INTEGER NOT NULL,
        accepted_by     INTEGER NOT NULL,
        accepted_at     TEXT NOT NULL,
        approval_ref    TEXT NULL,
        returned_by     INTEGER NULL,
        returned_at     TEXT NULL,
        return_status   TEXT NULL CHECK (
                            return_status IS NULL OR
                            return_status IN ('in_review', 'in_progress')
                        ),
        PRIMARY KEY (design_id, version),
        FOREIGN KEY (design_id, version)
            REFERENCES design_version(design_id, version)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS element (
        id              TEXT PRIMARY KEY,
        design_id       TEXT NOT NULL
                        REFERENCES design(id) ON DELETE CASCADE,
        role            TEXT NOT NULL,
        name            TEXT NOT NULL,
        first_version   INTEGER NOT NULL CHECK (first_version >= 1),
        removed_version INTEGER NULL,
        UNIQUE (design_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS binding (
        id                        TEXT PRIMARY KEY,
        design_id                 TEXT NOT NULL
                                  REFERENCES design(id) ON DELETE CASCADE,
        element_id                TEXT NOT NULL
                                  REFERENCES element(id) ON DELETE CASCADE,
        target_kind               TEXT NOT NULL CHECK (
                                      target_kind IN (
                                          'resource', 'element', 'question',
                                          'measure', 'dashboard', 'collector'
                                      )
                                  ),
        target_ref                TEXT NOT NULL,
        target_engine             TEXT NULL,
        target_endpoint_id        TEXT NULL,
        target_database_target_id TEXT NULL,
        state                     TEXT NOT NULL CHECK (
                                      state IN ('valid', 'suspect', 'unknown')
                                  ),
        state_reason              TEXT NULL,
        confirmed_by              INTEGER NULL,
        confirmed_at              TEXT NULL,
        UNIQUE (design_id, element_id, target_kind, target_ref)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_identity (
        id                 TEXT PRIMARY KEY,
        engine             TEXT NOT NULL,
        endpoint_id        TEXT NOT NULL,
        database_target_id TEXT NOT NULL,
        resource_kind      TEXT NOT NULL,
        resource_id        TEXT NOT NULL,
        previous_ids       TEXT NOT NULL DEFAULT '[]',
        last_seen_at       TEXT NOT NULL,
        UNIQUE (engine, endpoint_id, database_target_id, resource_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS design_dependency (
        design_id            TEXT NOT NULL,
        version              INTEGER NOT NULL,
        depends_on_design_id TEXT NOT NULL
                             REFERENCES design(id) ON DELETE RESTRICT,
        depends_on_version   INTEGER NULL,
        PRIMARY KEY (design_id, version, depends_on_design_id),
        FOREIGN KEY (design_id, version)
            REFERENCES design_version(design_id, version)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS target_deployment (
        design_id          TEXT NOT NULL
                           REFERENCES design(id) ON DELETE CASCADE,
        engine             TEXT NOT NULL,
        endpoint_id        TEXT NOT NULL,
        database_target_id TEXT NOT NULL,
        deployed_version   INTEGER NOT NULL,
        plan_sha256        TEXT NOT NULL,
        target_fingerprint TEXT NOT NULL,
        applied_by         INTEGER NOT NULL,
        applied_at         TEXT NOT NULL,
        PRIMARY KEY (design_id, engine, endpoint_id, database_target_id),
        FOREIGN KEY (design_id, deployed_version)
            REFERENCES design_version(design_id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS git_link (
        design_id           TEXT PRIMARY KEY
                            REFERENCES design(id) ON DELETE CASCADE,
        repository          TEXT NOT NULL,
        path                TEXT NOT NULL,
        branch              TEXT NOT NULL DEFAULT 'main',
        last_pushed_version INTEGER NULL,
        last_pushed_commit  TEXT NULL,
        last_pushed_sha256  TEXT NULL,
        last_pulled_commit  TEXT NULL,
        last_pulled_sha256  TEXT NULL,
        sync_state          TEXT NOT NULL CHECK (
                                sync_state IN (
                                    'synced', 'modified',
                                    'out_of_sync', 'conflict'
                                )
                            )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_blob (
        sha256      TEXT PRIMARY KEY,
        media_type  TEXT NOT NULL,
        bytes       BLOB NOT NULL,
        size        INTEGER NOT NULL CHECK (
                        size >= 0 AND size <= 16777216
                    ),
        created_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS design_asset (
        design_id   TEXT NOT NULL,
        version     INTEGER NOT NULL,
        path        TEXT NOT NULL,
        sha256      TEXT NOT NULL
                    REFERENCES asset_blob(sha256) ON DELETE RESTRICT,
        PRIMARY KEY (design_id, version, path),
        FOREIGN KEY (design_id, version)
            REFERENCES design_version(design_id, version)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_design_project_kind
        ON design(project_id, kind)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_element_design
        ON element(design_id, role)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_binding_target
        ON binding(target_kind, target_ref, state)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_binding_scope
        ON binding(
            target_engine, target_endpoint_id, target_database_target_id
        )
    """,
)

SQLITE_TRIGGERS_AND_FTS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_design_version_immutable
    BEFORE UPDATE ON design_version
    FOR EACH ROW
    WHEN (
        OLD.design_id != NEW.design_id OR
        OLD.version != NEW.version OR
         COALESCE(OLD.base_version, -1) != COALESCE(NEW.base_version, -1) OR
        OLD.ddn_text != NEW.ddn_text OR
        OLD.ddn_sha256 != NEW.ddn_sha256 OR
        OLD.dialect_version != NEW.dialect_version OR
        OLD.note != NEW.note OR
        OLD.actor_id != NEW.actor_id OR
        OLD.saved_at != NEW.saved_at OR
        OLD.origin != NEW.origin OR
        COALESCE(OLD.loss_report, '') != COALESCE(NEW.loss_report, '')
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'design_version content is immutable; save a new version'
        );
    END
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS design_version_fts USING fts5(
        design_id UNINDEXED,
        version UNINDEXED,
        ddn_text,
        note,
        content='design_version',
        content_rowid='rowid'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_design_version_fts_ai
    AFTER INSERT ON design_version
    BEGIN
        INSERT INTO design_version_fts(
            rowid, design_id, version, ddn_text, note
        )
        VALUES (
            new.rowid, new.design_id, new.version, new.ddn_text, new.note
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_design_version_fts_ad
    AFTER DELETE ON design_version
    BEGIN
        INSERT INTO design_version_fts(
            design_version_fts, rowid, design_id, version, ddn_text, note
        )
        VALUES (
            'delete', old.rowid, old.design_id, old.version,
            old.ddn_text, old.note
        );
    END
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS element_fts USING fts5(
        id UNINDEXED,
        design_id UNINDEXED,
        role,
        name,
        content='element',
        content_rowid='rowid'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_element_fts_ai
    AFTER INSERT ON element
    BEGIN
        INSERT INTO element_fts(rowid, id, design_id, role, name)
        VALUES (new.rowid, new.id, new.design_id, new.role, new.name);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_element_fts_ad
    AFTER DELETE ON element
    BEGIN
        INSERT INTO element_fts(
            element_fts, rowid, id, design_id, role, name
        )
        VALUES (
            'delete', old.rowid, old.id, old.design_id, old.role, old.name
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_element_fts_au
    AFTER UPDATE OF role, name ON element
    BEGIN
        INSERT INTO element_fts(
            element_fts, rowid, id, design_id, role, name
        )
        VALUES (
            'delete', old.rowid, old.id, old.design_id, old.role, old.name
        );
        INSERT INTO element_fts(rowid, id, design_id, role, name)
        VALUES (new.rowid, new.id, new.design_id, new.role, new.name);
    END
    """,
)


def apply_schema(connection, *, is_sqlite: bool = True) -> None:
    """Create all design-store tables, indexes, triggers and FTS tables."""
    cursor = connection.cursor()
    try:
        if is_sqlite:
            cursor.execute('PRAGMA foreign_keys = ON')
            cursor.execute('PRAGMA journal_mode = WAL')
        for statement in PORTABLE_DDL:
            cursor.execute(statement)
        if is_sqlite:
            for statement in SQLITE_TRIGGERS_AND_FTS:
                cursor.execute(statement)
        connection.commit()
    finally:
        cursor.close()
