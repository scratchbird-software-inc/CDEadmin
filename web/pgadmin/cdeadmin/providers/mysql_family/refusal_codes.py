"""The reason codes a MySQL refusal can carry (Decision 22). See ``visual_admin/refusal_vocabulary``.

MySQL's own rules come first, then the shared relational ones; the fixed messages of both scopes are read
from their registries. ``ui_descriptors/mysql/refusals.json`` gives the sentence for each code.
"""
from pathlib import Path

from pgadmin.cdeadmin.providers.relational_refusal_codes import GENERIC_CODES, RELATIONAL_RULES
from pgadmin.cdeadmin.visual_admin.refusal_vocabulary import Vocabulary

HERE = Path(__file__).parent
PROVIDERS = HERE.parent

CODES = GENERIC_CODES | {'confirmation_mismatch', 'password_not_carried', 'database_not_chosen'}

# exact static message -> (code, id of the field the refusal is about)
KNOWN_MESSAGES = {}

_L = r'(?:(?P<field>[A-Za-z0-9_.\[\]-]+)|.+?)'

MYSQL_RULES = (
    # what MySQL or one of its utilities itself said
    ('native_tool_rejected', r'(?:Native|MySQL native)\b.* failed \(.*\).*'),
    ('native_tool_rejected', r'Native NDB Cluster operation failed .*'),
    ('native_tool_rejected', r'MySQL X (?:Plugin rejected|Protocol connection failed|Protocol review failed|collection operation failed).*'),
    ('native_tool_rejected', r'MySQL rejected statement preparation .*'),
    ('native_tool_rejected', r'(?:ibd2sdi|innochecksum|myisamchk|myisampack|mysqlslap|Post-pack myisamchk)\b.* (?:failed|cancelled|timed out).*'),
    ('native_tool_rejected', r'mysqlslap benchmark (?:cancelled|timed out).*'),
    ('native_tool_rejected', r'.+ failed; inspect the redacted provider observation'),
    ('operation_state_unclear', r'.+ XA outcome is unconfirmed for .+; .*'),
    ('provider_unavailable', r'Missing UI descriptor for MySQL operation .+'),
    ('provider_unavailable', r'NDB management server .+ is unreachable: .*'),
    ('provider_unavailable', r'An idle .+ session is required to start XA'),
    ('provider_unavailable', r'.+ monitoring source is closed'),
    ('stale_listing', r'.+ retained native session identity (?:changed|is unavailable)'),
    ('stale_listing', r'Target `.*`\.`.*` is no longer an X COLLECTION'),
    ('stale_listing', r'Unknown MySQL connection thread ID .+'),
    ('unsupported_here', r'(?:Unsupported|Unknown) .+: .*'),
    ('unsupported_here', r'Unsupported .+'),
    ('unsupported_here', r'Unknown X collection .+ option'),
    ('unsupported_here', r'Unique .+ collection index is not supported by MySQL X Plugin'),
    ('unsupported_here', r'MySQL NDB Cluster storage engine .* is unavailable on this server .*'),
    ('unsupported_here', r'Object `.*`\.`.*` is .+, not a native MySQL X COLLECTION'),
    ('duplicate_value', r'Object `.*`\.`.*` already exists as .+, not a COLLECTION'),
    ('unsafe_syntax', r'.+ contains forbidden server-global, privilege, file, or schema-drop SQL'),
    ('invalid_value', r'(?:Native|Native NDB) .+ requires (?:bounded text without NUL|exact unsigned decimal text)'),
    ('invalid_value', _L + r' (?:requires (?:bounded UTF-8 text|native text without NUL|bounded native account records|bounded unsigned decimal text|an exact unsigned decimal integer|separate user and host values|1 to 64 characters without NUL)|must be native text without NUL or newlines|is invalid|must be a child path|escapes the MySQL Shell workspace)'),
    ('number_expected', _L + r' (?:requires a positive integer|must be a non-negative integer|is outside the native range)'),
    ('number_expected', r'Select a native failover integer in range .+'),
    ('boolean_expected', _L + r' must be boolean'),
    ('value_required', r'Supply (?:bounded non-empty SQL for|.+ for SSH utility host execution).*'),
    ('value_required', _L + r' monitoring requires an explicit native scope'),
    ('choice_expected', r'Select native (?:index .+|.+ explicitly)'),
    ('rule_not_met', r'Conflicting (?:index option|native MySQL).*'),
    ('rule_not_met', r'Cannot combine --count with .+'),
    ('rule_not_met', r'Benchmark scratch schema .+'),
    ('rule_not_met', r'.+ references schema .+ outside isolated benchmark schema .+'),
    ('rule_not_met', r'Execution-host datadir auto\.cnf server-uuid .*'),
    ('rule_not_met', r'Target connection .+ is idle or executing a non-explainable statement .*'),
    ('rule_not_met', r'Native privilege denied inspecting connection .+'),
)

RULES = MYSQL_RULES + RELATIONAL_RULES

VOCABULARY = Vocabulary(
    codes=CODES, known=KNOWN_MESSAGES, rules=RULES,
    literal_files=[HERE / 'refusal_literals.json', PROVIDERS / 'relational_refusal_literals.json'],
    wording_files=[HERE / 'refusal_wording.json', PROVIDERS / 'relational_refusal_wording.json'])

classify = VOCABULARY.classify
literals = VOCABULARY.literals
wording = VOCABULARY.wording
describe = VOCABULARY.describe
