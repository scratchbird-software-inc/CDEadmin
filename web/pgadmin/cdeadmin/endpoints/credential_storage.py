"""Protected configuration writes; never report crypto/SQL exception payloads.

Linux qualification uses the real cipher and copied configuration.
Windows/macOS teams must repeat key-unlock, persistence and reveal tests
with their platform credential/key storage. This is not target-engine DDL.
"""

from contextlib import contextmanager

from .profiles import EndpointRegistrationError


def encrypted_credentials(value):
    import config
    from pgadmin.utils.crypto import encrypt
    from pgadmin.utils.master_password import get_crypt_key

    if not config.ALLOW_SAVE_PASSWORD:
        raise EndpointRegistrationError(
            'saving endpoint credentials is disabled')
    try:
        present, key = get_crypt_key()
    except Exception:
        raise EndpointRegistrationError(
            'endpoint credential key is unavailable') from None
    if not present:
        raise EndpointRegistrationError(
            'the master password must be unlocked before '
            'credentials can be saved')
    try:
        return encrypt(value, key)
    except Exception:
        raise EndpointRegistrationError(
            'endpoint credentials could not be encrypted') from None


@contextmanager
def protected_configuration_write(session):
    try:
        yield
    except Exception as error:
        # Rollback errors can themselves contain SQL bind values. Do not log
        # either exception or chain it into an HTTP response/server traceback.
        try:
            session.rollback()
        except Exception:
            pass
        if isinstance(error, EndpointRegistrationError):
            raise
        raise EndpointRegistrationError(
            'endpoint configuration could not be saved') from None
