"""User-facing form text must not name implementation internals.

Help text, labels, titles and placeholders are shown to people. Text drafted from the inherited
pgAdmin schemas once carried notes meant for developers ("Provider tree: ...", "pgAdmin renders ...",
endpoint names such as get_columns, the *.ui.js file a field came from). Notes, gaps and reasons are
developer-facing and are not checked here.
"""
import json
import re
from pathlib import Path

DESCRIPTORS = Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/ui_descriptors'
USER_FACING = ('help', 'label', 'title', 'placeholder')
INTERNAL = re.compile(
    r'provider tree|pgadmin|baseuischema|\.ui\.js|depchange|vopts|properties mode|\bget_\w+|servers-api|'
    r'inherited (tree|dialog|properties)|see gaps|owner direction|descriptor set',
    re.IGNORECASE)


def _walk(node, path, found):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in USER_FACING and isinstance(value, str) and INTERNAL.search(value):
                found.append(f'{path}:{node.get("field_id") or node.get("operation_id") or ""}:{key}: {value[:120]}')
            _walk(value, path, found)
    elif isinstance(node, list):
        for value in node:
            _walk(value, path, found)


def test_no_engine_form_shows_implementation_wording_to_the_user():
    found = []
    for path in sorted(DESCRIPTORS.glob('*/forms/*.json')):
        _walk(json.loads(path.read_text(encoding='utf-8')), f'{path.parent.parent.name}/{path.name}', found)
    assert found == [], '\n'.join(found)
