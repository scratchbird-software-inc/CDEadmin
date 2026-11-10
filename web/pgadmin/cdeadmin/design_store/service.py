##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""SQLite-first design store service (designs.db) for DDN-based tools.

Implements DESIGN-STORE-PROPOSAL.md with the 2026-11-10 owner decisions:
- A1: UUIDv7 identifiers for design, element, binding and resource_identity.
- A2: Separate ``designs.db`` in ``DATA_DIR``.
- A3: Visual layout inside ``ddn_text``.
- A4: ``asset_blob`` table in ``designs.db``, SHA-256 keyed, 16 MiB cap.
- A5: ``binding`` table authoritative for validity state; DDN carries target.
- A6: Mark bindings ``suspect`` on target rename/drop until user confirms.
- A7: Retain every version (no automatic pruning).
- A8: BI alerts and embeds remain runtime tables outside the design store.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any

import config

from .ddn_elements import (
    assign_uuid7_element_ids,
    ddn_text_to_workspace,
    inspect_ddn_text,
    sha256_text,
    workspace_to_ddn_text,
)
from .identifiers import is_uuid7, uuid7
from .schema import (
    BINDING_STATES,
    DESIGN_KINDS,
    GIT_SYNC_STATES,
    MAX_BLOB_BYTES,
    SAVE_POINT_STATUSES,
    TARGET_KINDS,
    apply_schema,
)

APP_EXTENSION_KEY = 'cdeadmin_design_store'

_ALLOWED_ADVANCE = {
    ('draft', 'in_progress'),
    ('draft', 'in_review'),
    ('in_progress', 'draft'),
    ('in_progress', 'in_review'),
    ('in_review', 'in_progress'),
    ('in_review', 'draft'),
}


class DesignStoreError(ValueError):
    """Invalid design-store request or state transition."""


class DesignStoreNotFound(DesignStoreError):
    """Requested design, version, element, binding or blob was not found."""


class DesignStoreConflict(DesignStoreError):
    """Optimistic concurrency failure, base-version drift or conflict."""


