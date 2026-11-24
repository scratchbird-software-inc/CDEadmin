##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Encrypted UserConfigurationDatabase backed by FirebirdSQL 5.0 Embedded.

Stores:
  1. Vault encryption header (`UCFG_VAULT_HEADER`) wrapped with `database_key`
     via PBKDF2-HMAC-SHA256 + AES-256-GCM.
  2. Multi-user / single-user accounts (`UCFG_USERS`) with bcrypt password
     hashes and encrypted role grants.
  3. Engine / server / database connection parameters (`UCFG_CONNECTIONS`).
  4. Per-user preferences & shared field-type defaults (`UCFG_USER_PREFERENCES`).
  5. Per-user table/view column & result-set display layouts
     (`UCFG_OBJECT_DISPLAY_LAYOUTS`).
  6. Named shareable display templates (`UCFG_DISPLAY_TEMPLATES`).
  7. Server & database metrics, query execution history, SQL snippets, and
     quick queries (`UCFG_METRICS_HISTORY`).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import bcrypt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


SCHEMA_VERSION = 1
DEFAULT_KDF_ITERATIONS = 210_000
VAULT_DEK_AAD = b'scratchrobin.ucfg.vault_dek.v1'
CIPHERTEXT_PREFIX = 'enc:v1:'

ALLOWED_FONTS = frozenset({'', 'system', 'sans', 'serif', 'mono'})
ALLOWED_FONT_SIZES = frozenset({'', 'xs', 'sm', 'md', 'lg'})
ALLOWED_H_ALIGNS = frozenset({'', 'left', 'center', 'right'})
ALLOWED_V_ALIGNS = frozenset({'', 'top', 'middle', 'bottom'})
ALLOWED_WRAP_MODES = frozenset({'', 'none', 'wrap', 'clamp'})
_SAFE_COLOR_RE = re.compile(
    r'^(#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}'
    r'(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)|var\(--[a-zA-Z0-9_-]+\))$'
)

_RUNTIME_INIT_LOCK = threading.RLock()
_DEFAULT_DB_LOCK = threading.RLock()
_DEFAULT_DB_INSTANCE: UserConfigurationDatabase | None = None
_DESKTOP_HANDOFF_LOCK = threading.RLock()
_DESKTOP_HANDOFF_TICKETS: dict[str, dict[str, Any]] = {}


class UserConfigLockedError(RuntimeError):
    """Raised when UserConfigurationDatabase has not been unlocked with database_key."""


class UserConfigKeyError(ValueError):
    """Raised when the supplied database_key cannot decrypt UserConfigurationDatabase."""


class UserConfigAuthError(ValueError):
    """Raised when username or password authentication fails."""


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _discover_firebird_runtime() -> tuple[str | None, str | None]:
    """Locate the bundled Firebird 5.0 runtime root and libfbclient shared library."""
    env_lib = (os.environ.get('CDEADMIN_FIREBIRD_CLIENT_LIBRARY') or '').strip()
    if env_lib and Path(env_lib).is_file():
        lib_path = Path(env_lib).resolve()
        rt_root = lib_path.parent.parent if lib_path.parent.name == 'lib' else lib_path.parent
        return str(rt_root), str(lib_path)

    here = Path(__file__).resolve()
    # Walk ancestors to find tools/reference_engine_demos/runtime/firebird
    candidates: list[Path] = []
    for ancestor in here.parents:
        candidates.append(ancestor / 'tools' / 'reference_engine_demos' / 'runtime' / 'firebird')
    candidates.append(
        Path('/home/dcalford/SandBox/CDEadmin/tools/reference_engine_demos/runtime/firebird')
    )

    lib_names = (
        'libfbclient.so.5.0.4',
        'libfbclient.so.2',
        'libfbclient.so',
        'fbclient.dll',
        'libfbclient.dylib',
    )
    for rt_dir in candidates:
        lib_dir = rt_dir / 'lib'
        if lib_dir.is_dir():
            for name in lib_names:
                candidate = lib_dir / name
                if candidate.is_file():
                    return str(rt_dir.resolve()), str(candidate.resolve())
        for name in lib_names:
            candidate = rt_dir / name
            if candidate.is_file():
                return str(rt_dir.resolve()), str(candidate.resolve())
    return None, None


def _load_firebird_driver(lock_dir: Path | None = None):
    """Import and configure firebird.driver for FirebirdSQL Embedded."""
    with _RUNTIME_INIT_LOCK:
        rt_root, lib_path = _discover_firebird_runtime()
        if rt_root and not os.environ.get('FIREBIRD'):
            os.environ['FIREBIRD'] = rt_root
        if lock_dir is not None and not os.environ.get('FIREBIRD_LOCK'):
            lock_dir.mkdir(parents=True, exist_ok=True)
            try:
                if os.name != 'nt':
                    os.chmod(lock_dir, 0o700)
            except OSError:
                pass
            os.environ['FIREBIRD_LOCK'] = str(lock_dir)

        import firebird.driver as fbd

        if lib_path:
            current_val = (fbd.driver_config.fb_client_library.value or '').strip()
            if not current_val:
                try:
                    fbd.driver_config.fb_client_library.value = lib_path
                except Exception:
                    pass
        return fbd


