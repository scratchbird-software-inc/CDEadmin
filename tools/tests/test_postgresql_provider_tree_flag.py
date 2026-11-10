"""A PostgreSQL registration can choose the provider tree per server."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from pgadmin.cdeadmin.endpoints import postgresql_tree as tree  # noqa: E402

SERVERS_JS = (WEB / 'pgadmin' / 'browser' / 'server_groups' / 'servers' /
              'static' / 'js' / 'server.js')
SERVERS_PY = (WEB / 'pgadmin' / 'browser' / 'server_groups' / 'servers' /
              '__init__.py')


def server(profile_data='{}', schema=tree.EXTENSION_SCHEMA, preserved=True):
    extension = SimpleNamespace(schema_reference=schema,
                                profile_data=profile_data)
    return SimpleNamespace(endpoint_profile=SimpleNamespace(
        extension_profile=extension), _preserved=preserved)


class FlagTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(tree, 'is_preserved_postgresql',
                               lambda s: s._preserved)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_is_the_inherited_tree(self):
        self.assertFalse(tree.provider_tree_enabled(server()))
        self.assertFalse(tree.provider_tree_enabled(
            SimpleNamespace(endpoint_profile=None)))

    def test_choice_round_trips_in_the_extension_profile(self):
        item = server('{"other":1}')
        self.assertTrue(tree.set_provider_tree(item, True))
        stored = json.loads(item.endpoint_profile.extension_profile
                            .profile_data)
        self.assertEqual({'other': 1, tree.PROVIDER_TREE_KEY: True}, stored)
        self.assertTrue(tree.provider_tree_enabled(item))
        self.assertFalse(tree.set_provider_tree(item, False))
        self.assertEqual({'other': 1}, json.loads(
            item.endpoint_profile.extension_profile.profile_data))
        self.assertFalse(tree.provider_tree_enabled(item))

    def test_only_a_true_value_enables(self):
        self.assertFalse(tree.provider_tree_enabled(
            server('{"postgresql_provider_tree":"yes"}')))
        self.assertFalse(tree.provider_tree_enabled(server('not json')))

    def test_another_schema_in_the_slot_is_left_alone(self):
        item = server('{"binding":{}}',
                      schema='cdeadmin.mysql-recovery-registration.v1')
        self.assertFalse(tree.provider_tree_enabled(item))
        with self.assertRaisesRegex(ValueError, 'extension profile'):
            tree.set_provider_tree(item, True)

    def test_other_engines_cannot_choose(self):
        with self.assertRaisesRegex(ValueError, 'PostgreSQL registration'):
            tree.set_provider_tree(server(preserved=False), True)


class WiringTests(unittest.TestCase):
    """The choice is exposed on the node, settable by a route and offered
    on the server menu; these pin the wiring the Flask-bound module
    cannot be imported to test directly."""

    def test_node_fields_route_and_children_carry_the_choice(self):
        text = SERVERS_PY.read_text(encoding='utf-8')
        self.assertIn("'cde_provider_tree': provider_tree_enabled(server)",
                      text)
        self.assertIn("'provider_tree': [{'put': 'provider_tree'}]", text)
        self.assertIn('def provider_tree(self, gid, sid)', text)
        self.assertIn('provider_tree_enabled(server)', text.split(
            'def children(self, gid, sid)')[1].split('def ')[0])

    def test_server_menu_offers_both_trees(self):
        text = SERVERS_JS.read_text(encoding='utf-8')
        for name in ('use_provider_tree', 'use_inherited_tree'):
            self.assertIn(f"name: '{name}'", text)
        self.assertIn("'provider_tree'", text)


if __name__ == '__main__':
    unittest.main()
