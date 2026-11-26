#!/usr/bin/env python3
"""Every refusal an engine's provider can raise, read from its source (Decision 22).

A refusal is an exception raised with a message of one of the engine's refusal classes. The first
argument is one of

* a string literal: fixed text with no user data, registered as it stands in the engine's
  ``refusal_literals.json``;
* an f-string, a ``.format`` or ``%`` string or a built string: it may hold a value the user typed or native
  tool output, so it is matched by a rule in the engine's vocabulary and shown as the catalog's sentence for
  the rule;
* anything else (a name, a call, an attribute): the message of another exception passed on, which is
  classified where it began.

Scopes: ``postgresql`` (its provider), ``relational`` (the compilers the actual-engine providers share) and
``mysql`` (the MySQL family without MariaDB). ``python3 tools/refusal_inventory.py [--engine NAME] --write``
regenerates the literal list; ``--check`` fails when it is out of date. ``test_refusal_reasons.py`` runs the
same check, so a new refusal that is neither registered nor matched fails the build.
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CDEADMIN = ROOT / 'web/pgadmin/cdeadmin'
PROVIDERS = CDEADMIN / 'providers'
PROVIDER = PROVIDERS / 'postgresql'
MYSQL = PROVIDERS / 'mysql_family'
LITERALS = PROVIDER / 'refusal_literals.json'  # the PostgreSQL registry, kept for older callers

# the error classes the shared plan funnel catches, and the ones its compilers raise for a bad draft
_RELATIONAL = {'RelationalClientError', 'RelationalDependencyError', 'RelationalCredentialError',
               'ObserverUnavailable', 'MySQLParameterAdmissionError', 'PoolUnavailable', 'ValueError'}

ENGINES = {
    'postgresql': {
        # PostgreSQLStatementRejected is an apply-time rejection with its own contract (the server's own words).
        'files': lambda: sorted(PROVIDER.glob('*.py')),
        'raised': {'PostgreSQLNativeAdminError', 'PostgreSQLProviderError', '_refuse'},
        'literals': PROVIDER / 'refusal_literals.json',
    },
    'relational': {
        'files': lambda: [PROVIDERS / 'relational_admin.py', CDEADMIN / 'sdk/relational.py'],
        'raised': _RELATIONAL,
        'literals': PROVIDERS / 'relational_refusal_literals.json',
    },
    'mysql': {
        'files': lambda: [path for path in sorted(MYSQL.glob('*.py')) if not path.name.startswith('mariadb')],
        'raised': _RELATIONAL,
        'literals': MYSQL / 'refusal_literals.json',
    },
}

_FIELD = re.compile(r'\{[^{}]*\}')
_PERCENT = re.compile(r'%[sdrif]|%\([^)]*\)[sdrif]')


def _template(node):
    """('literal'|'dynamic'|'forwarded', text) for the message argument of a refusal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return 'literal', node.value
    if isinstance(node, ast.JoinedStr):
        return 'dynamic', ''.join(part.value if isinstance(part, ast.Constant) else '{}' for part in node.values)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'format'
            and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str)):
        return 'dynamic', _FIELD.sub('{}', node.func.value.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        (left_kind, left), (right_kind, right) = _template(node.left), _template(node.right)
        if left_kind == right_kind == 'literal':
            return 'literal', left + right
        return 'dynamic', (left if left_kind != 'forwarded' else '{}') + (right if right_kind != 'forwarded' else '{}')
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        kind, left = _template(node.left)
        return ('dynamic', _PERCENT.sub('{}', left)) if kind != 'forwarded' else ('forwarded', '')
    return 'forwarded', ''


def sites(engine='postgresql'):
    """[{file, line, kind, text}] for every refusal of the engine's scope that carries its own message."""
    scope = ENGINES[engine]
    found = []
    for path in scope['files']():
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else None
            if name in scope['raised'] and node.args:
                kind, text = _template(node.args[0])
                if kind != 'forwarded':
                    found.append({'file': path.name, 'line': node.lineno, 'kind': kind, 'text': text})
    return found


def literals(engine='postgresql'):
    return sorted({site['text'] for site in sites(engine) if site['kind'] == 'literal'})


def dynamic_templates(engine='postgresql'):
    return sorted({site['text'] for site in sites(engine) if site['kind'] == 'dynamic'})


def document(engine='postgresql'):
    return {'schema': 'cdeadmin.refusal-literals.v1',
            'engine': engine,
            'notes': 'Generated by tools/refusal_inventory.py --write. Each message is fixed text in the provider '
                     'source, with no user data; it may be shown to the user as it stands (Decision 22).',
            'messages': literals(engine)}


def main(argv):
    engines = [argv[argv.index('--engine') + 1]] if '--engine' in argv else list(ENGINES)
    status = 0
    for engine in engines:
        path = ENGINES[engine]['literals']
        text = json.dumps(document(engine), indent=1, ensure_ascii=False) + '\n'
        if '--write' in argv:
            path.write_text(text, encoding='utf-8')
            print(f'{engine}: wrote {len(document(engine)["messages"])} messages')
        elif '--check' in argv:
            if (path.read_text(encoding='utf-8') if path.exists() else '') != text:
                print(f'{engine}: {path.name} is out of date; run tools/refusal_inventory.py --engine {engine} --write')
                status = 1
        else:
            print(f'{engine}: {len(literals(engine))} literal messages, {len(dynamic_templates(engine))} dynamic templates')
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
