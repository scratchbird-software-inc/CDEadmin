"""The reason codes a PostgreSQL refusal can carry (Decision 22).

A refusal that carries one of these codes is shown to the user with the text of the same code in
``ui_descriptors/postgresql/refusals.json``. The text is never taken from the exception: a message
may interpolate what the user typed or native tool output. A refusal without a code keeps the
generic sentence.

Every refusal is dealt with, by one of three routes (``describe``), so no raise site needs an edit:

* ``KNOWN_MESSAGES``: an exact message mapped to a specific code, shown as that code's catalog sentence;
* ``refusal_literals.json``: an exact message that is fixed text in source with no user data, shown as it
  stands (``tools/refusal_inventory.py`` reads the source and keeps the list current);
* ``RULES``: a pattern for a message built from values, shown as the catalog's sentence for the rule,
  never the message itself, because the message may echo what the user typed or native tool output.

A site may instead pass ``code`` and ``field_id`` explicitly. A test reads every raise site and fails when
one is neither listed nor matched.
"""
import re
from pathlib import Path

from pgadmin.cdeadmin.visual_admin.refusal_vocabulary import (
    EXPLANATION_LIMIT, Reason, Vocabulary, sentence as _sentence)
CODES = frozenset({
    'database_not_chosen',
    'confirmation_mismatch',
    'password_not_carried',
    # shapes and ranges of a value
    'value_required', 'list_expected', 'number_expected', 'boolean_expected', 'choice_expected',
    'invalid_value', 'too_long', 'invalid_name', 'unsafe_syntax', 'invalid_sql', 'duplicate_value',
    # what the object or the server allows
    'version_required', 'not_changeable', 'not_in_object', 'secret_not_carried', 'unsupported_here',
    # what PostgreSQL or an earlier operation said or left behind
    'native_tool_rejected', 'operation_state_unclear', 'prepared_transaction_changed', 'file_invalid',
    # the provider's own state, which the user cannot fix in the dialog, and a listing that is out of date
    'provider_unavailable', 'stale_listing',
    # a fixed rule of the operation, explained by its own sentence, or a rule with no more specific reason
    'rule_not_met',
})

# exact static message -> (code, id of the field the refusal is about)
KNOWN_MESSAGES = {
    'choose the database the operation runs in': ('database_not_chosen', 'database'),
    'drop confirmation does not match object name': ('confirmation_mismatch', 'confirmation'),
    'The typed confirmation does not match the object name': ('confirmation_mismatch', 'confirmation'),
    'A plan never carries a password; set it with the inherited Properties dialog': (
        'password_not_carried', 'rolpassword'),
}



# --- patterns for messages built from values -------------------------------------------------------------

# A label the compiler names (a field, a kind): when it is one plain identifier it is the field the refusal
# is about; a label with spaces still matches but names no field.
_L = r'(?:(?P<field>[A-Za-z0-9_.\[\]-]+)|.+?)'