def normalize_column_display_prefs(prefs: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize per-column display preferences (DN-15 / DN-16)."""
    if not isinstance(prefs, Mapping):
        return {}
    out: dict[str, Any] = {}

    # Preserve non-display column keys (pinned, conversionPair, editor, inlineBox, rows, etc.)
    for passthrough in ('pinned', 'conversionPair', 'editor', 'inlineBox'):
        if passthrough in prefs and prefs[passthrough] is not None:
            out[passthrough] = prefs[passthrough]

    if 'rows' in prefs and prefs['rows'] not in (None, ''):
        try:
            out['rows'] = max(1, min(40, int(prefs['rows'])))
        except (TypeError, ValueError):
            pass

    if 'decimals' in prefs and prefs['decimals'] not in (None, ''):
        try:
            out['decimals'] = max(0, min(18, int(prefs['decimals'])))
        except (TypeError, ValueError):
            pass

    font = str(prefs.get('font') or '').strip().lower()
    if font in ALLOWED_FONTS and font:
        out['font'] = font

    font_size = str(prefs.get('fontSize') or '').strip().lower()
    if font_size in ALLOWED_FONT_SIZES and font_size:
        out['fontSize'] = font_size

    for color_key in ('color', 'bgColor'):
        raw_color = str(prefs.get(color_key) or '').strip()
        if raw_color and len(raw_color) <= 64 and _SAFE_COLOR_RE.match(raw_color):
            out[color_key] = raw_color

    h_align = str(prefs.get('hAlign') or '').strip().lower()
    if h_align in ALLOWED_H_ALIGNS and h_align:
        out['hAlign'] = h_align

    v_align = str(prefs.get('vAlign') or '').strip().lower()
    if v_align in ALLOWED_V_ALIGNS and v_align:
        out['vAlign'] = v_align

    wrap_mode = str(prefs.get('wrapMode') or '').strip().lower()
    if wrap_mode in ALLOWED_WRAP_MODES and wrap_mode:
        out['wrapMode'] = wrap_mode

    if prefs.get('maxWrapLines') not in (None, ''):
        try:
            mwl = int(prefs['maxWrapLines'])
            if mwl >= 1:
                out['maxWrapLines'] = max(1, min(50, mwl))
        except (TypeError, ValueError):
            pass

    min_w: int | None = None
    max_w: int | None = None
    if prefs.get('minWidth') not in (None, ''):
        try:
            min_w = max(32, min(1600, int(prefs['minWidth'])))
            out['minWidth'] = min_w
        except (TypeError, ValueError):
            pass

    if prefs.get('maxWidth') not in (None, ''):
        try:
            max_w = max(48, min(3200, int(prefs['maxWidth'])))
            if min_w is not None and max_w < min_w:
                max_w = min_w
            out['maxWidth'] = max_w
        except (TypeError, ValueError):
            pass

    for width_key in ('width', 'widthPx'):
        if prefs.get(width_key) not in (None, ''):
            try:
                w_val = int(prefs[width_key])
                lo = min_w if min_w is not None else 32
                hi = max_w if max_w is not None else 3200
                out[width_key] = max(lo, min(hi, w_val))
            except (TypeError, ValueError):
                pass

    return out


def _normalize_layout_payload(layout: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(layout, Mapping):
        return {}
    normalized = dict(layout)
    for map_key in ('gridColPrefs', 'formFieldPrefs'):
        raw_map = normalized.get(map_key)
        if isinstance(raw_map, Mapping):
            cleaned_map: dict[str, Any] = {}
            for col_name, col_prefs in raw_map.items():
                if isinstance(col_name, str) and col_name and isinstance(col_prefs, Mapping):
                    cleaned = normalize_column_display_prefs(col_prefs)
                    if cleaned:
                        cleaned_map[col_name] = cleaned
            normalized[map_key] = cleaned_map
    return normalized


class UserConfigurationDatabase:
    """Encrypted configuration, metrics, history & display preferences store on Firebird Embedded."""

    DDL_STATEMENTS: tuple[tuple[str, str], ...] = (
        (
            'UCFG_VAULT_HEADER',
            """
            CREATE TABLE UCFG_VAULT_HEADER (
                VAULT_ID VARCHAR(64) NOT NULL PRIMARY KEY,
                SCHEMA_VERSION INTEGER NOT NULL,
                KDF_ALGORITHM VARCHAR(32) NOT NULL,
                KDF_ITERATIONS INTEGER NOT NULL,
                KDF_SALT VARCHAR(128) NOT NULL,
                WRAPPED_DEK BLOB SUB_TYPE TEXT NOT NULL,
                CREATED_AT VARCHAR(40) NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL
            )
            """,
        ),
        (
            'UCFG_USERS',
            """
            CREATE TABLE UCFG_USERS (
                USER_ID INTEGER NOT NULL PRIMARY KEY,
                USERNAME VARCHAR(128) NOT NULL UNIQUE,
                EMAIL VARCHAR(256),
                PASSWORD_ENC BLOB SUB_TYPE TEXT NOT NULL,
                ROLES_ENC BLOB SUB_TYPE TEXT NOT NULL,
                IS_ACTIVE SMALLINT DEFAULT 1 NOT NULL,
                CREATED_AT VARCHAR(40) NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL
            )
            """,
        ),
        (
            'UCFG_CONNECTIONS',
            """
            CREATE TABLE UCFG_CONNECTIONS (
                OWNER_USER_ID INTEGER NOT NULL,
                CONNECTION_KEY VARCHAR(192) NOT NULL,
                ENGINE_ID VARCHAR(64) NOT NULL,
                IS_SHARED SMALLINT DEFAULT 0 NOT NULL,
                PARAMS_ENC BLOB SUB_TYPE TEXT NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL,
                PRIMARY KEY (OWNER_USER_ID, CONNECTION_KEY)
            )
            """,
        ),
        (
            'UCFG_USER_PREFERENCES',
            """
            CREATE TABLE UCFG_USER_PREFERENCES (
                USER_ID INTEGER NOT NULL,
                PREF_DOMAIN VARCHAR(96) NOT NULL,
                PREF_KEY VARCHAR(160) NOT NULL,
                VALUE_ENC BLOB SUB_TYPE TEXT NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL,
                PRIMARY KEY (USER_ID, PREF_DOMAIN, PREF_KEY)
            )
            """,
        ),
        (
            'UCFG_OBJECT_DISPLAY_LAYOUTS',
            """
            CREATE TABLE UCFG_OBJECT_DISPLAY_LAYOUTS (
                USER_ID INTEGER NOT NULL,
                SURFACE_KIND VARCHAR(64) NOT NULL,
                OBJECT_KEY VARCHAR(320) NOT NULL,
                LAYOUT_ENC BLOB SUB_TYPE TEXT NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL,
                PRIMARY KEY (USER_ID, SURFACE_KIND, OBJECT_KEY)
            )
            """,
        ),
        (
            'UCFG_DISPLAY_TEMPLATES',
            """
            CREATE TABLE UCFG_DISPLAY_TEMPLATES (
                TEMPLATE_ID VARCHAR(64) NOT NULL PRIMARY KEY,
                SURFACE_KIND VARCHAR(64) NOT NULL,
                TEMPLATE_NAME VARCHAR(160) NOT NULL,
                AUTHOR_USER_ID INTEGER NOT NULL,
                IS_SHARED SMALLINT DEFAULT 1 NOT NULL,
                DESCRIPTION_ENC BLOB SUB_TYPE TEXT NOT NULL,
                LAYOUT_ENC BLOB SUB_TYPE TEXT NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL
            )
            """,
        ),
        (
            'UCFG_METRICS_HISTORY',
            """
            CREATE TABLE UCFG_METRICS_HISTORY (
                RECORD_ID VARCHAR(96) NOT NULL PRIMARY KEY,
                USER_ID INTEGER NOT NULL,
                RECORD_KIND VARCHAR(48) NOT NULL,
                SERVER_ID INTEGER DEFAULT 0 NOT NULL,
                DATABASE_TARGET_ID VARCHAR(192) DEFAULT '' NOT NULL,
                ENGINE_ID VARCHAR(64) DEFAULT '' NOT NULL,
                SCOPE VARCHAR(32) DEFAULT 'personal' NOT NULL,
                PAYLOAD_ENC BLOB SUB_TYPE TEXT NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL
            )
            """,
        ),
        (
            'UCFG_METRIC_SERIES',
            """
            CREATE TABLE UCFG_METRIC_SERIES (
                SERIES_ID VARCHAR(96) NOT NULL PRIMARY KEY,
                USER_ID INTEGER NOT NULL,
                ENGINE_ID VARCHAR(64) DEFAULT '' NOT NULL,
                SERVER_ID INTEGER DEFAULT 0 NOT NULL,
                DATABASE_TARGET_ID VARCHAR(192) DEFAULT '' NOT NULL,
                OBJECT_KIND VARCHAR(32) DEFAULT 'server' NOT NULL,
                OBJECT_KEY VARCHAR(320) NOT NULL,
                METRIC_KEY VARCHAR(96) NOT NULL,
                METRIC_KIND VARCHAR(24) DEFAULT 'gauge' NOT NULL,
                UNIT VARCHAR(32) DEFAULT 'count' NOT NULL,
                META_ENC BLOB SUB_TYPE TEXT NOT NULL,
                LAST_EPOCH_ID VARCHAR(96) DEFAULT '' NOT NULL,
                UPDATED_AT VARCHAR(40) NOT NULL
            )
            """,
        ),
        (
            'UCFG_METRIC_SAMPLES_RAW',
            """
            CREATE TABLE UCFG_METRIC_SAMPLES_RAW (
                SERIES_ID VARCHAR(96) NOT NULL,
                OBSERVED_AT_MS BIGINT NOT NULL,
                EPOCH_ID VARCHAR(96) DEFAULT '' NOT NULL,
                SAMPLE_ENC BLOB SUB_TYPE TEXT NOT NULL,
                PRIMARY KEY (SERIES_ID, OBSERVED_AT_MS)
            )
            """,
        ),
        (
            'UCFG_METRIC_ROLLUP_5M',
            """
            CREATE TABLE UCFG_METRIC_ROLLUP_5M (
                SERIES_ID VARCHAR(96) NOT NULL,
                BUCKET_START_MS BIGINT NOT NULL,
                ROLLUP_ENC BLOB SUB_TYPE TEXT NOT NULL,
                PRIMARY KEY (SERIES_ID, BUCKET_START_MS)
            )
            """,
        ),
        (
            'UCFG_METRIC_ROLLUP_1H',
            """
            CREATE TABLE UCFG_METRIC_ROLLUP_1H (
                SERIES_ID VARCHAR(96) NOT NULL,
                BUCKET_START_MS BIGINT NOT NULL,
                ROLLUP_ENC BLOB SUB_TYPE TEXT NOT NULL,
                PRIMARY KEY (SERIES_ID, BUCKET_START_MS)
            )
            """,
        ),
    )

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        dsn: str | None = None,
        kdf_iterations: int = DEFAULT_KDF_ITERATIONS,
        auto_test_unlock_key: str | None = None,
    ):
        self._lock = threading.RLock()
        self._kdf_iterations = max(10_000, int(kdf_iterations))
        self._dek: bytearray | None = None

        if dsn:
            self.dsn = str(dsn)
            self.db_path: Path | None = None
            self._lock_dir: Path | None = None
        else:
            if db_path is None:
                env_path = (os.environ.get('CDEADMIN_USER_CONFIG_DB') or '').strip()
                if env_path:
                    resolved = Path(env_path)
                else:
                    try:
                        import config as pg_config
                        cfg_path = getattr(pg_config, 'USER_CONFIGURATION_DATABASE_PATH', None)
                        data_dir = getattr(pg_config, 'DATA_DIR', None)
                    except Exception:
                        cfg_path = None
                        data_dir = None
                    if cfg_path:
                        resolved = Path(cfg_path)
                    else:
                        base = Path(data_dir or os.path.expanduser('~/.cdeadmin'))
                        resolved = base / 'user_configuration.fdb'
            else:
                resolved = Path(db_path)
                if resolved.suffix.lower() in ('.db', '.sqlite', '.sqlite3'):
                    resolved = resolved.with_suffix('.fdb')

            resolved.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = resolved.resolve()
            self.dsn = str(self.db_path)
            self._lock_dir = self.db_path.parent / 'firebird_lock'

        if auto_test_unlock_key:
            self.unlock_with_key_only(auto_test_unlock_key, create_if_missing=True)

    @property
    def engine_name(self) -> str:
        return 'firebird-embedded' if self.db_path is not None else 'firebird-server'

    def is_unlocked(self) -> bool:
        with self._lock:
            return self._dek is not None and len(self._dek) == 32

    def lock(self) -> None:
        """Zeroize the in-memory DEK and lock the configuration database."""
        with self._lock:
            if self._dek is not None:
                for idx in range(len(self._dek)):
                    self._dek[idx] = 0
                self._dek = None

    def derived_session_crypt_key(self) -> str:
        """Return a deterministic 32-char key derived from DEK for runtime credential encryption."""
        with self._lock:
            dek = self._require_dek()
            return hmac.new(
                dek,
                b'scratchrobin.endpoint_credentials.v1',
                hashlib.sha256,
            ).hexdigest()[:32]

    def _require_dek(self) -> bytes:
        if self._dek is None or len(self._dek) != 32:
            if os.environ.get('PGADMIN_TESTING_MODE') == '1':
                self.unlock_with_key_only(
                    'cdeadmin-testing-mode-db-key', create_if_missing=True
                )
            else:
                raise UserConfigLockedError(
                    'UserConfigurationDatabase is locked; sign in with your database key first.'
                )
        return bytes(self._dek)

    def _derive_kek(self, database_key: str, salt: bytes, iterations: int) -> bytes:
        if not isinstance(database_key, str) or not database_key:
            raise UserConfigKeyError('Database key is required.')
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=int(iterations),
        )
        return kdf.derive(database_key.encode('utf-8'))

    def _encrypt_json(self, value: Any, aad_context: str) -> str:
        dek = self._require_dek()
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')
        nonce = os.urandom(12)
        ct = AESGCM(dek).encrypt(nonce, raw, aad_context.encode('utf-8'))
        token = base64.urlsafe_b64encode(nonce + ct).decode('ascii')
        return f'{CIPHERTEXT_PREFIX}{token}'

    def _decrypt_json(self, ciphertext: str, aad_context: str) -> Any:
        dek = self._require_dek()
        text = str(ciphertext or '')
        if not text.startswith(CIPHERTEXT_PREFIX):
            raise UserConfigKeyError('Encrypted configuration payload header is invalid.')
        blob = base64.urlsafe_b64decode(text[len(CIPHERTEXT_PREFIX):].encode('ascii'))
        if len(blob) < 28:
            raise UserConfigKeyError('Encrypted configuration payload is truncated.')
        nonce, ct = blob[:12], blob[12:]
        try:
            raw = AESGCM(dek).decrypt(nonce, ct, aad_context.encode('utf-8'))
        except InvalidTag as exc:
            raise UserConfigKeyError(
                'Unable to decrypt configuration record with active database key.'
            ) from exc
        return json.loads(raw.decode('utf-8'))

    def _open_or_create_connection(self, *, create_if_missing: bool = True):
        fbd = _load_firebird_driver(self._lock_dir)
        if self.db_path is not None and not self.db_path.exists():
            if not create_if_missing:
                raise FileNotFoundError(str(self.db_path))
            saved_umask = os.umask(0o077)
            try:
                con = fbd.create_database(
                    self.dsn,
                    user='SYSDBA',
                    charset='UTF8',
                )
            finally:
                os.umask(saved_umask)
            if os.name != 'nt' and self.db_path.exists():
                try:
                    os.chmod(self.db_path, 0o600)
                except OSError:
                    pass
            self._ensure_schema_on_connection(con)
            return con

        con = fbd.connect(self.dsn, user='SYSDBA', charset='UTF8')
        self._ensure_schema_on_connection(con)
        return con

    def _ensure_schema_on_connection(self, con) -> None:
        cur = con.cursor()
        cur.execute(
            'SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS '
            'WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0'
        )
        existing = {str(r[0]).upper() for r in cur.fetchall()}
        created_any = False
        for table_name, ddl in self.DDL_STATEMENTS:
            if table_name.upper() not in existing:
                cur.execute(ddl)
                con.commit()
                created_any = True
        if created_any:
            for idx_name, idx_sql in (
                (
                    'IDX_UCFG_HIST_LOOKUP',
                    'CREATE INDEX IDX_UCFG_HIST_LOOKUP '
                    'ON UCFG_METRICS_HISTORY (USER_ID, RECORD_KIND)',
                ),
                (
                    'IDX_UCFG_TPL_SURFACE',
                    'CREATE INDEX IDX_UCFG_TPL_SURFACE '
                    'ON UCFG_DISPLAY_TEMPLATES (SURFACE_KIND)',
                ),
                (
                    'IDX_UCFG_SERIES_OBJ',
                    'CREATE INDEX IDX_UCFG_SERIES_OBJ '
                    'ON UCFG_METRIC_SERIES (USER_ID, OBJECT_KIND, OBJECT_KEY)',
                ),
            ):
                cur.execute(
                    'SELECT 1 FROM RDB$INDICES WHERE TRIM(RDB$INDEX_NAME) = ?',
                    (idx_name,),
                )
                if cur.fetchone() is None:
                    cur.execute(idx_sql)
                    con.commit()

    def is_vault_initialized(self) -> bool:
        """Return True if the Firebird database exists and has an encrypted vault header."""
        with self._lock:
            if self.db_path is not None and not self.db_path.exists():
                return False
            try:
                with self._open_or_create_connection(create_if_missing=False) as con:
                    cur = con.cursor()
                    cur.execute(
                        "SELECT 1 FROM UCFG_VAULT_HEADER WHERE VAULT_ID = 'default'"
                    )
                    return cur.fetchone() is not None
            except Exception:
                return False

    def unlock_with_key_only(
        self, database_key: str, *, create_if_missing: bool = False
    ) -> bool:
        """Unlock the DEK using database_key (initializing the vault header only if requested)."""
        if not isinstance(database_key, str) or not database_key.strip():
            raise UserConfigKeyError('Database key is required.')
        with self._lock:
            with self._open_or_create_connection(
                create_if_missing=create_if_missing
            ) as con:
                cur = con.cursor()
                cur.execute(
                    'SELECT KDF_ITERATIONS, KDF_SALT, WRAPPED_DEK '
                    "FROM UCFG_VAULT_HEADER WHERE VAULT_ID = 'default'"
                )
                row = cur.fetchone()
                if row is None:
                    if not create_if_missing:
                        raise UserConfigKeyError(
                            'UserConfigurationDatabase is not initialized yet.'
                        )
                    salt = os.urandom(16)
                    dek = os.urandom(32)
                    kek = self._derive_kek(database_key, salt, self._kdf_iterations)
                    nonce = os.urandom(12)
                    wrapped = AESGCM(kek).encrypt(nonce, dek, VAULT_DEK_AAD)
                    now = _now_iso()
                    cur.execute(
                        """
                        INSERT INTO UCFG_VAULT_HEADER
                            (VAULT_ID, SCHEMA_VERSION, KDF_ALGORITHM, KDF_ITERATIONS,
                             KDF_SALT, WRAPPED_DEK, CREATED_AT, UPDATED_AT)
                        VALUES ('default', ?, 'PBKDF2-HMAC-SHA256', ?, ?, ?, ?, ?)
                        """,
                        (
                            SCHEMA_VERSION,
                            self._kdf_iterations,
                            base64.urlsafe_b64encode(salt).decode('ascii'),
                            base64.urlsafe_b64encode(nonce + wrapped).decode('ascii'),
                            now,
                            now,
                        ),
                    )
                    con.commit()
                    self._dek = bytearray(dek)
                    return True

                iterations = int(row[0])
                salt = base64.urlsafe_b64decode(str(row[1]).encode('ascii'))
                wrapped_blob = base64.urlsafe_b64decode(str(row[2]).encode('ascii'))
                nonce, ct = wrapped_blob[:12], wrapped_blob[12:]
                kek = self._derive_kek(database_key, salt, iterations)
                try:
                    dek = AESGCM(kek).decrypt(nonce, ct, VAULT_DEK_AAD)
                except InvalidTag as exc:
                    raise UserConfigKeyError(
                        'Invalid database key: unable to decrypt UserConfigurationDatabase.'
                    ) from exc
                self._dek = bytearray(dek)
                return False

    def unlock_and_authenticate(
        self,
        username: str,
        password: str,
        database_key: str,
        *,
        legacy_data_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Unlock UserConfigurationDatabase with database_key and authenticate (or bootstrap) user."""
        clean_user = str(username or '').strip()
        if not clean_user:
            raise UserConfigAuthError('User name is required.')
        if not isinstance(password, str) or not password:
            raise UserConfigAuthError('User password is required.')
        if not isinstance(database_key, str) or not database_key:
            raise UserConfigKeyError('Database key is required.')

        with self._lock:
            created_vault = self.unlock_with_key_only(
                database_key, create_if_missing=True
            )
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute('SELECT COUNT(*) FROM UCFG_USERS')
                user_count = int(cur.fetchone()[0] or 0)

                if user_count == 0:
                    user_info = self._insert_user_on_cursor(
                        cur,
                        user_id=1,
                        username=clean_user,
                        password=password,
                        email=clean_user if '@' in clean_user else f'{clean_user}@local.invalid',
                        roles=['Administrator'],
                    )
                    con.commit()
                    self._migrate_legacy_sqlite_stores(
                        default_user_id=user_info['user_id'],
                        data_dir=legacy_data_dir,
                    )
                    user_info['vault_created'] = bool(created_vault or True)
                    return user_info

                cur.execute(
                    """
                    SELECT USER_ID, USERNAME, EMAIL, PASSWORD_ENC, ROLES_ENC, IS_ACTIVE
                    FROM UCFG_USERS
                    WHERE LOWER(USERNAME) = LOWER(?) OR LOWER(COALESCE(EMAIL, '')) = LOWER(?)
                    """,
                    (clean_user, clean_user),
                )
                row = cur.fetchone()
                if row is None:
                    raise UserConfigAuthError('Incorrect user name or password.')

                uid, stored_username, stored_email, pw_enc, roles_enc, is_active = row
                if not int(is_active or 0):
                    raise UserConfigAuthError('User account is inactive.')

                pw_record = self._decrypt_json(str(pw_enc), f'UCFG_USERS:pw:{uid}')
                pw_hash = str(pw_record.get('bcrypt') or '').encode('utf-8')
                if not pw_hash or not bcrypt.checkpw(password.encode('utf-8'), pw_hash):
                    raise UserConfigAuthError('Incorrect user name or password.')

                roles = self._decrypt_json(str(roles_enc), f'UCFG_USERS:roles:{uid}')
                return {
                    'user_id': int(uid),
                    'username': str(stored_username),
                    'email': str(stored_email or ''),
                    'roles': list(roles) if isinstance(roles, list) else ['Administrator'],
                    'vault_created': False,
                }

    def _insert_user_on_cursor(
        self,
        cur,
        *,
        user_id: int | None,
        username: str,
        password: str,
        email: str | None = None,
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        if user_id is None:
            cur.execute('SELECT COALESCE(MAX(USER_ID), 0) + 1 FROM UCFG_USERS')
            uid = int(cur.fetchone()[0] or 1)
        else:
            uid = int(user_id)
        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        pw_enc = self._encrypt_json({'bcrypt': pw_hash}, f'UCFG_USERS:pw:{uid}')
        role_list = list(roles or ['Administrator'])
        roles_enc = self._encrypt_json(role_list, f'UCFG_USERS:roles:{uid}')
        resolved_email = str(
            email or (username if '@' in username else f'{username}@local.invalid')
        )
        now = _now_iso()
        cur.execute(
            """
            UPDATE OR INSERT INTO UCFG_USERS
                (USER_ID, USERNAME, EMAIL, PASSWORD_ENC, ROLES_ENC, IS_ACTIVE, CREATED_AT, UPDATED_AT)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            MATCHING (USER_ID)
            """,
            (uid, username, resolved_email, pw_enc, roles_enc, now, now),
        )
        return {
            'user_id': uid,
            'username': username,
            'email': resolved_email,
            'roles': role_list,
        }

    def create_or_update_user(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        roles: list[str] | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Provision or update a user in the multi-user UserConfigurationDatabase."""
        clean_user = str(username or '').strip()
        if not clean_user or not password:
            raise UserConfigAuthError('User name and password are required.')
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                if user_id is None:
                    cur.execute(
                        'SELECT USER_ID FROM UCFG_USERS WHERE LOWER(USERNAME) = LOWER(?)',
                        (clean_user,),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        user_id = int(existing[0])
                info = self._insert_user_on_cursor(
                    cur,
                    user_id=user_id,
                    username=clean_user,
                    password=password,
                    email=email,
                    roles=roles,
                )
                con.commit()
                return info

    # ------------------------------------------------------------------
    # Per-Object Display Layouts & Shareable Templates
    # ------------------------------------------------------------------

    def get_specific_layout(
        self, user_id: int, surface_kind: str, object_key: str
    ) -> dict[str, Any] | None:
        uid = int(user_id)
        sk = str(surface_kind)
        ok = str(object_key)
        aad = f'UCFG_OBJECT_DISPLAY_LAYOUTS:{uid}:{sk}:{ok}'
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'SELECT LAYOUT_ENC FROM UCFG_OBJECT_DISPLAY_LAYOUTS '
                    'WHERE USER_ID = ? AND SURFACE_KIND = ? AND OBJECT_KEY = ?',
                    (uid, sk, ok),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._decrypt_json(str(row[0]), aad)

    def save_specific_layout(
        self,
        user_id: int,
        surface_kind: str,
        object_key: str,
        layout: Mapping[str, Any],
    ) -> dict[str, Any]:
        uid = int(user_id)
        sk = str(surface_kind)
        ok = str(object_key)[:320]
        normalized = _normalize_layout_payload(layout)
        aad = f'UCFG_OBJECT_DISPLAY_LAYOUTS:{uid}:{sk}:{ok}'
        now = _now_iso()
        with self._lock:
            enc = self._encrypt_json(normalized, aad)
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    """
                    UPDATE OR INSERT INTO UCFG_OBJECT_DISPLAY_LAYOUTS
                        (USER_ID, SURFACE_KIND, OBJECT_KEY, LAYOUT_ENC, UPDATED_AT)
                    VALUES (?, ?, ?, ?, ?)
                    MATCHING (USER_ID, SURFACE_KIND, OBJECT_KEY)
                    """,
                    (uid, sk, ok, enc, now),
                )
                con.commit()
        return {'saved': 'specific', 'object_key': ok, 'updated_at': now}

    def save_template(
        self,
        user_id: int,
        surface_kind: str,
        name: str,
        layout: Mapping[str, Any],
        description: str = '',
        template_id: str | None = None,
        is_shared: bool = True,
    ) -> dict[str, Any]:
        tid = str(template_id or uuid.uuid4())[:64]
        sk = str(surface_kind)[:64]
        clean_name = str(name or 'Untitled Template').strip()[:160]
        clean_desc = str(description or '')[:512]
        normalized = _normalize_layout_payload(layout)
        now = _now_iso()
        with self._lock:
            desc_enc = self._encrypt_json(
                {'description': clean_desc}, f'UCFG_DISPLAY_TEMPLATES:desc:{tid}'
            )
            layout_enc = self._encrypt_json(
                normalized, f'UCFG_DISPLAY_TEMPLATES:layout:{tid}'
            )
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    """
                    UPDATE OR INSERT INTO UCFG_DISPLAY_TEMPLATES
                        (TEMPLATE_ID, SURFACE_KIND, TEMPLATE_NAME, AUTHOR_USER_ID,
                         IS_SHARED, DESCRIPTION_ENC, LAYOUT_ENC, UPDATED_AT)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    MATCHING (TEMPLATE_ID)
                    """,
                    (
                        tid,
                        sk,
                        clean_name,
                        int(user_id),
                        1 if is_shared else 0,
                        desc_enc,
                        layout_enc,
                        now,
                    ),
                )
                con.commit()
        return {
            'saved': 'template',
            'template_id': tid,
            'name': clean_name,
            'updated_at': now,
        }

    def list_templates(
        self, surface_kind: str, *, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        sk = str(surface_kind)
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                if user_id is None:
                    cur.execute(
                        'SELECT TEMPLATE_ID, TEMPLATE_NAME, AUTHOR_USER_ID, IS_SHARED, '
                        'DESCRIPTION_ENC, LAYOUT_ENC, UPDATED_AT '
                        'FROM UCFG_DISPLAY_TEMPLATES '
                        'WHERE SURFACE_KIND = ? '
                        'ORDER BY UPPER(TEMPLATE_NAME) ASC',
                        (sk,),
                    )
                else:
                    cur.execute(
                        'SELECT TEMPLATE_ID, TEMPLATE_NAME, AUTHOR_USER_ID, IS_SHARED, '
                        'DESCRIPTION_ENC, LAYOUT_ENC, UPDATED_AT '
                        'FROM UCFG_DISPLAY_TEMPLATES '
                        'WHERE SURFACE_KIND = ? AND (IS_SHARED = 1 OR AUTHOR_USER_ID = ?) '
                        'ORDER BY UPPER(TEMPLATE_NAME) ASC',
                        (sk, int(user_id)),
                    )
                rows = cur.fetchall()

            out: list[dict[str, Any]] = []
            for r in rows:
                tid, tname, author_id, is_shared, desc_enc, layout_enc, updated_at = r
                try:
                    desc_obj = self._decrypt_json(
                        str(desc_enc), f'UCFG_DISPLAY_TEMPLATES:desc:{tid}'
                    )
                    parsed_layout = self._decrypt_json(
                        str(layout_enc), f'UCFG_DISPLAY_TEMPLATES:layout:{tid}'
                    )
                except Exception:
                    desc_obj = {'description': ''}
                    parsed_layout = {}
                out.append({
                    'template_id': str(tid),
                    'name': str(tname),
                    'description': str(desc_obj.get('description') or ''),
                    'author_user_id': int(author_id),
                    'is_shared': bool(is_shared),
                    'layout': parsed_layout,
                    'updated_at': str(updated_at),
                })
            return out

    def delete_template(self, user_id: int, template_id: str) -> dict[str, Any]:
        tid = str(template_id)[:64]
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'DELETE FROM UCFG_DISPLAY_TEMPLATES '
                    'WHERE TEMPLATE_ID = ? AND (AUTHOR_USER_ID = ? OR IS_SHARED = 1)',
                    (tid, int(user_id)),
                )
                con.commit()
        return {'deleted': tid}

    # ------------------------------------------------------------------
    # User Preferences & Shared Field-Type Defaults
    # ------------------------------------------------------------------

    def save_user_preference(
        self, user_id: int, pref_domain: str, pref_key: str, value: Any
    ) -> dict[str, Any]:
        uid = int(user_id)
        dom = str(pref_domain)[:96]
        key = str(pref_key)[:160]
        aad = f'UCFG_USER_PREFERENCES:{uid}:{dom}:{key}'
        now = _now_iso()
        with self._lock:
            enc = self._encrypt_json({'value': value}, aad)
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    """
                    UPDATE OR INSERT INTO UCFG_USER_PREFERENCES
                        (USER_ID, PREF_DOMAIN, PREF_KEY, VALUE_ENC, UPDATED_AT)
                    VALUES (?, ?, ?, ?, ?)
                    MATCHING (USER_ID, PREF_DOMAIN, PREF_KEY)
                    """,
                    (uid, dom, key, enc, now),
                )
                con.commit()
        return {'user_id': uid, 'domain': dom, 'key': key, 'updated_at': now}

    def get_user_preference(
        self, user_id: int, pref_domain: str, pref_key: str, default: Any = None
    ) -> Any:
        uid = int(user_id)
        dom = str(pref_domain)[:96]
        key = str(pref_key)[:160]
        aad = f'UCFG_USER_PREFERENCES:{uid}:{dom}:{key}'
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'SELECT VALUE_ENC FROM UCFG_USER_PREFERENCES '
                    'WHERE USER_ID = ? AND PREF_DOMAIN = ? AND PREF_KEY = ?',
                    (uid, dom, key),
                )
                row = cur.fetchone()
                if row is None:
                    return default
                decoded = self._decrypt_json(str(row[0]), aad)
                return decoded.get('value', default) if isinstance(decoded, dict) else default

    def list_user_preferences(
        self, user_id: int, pref_domain: str | None = None
    ) -> dict[str, dict[str, Any]]:
        uid = int(user_id)
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                if pref_domain is None:
                    cur.execute(
                        'SELECT PREF_DOMAIN, PREF_KEY, VALUE_ENC '
                        'FROM UCFG_USER_PREFERENCES WHERE USER_ID = ?',
                        (uid,),
                    )
                else:
                    cur.execute(
                        'SELECT PREF_DOMAIN, PREF_KEY, VALUE_ENC '
                        'FROM UCFG_USER_PREFERENCES WHERE USER_ID = ? AND PREF_DOMAIN = ?',
                        (uid, str(pref_domain)[:96]),
                    )
                rows = cur.fetchall()
            out: dict[str, dict[str, Any]] = {}
            for dom, key, val_enc in rows:
                aad = f'UCFG_USER_PREFERENCES:{uid}:{dom}:{key}'
                try:
                    decoded = self._decrypt_json(str(val_enc), aad)
                    out.setdefault(str(dom), {})[str(key)] = decoded.get('value')
                except Exception:
                    continue
            return out

    def get_field_type_defaults(self, user_id: int) -> dict[str, Any]:
        stored = self.get_user_preference(
            user_id, 'shared-field-format', 'defaults', default=None
        )
        if isinstance(stored, dict):
            return stored
        legacy = self.get_specific_layout(user_id, 'shared-field-format', 'defaults')
        return legacy if isinstance(legacy, dict) else {}

    def save_field_type_defaults(
        self, user_id: int, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(defaults, Mapping) or len(defaults) > 64:
            raise ValueError('Field type defaults must be a mapping.')
        allowed_keys = {
            'font',
            'fontSize',
            'color',
            'bgColor',
            'hAlign',
            'vAlign',
            'wrapMode',
            'maxWrapLines',
            'minWidth',
            'maxWidth',
        }
        cleaned: dict[str, dict[str, Any]] = {}
        for field_type, preferences in defaults.items():
            if not isinstance(field_type, str) or len(field_type) > 64:
                raise ValueError('Invalid field type.')
            if not isinstance(preferences, Mapping) or (set(preferences) - allowed_keys):
                raise ValueError('Invalid field formatting preferences.')
            if preferences.get('font', '') not in ALLOWED_FONTS:
                raise ValueError('Invalid font preference.')
            if preferences.get('hAlign', '') not in ALLOWED_H_ALIGNS:
                raise ValueError('Invalid alignment preference.')
            cleaned[field_type] = normalize_column_display_prefs(preferences)
        self.save_user_preference(user_id, 'shared-field-format', 'defaults', cleaned)
        return {'field_type_defaults': cleaned}

    # ------------------------------------------------------------------
    # Engine / Server / Database Connection Parameters
    # ------------------------------------------------------------------

    def save_connection_parameters(
        self,
        owner_user_id: int,
        connection_key: str,
        engine_id: str,
        params: Mapping[str, Any],
        *,
        is_shared: bool = False,
    ) -> dict[str, Any]:
        uid = int(owner_user_id)
        ckey = str(connection_key)[:192]
        eng = str(engine_id or 'generic')[:64]
        aad = f'UCFG_CONNECTIONS:{uid}:{ckey}'
        now = _now_iso()
        with self._lock:
            enc = self._encrypt_json(dict(params), aad)
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    """
                    UPDATE OR INSERT INTO UCFG_CONNECTIONS
                        (OWNER_USER_ID, CONNECTION_KEY, ENGINE_ID, IS_SHARED, PARAMS_ENC, UPDATED_AT)
                    VALUES (?, ?, ?, ?, ?, ?)
                    MATCHING (OWNER_USER_ID, CONNECTION_KEY)
                    """,
                    (uid, ckey, eng, 1 if is_shared else 0, enc, now),
                )
                con.commit()
        return {'connection_key': ckey, 'engine_id': eng, 'updated_at': now}

    def list_connection_parameters(self, user_id: int) -> list[dict[str, Any]]:
        uid = int(user_id)
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'SELECT OWNER_USER_ID, CONNECTION_KEY, ENGINE_ID, IS_SHARED, PARAMS_ENC, UPDATED_AT '
                    'FROM UCFG_CONNECTIONS '
                    'WHERE OWNER_USER_ID = ? OR IS_SHARED = 1 '
                    'ORDER BY CONNECTION_KEY ASC',
                    (uid,),
                )
                rows = cur.fetchall()
            out: list[dict[str, Any]] = []
            for owner_id, ckey, eng, is_shared, params_enc, updated_at in rows:
                aad = f'UCFG_CONNECTIONS:{owner_id}:{ckey}'
                try:
                    params = self._decrypt_json(str(params_enc), aad)
                except Exception:
                    continue
                out.append({
                    'owner_user_id': int(owner_id),
                    'connection_key': str(ckey),
                    'engine_id': str(eng),
                    'is_shared': bool(is_shared),
                    'parameters': params,
                    'updated_at': str(updated_at),
                })
            return out

    def delete_connection_parameters(
        self, owner_user_id: int, connection_key: str
    ) -> dict[str, Any]:
        uid = int(owner_user_id)
        ckey = str(connection_key)[:192]
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'DELETE FROM UCFG_CONNECTIONS WHERE OWNER_USER_ID = ? AND CONNECTION_KEY = ?',
                    (uid, ckey),
                )
                con.commit()
        return {'deleted': ckey}

    # ------------------------------------------------------------------
    # Metrics, Query Execution History, Snippets & Quick Queries
    # ------------------------------------------------------------------

    def save_metrics_history_record(
        self,
        *,
        record_id: str,
        user_id: int,
        record_kind: str,
        payload: Mapping[str, Any],
        server_id: int = 0,
        database_target_id: str = '',
        engine_id: str = '',
        scope: str = 'personal',
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        rid = str(record_id)[:96]
        uid = int(user_id)
        rkind = str(record_kind)[:48]
        srv_id = int(server_id or 0)
        db_target = str(database_target_id or '')[:192]
        eng = str(engine_id or '')[:64]
        scp = str(scope or 'personal')[:32]
        now = str(updated_at or _now_iso())
        aad = f'UCFG_METRICS_HISTORY:{rid}'
        with self._lock:
            enc = self._encrypt_json(dict(payload), aad)
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    """
                    UPDATE OR INSERT INTO UCFG_METRICS_HISTORY
                        (RECORD_ID, USER_ID, RECORD_KIND, SERVER_ID, DATABASE_TARGET_ID,
                         ENGINE_ID, SCOPE, PAYLOAD_ENC, UPDATED_AT)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    MATCHING (RECORD_ID)
                    """,
                    (rid, uid, rkind, srv_id, db_target, eng, scp, enc, now),
                )
                con.commit()
        return {'record_id': rid, 'record_kind': rkind, 'updated_at': now}

    def get_metrics_history_record(self, record_id: str) -> dict[str, Any] | None:
        rid = str(record_id)[:96]
        aad = f'UCFG_METRICS_HISTORY:{rid}'
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'SELECT RECORD_ID, USER_ID, RECORD_KIND, SERVER_ID, DATABASE_TARGET_ID, '
                    'ENGINE_ID, SCOPE, PAYLOAD_ENC, UPDATED_AT '
                    'FROM UCFG_METRICS_HISTORY WHERE RECORD_ID = ?',
                    (rid,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                payload = self._decrypt_json(str(row[7]), aad)
                return {
                    'record_id': str(row[0]),
                    'user_id': int(row[1]),
                    'record_kind': str(row[2]),
                    'server_id': int(row[3]),
                    'database_target_id': str(row[4]),
                    'engine_id': str(row[5]),
                    'scope': str(row[6]),
                    'payload': payload,
                    'updated_at': str(row[8]),
                }

    def list_metrics_history_records(
        self,
        record_kind: str,
        *,
        user_id: int | None = None,
        include_shared_scopes: tuple[str, ...] = (),
        server_id: int | None = None,
        database_target_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rkind = str(record_kind)[:48]
        max_rows = max(1, min(5000, int(limit)))
        clauses = ['RECORD_KIND = ?']
        params: list[Any] = [rkind]

        if user_id is not None:
            if include_shared_scopes:
                placeholders = ', '.join('?' for _ in include_shared_scopes)
                clauses.append(f'(USER_ID = ? OR SCOPE IN ({placeholders}))')
                params.append(int(user_id))
                params.extend(str(s) for s in include_shared_scopes)
            else:
                clauses.append('USER_ID = ?')
                params.append(int(user_id))

        if server_id is not None and int(server_id) > 0:
            clauses.append('(SERVER_ID = ? OR SERVER_ID = 0)')
            params.append(int(server_id))

        if database_target_id:
            clauses.append("(DATABASE_TARGET_ID = ? OR DATABASE_TARGET_ID = '')")
            params.append(str(database_target_id)[:192])

        where_sql = ' AND '.join(clauses)
        sql = (
            f'SELECT FIRST {max_rows} RECORD_ID, USER_ID, RECORD_KIND, SERVER_ID, '
            'DATABASE_TARGET_ID, ENGINE_ID, SCOPE, PAYLOAD_ENC, UPDATED_AT '
            f'FROM UCFG_METRICS_HISTORY WHERE {where_sql} '
            'ORDER BY UPDATED_AT DESC'
        )
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

            out: list[dict[str, Any]] = []
            for r in rows:
                rid = str(r[0])
                try:
                    payload = self._decrypt_json(str(r[7]), f'UCFG_METRICS_HISTORY:{rid}')
                except Exception:
                    continue
                out.append({
                    'record_id': rid,
                    'user_id': int(r[1]),
                    'record_kind': str(r[2]),
                    'server_id': int(r[3]),
                    'database_target_id': str(r[4]),
                    'engine_id': str(r[5]),
                    'scope': str(r[6]),
                    'payload': payload,
                    'updated_at': str(r[8]),
                })
            return out

    def delete_metrics_history_record(
        self, record_id: str, *, forbid_builtin: bool = False
    ) -> dict[str, Any]:
        rid = str(record_id)[:96]
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                if forbid_builtin:
                    cur.execute(
                        "DELETE FROM UCFG_METRICS_HISTORY WHERE RECORD_ID = ? AND SCOPE <> 'builtin'",
                        (rid,),
                    )
                else:
                    cur.execute(
                        'DELETE FROM UCFG_METRICS_HISTORY WHERE RECORD_ID = ?',
                        (rid,),
                    )
                con.commit()
        return {'deleted': rid}

    # ------------------------------------------------------------------
    # Historic Time-Series Metrics, Deep-Scan Cache & View Customization
    # ------------------------------------------------------------------

    DEFAULT_METRICS_RETENTION: dict[str, int] = {
        'raw_hours': 24,
        'rollup_5m_days': 30,
        'rollup_1h_days': 365,
    }

    def get_metrics_retention_policy(self, user_id: int) -> dict[str, int]:
        raw = self.get_user_preference(
            int(user_id), 'dashboard', 'metrics_retention', default={}
        )
        src = raw if isinstance(raw, Mapping) else {}
        return {
            'raw_hours': max(
                1, min(720, int(src.get('raw_hours') or self.DEFAULT_METRICS_RETENTION['raw_hours']))
            ),
            'rollup_5m_days': max(
                1, min(365, int(src.get('rollup_5m_days') or self.DEFAULT_METRICS_RETENTION['rollup_5m_days']))
            ),
            'rollup_1h_days': max(
                1, min(3650, int(src.get('rollup_1h_days') or self.DEFAULT_METRICS_RETENTION['rollup_1h_days']))
            ),
        }

    def set_metrics_retention_policy(
        self, user_id: int, policy: Mapping[str, Any]
    ) -> dict[str, int]:
        uid = int(user_id)
        current = self.get_metrics_retention_policy(uid)
        merged = {
            'raw_hours': max(
                1, min(720, int(policy.get('raw_hours') or current['raw_hours']))
            ),
            'rollup_5m_days': max(
                1, min(365, int(policy.get('rollup_5m_days') or current['rollup_5m_days']))
            ),
            'rollup_1h_days': max(
                1, min(3650, int(policy.get('rollup_1h_days') or current['rollup_1h_days']))
            ),
        }
        self.save_user_preference(uid, 'dashboard', 'metrics_retention', merged)
        return merged

    @staticmethod
    def _metric_series_id(
        user_id: int,
        engine_id: str,
        server_id: int,
        database_target_id: str,
        object_kind: str,
        object_key: str,
        metric_key: str,
    ) -> str:
        raw = (
            f'{int(user_id)}|{str(engine_id or "")}|{int(server_id or 0)}|'
            f'{str(database_target_id or "")}|{str(object_kind or "server")}|'
            f'{str(object_key or "")}|{str(metric_key or "")}'
        )
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:64]

    def record_object_metric_observations(
        self,
        *,
        user_id: int,
        engine_id: str,
        server_id: int = 0,
        database_target_id: str = '',
        object_kind: str = 'server',
        object_key: str,
        observations: Sequence[Mapping[str, Any]],
        observed_at_ms: int | None = None,
        epoch_id: str = '',
    ) -> dict[str, Any]:
        """Record encrypted raw metric samples and maintain 5m and 1h rollups."""
        if not observations:
            return {'recorded_count': 0, 'series_ids': []}

        uid = int(user_id)
        eng = str(engine_id or '')[:64]
        srv_id = int(server_id or 0)
        db_target = str(database_target_id or '')[:192]
        obj_kind = str(object_kind or 'server')[:32]
        obj_key = str(object_key or '')[:320]
        ts_ms = int(observed_at_ms if observed_at_ms is not None else round(time.time() * 1000))
        ep_id = str(epoch_id or '')[:96]
        now_iso = _now_iso()

        retention = self.get_metrics_retention_policy(uid)
        raw_cutoff_ms = ts_ms - retention['raw_hours'] * 3_600_000
        r5m_cutoff_ms = ts_ms - retention['rollup_5m_days'] * 86_400_000
        r1h_cutoff_ms = ts_ms - retention['rollup_1h_days'] * 86_400_000

        bucket_5m = (ts_ms // 300_000) * 300_000
        bucket_1h = (ts_ms // 3_600_000) * 3_600_000

        recorded_ids: list[str] = []
        computed_rates: dict[str, float] = {}

        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                for obs in observations:
                    if not isinstance(obs, Mapping):
                        continue
                    mkey = str(obs.get('metric_key') or '').strip()[:96]
                    if not mkey:
                        continue
                    mkind = str(obs.get('kind') or 'gauge').strip()[:24]
                    if mkind not in ('gauge', 'counter_rate'):
                        mkind = 'gauge'
                    unit = str(obs.get('unit') or 'count').strip()[:32]
                    label = str(obs.get('label') or mkey)[:160]
                    group = str(obs.get('group') or 'general')[:64]

                    sid = self._metric_series_id(
                        uid, eng, srv_id, db_target, obj_kind, obj_key, mkey
                    )
                    series_aad = f'UCFG_METRIC_SERIES:{sid}'

                    cur.execute(
                        'SELECT META_ENC, LAST_EPOCH_ID FROM UCFG_METRIC_SERIES WHERE SERIES_ID = ?',
                        (sid,),
                    )
                    existing_row = cur.fetchone()
                    prev_meta: dict[str, Any] = {}
                    prev_epoch = ''
                    if existing_row is not None:
                        prev_epoch = str(existing_row[1] or '')
                        try:
                            dec = self._decrypt_json(str(existing_row[0]), series_aad)
                            if isinstance(dec, dict):
                                prev_meta = dec
                        except Exception:
                            prev_meta = {}

                    raw_val = obs.get('value')
                    raw_counter = obs.get('raw_counter')
                    effective_val: float | None = None

                    if mkind == 'counter_rate' and raw_counter is not None:
                        try:
                            c_num = float(raw_counter)
                        except (TypeError, ValueError):
                            continue
                        if not math.isfinite(c_num):
                            continue
                        prev_c = prev_meta.get('last_counter')
                        prev_c_ts = prev_meta.get('last_counter_ts_ms')
                        same_epoch = (prev_epoch == ep_id) or (not prev_epoch and not ep_id)
                        if (
                            same_epoch
                            and isinstance(prev_c, (int, float))
                            and isinstance(prev_c_ts, (int, float))
                            and ts_ms > int(prev_c_ts)
                            and c_num >= float(prev_c)
                        ):
                            dt_sec = (ts_ms - int(prev_c_ts)) / 1000.0
                            if dt_sec > 0:
                                effective_val = (c_num - float(prev_c)) / dt_sec
                                computed_rates[mkey] = effective_val
                        elif raw_val is not None:
                            try:
                                fallback_f = float(raw_val)
                                if math.isfinite(fallback_f):
                                    effective_val = fallback_f
                                    computed_rates[mkey] = effective_val
                            except (TypeError, ValueError):
                                pass

                        next_meta = {
                            **prev_meta,
                            'label': label,
                            'group': group,
                            'object_label': str(obs.get('object_label') or obj_key)[:192],
                            'last_counter': c_num,
                            'last_counter_ts_ms': ts_ms,
                        }
                    else:
                        if raw_val is None or isinstance(raw_val, bool):
                            continue
                        try:
                            f_val = float(raw_val)
                        except (TypeError, ValueError):
                            continue
                        if not math.isfinite(f_val):
                            continue
                        effective_val = f_val
                        next_meta = {
                            **prev_meta,
                            'label': label,
                            'group': group,
                            'object_label': str(obs.get('object_label') or obj_key)[:192],
                        }

                    if effective_val is not None:
                        next_meta['latest_value'] = effective_val
                        next_meta['latest_ts_ms'] = ts_ms

                    meta_enc = self._encrypt_json(next_meta, series_aad)
                    cur.execute(
                        """
                        UPDATE OR INSERT INTO UCFG_METRIC_SERIES
                            (SERIES_ID, USER_ID, ENGINE_ID, SERVER_ID, DATABASE_TARGET_ID,
                             OBJECT_KIND, OBJECT_KEY, METRIC_KEY, METRIC_KIND, UNIT,
                             META_ENC, LAST_EPOCH_ID, UPDATED_AT)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        MATCHING (SERIES_ID)
                        """,
                        (
                            sid, uid, eng, srv_id, db_target,
                            obj_kind, obj_key, mkey, mkind, unit,
                            meta_enc, ep_id, now_iso,
                        ),
                    )

                    if effective_val is None:
                        continue

                    sample_aad = f'UCFG_METRIC_SAMPLES_RAW:{sid}:{ts_ms}'
                    sample_payload: dict[str, Any] = {'v': effective_val}
                    if raw_counter is not None:
                        try:
                            sample_payload['c'] = float(raw_counter)
                        except (TypeError, ValueError):
                            pass
                    sample_enc = self._encrypt_json(sample_payload, sample_aad)
                    cur.execute(
                        """
                        UPDATE OR INSERT INTO UCFG_METRIC_SAMPLES_RAW
                            (SERIES_ID, OBSERVED_AT_MS, EPOCH_ID, SAMPLE_ENC)
                        VALUES (?, ?, ?, ?)
                        MATCHING (SERIES_ID, OBSERVED_AT_MS)
                        """,
                        (sid, ts_ms, ep_id, sample_enc),
                    )

                    self._upsert_metric_rollup_bucket(
                        cur, 'UCFG_METRIC_ROLLUP_5M', sid, bucket_5m, effective_val, ts_ms
                    )
                    self._upsert_metric_rollup_bucket(
                        cur, 'UCFG_METRIC_ROLLUP_1H', sid, bucket_1h, effective_val, ts_ms
                    )

                    cur.execute(
                        'DELETE FROM UCFG_METRIC_SAMPLES_RAW '
                        'WHERE SERIES_ID = ? AND OBSERVED_AT_MS < ?',
                        (sid, raw_cutoff_ms),
                    )
                    cur.execute(
                        'DELETE FROM UCFG_METRIC_ROLLUP_5M '
                        'WHERE SERIES_ID = ? AND BUCKET_START_MS < ?',
                        (sid, r5m_cutoff_ms),
                    )
                    cur.execute(
                        'DELETE FROM UCFG_METRIC_ROLLUP_1H '
                        'WHERE SERIES_ID = ? AND BUCKET_START_MS < ?',
                        (sid, r1h_cutoff_ms),
                    )
                    recorded_ids.append(sid)

                con.commit()

        return {
            'recorded_count': len(recorded_ids),
            'series_ids': recorded_ids,
            'observed_at_ms': ts_ms,
            'computed_rates': computed_rates,
        }

    def _upsert_metric_rollup_bucket(
        self,
        cur,
        table_name: str,
        series_id: str,
        bucket_start_ms: int,
        val: float,
        ts_ms: int,
    ) -> None:
        aad = f'{table_name}:{series_id}:{bucket_start_ms}'
        cur.execute(
            f'SELECT ROLLUP_ENC FROM {table_name} '
            'WHERE SERIES_ID = ? AND BUCKET_START_MS = ?',
            (series_id, bucket_start_ms),
        )
        row = cur.fetchone()
        agg: dict[str, Any] | None = None
        if row is not None:
            try:
                dec = self._decrypt_json(str(row[0]), aad)
                if isinstance(dec, dict):
                    agg = dec
            except Exception:
                agg = None

        if agg is None:
            next_agg = {
                'min': val,
                'max': val,
                'sum': val,
                'count': 1,
                'last': val,
                'last_ts': ts_ms,
            }
        else:
            prev_count = max(0, int(agg.get('count') or 0))
            prev_last_ts = int(agg.get('last_ts') or 0)
            next_agg = {
                'min': min(float(agg.get('min', val)), val),
                'max': max(float(agg.get('max', val)), val),
                'sum': float(agg.get('sum', 0.0)) + val,
                'count': prev_count + 1,
                'last': val if ts_ms >= prev_last_ts else float(agg.get('last', val)),
                'last_ts': max(prev_last_ts, ts_ms),
            }

        enc = self._encrypt_json(next_agg, aad)
        cur.execute(
            f"""
            UPDATE OR INSERT INTO {table_name}
                (SERIES_ID, BUCKET_START_MS, ROLLUP_ENC)
            VALUES (?, ?, ?)
            MATCHING (SERIES_ID, BUCKET_START_MS)
            """,
            (series_id, bucket_start_ms, enc),
        )

    def query_object_metric_history(
        self,
        *,
        user_id: int,
        object_kind: str,
        object_key: str,
        window: str = '1h',
        server_id: int | None = None,
        database_target_id: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Query encrypted time-series points from RAW, 5M, or 1H tables."""
        uid = int(user_id)
        obj_kind = str(object_kind or 'server')[:32]
        obj_key = str(object_key or '')[:320]
        win = str(window or '1h').strip().lower()
        end_ms = int(now_ms if now_ms is not None else round(time.time() * 1000))

        window_specs = {
            'live': ('raw', 900_000),
            '15m': ('raw', 900_000),
            '1h': ('raw', 3_600_000),
            '24h': ('raw', 86_400_000),
            '7d': ('5m', 7 * 86_400_000),
            '30d': ('5m', 30 * 86_400_000),
            '90d': ('1h', 90 * 86_400_000),
            '365d': ('1h', 365 * 86_400_000),
        }
        resolution, span_ms = window_specs.get(win, ('raw', 3_600_000))
        start_ms = end_ms - span_ms
        retention = self.get_metrics_retention_policy(uid)

        clauses = ['USER_ID = ?', 'OBJECT_KIND = ?', 'OBJECT_KEY = ?']
        params: list[Any] = [uid, obj_kind, obj_key]
        if server_id is not None and int(server_id) > 0:
            clauses.append('SERVER_ID = ?')
            params.append(int(server_id))
        if database_target_id is not None and str(database_target_id):
            clauses.append('DATABASE_TARGET_ID = ?')
            params.append(str(database_target_id)[:192])

        where_sql = ' AND '.join(clauses)
        out_series: list[dict[str, Any]] = []

        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    'SELECT SERIES_ID, ENGINE_ID, METRIC_KEY, METRIC_KIND, UNIT, META_ENC, UPDATED_AT '
                    f'FROM UCFG_METRIC_SERIES WHERE {where_sql} '
                    'ORDER BY METRIC_KEY ASC',
                    tuple(params),
                )
                series_rows = cur.fetchall()

                for srow in series_rows:
                    sid = str(srow[0])
                    eng = str(srow[1] or '')
                    mkey = str(srow[2] or '')
                    mkind = str(srow[3] or 'gauge')
                    unit = str(srow[4] or 'count')
                    updated_at = str(srow[6] or '')
                    meta: dict[str, Any] = {}
                    try:
                        dec_meta = self._decrypt_json(
                            str(srow[5]), f'UCFG_METRIC_SERIES:{sid}'
                        )
                        if isinstance(dec_meta, dict):
                            meta = dec_meta
                    except Exception:
                        meta = {}

                    points = self._fetch_series_points(
                        cur, sid, resolution, start_ms, end_ms
                    )
                    if not points and resolution == 'raw' and win == '24h':
                        points = self._fetch_series_points(
                            cur, sid, '5m', start_ms, end_ms
                        )

                    vals = [float(p['value']) for p in points]
                    latest_val = (
                        vals[-1]
                        if vals
                        else (
                            float(meta['latest_value'])
                            if isinstance(meta.get('latest_value'), (int, float))
                            else None
                        )
                    )
                    out_series.append({
                        'series_id': sid,
                        'engine_id': eng,
                        'metric_key': mkey,
                        'label': str(meta.get('label') or mkey),
                        'group': str(meta.get('group') or 'general'),
                        'kind': mkind,
                        'unit': unit,
                        'resolution': resolution,
                        'latest_value': latest_val,
                        'min_value': min(vals) if vals else latest_val,
                        'max_value': max(vals) if vals else latest_val,
                        'avg_value': (sum(vals) / len(vals)) if vals else latest_val,
                        'sample_count': len(points),
                        'updated_at': updated_at,
                        'points': points,
                    })

        return {
            'window': win if win in window_specs else '1h',
            'resolution': resolution,
            'from_ms': start_ms,
            'to_ms': end_ms,
            'retention_policy': retention,
            'series': out_series,
        }

    def _fetch_series_points(
        self,
        cur,
        series_id: str,
        resolution: str,
        start_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        if resolution == 'raw':
            cur.execute(
                'SELECT FIRST 2500 OBSERVED_AT_MS, SAMPLE_ENC '
                'FROM UCFG_METRIC_SAMPLES_RAW '
                'WHERE SERIES_ID = ? AND OBSERVED_AT_MS >= ? AND OBSERVED_AT_MS <= ? '
                'ORDER BY OBSERVED_AT_MS ASC',
                (series_id, start_ms, end_ms),
            )
            for ts_ms, enc in cur.fetchall():
                ts_int = int(ts_ms)
                try:
                    dec = self._decrypt_json(
                        str(enc), f'UCFG_METRIC_SAMPLES_RAW:{series_id}:{ts_int}'
                    )
                except Exception:
                    continue
                if not isinstance(dec, dict) or not isinstance(dec.get('v'), (int, float)):
                    continue
                v = float(dec['v'])
                points.append({
                    'ts': ts_int,
                    'value': v,
                    'min': v,
                    'max': v,
                    'count': 1,
                })
            return points

        table_name = 'UCFG_METRIC_ROLLUP_5M' if resolution == '5m' else 'UCFG_METRIC_ROLLUP_1H'
        cur.execute(
            f'SELECT FIRST 9000 BUCKET_START_MS, ROLLUP_ENC FROM {table_name} '
            'WHERE SERIES_ID = ? AND BUCKET_START_MS >= ? AND BUCKET_START_MS <= ? '
            'ORDER BY BUCKET_START_MS ASC',
            (series_id, start_ms, end_ms),
        )
        for bucket_ms, enc in cur.fetchall():
            b_int = int(bucket_ms)
            try:
                dec = self._decrypt_json(
                    str(enc), f'{table_name}:{series_id}:{b_int}'
                )
            except Exception:
                continue
            if not isinstance(dec, dict):
                continue
            cnt = max(1, int(dec.get('count') or 1))
            avg_v = float(dec.get('sum', 0.0)) / cnt
            points.append({
                'ts': b_int,
                'value': avg_v,
                'min': float(dec.get('min', avg_v)),
                'max': float(dec.get('max', avg_v)),
                'last': float(dec.get('last', avg_v)),
                'count': cnt,
            })
        return points

    def list_tracked_metric_objects(
        self, user_id: int, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return summary of tracked objects with stored historic metrics for fleet views."""
        uid = int(user_id)
        max_rows = max(1, min(1000, int(limit)))
        with self._lock:
            self._require_dek()
            with self._open_or_create_connection(create_if_missing=True) as con:
                cur = con.cursor()
                cur.execute(
                    f'SELECT FIRST {max_rows} ENGINE_ID, SERVER_ID, DATABASE_TARGET_ID, '
                    'OBJECT_KIND, OBJECT_KEY, COUNT(*), MAX(UPDATED_AT) '
                    'FROM UCFG_METRIC_SERIES WHERE USER_ID = ? '
                    'GROUP BY ENGINE_ID, SERVER_ID, DATABASE_TARGET_ID, OBJECT_KIND, OBJECT_KEY '
                    'ORDER BY 7 DESC',
                    (uid,),
                )
                return [
                    {
                        'engine_id': str(r[0] or ''),
                        'server_id': int(r[1] or 0),
                        'database_target_id': str(r[2] or ''),
                        'object_kind': str(r[3] or ''),
                        'object_key': str(r[4] or ''),
                        'series_count': int(r[5] or 0),
                        'updated_at': str(r[6] or ''),
                    }
                    for r in cur.fetchall()
                ]

    @staticmethod
    def _deep_stats_record_id(
        user_id: int,
        server_id: int,
        database_target_id: str,
        object_kind: str,
        object_key: str,
    ) -> str:
        raw = (
            f'{int(user_id)}|{int(server_id or 0)}|'
            f'{str(database_target_id or "")}|{str(object_kind or "")}|{str(object_key or "")}'
        )
        return 'deep:' + hashlib.sha256(raw.encode('utf-8')).hexdigest()[:64]

    def save_on_demand_object_stats(
        self,
        *,
        user_id: int,
        engine_id: str,
        server_id: int = 0,
        database_target_id: str = '',
        object_kind: str,
        object_key: str,
        stats: Mapping[str, Any],
        computed_at: str | None = None,
    ) -> dict[str, Any]:
        ts = str(computed_at or _now_iso())
        rid = self._deep_stats_record_id(
            user_id, server_id, database_target_id, object_kind, object_key
        )
        payload = {
            'object_kind': str(object_kind),
            'object_key': str(object_key),
            'computed_at': ts,
            'stats': dict(stats),
        }
        self.save_metrics_history_record(
            record_id=rid,
            user_id=int(user_id),
            record_kind='on_demand_object_stats',
            payload=payload,
            server_id=int(server_id or 0),
            database_target_id=str(database_target_id or ''),
            engine_id=str(engine_id or ''),
            scope='personal',
            updated_at=ts,
        )
        return payload

    def get_on_demand_object_stats(
        self,
        *,
        user_id: int,
        object_kind: str,
        object_key: str,
        server_id: int = 0,
        database_target_id: str = '',
    ) -> dict[str, Any] | None:
        rid = self._deep_stats_record_id(
            user_id, server_id, database_target_id, object_kind, object_key
        )
        rec = self.get_metrics_history_record(rid)
        if rec is None or not isinstance(rec.get('payload'), dict):
            return None
        return rec['payload']

    def get_object_view_customization(
        self, user_id: int, surface_kind: str, scope_key: str = 'default'
    ) -> dict[str, Any]:
        stored = self.get_specific_layout(
            int(user_id), str(surface_kind or 'object_dashboard'), str(scope_key or 'default')
        )
        return dict(stored) if isinstance(stored, dict) else {}

    def save_object_view_customization(
        self,
        user_id: int,
        surface_kind: str,
        customization: Mapping[str, Any],
        scope_key: str = 'default',
    ) -> dict[str, Any]:
        clean = dict(customization)
        self.save_specific_layout(
            int(user_id),
            str(surface_kind or 'object_dashboard'),
            str(scope_key or 'default'),
            clean,
        )
        return clean

    # ------------------------------------------------------------------
    # Legacy SQLite Import & Runtime SQLAlchemy Sync
    # ------------------------------------------------------------------

    def _migrate_legacy_sqlite_stores(
        self,
        *,
        default_user_id: int,
        data_dir: str | Path | None = None,
    ) -> None:
        base_dir = Path(
            data_dir
            or (self.db_path.parent if self.db_path is not None else os.path.expanduser('~/.cdeadmin'))
        )
        if not base_dir.is_dir():
            return

        # 1. surface_layouts.db
        layouts_sqlite = base_dir / 'surface_layouts.db'
        if layouts_sqlite.is_file():
            try:
                with sqlite3.connect(str(layouts_sqlite), timeout=5.0) as conn:
                    conn.row_factory = sqlite3.Row
                    for row in conn.execute(
                        'SELECT user_id, surface_kind, object_key, layout_json FROM surface_specific_layout'
                    ).fetchall():
                        parsed = json.loads(row['layout_json'])
                        uid = int(row['user_id']) or default_user_id
                        if row['surface_kind'] == 'shared-field-format' and row['object_key'] == 'defaults':
                            self.save_user_preference(uid, 'shared-field-format', 'defaults', parsed)
                        else:
                            self.save_specific_layout(
                                uid, str(row['surface_kind']), str(row['object_key']), parsed
                            )
                    for row in conn.execute(
                        'SELECT template_id, surface_kind, name, description, author_user_id, layout_json '
                        'FROM surface_layout_template'
                    ).fetchall():
                        parsed = json.loads(row['layout_json'])
                        self.save_template(
                            int(row['author_user_id']) or default_user_id,
                            str(row['surface_kind']),
                            str(row['name']),
                            parsed,
                            description=str(row['description'] or ''),
                            template_id=str(row['template_id']),
                        )
            except Exception:
                pass

        # 2. sql_snippets.db
        snippets_sqlite = base_dir / 'sql_snippets.db'
        if snippets_sqlite.is_file():
            try:
                with sqlite3.connect(str(snippets_sqlite), timeout=5.0) as conn:
                    conn.row_factory = sqlite3.Row
                    tag_map: dict[str, list[str]] = {}
                    for tr in conn.execute('SELECT snippet_id, tag FROM sql_snippet_tag').fetchall():
                        tag_map.setdefault(str(tr['snippet_id']), []).append(str(tr['tag']))
                    for row in conn.execute('SELECT * FROM sql_snippet').fetchall():
                        sid = str(row['snippet_id'])
                        if row['scope'] == 'builtin':
                            continue
                        payload = {
                            'snippet_id': sid,
                            'title': str(row['title']),
                            'description': str(row['description']),
                            'shortcut': str(row['shortcut']),
                            'engine_id': str(row['engine_id']),
                            'scope': str(row['scope']),
                            'project_id': str(row['project_id']),
                            'owner_user_id': int(row['owner_user_id']) or default_user_id,
                            'favorite': bool(row['favorite']),
                            'sql_text': str(row['sql_text']),
                            'tags': tag_map.get(sid, []),
                            'updated_at': str(row['updated_at']),
                        }
                        self.save_metrics_history_record(
                            record_id=f'snippet:{sid}',
                            user_id=int(row['owner_user_id']) or default_user_id,
                            record_kind='sql_snippet',
                            engine_id=str(row['engine_id']),
                            scope=str(row['scope']),
                            payload=payload,
                            updated_at=str(row['updated_at']),
                        )
            except Exception:
                pass

        # 3. quick_queries.db
        qq_sqlite = base_dir / 'quick_queries.db'
        if qq_sqlite.is_file():
            try:
                with sqlite3.connect(str(qq_sqlite), timeout=5.0) as conn:
                    conn.row_factory = sqlite3.Row
                    for row in conn.execute('SELECT * FROM quick_query').fetchall():
                        qid = str(row['query_id'])
                        payload = {
                            'query_id': qid,
                            'user_id': int(row['user_id']) or default_user_id,
                            'server_id': int(row['server_id'] or 0),
                            'database_target_id': str(row['database_target_id'] or ''),
                            'engine_id': str(row['engine_id'] or ''),
                            'project_id': str(row['project_id'] or ''),
                            'name': str(row['name']),
                            'description': str(row['description'] or ''),
                            'sql_text': str(row['sql_text']),
                            'terminator': str(row['terminator'] or ';'),
                            'parameters': json.loads(row['parameters_json'] or '[]'),
                            'display_layout': json.loads(row['display_layout_json'] or '{}'),
                            'updated_at': str(row['updated_at']),
                        }
                        self.save_metrics_history_record(
                            record_id=f'quick_query:{qid}',
                            user_id=int(row['user_id']) or default_user_id,
                            record_kind='quick_query',
                            server_id=int(row['server_id'] or 0),
                            database_target_id=str(row['database_target_id'] or ''),
                            engine_id=str(row['engine_id'] or ''),
                            payload=payload,
                            updated_at=str(row['updated_at']),
                        )
            except Exception:
                pass


def get_user_config_db() -> UserConfigurationDatabase:
    """Return the process-wide encrypted UserConfigurationDatabase instance."""
    global _DEFAULT_DB_INSTANCE
    with _DEFAULT_DB_LOCK:
        if _DEFAULT_DB_INSTANCE is None:
            dsn = None
            db_path = None
            try:
                import config as pg_config
                dsn = getattr(pg_config, 'USER_CONFIGURATION_DATABASE_DSN', None)
                db_path = getattr(pg_config, 'USER_CONFIGURATION_DATABASE_PATH', None)
                if not db_path:
                    data_dir = getattr(pg_config, 'DATA_DIR', None)
                    if data_dir:
                        db_path = Path(data_dir) / 'user_configuration.fdb'
            except Exception:
                pass
            _DEFAULT_DB_INSTANCE = UserConfigurationDatabase(
                db_path=db_path, dsn=dsn
            )
        return _DEFAULT_DB_INSTANCE


def reset_default_user_config_db_for_tests(
    instance: UserConfigurationDatabase | None = None,
) -> None:
    global _DEFAULT_DB_INSTANCE
    with _DEFAULT_DB_LOCK:
        if _DEFAULT_DB_INSTANCE is not None and _DEFAULT_DB_INSTANCE is not instance:
            _DEFAULT_DB_INSTANCE.lock()
        _DEFAULT_DB_INSTANCE = instance


def mint_desktop_handoff_ticket(user_id: int, username: str) -> str:
    """Create a short-lived single-use ticket for Electron splash -> BrowserWindow login handoff."""
    ticket = secrets.token_urlsafe(32)
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=90)
    with _DESKTOP_HANDOFF_LOCK:
        now = datetime.datetime.now(datetime.timezone.utc)
        expired = [k for k, v in _DESKTOP_HANDOFF_TICKETS.items() if v['expires_at'] < now]
        for k in expired:
            _DESKTOP_HANDOFF_TICKETS.pop(k, None)
        _DESKTOP_HANDOFF_TICKETS[ticket] = {
            'user_id': int(user_id),
            'username': str(username),
            'expires_at': expires,
        }
    return ticket


def consume_desktop_handoff_ticket(ticket: str) -> dict[str, Any] | None:
    """Consume a single-use Electron splash login handoff ticket."""
    if not ticket:
        return None
    with _DESKTOP_HANDOFF_LOCK:
        entry = _DESKTOP_HANDOFF_TICKETS.pop(str(ticket), None)
    if not entry:
        return None
    if entry['expires_at'] < datetime.datetime.now(datetime.timezone.utc):
        return None
    return entry


def sync_runtime_orm_to_user_config_db(user_id: int) -> None:
    """Mirror runtime SQLAlchemy Server, CDEEndpoint, UserPreference & Setting rows into encrypted Firebird store."""
    ucfg = get_user_config_db()
    if not ucfg.is_unlocked():
        return
    try:
        from pgadmin.model import (
            CDEEndpoint,
            Preferences as PrefTable,
            Server,
            Setting,
            UserPreference,
        )

        for srv in Server.query.filter_by(user_id=user_id).all():
            ep: CDEEndpoint | None = getattr(srv, 'endpoint_profile', None)
            engine_id = str(getattr(ep, 'engine_id', None) or 'postgresql')
            payload = {
                'server_id': srv.id,
                'name': srv.name,
                'host': srv.host,
                'port': srv.port,
                'maintenance_db': srv.maintenance_db,
                'username': srv.username,
                'shared': bool(getattr(srv, 'shared', False)),
                'comment': srv.comment,
                'connection_params': getattr(srv, 'connection_params', None) or {},
            }
            if ep is not None:
                payload['endpoint'] = {
                    'endpoint_id': ep.id,
                    'engine_id': ep.engine_id,
                    'profile_id': ep.profile_id,
                    'mode': ep.mode,
                    'options_json': getattr(ep, 'options_json', None),
                }
            ucfg.save_connection_parameters(
                user_id,
                f'server:{srv.id}',
                engine_id,
                payload,
                is_shared=bool(getattr(srv, 'shared', False)),
            )

        for setting_row in Setting.query.filter_by(user_id=user_id).all():
            ucfg.save_user_preference(
                user_id, 'ui_setting', str(setting_row.setting), setting_row.value
            )

        for up in UserPreference.query.filter_by(uid=user_id).all():
            pref_meta = PrefTable.query.filter_by(id=up.pid).first()
            if pref_meta is not None:
                ucfg.save_user_preference(
                    user_id,
                    f'pref_cid_{pref_meta.cid}',
                    str(pref_meta.name),
                    up.value,
                )
    except Exception:
        pass


def ensure_flask_security_user_for_vault_user(vault_user: Mapping[str, Any]):
    """Ensure the authenticated UserConfigurationDatabase user exists in Flask-Security's runtime session store."""
    from pgadmin.model import Role, ServerGroup, User, db
    from pgadmin.utils.constants import INTERNAL

    username = str(vault_user['username'])
    email = str(
        vault_user.get('email')
        or (username if '@' in username else f'{username}@local.invalid')
    )
    user = User.query.filter(
        (db.func.lower(User.username) == username.lower())
        | (db.func.lower(User.email) == email.lower())
    ).first()

    # Check if there is a single default desktop user (id=1) we should bind on first run
    if user is None and int(vault_user.get('user_id') or 0) == 1:
        default_user = User.query.order_by(User.id.asc()).first()
        if default_user is not None and default_user.id == 1 and User.query.count() == 1:
            default_user.username = username[:64]
            default_user.email = email[:256]
            default_user.active = True
            default_user.locked = False
            db.session.commit()
            user = default_user

    if user is None:
        admin_role = Role.query.filter_by(name='Administrator').first()
        roles = [admin_role] if admin_role is not None else []
        user = User(
            username=username[:64],
            email=email[:256],
            password=secrets.token_hex(16),
            active=True,
            auth_source=INTERNAL,
            fs_uniquifier=uuid.uuid4().hex,
            roles=roles,
        )
        db.session.add(user)
        db.session.commit()

    if ServerGroup.query.filter_by(user_id=user.id).count() == 0:
        db.session.add(ServerGroup(user_id=user.id, name='Servers'))
        db.session.commit()

    return user


def init_user_config_db_app(app) -> UserConfigurationDatabase:
    """Attach UserConfigurationDatabase to the Flask app and wire ORM commit sync."""
    ucfg = get_user_config_db()
    app.extensions['cdeadmin_user_config_db'] = ucfg

    try:
        from sqlalchemy import event
        from pgadmin.model import Server, Setting, UserPreference, db

        @event.listens_for(db.session, 'after_commit')
        def _on_after_commit(session):
            if not ucfg.is_unlocked():
                return
            try:
                from flask_login import current_user
                if current_user and getattr(current_user, 'is_authenticated', False):
                    sync_runtime_orm_to_user_config_db(int(current_user.id))
            except Exception:
                pass

        _ = (Server, Setting, UserPreference)
    except Exception:
        pass

    return ucfg
