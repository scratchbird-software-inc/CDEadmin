"""Portable identities for large payload test cases."""
import hashlib


def pytest_make_parametrize_id(config, val, argname):
    # pytest exports the current node ID in PYTEST_CURRENT_TEST. Windows
    # limits an environment value to 32,767 characters; payload contents
    # belong in assertions rather than the test's process environment.
    if isinstance(val, (str, bytes)) and len(val) > 128:
        raw = val.encode('utf-8', errors='surrogatepass') if isinstance(val, str) else val
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f'{argname}-{type(val).__name__}-{len(val)}-{digest}'
    return None
