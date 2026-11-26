"""Reasons shared by the actual-engine providers that use the common relational compilers (Decision 22).

The compilers in ``relational_admin.py`` and the shared client in ``sdk/relational.py`` refuse with messages
that every engine built on them can show. The patterns here match the built ones; the fixed ones are
registered once in ``relational_refusal_literals.json`` with their wording in
``relational_refusal_wording.json``. An engine adds its own rules and reads these alongside.
"""
from pathlib import Path

from pgadmin.cdeadmin.visual_admin.refusal_vocabulary import Vocabulary

HERE = Path(__file__).parent

# the reasons common to the engines; each engine's refusals.json gives its own sentence for each
GENERIC_CODES = frozenset({
    'value_required', 'list_expected', 'number_expected', 'boolean_expected', 'choice_expected',
    'invalid_value', 'too_long', 'invalid_name', 'unsafe_syntax', 'invalid_sql', 'duplicate_value',
    'version_required', 'not_changeable', 'not_in_object', 'secret_not_carried', 'unsupported_here',
    'native_tool_rejected', 'operation_state_unclear', 'file_invalid', 'rule_not_met',
    'provider_unavailable', 'stale_listing',
})

_L = r'(?:(?P<field>[A-Za-z0-9_.\[\]-]+)|.+?)'

RELATIONAL_RULES = (
    ('unsafe_syntax', _L + r' contains unsafe syntax'),
    ('invalid_sql', _L + r' has unbalanced brackets(?: or quotes)?'),
    ('operation_state_unclear', r'relational transaction action outcome is provider-owned \(.*\)'),
    ('operation_state_unclear', r'.*; Firebird task rollback could not be verified; .*'),
    ('provider_unavailable', r'provider (?:database|server) operation failed \(.*\)'),
    ('provider_unavailable', r'relational (?:administration execution|execution|profile verification|row paging|server verification) failed \(.*\).*'),
    ('provider_unavailable', r'relational client dependency .+ is unavailable'),
    ('provider_unavailable', r'administration adapter requires .+'),
    ('provider_unavailable', r'.+ endpoint credentials are unavailable'),
    ('provider_unavailable', _L + r' must be callable'),
    ('unsupported_here', r'This trigger is maintained by constraint .+; use the constraint lifecycle\.'),
    ('unsupported_here', r'this editor cannot yet change existing .+ on this engine; .*'),
    ('unsupported_here', r'this engine cannot grant privileges on .+ objects'),
    ('value_required', _L + r' (?:creation requires an object body|is required|must not be empty)'),
    ('list_expected', r'.+s must be an array'),
    ('boolean_expected', _L + r' must be (?:boolean|true or false)'),
    ('number_expected', _L + r' (?:is outside its range|must be an integer|must be .+ to .+)'),
    ('invalid_value', r'SQLite .+ is invalid'),
    ('invalid_value', r'.+: arrays have at most .+ dimension.* on this engine'),
    ('rule_not_met', _L + r' needs the (?:options before it|trigger to order against)'),
)

VOCABULARY = Vocabulary(
    codes=GENERIC_CODES, rules=RELATIONAL_RULES,
    literal_files=[HERE / 'relational_refusal_literals.json'], wording_files=[HERE / 'relational_refusal_wording.json'])
