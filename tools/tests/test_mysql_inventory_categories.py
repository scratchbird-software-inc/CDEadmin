"""Committed inventories retain separate native categories, not product totals."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dispatch_ids_and_statement_grammar_are_distinct_categories():
    data = json.loads((ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json').read_text())
    inventory = data['inventories']
    commands = inventory['commands']
    assert commands and all(row['native_name'].startswith('SQLCOM_') for row in commands)
    assert all(row['inventory_kind'] == 'native-dispatch-id' and
               row['source'].startswith('include/my_sqlcommand.h:') for row in commands)
    assert all(row['native_name'] != 'Note' for rows in inventory.values() for row in rows)
    assert all(row.get('production', data['source_inventory_reconciliation']['serialization_defaults']['statement_production']) == 'simple_statement' and
               row['inventory_kind'] == 'grammar-entry' for row in inventory['statements'])
    assert all(row['native_name'].startswith('ER_') for row in inventory['diagnostics'])
    assert len({row['native_name'] for row in commands}) == len(commands)
