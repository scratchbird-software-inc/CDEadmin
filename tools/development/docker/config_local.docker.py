"""Loopback-facing dev defaults for Docker Compose (copy to web/config_local.py)."""
import os

# Lives at web/config_local.py in the container: one level up is /cdeadmin.
_DATA_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.devstate', 'application')
)

DATA_DIR = _DATA_ROOT
SERVER_MODE = True
DEBUG = True
DEFAULT_SERVER = '0.0.0.0'
DEFAULT_SERVER_PORT = 5051
LOG_FILE = os.path.join(DATA_DIR, 'cdeadmin.log')
SQLITE_PATH = os.path.join(DATA_DIR, 'cdeadmin.db')
SESSION_DB_PATH = os.path.join(DATA_DIR, 'sessions')
STORAGE_DIR = os.path.join(DATA_DIR, 'storage')
KERBEROS_CCACHE_DIR = os.path.join(DATA_DIR, 'krbccache')
AZURE_CREDENTIAL_CACHE_DIR = os.path.join(DATA_DIR, 'azurecredentialcache')
CDEADMIN_OPERATION_STORE_PATH = os.path.join(DATA_DIR, 'operations.json')
MASTER_PASSWORD_REQUIRED = False
ALLOW_SAVE_PASSWORD = True
