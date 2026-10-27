##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""MySQL native maintenance browser-gate contract tests."""

import unittest

from tools.cdeadmin_mysql_maintenance_ui_gate import (
    CASES,
    _operations,
    _using_data_case,
)


class MySQLMaintenanceUIGateTests(unittest.TestCase):

    def test_retired_legacy_gate_cannot_claim_the_empty_fallback_is_a_form(self):
        with self.assertRaisesRegex(RuntimeError, 'Decision12'):
            _operations()
        self.assertEqual(9, len(CASES))

    def test_using_data_uses_canonical_server_document(self):
        template = next(
            case for case in CASES
            if case['case_id'] == 'analyze_histogram_using_data'
        )
        document = {'z': "operator's value", 'a': [1, 2]}
        case = _using_data_case(template, document)
        self.assertIsNone(template['expected'])
        self.assertEqual(document, case['values']['histogram_data'])
        self.assertEqual(
            'ANALYZE TABLE `cdeadmin_demo`.`qualification` UPDATE '
            'HISTOGRAM ON `value` USING DATA '
            "'{\"a\":[1,2],\"z\":\"operator''s value\"}'",
            case['expected'],
        )


if __name__ == '__main__':
    unittest.main()
