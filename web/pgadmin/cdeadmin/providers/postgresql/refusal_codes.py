"""The reason codes a PostgreSQL refusal can carry (Decision 22).

A refusal that carries one of these codes is shown to the user with the text of the same code in
``ui_descriptors/postgresql/refusals.json``. The text is never taken from the exception: a message
may interpolate what the user typed or native tool output. A refusal without a code keeps the
generic sentence.

``KNOWN_MESSAGES`` maps a static message a compiler already raises to its code, so the many sites
that raise it (every drop form checks its typed confirmation) need no edit; a site may instead pass
``code`` and ``field_id`` explicitly. Only an exact match counts.
"""

CODES = frozenset({
    'database_not_chosen',
    'confirmation_mismatch',
    'password_not_carried',
})

# exact static message -> (code, id of the field the refusal is about)
KNOWN_MESSAGES = {
    'choose the database the operation runs in': ('database_not_chosen', 'database'),
    'drop confirmation does not match object name': ('confirmation_mismatch', 'confirmation'),
    'The typed confirmation does not match the object name': ('confirmation_mismatch', 'confirmation'),
    'A plan never carries a password; set it with the inherited Properties dialog': (
        'password_not_carried', 'rolpassword'),
}


def classify(message, code=None, field_id=None):
    """The (code, field_id) a refusal carries: the explicit ones, else the known message's, else none.

    An explicit code must be registered; an unregistered one is a programming error.
    """
    if code is not None:
        if code not in CODES:
            raise ValueError(f'unregistered refusal code {code!r}')
        return code, field_id
    return KNOWN_MESSAGES.get(message, (None, None)) if field_id is None else (None, field_id)
