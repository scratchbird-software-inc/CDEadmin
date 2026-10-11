"""Include registration-owned protected columns in existing key lifecycle."""


def targets(server):
    return getattr(getattr(server, 'endpoint_profile', None), 'database_targets', ())


def has_saved(server):
    return any(target.registration_password is not None for target in targets(server))


def clear(server):
    for target in targets(server):
        target.registration_password = None


def reencrypt(server, old_key, new_key):
    from pgadmin.utils.crypto import decrypt, encrypt
    # Prepare every ciphertext before changing any of this server's rows.
    replacements = []
    for target in targets(server):
        if target.registration_password is not None:
            value = decrypt(target.registration_password, old_key)
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            replacements.append((target, encrypt(value, new_key)))
    for target, ciphertext in replacements:
        target.registration_password = ciphertext
