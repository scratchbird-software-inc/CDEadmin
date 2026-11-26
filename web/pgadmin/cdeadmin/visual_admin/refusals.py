"""Bounded, secret-free HTTP contracts for pre-dispatch refusals.

A refusal says which field and which registered reason (``code``), and the sentence for it as
``message`` (Decision 22): the engine's catalog text for the code, or, when the provider's source
registers the refusal as fixed text with no user data (``explanation``), that text. Nothing else the
exception says is sent: a built message may carry what the user typed or native tool output. The
full reason is kept separately under ``reference`` (see ``refusal_log``).
"""
import re

MESSAGE_LIMIT = 300


def response(error, reference=None, catalog=None):
    """The response body for a refusal.

    ``catalog`` maps a reason code to the engine's text for it; a code without an entry, or any
    entry that is not text, carries no message and the user sees the generic sentence.
    """
    errors = []
    for value in getattr(error, 'errors', ())[:128]:
        if not isinstance(value, dict):
            continue
        field, code = value.get('field_id'), value.get('code')
        if field is not None and (not isinstance(field, str) or not re.fullmatch(r'[A-Za-z0-9_.\[\]-]{1,128}', field)):
            field = None
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', code):
            code = 'invalid_field'
        entry = {'field_id': field, 'code': code}
        # A fixed message the provider's source registers is shown as it stands (``explanation``); any other
        # entry gets the catalog's sentence for its code. An entry's own ``message`` is never sent.
        text = value.get('explanation')
        if not (isinstance(text, str) and text.strip()):
            text = (catalog or {}).get(code)
        if isinstance(text, str) and text.strip():
            entry['message'] = text.strip()[:MESSAGE_LIMIT]
        errors.append(entry)
    refusal = {'code': error.code, 'errors': errors, 'native_dispatched': False, 'automatic_retry': False}
    if isinstance(reference, str) and re.fullmatch(r'[0-9a-f]{16}', reference):
        refusal['reference'] = reference
    return {'status': error.status, 'success': 0, 'info': error.code,
            'errormsg': 'The operation was refused before dispatch. Review the indicated fields or create a new plan.',
            'data': {'refusal': refusal}}