class DesignStoreForbidden(DesignStoreError):
    """Caller is not authorized to perform the requested store operation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_store_path() -> str:
    """Resolve the default ``designs.db`` path in ``DATA_DIR``."""
    explicit = os.environ.get('CDEADMIN_DESIGN_STORE_PATH')
    if explicit:
        return explicit
    cfg_path = getattr(config, 'CDEADMIN_DESIGN_STORE_PATH', None)
    sqlite_path = getattr(config, 'SQLITE_PATH', None)
    data_dir = getattr(config, 'DATA_DIR', None)
    if sqlite_path and data_dir:
        sqlite_dir = os.path.dirname(os.path.abspath(sqlite_path))
        if sqlite_dir != os.path.abspath(data_dir):
            return os.path.join(sqlite_dir, 'designs.db')
    if cfg_path:
        return str(cfg_path)
    if data_dir:
        return os.path.join(str(data_dir), 'designs.db')
    raise DesignStoreError('Design store path is not configured')


class DesignStore:
    """Manage versioned DDN designs, elements, bindings and Git links."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path) if db_path is not None else (
            default_store_path()
        )
        self._lock = threading.RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        if self.db_path != ':memory:':
            parent = os.path.dirname(os.path.abspath(self.db_path))
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, mode=0o700, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        if not self._initialized or self.db_path == ':memory:':
            apply_schema(conn, is_sqlite=True)
            self._initialized = True
        return conn

    def initialize(self) -> None:
        """Ensure the store schema is created and ready."""
        with self._lock:
            conn = self._connect()
            try:
                apply_schema(conn, is_sqlite=True)
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Design creation, save, read and list
    # ------------------------------------------------------------------

    def create_design(
        self,
        *,
        project_id: str,
        key: str,
        kind: str,
        title: str,
        ddn_text: str,
        actor_id: int,
        status: str = 'draft',
        note: str = '',
        origin: str = 'local',
        loss_report: dict[str, Any] | None = None,
        name_mapping: dict[str, str] | None = None,
        observe_resources: bool = False,
        design_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new design at version 1."""
        if kind not in DESIGN_KINDS:
            raise DesignStoreError(f'Unsupported design kind: {kind}')
        if status not in ('draft', 'in_progress', 'in_review'):
            raise DesignStoreError(
                'New designs must start as draft, in_progress or in_review'
            )
        if not isinstance(project_id, str) or not project_id.strip():
            raise DesignStoreError('project_id is required')
        if not isinstance(key, str) or not key.strip():
            raise DesignStoreError('design key is required')
        if not isinstance(title, str) or not title.strip():
            raise DesignStoreError('design title is required')
        if isinstance(actor_id, bool) or not isinstance(actor_id, int):
            raise DesignStoreError('actor_id must be an integer user ID')

        if design_id is not None:
            if not is_uuid7(design_id):
                raise DesignStoreError('design_id must be a UUIDv7 string')
            did = design_id
        else:
            did = uuid7()

        rewritten, id_map, info = assign_uuid7_element_ids(
            ddn_text, name_mapping=name_mapping
        )
        digest = sha256_text(rewritten)
        now = _utc_now()
        loss_json = (
            json.dumps(loss_report, sort_keys=True)
            if loss_report is not None
            else None
        )

        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    'SELECT id FROM design WHERE project_id = ? AND key = ?',
                    (project_id, key),
                ).fetchone()
                if existing is not None:
                    raise DesignStoreConflict(
                        f'Design {key!r} already exists in project '
                        f'{project_id!r}'
                    )
                conn.execute(
                    """
                    INSERT INTO design (
                        id, kind, project_id, key, title,
                        active_version, head_version,
                        created_by, created_at, updated_by, updated_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, 1, ?, ?, ?, ?)
                    """,
                    (
                        did, kind, project_id, key, title.strip(),
                        actor_id, now, actor_id, now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO design_version (
                        design_id, version, base_version, status,
                        ddn_text, ddn_sha256, dialect_version, note,
                        actor_id, saved_at, origin, loss_report
                    ) VALUES (?, 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        did, status, rewritten, digest,
                        info['dialect_version'], note or '',
                        actor_id, now, origin or 'local', loss_json,
                    ),
                )
                self._sync_elements_and_bindings(
                    conn,
                    design_id=did,
                    version=1,
                    info=info,
                    observe_resources=observe_resources,
                    now=now,
                )
                conn.commit()
                result = self._read_design(conn, did, version=1)
                result['allocated_id_map'] = id_map
                return result
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise DesignStoreConflict(str(exc)) from exc
            finally:
                conn.close()

    def save_version(
        self,
        design_id: str,
        *,
        expected_head_version: int,
        ddn_text: str,
        actor_id: int,
        base_version: int | None = None,
        status: str = 'draft',
        note: str = '',
        origin: str = 'local',
        loss_report: dict[str, Any] | None = None,
        title: str | None = None,
        name_mapping: dict[str, str] | None = None,
        observe_resources: bool = False,
        allow_conflict_note: bool = False,
    ) -> dict[str, Any]:
        """Append a new immutable version to an existing design."""
        if status not in ('draft', 'in_progress', 'in_review'):
            raise DesignStoreError(
                'Saved versions must have status draft, in_progress '
                'or in_review; use accept_version to accept'
            )
        if (
            isinstance(expected_head_version, bool)
            or not isinstance(expected_head_version, int)
            or expected_head_version < 1
        ):
            raise DesignStoreError(
                'expected_head_version must be a positive integer'
            )
        if isinstance(actor_id, bool) or not isinstance(actor_id, int):
            raise DesignStoreError('actor_id must be an integer user ID')

        with self._lock:
            conn = self._connect()
            try:
                design_row = conn.execute(
                    'SELECT * FROM design WHERE id = ?', (design_id,)
                ).fetchone()
                if design_row is None:
                    raise DesignStoreNotFound(
                        f'Design {design_id!r} was not found'
                    )
                if design_row['head_version'] != expected_head_version:
                    raise DesignStoreConflict(
                        f'Design head_version is '
                        f'{design_row["head_version"]}, expected '
                        f'{expected_head_version}'
                    )
                effective_base = (
                    base_version
                    if base_version is not None
                    else expected_head_version
                )
                base_row = conn.execute(
                    'SELECT version FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, effective_base),
                ).fetchone()
                if base_row is None:
                    raise DesignStoreNotFound(
                        f'Base version {effective_base} was not found'
                    )

                conflicts: list[str] = []
                active_ver = design_row['active_version']
                if active_ver is not None and effective_base != active_ver:
                    conflicts.append(
                        f'active version advanced to {active_ver} since '
                        f'base version {effective_base}'
                    )
                suspect_rows = conn.execute(
                    "SELECT element_id, target_ref, state_reason "
                    "FROM binding WHERE design_id = ? AND state = 'suspect'",
                    (design_id,),
                ).fetchall()
                for srow in suspect_rows:
                    reason = srow['state_reason'] or 'target changed'
                    conflicts.append(
                        f'element {srow["element_id"]} binding to '
                        f'{srow["target_ref"]} is suspect ({reason})'
                    )

                if conflicts and not allow_conflict_note:
                    raise DesignStoreConflict(
                        'Save blocked by conflicts: ' + '; '.join(conflicts)
                    )
                final_note = note or ''
                if conflicts and allow_conflict_note:
                    conflict_line = (
                        '[conflicts recorded at save: '
                        + '; '.join(conflicts)
                        + ']'
                    )
                    final_note = (
                        f'{final_note}\n{conflict_line}'.strip()
                        if final_note
                        else conflict_line
                    )

                existing_by_id, existing_by_res = self._existing_element_maps(
                    conn, design_id
                )
                rewritten, id_map, info = assign_uuid7_element_ids(
                    ddn_text,
                    existing_by_id=existing_by_id,
                    existing_by_resource=existing_by_res,
                    name_mapping=name_mapping,
                )
                digest = sha256_text(rewritten)
                new_version = design_row['head_version'] + 1
                now = _utc_now()
                loss_json = (
                    json.dumps(loss_report, sort_keys=True)
                    if loss_report is not None
                    else None
                )
                new_title = (
                    title.strip()
                    if isinstance(title, str) and title.strip()
                    else design_row['title']
                )

                conn.execute(
                    """
                    INSERT INTO design_version (
                        design_id, version, base_version, status,
                        ddn_text, ddn_sha256, dialect_version, note,
                        actor_id, saved_at, origin, loss_report
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        design_id, new_version, effective_base, status,
                        rewritten, digest, info['dialect_version'],
                        final_note, actor_id, now, origin or 'local',
                        loss_json,
                    ),
                )
                conn.execute(
                    """
                    UPDATE design
                    SET head_version = ?, title = ?,
                        updated_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_version, new_title, actor_id, now, design_id),
                )
                self._sync_elements_and_bindings(
                    conn,
                    design_id=design_id,
                    version=new_version,
                    info=info,
                    observe_resources=observe_resources,
                    now=now,
                )
                git_row = conn.execute(
                    'SELECT sync_state, last_pushed_sha256 '
                    'FROM git_link WHERE design_id = ?',
                    (design_id,),
                ).fetchone()
                if git_row is not None:
                    if git_row['last_pushed_sha256'] == digest:
                        next_sync = 'synced'
                    elif git_row['sync_state'] in ('out_of_sync', 'conflict'):
                        next_sync = 'conflict'
                    else:
                        next_sync = 'modified'
                    conn.execute(
                        'UPDATE git_link SET sync_state = ? '
                        'WHERE design_id = ?',
                        (next_sync, design_id),
                    )
                conn.commit()
                result = self._read_design(
                    conn, design_id, version=new_version
                )
                result['allocated_id_map'] = id_map
                result['recorded_conflicts'] = conflicts
                return result
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise DesignStoreConflict(str(exc)) from exc
            finally:
                conn.close()

    def get_design(
        self,
        design_id: str,
        *,
        version: int | None = None,
        active_only: bool = False,
    ) -> dict[str, Any]:
        """Return a design and its requested (or head/active) version."""
        with self._lock:
            conn = self._connect()
            try:
                return self._read_design(
                    conn,
                    design_id,
                    version=version,
                    active_only=active_only,
                )
            finally:
                conn.close()

    def get_design_by_key(
        self,
        project_id: str,
        key: str,
        *,
        version: int | None = None,
    ) -> dict[str, Any]:
        """Return a design looked up by (project_id, key)."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    'SELECT id FROM design WHERE project_id = ? AND key = ?',
                    (project_id, key),
                ).fetchone()
                if row is None:
                    raise DesignStoreNotFound(
                        f'Design {key!r} not found in project {project_id!r}'
                    )
                return self._read_design(conn, row['id'], version=version)
            finally:
                conn.close()

    def list_designs(
        self,
        *,
        project_id: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """List design summaries filtered by project_id and/or kind."""
        clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append('d.project_id = ?')
            params.append(project_id)
        if kind is not None:
            clauses.append('d.kind = ?')
            params.append(kind)
        where_sql = (
            'WHERE ' + ' AND '.join(clauses) if clauses else ''
        )
        query = f"""
            SELECT d.*,
                   hv.status AS head_status,
                   hv.ddn_sha256 AS head_sha256,
                   hv.saved_at AS head_saved_at,
                   g.sync_state AS git_sync_state
            FROM design d
            JOIN design_version hv
              ON hv.design_id = d.id AND hv.version = d.head_version
            LEFT JOIN git_link g
              ON g.design_id = d.id
            {where_sql}
            ORDER BY d.updated_at DESC, d.id ASC
        """
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def list_versions(self, design_id: str) -> list[dict[str, Any]]:
        """List all saved versions of ``design_id`` newest-first."""
        with self._lock:
            conn = self._connect()
            try:
                exists = conn.execute(
                    'SELECT id FROM design WHERE id = ?', (design_id,)
                ).fetchone()
                if exists is None:
                    raise DesignStoreNotFound(
                        f'Design {design_id!r} was not found'
                    )
                rows = conn.execute(
                    """
                    SELECT v.design_id, v.version, v.base_version, v.status,
                           v.ddn_sha256, v.dialect_version, v.note,
                           v.actor_id, v.saved_at, v.origin, v.loss_report,
                           a.accepted_by, a.accepted_at, a.approval_ref,
                           a.returned_by, a.returned_at, a.return_status
                    FROM design_version v
                    LEFT JOIN acceptance a
                      ON a.design_id = v.design_id AND a.version = v.version
                    WHERE v.design_id = ?
                    ORDER BY v.version DESC
                    """,
                    (design_id,),
                ).fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item['loss_report'] = (
                        json.loads(item['loss_report'])
                        if item['loss_report']
                        else None
                    )
                    result.append(item)
                return result
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Save points and Acceptance workflow
    # ------------------------------------------------------------------

    def advance_status(
        self,
        design_id: str,
        version: int,
        target_status: str,
        actor_id: int,
    ) -> dict[str, Any]:
        """Move a non-accepted version between save-point statuses."""
        if target_status == 'accepted':
            raise DesignStoreError(
                'Use accept_version to transition a version to accepted'
            )
        if target_status not in SAVE_POINT_STATUSES:
            raise DesignStoreError(f'Invalid status: {target_status!r}')
        with self._lock:
            conn = self._connect()
            try:
                vrow = conn.execute(
                    'SELECT status FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, version),
                ).fetchone()
                if vrow is None:
                    raise DesignStoreNotFound(
                        f'Version {version} of design {design_id!r} not found'
                    )
                current = vrow['status']
                if current == target_status:
                    return self._read_design(conn, design_id, version=version)
                if (current, target_status) not in _ALLOWED_ADVANCE:
                    raise DesignStoreError(
                        f'Cannot transition version {version} from '
                        f'{current!r} to {target_status!r}'
                    )
                now = _utc_now()
                conn.execute(
                    'UPDATE design_version SET status = ? '
                    'WHERE design_id = ? AND version = ?',
                    (target_status, design_id, version),
                )
                conn.execute(
                    'UPDATE design SET updated_by = ?, updated_at = ? '
                    'WHERE id = ?',
                    (actor_id, now, design_id),
                )
                conn.commit()
                return self._read_design(conn, design_id, version=version)
            finally:
                conn.close()

    def accept_version(
        self,
        design_id: str,
        version: int,
        actor_id: int,
        *,
        approval_ref: str | None = None,
        authorized: bool = True,
    ) -> dict[str, Any]:
        """Accept an in_review version, making it the active version."""
        if not authorized:
            raise DesignStoreForbidden(
                'Caller is not authorized by the security setup to accept '
                'this design version'
            )
        if isinstance(actor_id, bool) or not isinstance(actor_id, int):
            raise DesignStoreError('actor_id must be an integer user ID')

        with self._lock:
            conn = self._connect()
            try:
                drow = conn.execute(
                    'SELECT * FROM design WHERE id = ?', (design_id,)
                ).fetchone()
                if drow is None:
                    raise DesignStoreNotFound(
                        f'Design {design_id!r} was not found'
                    )
                vrow = conn.execute(
                    'SELECT * FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, version),
                ).fetchone()
                if vrow is None:
                    raise DesignStoreNotFound(
                        f'Version {version} of design {design_id!r} not found'
                    )
                if vrow['status'] != 'in_review':
                    raise DesignStoreError(
                        f'Version {version} must be in_review before '
                        f'acceptance (current status: {vrow["status"]!r})'
                    )
                active_ver = drow['active_version']
                if (
                    active_ver is not None
                    and vrow['base_version'] != active_ver
                ):
                    raise DesignStoreConflict(
                        f'Version {version} is based on version '
                        f'{vrow["base_version"]}, but the active version is '
                        f'{active_ver}; reconcile via DDN diff before '
                        f'accepting'
                    )
                suspect = conn.execute(
                    "SELECT id, element_id, target_ref, state_reason "
                    "FROM binding WHERE design_id = ? AND state = 'suspect'",
                    (design_id,),
                ).fetchall()
                if suspect:
                    details = ', '.join(
                        f'{r["element_id"]}->{r["target_ref"]} '
                        f'({r["state_reason"] or "suspect"})'
                        for r in suspect
                    )
                    raise DesignStoreConflict(
                        f'Cannot accept while bindings are suspect: {details}'
                    )

                now = _utc_now()
                conn.execute(
                    "UPDATE design_version SET status = 'accepted' "
                    "WHERE design_id = ? AND version = ?",
                    (design_id, version),
                )
                conn.execute(
                    """
                    INSERT INTO acceptance (
                        design_id, version, accepted_by, accepted_at,
                        approval_ref, returned_by, returned_at, return_status
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
                    ON CONFLICT(design_id, version) DO UPDATE SET
                        accepted_by = excluded.accepted_by,
                        accepted_at = excluded.accepted_at,
                        approval_ref = excluded.approval_ref,
                        returned_by = NULL,
                        returned_at = NULL,
                        return_status = NULL
                    """,
                    (design_id, version, actor_id, now, approval_ref),
                )
                conn.execute(
                    """
                    UPDATE design
                    SET active_version = ?, updated_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (version, actor_id, now, design_id),
                )
                conn.commit()
                return self._read_design(conn, design_id, version=version)
            finally:
                conn.close()

    def return_accepted_version(
        self,
        design_id: str,
        version: int,
        actor_id: int,
        *,
        target_status: str = 'in_review',
        authorized: bool = True,
    ) -> dict[str, Any]:
        """Return an accepted version to in_review or in_progress."""
        if not authorized:
            raise DesignStoreForbidden(
                'Caller is not authorized to return an accepted version'
            )
        if target_status not in ('in_review', 'in_progress'):
            raise DesignStoreError(
                'Accepted version can only be returned to in_review '
                'or in_progress'
            )
        with self._lock:
            conn = self._connect()
            try:
                vrow = conn.execute(
                    'SELECT status FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, version),
                ).fetchone()
                if vrow is None:
                    raise DesignStoreNotFound(
                        f'Version {version} of design {design_id!r} not found'
                    )
                if vrow['status'] != 'accepted':
                    raise DesignStoreError(
                        f'Version {version} is not currently accepted'
                    )
                now = _utc_now()
                conn.execute(
                    'UPDATE design_version SET status = ? '
                    'WHERE design_id = ? AND version = ?',
                    (target_status, design_id, version),
                )
                conn.execute(
                    """
                    UPDATE acceptance
                    SET returned_by = ?, returned_at = ?, return_status = ?
                    WHERE design_id = ? AND version = ?
                    """,
                    (actor_id, now, target_status, design_id, version),
                )
                prev_accepted = conn.execute(
                    """
                    SELECT version FROM design_version
                    WHERE design_id = ? AND status = 'accepted'
                    ORDER BY version DESC LIMIT 1
                    """,
                    (design_id,),
                ).fetchone()
                new_active = (
                    prev_accepted['version'] if prev_accepted else None
                )
                conn.execute(
                    """
                    UPDATE design
                    SET active_version = ?, updated_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_active, actor_id, now, design_id),
                )
                conn.commit()
                return self._read_design(conn, design_id, version=version)
            finally:
                conn.close()

    def rollback_to_version(
        self,
        design_id: str,
        target_version: int,
        actor_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Restore an earlier version by appending a new draft version."""
        with self._lock:
            conn = self._connect()
            try:
                drow = conn.execute(
                    'SELECT * FROM design WHERE id = ?', (design_id,)
                ).fetchone()
                if drow is None:
                    raise DesignStoreNotFound(
                        f'Design {design_id!r} was not found'
                    )
                trow = conn.execute(
                    'SELECT * FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, target_version),
                ).fetchone()
                if trow is None:
                    raise DesignStoreNotFound(
                        f'Target version {target_version} was not found'
                    )
                head_ver = drow['head_version']
                base_ver = drow['active_version'] or head_ver
                ddn_text = trow['ddn_text']
            finally:
                conn.close()

        return self.save_version(
            design_id,
            expected_head_version=head_ver,
            ddn_text=ddn_text,
            actor_id=actor_id,
            base_version=base_ver,
            status='in_review',
            note=note or f'Rollback to version {target_version}',
            origin=f'rollback:{target_version}',
            allow_conflict_note=True,
        )

    def branch_draft_from_accepted(
        self,
        design_id: str,
        actor_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Start a new draft version from the currently accepted version."""
        with self._lock:
            conn = self._connect()
            try:
                drow = conn.execute(
                    'SELECT * FROM design WHERE id = ?', (design_id,)
                ).fetchone()
                if drow is None:
                    raise DesignStoreNotFound(
                        f'Design {design_id!r} was not found'
                    )
                active_ver = drow['active_version']
                if active_ver is None:
                    raise DesignStoreError(
                        'Design has no accepted version to branch from'
                    )
                arow = conn.execute(
                    'SELECT ddn_text FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, active_ver),
                ).fetchone()
                head_ver = drow['head_version']
                ddn_text = arow['ddn_text']
            finally:
                conn.close()

        return self.save_version(
            design_id,
            expected_head_version=head_ver,
            ddn_text=ddn_text,
            actor_id=actor_id,
            base_version=active_ver,
            status='draft',
            note=note or f'Draft branched from accepted version {active_ver}',
            origin='local',
        )

    # ------------------------------------------------------------------
    # Resource identity and Binding state management (A5, A6)
    # ------------------------------------------------------------------

    def register_resource_identity(
        self,
        *,
        engine: str,
        endpoint_id: str,
        database_target_id: str,
        resource_kind: str,
        resource_id: str,
    ) -> dict[str, Any]:
        """Ensure a stable UUIDv7 identity row exists for a provider object."""
        now = _utc_now()
        with self._lock:
            conn = self._connect()
            try:
                row = self._upsert_resource_identity(
                    conn,
                    engine=engine,
                    endpoint_id=str(endpoint_id),
                    database_target_id=str(database_target_id),
                    resource_kind=resource_kind,
                    resource_id=resource_id,
                    now=now,
                )
                conn.commit()
                return row
            finally:
                conn.close()

    def record_resource_rename(
        self,
        *,
        engine: str,
        endpoint_id: str,
        database_target_id: str,
        old_resource_id: str,
        new_resource_id: str,
    ) -> dict[str, Any]:
        """Record a catalog rename and mark affected bindings suspect (A6)."""
        now = _utc_now()
        ep = str(endpoint_id)
        db_target = str(database_target_id)
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM resource_identity
                    WHERE engine = ? AND endpoint_id = ?
                      AND database_target_id = ? AND resource_id = ?
                    """,
                    (engine, ep, db_target, old_resource_id),
                ).fetchone()
                identity_id = None
                if row is not None:
                    identity_id = row['id']
                    prev = json.loads(row['previous_ids'] or '[]')
                    if old_resource_id not in prev:
                        prev.append(old_resource_id)
                    conn.execute(
                        """
                        UPDATE resource_identity
                        SET resource_id = ?, previous_ids = ?, last_seen_at = ?
                        WHERE id = ?
                        """,
                        (
                            new_resource_id,
                            json.dumps(prev),
                            now,
                            identity_id,
                        ),
                    )
                refs = [old_resource_id, new_resource_id]
                if identity_id:
                    refs.append(identity_id)
                placeholders = ', '.join('?' for _ in refs)
                cursor = conn.execute(
                    f"""
                    UPDATE binding
                    SET state = 'suspect',
                        state_reason = 'target renamed',
                        confirmed_by = NULL,
                        confirmed_at = NULL
                    WHERE target_kind = 'resource'
                      AND (
                          target_ref IN ({placeholders})
                      )
                      AND (target_engine IS NULL OR target_engine = ?)
                      AND (
                          target_endpoint_id IS NULL OR target_endpoint_id = ?
                      )
                      AND (
                          target_database_target_id IS NULL
                          OR target_database_target_id = ?
                      )
                    """,
                    [*refs, engine, ep, db_target],
                )
                conn.commit()
                return {
                    'identity_id': identity_id,
                    'old_resource_id': old_resource_id,
                    'new_resource_id': new_resource_id,
                    'suspect_bindings_marked': cursor.rowcount,
                }
            finally:
                conn.close()

    def record_resource_drop(
        self,
        *,
        engine: str,
        endpoint_id: str,
        database_target_id: str,
        resource_id: str,
    ) -> dict[str, Any]:
        """Record a catalog drop and mark affected bindings suspect (A6)."""
        ep = str(endpoint_id)
        db_target = str(database_target_id)
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT id FROM resource_identity
                    WHERE engine = ? AND endpoint_id = ?
                      AND database_target_id = ? AND resource_id = ?
                    """,
                    (engine, ep, db_target, resource_id),
                ).fetchone()
                refs = [resource_id]
                if row is not None:
                    refs.append(row['id'])
                placeholders = ', '.join('?' for _ in refs)
                cursor = conn.execute(
                    f"""
                    UPDATE binding
                    SET state = 'suspect',
                        state_reason = 'target dropped',
                        confirmed_by = NULL,
                        confirmed_at = NULL
                    WHERE target_kind = 'resource'
                      AND target_ref IN ({placeholders})
                      AND (target_engine IS NULL OR target_engine = ?)
                      AND (
                          target_endpoint_id IS NULL OR target_endpoint_id = ?
                      )
                      AND (
                          target_database_target_id IS NULL
                          OR target_database_target_id = ?
                      )
                    """,
                    [*refs, engine, ep, db_target],
                )
                conn.commit()
                return {
                    'resource_id': resource_id,
                    'suspect_bindings_marked': cursor.rowcount,
                }
            finally:
                conn.close()

    def confirm_binding(
        self,
        binding_id: str,
        actor_id: int,
        *,
        new_target_ref: str | None = None,
    ) -> dict[str, Any]:
        """Confirm a suspect or unknown binding as valid (A6)."""
        if isinstance(actor_id, bool) or not isinstance(actor_id, int):
            raise DesignStoreError('actor_id must be an integer user ID')
        now = _utc_now()
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    'SELECT * FROM binding WHERE id = ?', (binding_id,)
                ).fetchone()
                if row is None:
                    raise DesignStoreNotFound(
                        f'Binding {binding_id!r} was not found'
                    )
                target_ref = (
                    new_target_ref
                    if new_target_ref is not None
                    else row['target_ref']
                )
                conn.execute(
                    """
                    UPDATE binding
                    SET target_ref = ?,
                        state = 'valid',
                        state_reason = NULL,
                        confirmed_by = ?,
                        confirmed_at = ?
                    WHERE id = ?
                    """,
                    (target_ref, actor_id, now, binding_id),
                )
                conn.commit()
                updated = conn.execute(
                    'SELECT * FROM binding WHERE id = ?', (binding_id,)
                ).fetchone()
                return dict(updated)
            finally:
                conn.close()

    def add_binding(
        self,
        *,
        design_id: str,
        element_id: str,
        target_kind: str,
        target_ref: str,
        target_engine: str | None = None,
        target_endpoint_id: str | None = None,
        target_database_target_id: str | None = None,
        state: str = 'valid',
        state_reason: str | None = None,
    ) -> dict[str, Any]:
        """Add or update an explicit binding row for a design element."""
        if target_kind not in TARGET_KINDS:
            raise DesignStoreError(f'Unsupported target_kind: {target_kind!r}')
        if state not in BINDING_STATES:
            raise DesignStoreError(f'Unsupported binding state: {state!r}')
        with self._lock:
            conn = self._connect()
            try:
                elem = conn.execute(
                    'SELECT id FROM element WHERE id = ? AND design_id = ?',
                    (element_id, design_id),
                ).fetchone()
                if elem is None:
                    raise DesignStoreNotFound(
                        f'Element {element_id!r} not found in design '
                        f'{design_id!r}'
                    )
                existing = conn.execute(
                    """
                    SELECT id FROM binding
                    WHERE design_id = ? AND element_id = ?
                      AND target_kind = ? AND target_ref = ?
                    """,
                    (design_id, element_id, target_kind, target_ref),
                ).fetchone()
                if existing is not None:
                    bid = existing['id']
                    conn.execute(
                        """
                        UPDATE binding
                        SET target_engine = ?,
                            target_endpoint_id = ?,
                            target_database_target_id = ?,
                            state = ?,
                            state_reason = ?
                        WHERE id = ?
                        """,
                        (
                            target_engine,
                            target_endpoint_id,
                            target_database_target_id,
                            state,
                            state_reason,
                            bid,
                        ),
                    )
                else:
                    bid = uuid7()
                    conn.execute(
                        """
                        INSERT INTO binding (
                            id, design_id, element_id, target_kind, target_ref,
                            target_engine, target_endpoint_id,
                            target_database_target_id, state, state_reason,
                            confirmed_by, confirmed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                        """,
                        (
                            bid,
                            design_id,
                            element_id,
                            target_kind,
                            target_ref,
                            target_engine,
                            target_endpoint_id,
                            target_database_target_id,
                            state,
                            state_reason,
                        ),
                    )
                conn.commit()
                row = conn.execute(
                    'SELECT * FROM binding WHERE id = ?', (bid,)
                ).fetchone()
                return dict(row)
            finally:
                conn.close()

    def list_bindings(
        self,
        design_id: str,
        *,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        """List bindings for ``design_id``, optionally filtered by state."""
        with self._lock:
            conn = self._connect()
            try:
                if state is not None:
                    rows = conn.execute(
                        'SELECT * FROM binding '
                        'WHERE design_id = ? AND state = ? ORDER BY id ASC',
                        (design_id, state),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        'SELECT * FROM binding '
                        'WHERE design_id = ? ORDER BY id ASC',
                        (design_id,),
                    ).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Design dependencies and Target deployments
    # ------------------------------------------------------------------

    def set_dependencies(
        self,
        design_id: str,
        version: int,
        dependencies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Record version pins from (design_id, version) to other designs."""
        with self._lock:
            conn = self._connect()
            try:
                vrow = conn.execute(
                    'SELECT 1 FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, version),
                ).fetchone()
                if vrow is None:
                    raise DesignStoreNotFound(
                        f'Version {version} of design {design_id!r} not found'
                    )
                conn.execute(
                    'DELETE FROM design_dependency '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, version),
                )
                for dep in dependencies:
                    target_id = dep.get('depends_on_design_id')
                    target_ver = dep.get('depends_on_version')
                    if not target_id or target_id == design_id:
                        raise DesignStoreError(
                            'Invalid depends_on_design_id'
                        )
                    conn.execute(
                        """
                        INSERT INTO design_dependency (
                            design_id, version,
                            depends_on_design_id, depends_on_version
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (design_id, version, target_id, target_ver),
                    )
                conn.commit()
                rows = conn.execute(
                    'SELECT * FROM design_dependency '
                    'WHERE design_id = ? AND version = ? '
                    'ORDER BY depends_on_design_id ASC',
                    (design_id, version),
                ).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def record_deployment(
        self,
        *,
        design_id: str,
        deployed_version: int,
        engine: str,
        endpoint_id: str,
        database_target_id: str,
        plan_sha256: str,
        target_fingerprint: str,
        applied_by: int,
    ) -> dict[str, Any]:
        """Record which design version is deployed to a target database."""
        now = _utc_now()
        with self._lock:
            conn = self._connect()
            try:
                vrow = conn.execute(
                    'SELECT status FROM design_version '
                    'WHERE design_id = ? AND version = ?',
                    (design_id, deployed_version),
                ).fetchone()
                if vrow is None:
                    raise DesignStoreNotFound(
                        f'Version {deployed_version} of design {design_id!r} '
                        f'was not found'
                    )
                conn.execute(
                    """
                    INSERT INTO target_deployment (
                        design_id, engine, endpoint_id, database_target_id,
                        deployed_version, plan_sha256, target_fingerprint,
                        applied_by, applied_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                        design_id, engine, endpoint_id, database_target_id
                    ) DO UPDATE SET
                        deployed_version = excluded.deployed_version,
                        plan_sha256 = excluded.plan_sha256,
                        target_fingerprint = excluded.target_fingerprint,
                        applied_by = excluded.applied_by,
                        applied_at = excluded.applied_at
                    """,
                    (
                        design_id,
                        engine,
                        str(endpoint_id),
                        str(database_target_id),
                        deployed_version,
                        plan_sha256,
                        target_fingerprint,
                        applied_by,
                        now,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    """
                    SELECT * FROM target_deployment
                    WHERE design_id = ? AND engine = ?
                      AND endpoint_id = ? AND database_target_id = ?
                    """,
                    (
                        design_id,
                        engine,
                        str(endpoint_id),
                        str(database_target_id),
                    ),
                ).fetchone()
                return dict(row)
            finally:
                conn.close()

    def list_deployments(self, design_id: str) -> list[dict[str, Any]]:
        """List recorded database deployments for ``design_id``."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    'SELECT * FROM target_deployment WHERE design_id = ? '
                    'ORDER BY engine, endpoint_id, database_target_id',
                    (design_id,),
                ).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Binary attachments: asset_blob and design_asset (A4: 16 MiB cap)
    # ------------------------------------------------------------------

    def put_blob(self, media_type: str, data: bytes) -> dict[str, Any]:
        """Store a binary attachment in asset_blob (<= 16 MiB, SHA-256 key)."""
        if not isinstance(media_type, str) or not media_type.strip():
            raise DesignStoreError('media_type is required')
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise DesignStoreError('blob payload must be bytes')
        raw = bytes(data)
        size = len(raw)
        if size > MAX_BLOB_BYTES:
            raise DesignStoreError(
                f'Blob size {size} exceeds the 16 MiB cap ({MAX_BLOB_BYTES})'
            )
        digest = hashlib.sha256(raw).hexdigest()
        now = _utc_now()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO asset_blob (
                        sha256, media_type, bytes, size, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(sha256) DO NOTHING
                    """,
                    (digest, media_type.strip(), raw, size, now),
                )
                conn.commit()
                return {
                    'sha256': digest,
                    'media_type': media_type.strip(),
                    'size': size,
                    'created_at': now,
                }
            finally:
                conn.close()

    def get_blob(self, sha256: str) -> dict[str, Any]:
        """Fetch a content-addressed binary attachment by SHA-256."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    'SELECT * FROM asset_blob WHERE sha256 = ?', (sha256,)
                ).fetchone()
                if row is None:
                    raise DesignStoreNotFound(
                        f'Asset blob {sha256!r} was not found'
                    )
                return {
                    'sha256': row['sha256'],
                    'media_type': row['media_type'],
                    'bytes': bytes(row['bytes']),
                    'size': row['size'],
                    'created_at': row['created_at'],
                }
            finally:
                conn.close()

    def attach_blob(
        self,
        design_id: str,
        version: int,
        path: str,
        sha256: str,
    ) -> dict[str, Any]:
        """Link an existing asset_blob to a (design_id, version, path)."""
        if (
            not isinstance(path, str)
            or not path.strip()
            or path.startswith('/')
            or '..' in path.split('/')
        ):
            raise DesignStoreError('Invalid design asset path')
        with self._lock:
            conn = self._connect()
            try:
                blob = conn.execute(
                    'SELECT sha256, media_type, size FROM asset_blob '
                    'WHERE sha256 = ?',
                    (sha256,),
                ).fetchone()
                if blob is None:
                    raise DesignStoreNotFound(
                        f'Asset blob {sha256!r} was not found'
                    )
                conn.execute(
                    """
                    INSERT INTO design_asset (design_id, version, path, sha256)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(design_id, version, path) DO UPDATE SET
                        sha256 = excluded.sha256
                    """,
                    (design_id, version, path.strip(), sha256),
                )
                conn.commit()
                return {
                    'design_id': design_id,
                    'version': version,
                    'path': path.strip(),
                    'sha256': sha256,
                    'media_type': blob['media_type'],
                    'size': blob['size'],
                }
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # DDN Export / Import and Physical ERD Bridge
    # ------------------------------------------------------------------

    def export_ddn(
        self,
        design_id: str,
        *,
        version: int | None = None,
        entry: str = 'design.ddn',
    ) -> dict[str, Any]:
        """Export a design version as canonical DDN text and workspace."""
        record = self.get_design(design_id, version=version)
        ver_info = record['version']
        ddn_text = ver_info['ddn_text']
        workspace = ddn_text_to_workspace(ddn_text, entry=entry)
        return {
            'design_id': record['id'],
            'project_id': record['project_id'],
            'key': record['key'],
            'kind': record['kind'],
            'title': record['title'],
            'version': ver_info['version'],
            'status': ver_info['status'],
            'ddn_text': ddn_text,
            'ddn_sha256': ver_info['ddn_sha256'],
            'dialect_version': ver_info['dialect_version'],
            'workspace': workspace,
        }

    def import_ddn(
        self,
        *,
        project_id: str,
        key: str,
        kind: str,
        title: str,
        ddn_or_workspace: str | dict[str, Any],
        actor_id: int,
        origin: str = 'import:file',
        loss_report: dict[str, Any] | None = None,
        name_mapping: dict[str, str] | None = None,
        observe_resources: bool = False,
        note: str = '',
    ) -> dict[str, Any]:
        """Import a DDN document or workspace into a new or existing design.

        Matches elements by UUIDv7 id first, then falls back to
        ``name_mapping`` or existing resource bindings, and never deletes
        existing designs on import.
        """
        ddn_text, _entry, _view = workspace_to_ddn_text(ddn_or_workspace)
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    'SELECT id, head_version FROM design '
                    'WHERE project_id = ? AND key = ?',
                    (project_id, key),
                ).fetchone()
            finally:
                conn.close()

        if existing is None:
            return self.create_design(
                project_id=project_id,
                key=key,
                kind=kind,
                title=title,
                ddn_text=ddn_text,
                actor_id=actor_id,
                status='draft',
                note=note or f'Imported from {origin}',
                origin=origin,
                loss_report=loss_report,
                name_mapping=name_mapping,
                observe_resources=observe_resources,
            )

        return self.save_version(
            existing['id'],
            expected_head_version=existing['head_version'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note or f'Imported from {origin}',
            origin=origin,
            loss_report=loss_report,
            title=title,
            name_mapping=name_mapping,
            observe_resources=observe_resources,
            allow_conflict_note=True,
        )

    def import_physical_erd_workspace(
        self,
        *,
        project_id: str,
        key: str,
        title: str,
        workspace: dict[str, Any] | str,
        actor_id: int,
        origin: str = 'import:catalog',
        note: str = '',
    ) -> dict[str, Any]:
        """Bridge an existing ``scratchrobin.physical-schema@1`` /
        ``scratchrobin.<engine>.relations`` workspace into an ERD design.

        Owner decision, 2026-11-10: start the ERD physical level from the
        existing ``ddn_database_roundtrip`` /
        ``scratchrobin.physical-schema@1`` vocabulary and bridge into the
        design store's element and resource_identity model.
        """
        return self.import_ddn(
            project_id=project_id,
            key=key,
            kind='erd',
            title=title,
            ddn_or_workspace=workspace,
            actor_id=actor_id,
            origin=origin,
            observe_resources=True,
            note=note or 'Imported physical ERD from catalog',
        )

    # ------------------------------------------------------------------
    # Git link and local repository synchronization
    # ------------------------------------------------------------------

    def link_git(
        self,
        design_id: str,
        *,
        repository: str,
        path: str,
        branch: str = 'main',
    ) -> dict[str, Any]:
        """Configure where a design's DDN text lives in Git."""
        if not isinstance(repository, str) or not repository.strip():
            raise DesignStoreError('Git repository is required')
        if (
            not isinstance(path, str)
            or not path.strip()
            or path.startswith('/')
            or '..' in path.split('/')
            or not path.endswith('.ddn')
        ):
            raise DesignStoreError(
                'Git path must be a relative .ddn file path'
            )
        with self._lock:
            conn = self._connect()
            try:
                drow = conn.execute(
                    'SELECT id FROM design WHERE id = ?', (design_id,)
                ).fetchone()
                if drow is None:
                    raise DesignStoreNotFound(
                        f'Design {design_id!r} was not found'
                    )
                conn.execute(
                    """
                    INSERT INTO git_link (
                        design_id, repository, path, branch,
                        last_pushed_version, last_pushed_commit,
                        last_pushed_sha256, last_pulled_commit,
                        last_pulled_sha256, sync_state
                    ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL,
                              'modified')
                    ON CONFLICT(design_id) DO UPDATE SET
                        repository = excluded.repository,
                        path = excluded.path,
                        branch = excluded.branch
                    """,
                    (
                        design_id,
                        repository.strip(),
                        path.strip(),
                        (branch or 'main').strip(),
                    ),
                )
                conn.commit()
                row = conn.execute(
                    'SELECT * FROM git_link WHERE design_id = ?',
                    (design_id,),
                ).fetchone()
                return dict(row)
            finally:
                conn.close()

    def export_to_git(
        self,
        design_id: str,
        repo_root: str | Path,
        *,
        version: int | None = None,
        commit: bool = False,
        author_name: str = 'ScratchRobin',
        author_email: str = 'scratchrobin@localhost',
    ) -> dict[str, Any]:
        """Write a design's DDN text to its linked Git worktree path."""
        record = self.get_design(design_id, version=version)
        git_info = record.get('git_link')
        if not git_info:
            raise DesignStoreError(
                f'Design {design_id!r} has no git_link configured'
            )
        ver = record['version']
        root = Path(repo_root).resolve()
        target = (root / git_info['path']).resolve()
        if root not in target.parents:
            raise DesignStoreError('Git path escapes repository root')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ver['ddn_text'], encoding='utf-8')

        commit_sha = git_info.get('last_pushed_commit')
        if commit:
            rel_path = git_info['path']
            subprocess.run(
                ['git', '-C', str(root), 'add', '--', rel_path],
                check=True,
                capture_output=True,
                text=True,
            )
            status_out = subprocess.run(
                [
                    'git', '-C', str(root),
                    'status', '--porcelain', '--', rel_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if status_out:
                msg = (
                    f'design({record["key"]}): version {ver["version"]} '
                    f'[{ver["status"]}]\n\n'
                    f'Design-Id: {design_id}\n'
                    f'Design-Version: {ver["version"]}\n'
                    f'DDN-SHA256: {ver["ddn_sha256"]}\n'
                )
                subprocess.run(
                    [
                        'git', '-C', str(root),
                        '-c', f'user.name={author_name}',
                        '-c', f'user.email={author_email}',
                        'commit', '-m', msg, '--', rel_path,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            commit_sha = subprocess.run(
                ['git', '-C', str(root), 'rev-parse', 'HEAD'],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE git_link
                    SET last_pushed_version = ?,
                        last_pushed_commit = ?,
                        last_pushed_sha256 = ?,
                        sync_state = 'synced'
                    WHERE design_id = ?
                    """,
                    (
                        ver['version'],
                        commit_sha,
                        ver['ddn_sha256'],
                        design_id,
                    ),
                )
                conn.commit()
                updated = conn.execute(
                    'SELECT * FROM git_link WHERE design_id = ?',
                    (design_id,),
                ).fetchone()
                return dict(updated)
            finally:
                conn.close()

    def import_from_git(
        self,
        design_id: str,
        repo_root: str | Path,
        *,
        actor_id: int,
        note: str = '',
    ) -> dict[str, Any]:
        """Load DDN text from a linked Git worktree into a new draft."""
        record = self.get_design(design_id)
        git_info = record.get('git_link')
        if not git_info:
            raise DesignStoreError(
                f'Design {design_id!r} has no git_link configured'
            )
        root = Path(repo_root).resolve()
        target = (root / git_info['path']).resolve()
        if root not in target.parents or not target.is_file():
            raise DesignStoreNotFound(
                f'Git DDN file {git_info["path"]!r} was not found'
            )
        file_text = target.read_text(encoding='utf-8')
        file_sha = sha256_text(file_text)
        commit_sha = None
        try:
            commit_sha = subprocess.run(
                ['git', '-C', str(root), 'rev-parse', 'HEAD'],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            commit_sha = 'worktree'

        origin = f'git:{git_info["repository"]}@{commit_sha}'
        saved = self.save_version(
            design_id,
            expected_head_version=record['head_version'],
            ddn_text=file_text,
            actor_id=actor_id,
            status='draft',
            note=note or f'Loaded from Git ({commit_sha})',
            origin=origin,
            allow_conflict_note=True,
        )
        saved_sha = saved['version']['ddn_sha256']
        if saved_sha != file_sha:
            target.write_text(saved['version']['ddn_text'], encoding='utf-8')
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE git_link
                    SET last_pulled_commit = ?,
                        last_pulled_sha256 = ?,
                        last_pushed_version = ?,
                        last_pushed_sha256 = ?,
                        sync_state = 'synced'
                    WHERE design_id = ?
                    """,
                    (
                        commit_sha,
                        saved_sha,
                        saved['head_version'],
                        saved_sha,
                        design_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_design(design_id)

    def check_git_drift(
        self,
        design_id: str,
        *,
        repo_root: str | Path | None = None,
        remote_ddn_text: str | None = None,
    ) -> dict[str, Any]:
        """Compare store head DDN hash with Git file hash to detect drift."""
        record = self.get_design(design_id)
        git_info = record.get('git_link')
        if not git_info:
            raise DesignStoreError(
                f'Design {design_id!r} has no git_link configured'
            )
        if remote_ddn_text is None:
            if repo_root is None:
                raise DesignStoreError(
                    'Supply either repo_root or remote_ddn_text'
                )
            root = Path(repo_root).resolve()
            target = (root / git_info['path']).resolve()
            if root not in target.parents or not target.is_file():
                raise DesignStoreNotFound(
                    f'Git DDN file {git_info["path"]!r} was not found'
                )
            remote_ddn_text = target.read_text(encoding='utf-8')

        remote_sha = sha256_text(remote_ddn_text)
        head_sha = record['version']['ddn_sha256']
        base_sha = (
            git_info.get('last_pushed_sha256')
            or git_info.get('last_pulled_sha256')
        )
        if head_sha == remote_sha:
            state = 'synced'
        elif base_sha is None:
            state = 'conflict'
        elif head_sha != base_sha and remote_sha == base_sha:
            state = 'modified'
        elif head_sha == base_sha and remote_sha != base_sha:
            state = 'out_of_sync'
        else:
            state = 'conflict'

        if state not in GIT_SYNC_STATES:
            state = 'conflict'

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    'UPDATE git_link SET sync_state = ? WHERE design_id = ?',
                    (state, design_id),
                )
                conn.commit()
                updated = conn.execute(
                    'SELECT * FROM git_link WHERE design_id = ?',
                    (design_id,),
                ).fetchone()
                result = dict(updated)
                result['head_sha256'] = head_sha
                result['git_sha256'] = remote_sha
                return result
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        project_id: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search designs across DDN text, notes and element names via FTS5."""
        if not isinstance(query, str) or not query.strip():
            return []
        tokens = [
            re.sub(r'[^A-Za-z0-9_]', '', part)
            for part in query.strip().split()
        ]
        tokens = [tok for tok in tokens if tok]
        if not tokens:
            return []
        fts_query = ' AND '.join(f'"{tok}"*' for tok in tokens)

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT DISTINCT d.*
                    FROM design d
                    LEFT JOIN design_version_fts vf
                      ON vf.design_id = d.id
                    LEFT JOIN element_fts ef
                      ON ef.design_id = d.id
                    WHERE (
                        d.id IN (
                            SELECT design_id FROM design_version_fts
                            WHERE design_version_fts MATCH ?
                        )
                        OR d.id IN (
                            SELECT design_id FROM element_fts
                            WHERE element_fts MATCH ?
                        )
                    )
                    ORDER BY d.updated_at DESC
                    """,
                    (fts_query, fts_query),
                ).fetchall()
                results = []
                for row in rows:
                    if project_id and row['project_id'] != project_id:
                        continue
                    if kind and row['kind'] != kind:
                        continue
                    results.append(dict(row))
                return results
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _existing_element_maps(
        conn: sqlite3.Connection,
        design_id: str,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        erows = conn.execute(
            'SELECT * FROM element WHERE design_id = ?', (design_id,)
        ).fetchall()
        by_id = {row['id']: dict(row) for row in erows}
        brows = conn.execute(
            """
            SELECT b.element_id, b.target_ref, r.resource_id
            FROM binding b
            LEFT JOIN resource_identity r ON r.id = b.target_ref
            WHERE b.design_id = ?
            """,
            (design_id,),
        ).fetchall()
        by_res: dict[str, str] = {}
        for brow in brows:
            if brow['target_ref']:
                by_res[brow['target_ref']] = brow['element_id']
            if brow['resource_id']:
                by_res[brow['resource_id']] = brow['element_id']
        return by_id, by_res

    @staticmethod
    def _upsert_resource_identity(
        conn: sqlite3.Connection,
        *,
        engine: str,
        endpoint_id: str,
        database_target_id: str,
        resource_kind: str,
        resource_id: str,
        now: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT * FROM resource_identity
            WHERE engine = ? AND endpoint_id = ?
              AND database_target_id = ? AND resource_id = ?
            """,
            (engine, endpoint_id, database_target_id, resource_id),
        ).fetchone()
        if row is not None:
            conn.execute(
                'UPDATE resource_identity SET last_seen_at = ? WHERE id = ?',
                (now, row['id']),
            )
            return dict(row) | {'last_seen_at': now}
        rid = uuid7()
        conn.execute(
            """
            INSERT INTO resource_identity (
                id, engine, endpoint_id, database_target_id,
                resource_kind, resource_id, previous_ids, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', ?)
            """,
            (
                rid,
                engine,
                endpoint_id,
                database_target_id,
                resource_kind,
                resource_id,
                now,
            ),
        )
        return {
            'id': rid,
            'engine': engine,
            'endpoint_id': endpoint_id,
            'database_target_id': database_target_id,
            'resource_kind': resource_kind,
            'resource_id': resource_id,
            'previous_ids': '[]',
            'last_seen_at': now,
        }

    def _sync_elements_and_bindings(
        self,
        conn: sqlite3.Connection,
        *,
        design_id: str,
        version: int,
        info: dict[str, Any],
        observe_resources: bool,
        now: str,
    ) -> None:
        existing_rows = conn.execute(
            'SELECT * FROM element WHERE design_id = ?', (design_id,)
        ).fetchall()
        existing_by_id = {row['id']: dict(row) for row in existing_rows}
        seen_ids: set[str] = set()

        for elem in info['elements']:
            eid = elem['id']
            seen_ids.add(eid)
            if eid in existing_by_id:
                conn.execute(
                    """
                    UPDATE element
                    SET role = ?, name = ?, removed_version = NULL
                    WHERE id = ? AND design_id = ?
                    """,
                    (elem['role'], elem['name'], eid, design_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO element (
                        id, design_id, role, name,
                        first_version, removed_version
                    ) VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (eid, design_id, elem['role'], elem['name'], version),
                )

        for old_id, old_row in existing_by_id.items():
            if (
                old_id not in seen_ids
                and old_row['removed_version'] is None
            ):
                conn.execute(
                    """
                    UPDATE element
                    SET removed_version = ?
                    WHERE id = ? AND design_id = ?
                    """,
                    (version, old_id, design_id),
                )

        for bind in info['bindings']:
            element_id = bind['element_id']
            if element_id not in seen_ids:
                continue
            target_kind = bind['target_kind']
            if target_kind not in TARGET_KINDS:
                continue
            target_ref = bind['target_ref']
            engine = bind.get('target_engine')
            ep_id = bind.get('target_endpoint_id')
            db_id = bind.get('target_database_target_id')
            res_kind = bind.get('resource_kind') or 'object'

            initial_state = 'unknown'
            if target_kind == 'resource' and engine and ep_id and db_id:
                if observe_resources:
                    res_row = self._upsert_resource_identity(
                        conn,
                        engine=engine,
                        endpoint_id=ep_id,
                        database_target_id=db_id,
                        resource_kind=res_kind,
                        resource_id=target_ref,
                        now=now,
                    )
                    initial_state = 'valid'
                    target_ref = res_row['id']
                else:
                    res_row = conn.execute(
                        """
                        SELECT id FROM resource_identity
                        WHERE engine = ? AND endpoint_id = ?
                          AND database_target_id = ?
                          AND (resource_id = ? OR id = ?)
                        """,
                        (engine, ep_id, db_id, target_ref, target_ref),
                    ).fetchone()
                    if res_row is not None:
                        initial_state = 'valid'
                        target_ref = res_row['id']

            existing_bind = conn.execute(
                """
                SELECT * FROM binding
                WHERE design_id = ? AND element_id = ?
                  AND target_kind = ? AND target_ref = ?
                """,
                (design_id, element_id, target_kind, target_ref),
            ).fetchone()
            if existing_bind is None:
                conn.execute(
                    """
                    INSERT INTO binding (
                        id, design_id, element_id, target_kind, target_ref,
                        target_engine, target_endpoint_id,
                        target_database_target_id, state, state_reason,
                        confirmed_by, confirmed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                    """,
                    (
                        uuid7(),
                        design_id,
                        element_id,
                        target_kind,
                        target_ref,
                        engine,
                        ep_id,
                        db_id,
                        initial_state,
                    ),
                )

    @staticmethod
    def _read_design(
        conn: sqlite3.Connection,
        design_id: str,
        *,
        version: int | None = None,
        active_only: bool = False,
    ) -> dict[str, Any]:
        drow = conn.execute(
            'SELECT * FROM design WHERE id = ?', (design_id,)
        ).fetchone()
        if drow is None:
            raise DesignStoreNotFound(f'Design {design_id!r} was not found')

        if active_only:
            target_ver = drow['active_version']
            if target_ver is None:
                raise DesignStoreNotFound(
                    f'Design {design_id!r} has no accepted active version'
                )
        elif version is not None:
            target_ver = version
        else:
            target_ver = drow['head_version']

        vrow = conn.execute(
            """
            SELECT v.*,
                   a.accepted_by, a.accepted_at, a.approval_ref,
                   a.returned_by, a.returned_at, a.return_status
            FROM design_version v
            LEFT JOIN acceptance a
              ON a.design_id = v.design_id AND a.version = v.version
            WHERE v.design_id = ? AND v.version = ?
            """,
            (design_id, target_ver),
        ).fetchone()
        if vrow is None:
            raise DesignStoreNotFound(
                f'Version {target_ver} of design {design_id!r} was not found'
            )

        elements = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM element WHERE design_id = ? ORDER BY id ASC',
                (design_id,),
            ).fetchall()
        ]
        bindings = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM binding WHERE design_id = ? ORDER BY id ASC',
                (design_id,),
            ).fetchall()
        ]
        dependencies = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM design_dependency '
                'WHERE design_id = ? AND version = ? '
                'ORDER BY depends_on_design_id ASC',
                (design_id, target_ver),
            ).fetchall()
        ]
        assets = [
            dict(row)
            for row in conn.execute(
                """
                SELECT da.path, da.sha256, ab.media_type, ab.size
                FROM design_asset da
                JOIN asset_blob ab ON ab.sha256 = da.sha256
                WHERE da.design_id = ? AND da.version = ?
                ORDER BY da.path ASC
                """,
                (design_id, target_ver),
            ).fetchall()
        ]
        git_row = conn.execute(
            'SELECT * FROM git_link WHERE design_id = ?', (design_id,)
        ).fetchone()

        ver_dict = dict(vrow)
        ver_dict['loss_report'] = (
            json.loads(ver_dict['loss_report'])
            if ver_dict['loss_report']
            else None
        )
        result = dict(drow)
        result['version'] = ver_dict
        result['elements'] = elements
        result['bindings'] = bindings
        result['dependencies'] = dependencies
        result['assets'] = assets
        result['git_link'] = dict(git_row) if git_row is not None else None
        return result


def init_app(app, db_path: str | Path | None = None) -> DesignStore:
    """Register a shared DesignStore instance on a Flask application."""
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None and db_path is None:
        return existing
    store = DesignStore(db_path=db_path)
    app.extensions[APP_EXTENSION_KEY] = store
    return store


def store_for_app(app=None) -> DesignStore:
    """Return the active DesignStore for ``app`` or ``current_app``."""
    if app is None:
        from flask import current_app, has_app_context
        if has_app_context():
            app = current_app
    if app is not None:
        existing = app.extensions.get(APP_EXTENSION_KEY)
        if existing is not None:
            return existing
        return init_app(app)
    return DesignStore()
