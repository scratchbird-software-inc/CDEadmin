"""Single-developer, loopback-only setup. Copy to web/config_local.py."""
import os

DATA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '.devstate', 'application'))
SERVER_MODE = True
DEBUG = False
DEFAULT_SERVER = '127.0.0.1'
DEFAULT_SERVER_PORT = 5051
LOG_FILE = os.path.join(DATA_DIR, 'cdeadmin.log')
SQLITE_PATH = os.path.join(DATA_DIR, 'cdeadmin.db')
SESSION_DB_PATH = os.path.join(DATA_DIR, 'sessions')
STORAGE_DIR = os.path.join(DATA_DIR, 'storage')
KERBEROS_CCACHE_DIR = os.path.join(DATA_DIR, 'krbccache')
AZURE_CREDENTIAL_CACHE_DIR = os.path.join(DATA_DIR, 'azurecredentialcache')
CDEADMIN_OPERATION_STORE_PATH = os.path.join(DATA_DIR, 'operations.json')
MASTER_PASSWORD_REQUIRED = True
ALLOW_SAVE_PASSWORD = True