RULES = tuple((code, re.compile(pattern, re.DOTALL)) for code, pattern in (
    ('unsafe_syntax', _L + r' contains unsafe syntax'),
    ('too_long', _L + r' exceeds \d+ bytes'),
    ('too_long', _L + r' exceeds \d+ MiB'),
    ('invalid_sql', _L + r' is not a valid (?:expression|query): .*'),
    ('invalid_sql', r'commands are not valid SQL: .*'),
    ('invalid_sql', r'the partition bound is not valid: .*'),
    ('invalid_sql', _L + r' must be one SELECT'),
    ('native_tool_rejected', r'Native postgres -C rejected postgresql\.conf: .*'),
    ('native_tool_rejected', r'PostgreSQL rejected .+: .*'),
    ('operation_state_unclear', r'PostgreSQL administrative commit outcome is unknown.*'),
    ('operation_state_unclear', r'PostgreSQL outcome is unknown for .+; .*'),
    ('operation_state_unclear', r'Resolve prepared PostgreSQL transaction .+ before closing'),
    ('operation_state_unclear', r'Session catalog capture failed; .*'),
    ('prepared_transaction_changed', r'Prepared transaction .+'),
    ('prepared_transaction_changed', r'Resolving prepared transaction .+ requires owner .+ or superuser authority'),
    ('version_required', r'This native operation requires PostgreSQL .+ or later'),
    ('secret_not_carried', r'Parameter .+ carries shell commands or connection secrets; .*'),
    ('secret_not_carried', r'the .+ option carries a credential; .*'),
    ('secret_not_carried', _L + r' holds a plain connection value'),
    ('unsupported_here', r'Unsupported PostgreSQL .+: .*'),
    ('unsupported_here', r'unsupported PostgreSQL catalog kind .*'),
    ('unsupported_here', _L + r' inspection stays with the provider tree'),
    ('unsupported_here', _L + r': edit existing columns and constraints on their own provider nodes; .*'),
    ('not_changeable', _L + r' is fixed once created; .*'),
    ('not_changeable', r'the check expression of .+ is fixed once created; .*'),
    ('not_changeable', r"a policy's .+ cannot be removed in place; .*"),
    ('not_changeable', r'this extension is not relocatable; .*'),
    ('duplicate_value', _L + r' must be distinct'),
    ('duplicate_value', r'enum label .+ repeats'),
    ('duplicate_value', r'the enumeration already has .+'),
    ('not_in_object', r'partition .+ does not belong to this table'),
    ('not_in_object', r'the enumeration has no value .+'),
    ('not_in_object', r'the type has no attribute .+'),
    ('not_in_object', r'.+ .+ does not belong to this job'),
    ('file_invalid', _L + r' must contain a valid PEM X\.509 certificate block'),
    ('file_invalid', _L + r' line .+ has fewer than .+ fields'),
    ('value_required', _L + r' (?:must not be empty|is required|needs a value|needs at least one (?:column|entry)|requires 1 or more distinct table names)'),
    ('value_required', r'option .+ needs (?:a text )?value'),
    ('value_required', r'the .+ mapping needs at least one dictionary'),
    ('list_expected', _L + r' (?:must be a list of (?:rows|catalog type references)|must be a bounded typed grid|rows must be objects|must be a list|must be an object)'),
    ('boolean_expected', _L + r' (?:must be boolean|is yes, no or empty)'),
    ('number_expected', _L + r' (?:must be (?:a whole number|an integer|a number)|is a whole number|is at least .+|runs from .+ to .+|takes a number(?:, on/off or a plain word)?|is outside bigint|positions run from 0 to .+)'),
    ('number_expected', r'PARALLEL requires an integer from 0 to .+'),
    ('number_expected', r'postgresql\..+ must be an integer'),
    ('invalid_name', _L + r' (?:is a locale name|is not a catalog reference|is not an admitted native type|is written name\(argument types\)|names a table as schema\.table|must contain only a native type)'),
    ('invalid_value', _L + r' (?:must be text|must be a timestamp such as .+|must be a comma list of positions|must be positions or .+ booleans|rows name an autovacuum storage parameter)'),
    ('choice_expected', r'(?:argument mode|attoptions|event|fires|locale provider|strategy|synchronous commit) (?:is|are) .+'),
    ('choice_expected', r'default privileges apply to .+'),
    ('choice_expected', r'default privileges on .+ are among ALL, .+'),
    ('choice_expected', r'object_type must be one of .+'),
    ('choice_expected', r'event is one of: .+'),
    ('choice_expected', _L + r' (?:privileges are among .+|must be one of .+|is .+ or .+)'),
    ('rule_not_met', r'a .+ policy has no WITH CHECK'),
    ('rule_not_met', _L + r' needs the .+ locale provider'),
    ('rule_not_met', _L + r' default privileges cannot use IN SCHEMA'),
    # a label followed by the words it can be: 'sort order is ASC or DESC', 'volatility is IMMUTABLE, STABLE, VOLATILE'
    ('choice_expected', _L + r' is [A-Za-z0-9_]+(?:(?:, | or )[A-Za-z0-9_ ]+)*'),
))

HERE = Path(__file__).parent

VOCABULARY = Vocabulary(
    codes=CODES, known=KNOWN_MESSAGES, rules=[(code, pattern.pattern) for code, pattern in RULES],
    literal_files=[HERE / 'refusal_literals.json'], wording_files=[HERE / 'refusal_wording.json'])

classify = VOCABULARY.classify
literals = VOCABULARY.literals
wording = VOCABULARY.wording
describe = VOCABULARY.describe
