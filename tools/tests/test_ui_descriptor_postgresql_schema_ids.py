"""PostgreSQL descriptors are legacy_preserved: every field id must be a
BaseUISchema id in the pgAdmin ``*.ui.js`` sources (the shell will route
these forms to the existing SQL templates in phase 5). This gate catches
drift when a ui.js schema renames or drops a field.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORMS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms'
SOURCES = (
    ROOT / 'web/pgadmin/browser/server_groups/servers',
    ROOT / 'web/pgadmin/browser/static/js',
    ROOT / 'web/pgadmin/static/js',
)
# Descriptor-only ids the shell owns (never sent to pgAdmin).
SHELL_IDS = {'variant'}


def schema_ids():
    ids = set()
    for root in SOURCES:
        for path in root.rglob('*.ui.js'):
            ids |= set(re.findall(r"\bid:\s*['\"]([A-Za-z0-9_]+)['\"]", path.read_text(encoding='utf-8')))
    return ids


def test_every_postgresql_field_id_is_a_ui_schema_id():
    ids = schema_ids()
    assert len(ids) > 300, 'pgAdmin ui.js schema ids were not found'
    unknown = []
    for path in sorted(FORMS.glob('*.form.json')):
        form = json.loads(path.read_text(encoding='utf-8'))
        for field in form['fields']:
            if field['field_id'] not in ids and field['field_id'] not in SHELL_IDS:
                unknown.append(f"{form['family']}.{field['field_id']}")
            if field['field_id'] in SHELL_IDS:
                assert field.get('ui_only') is True, f"{form['family']}.{field['field_id']} must be ui_only"
            for column in field.get('columns', []):
                if column['field_id'] not in ids:
                    unknown.append(f"{form['family']}.{field['field_id']}.{column['field_id']}")
    assert unknown == [], unknown
