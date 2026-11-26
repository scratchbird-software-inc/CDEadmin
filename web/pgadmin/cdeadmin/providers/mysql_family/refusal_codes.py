"""The reason codes a MySQL refusal can carry (Decision 22). See ``visual_admin/refusal_vocabulary``."""
from pathlib import Path

from pgadmin.cdeadmin.visual_admin.refusal_vocabulary import Vocabulary

HERE = Path(__file__).parent
PROVIDERS = HERE.parent

CODES = frozenset({'rule_not_met'})
KNOWN_MESSAGES = {}
RULES = ()

VOCABULARY = Vocabulary(
    codes=CODES, known=KNOWN_MESSAGES, rules=RULES,
    literal_files=[HERE / 'refusal_literals.json', PROVIDERS / 'relational_refusal_literals.json'],
    wording_files=[HERE / 'refusal_wording.json', PROVIDERS / 'relational_refusal_wording.json'])

classify = VOCABULARY.classify
literals = VOCABULARY.literals
wording = VOCABULARY.wording
describe = VOCABULARY.describe
