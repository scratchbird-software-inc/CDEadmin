"""The vocabulary an engine gives its refusals (Decision 22).

One ``Vocabulary`` per engine turns the message a compiler refused with into a reason the user can be
shown, by one of three routes (``describe``), so no raise site needs an edit:

* a known message: an exact message mapped to a specific code, shown as the catalog's sentence for it;
* a registered fixed message: text that is a literal in source with no user data, listed in the engine's
  ``refusal_literals.json``, shown as it stands or as the plainer sentence or reason code that its
  ``refusal_wording.json`` gives it;
* a rule: a pattern for a message built from values, shown as the catalog's sentence for the rule, never
  the message itself, because that may echo what the user typed or native tool output.

``tools/refusal_inventory.py`` reads the source to keep the registered messages current, and
``test_refusal_reasons.py`` fails when a refusal is neither registered nor matched.
"""
import json
import re
from pathlib import Path
from typing import NamedTuple

EXPLANATION_LIMIT = 300


class Reason(NamedTuple):
    code: str | None
    field_id: str | None
    explanation: str | None = None


def sentence(message):
    """A message reviewed and kept as written, shown as a sentence: a capital letter and a full stop."""
    text = message.strip()
    if text[:1].islower():
        text = text[0].upper() + text[1:]
    return text if text[-1:] in '.!?' else text + '.'


class Vocabulary:
    def __init__(self, *, codes, known=None, rules=(), literal_files=(), wording_files=()):
        self.codes = frozenset(codes)
        self.known = dict(known or {})
        self.rules = tuple((code, re.compile(pattern, re.DOTALL)) for code, pattern in rules)
        self.literal_files = tuple(Path(path) for path in literal_files)
        self.wording_files = tuple(Path(path) for path in wording_files)
        self._literals = None
        self._wording = None

    def classify(self, message, code=None, field_id=None):
        """The (code, field_id) a refusal carries: the explicit ones, else the known message's, else none.

        An explicit code must be registered; an unregistered one is a programming error.
        """
        if code is not None:
            if code not in self.codes:
                raise ValueError(f'unregistered refusal code {code!r}')
            return code, field_id
        return self.known.get(message, (None, None)) if field_id is None else (None, field_id)

    def literals(self):
        """The fixed refusal messages registered for the engine (read once)."""
        if self._literals is None:
            found = set()
            for path in self.literal_files:
                if path.exists():
                    found.update(json.loads(path.read_text(encoding='utf-8'))['messages'])
            self._literals = frozenset(found)
        return self._literals

    def wording(self):
        """How a registered message is shown instead of as written: ``text`` (a plainer sentence), ``code`` (a
        reason code with an optional field), ``keep`` (reviewed, fine as written) or ``unreviewed`` (not yet
        reviewed, shown as written). A message in none is shown as written."""
        if self._wording is None:
            merged = {'text': {}, 'code': {}, 'keep': set(), 'unreviewed': set()}
            for path in self.wording_files:
                if path.exists():
                    data = json.loads(path.read_text(encoding='utf-8'))
                    merged['text'].update(data.get('text', {}))
                    merged['code'].update(data.get('code', {}))
                    merged['keep'].update(data.get('keep', ()))
                    merged['unreviewed'].update(data.get('unreviewed', ()))
            merged['keep'], merged['unreviewed'] = frozenset(merged['keep']), frozenset(merged['unreviewed'])
            self._wording = merged
        return self._wording

    def describe(self, message, code=None, field_id=None):
        """Why a refusal happened, whatever raised it: its explicit or known code, else a registered message shown
        as the wording says, else the rule that matches it, else nothing (the generic sentence)."""
        message = message if isinstance(message, str) else ''
        code, field_id = self.classify(message, code, field_id)
        if code is not None:
            return Reason(code, field_id)
        if message in self.literals():
            wording = self.wording()
            reworded = wording['code'].get(message)
            if reworded:
                return Reason(reworded['code'], reworded.get('field'))
            text = wording['text'].get(message)
            shown = text if text is not None else sentence(message)
            if len(shown) <= EXPLANATION_LIMIT:
                return Reason('rule_not_met', None, shown)
        for rule_code, pattern in self.rules:
            match = pattern.fullmatch(message)
            if match:
                return Reason(rule_code, (match.groupdict().get('field') or None) if 'field' in pattern.groupindex else None)
        return Reason(None, None)
