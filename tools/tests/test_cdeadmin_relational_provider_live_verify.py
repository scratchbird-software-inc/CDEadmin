##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Relational live-verifier result classification tests."""

import pytest

from tools.cdeadmin_relational_provider_live_verify import (
    GRAPHICAL_OBJECT_CATEGORIES,
    _live_result,
    graphical_object_activation_ready,
)


def _passed_categories():
    categories = {
        name: 'passed' for name in GRAPHICAL_OBJECT_CATEGORIES
    }
    categories['semantic_query'] = 'blocked_contract'
    return categories


def test_graphical_activation_is_independent_of_semantic_compiler():
    assert graphical_object_activation_ready(
        _passed_categories(), {
            'operation_failures': {},
            'raw_commands_used': False,
        }
    )


def test_graphical_activation_rejects_failed_or_raw_operations():
    categories = _passed_categories()
    categories['transaction'] = 'not_run'
    assert not graphical_object_activation_ready(
        categories, {'operation_failures': {}, 'raw_commands_used': False}
    )
    assert not graphical_object_activation_ready(
        _passed_categories(), {
            'operation_failures': {'table': 'RuntimeError'},
            'raw_commands_used': False,
        }
    )
    assert not graphical_object_activation_ready(
        _passed_categories(), {
            'operation_failures': {},
            'raw_commands_used': True,
        }
    )


def test_graphical_activation_rejects_run_level_errors():
    assert not graphical_object_activation_ready(
        _passed_categories(), {
            'operation_failures': {},
            'raw_commands_used': False,
        }, 'RuntimeError'
    )


@pytest.mark.parametrize('engine', ['sqlite', 'firebird'])
def test_async_live_verifier_waits_for_final_native_error(engine):
    class DelayedError:
        def __init__(self):
            self.calls = 0

        def describe_result(self, _operation):
            self.calls += 1
            return {
                'complete': self.calls > 1,
                'extensions': {engine: {'payload': {
                    'rows': [],
                    'error': {'errno': 1} if self.calls > 1 else None,
                }}},
            }

    provider = DelayedError()
    with pytest.raises(RuntimeError, match='Native live query failed'):
        _live_result(provider, object(), engine)
    assert provider.calls == 2
