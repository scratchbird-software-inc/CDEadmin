"""Discard unpublished failed attachments without detach-retention hooks.

Linux native qualification is covered by the native-opening failed-detach gate.
Windows/macOS qualification must repeat that gate with their native libraries:
verify retained handle ownership, rollback, failed detach and explicit retry.
Linux evidence does not qualify platform-specific client teardown behavior.
"""


def discard_failed_session(connection):
    attachment = connection._att
    if attachment is None:
        return
    try:
        try:
            # Native driver cleanup rolls back its owned transaction managers.
            connection._close()
        finally:
            connection._close_internals()
    finally:
        # A failed detach does not confirm release. Keep the native reference
        # so the provider can quarantine and explicitly retry this attachment.
        attachment.detach()
        connection._att = None
