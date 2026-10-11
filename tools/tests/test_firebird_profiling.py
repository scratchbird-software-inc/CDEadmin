"""Profiler failures cannot replace user outcomes or repeat dispatch."""
from unittest.mock import Mock, patch
import pytest
from tools.tests.test_firebird_async_queries import rig
from pgadmin.cdeadmin.providers.firebird.profiling import ProfileRun
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('stage', ['none', 'start', 'finish'])
def test_profiler_failure_preserves_execution_and_fences_uncertainty(rig, stage):
    profile = Mock(spec=ProfileRun)
    profile.receipt = {'state': 'complete'}
    profile.uncertain = stage in ('start', 'finish')
    if stage == 'start':
        profile.start.side_effect = RuntimeError('lost start reply')
    if stage == 'finish':
        profile.finish.side_effect = RuntimeError('lost finish reply')
    rig.finish.set()
    with patch('pgadmin.cdeadmin.providers.firebird.profiling.ProfileRun', return_value=profile):
        query = rig.client.submit_query(rig.handle, {'source': 'SELECT 42',
            'output_policy': {'firebird_profile': True}})
        query.worker.join(5)
        assert query.done
    result = rig.client.describe_result(query)['payload']
    assert result['execution_state'] == ('failed' if stage == 'start' else 'succeeded')
    assert rig.cursor.execute.call_count == (0 if stage == 'start' else 1)
    if stage != 'none':
        assert result['session_reuse_blocked']
        with pytest.raises(RelationalClientError, match='profiler state'):
            rig.client.submit_query(rig.handle, {'source': 'SELECT 42'})
        with rig.client._exclusive(rig.handle, closing=True):
            pass


@pytest.mark.parametrize('policy', [
    {'firebird_profile': 'yes'}, {'firebird_profile': True, 'firebird_script': True},
    {'firebird_profile': True, 'firebird_plan': True},
])
def test_profile_mode_refuses_ambiguous_execution(rig, policy):
    with pytest.raises(RelationalClientError):
        rig.client.submit_query(rig.handle, {'source': 'SELECT 42', 'output_policy': policy})
    rig.cursor.execute.assert_not_called()


def test_synchronous_profile_cannot_silently_run_without_profiling(rig):
    with pytest.raises(RelationalClientError, match='asynchronous'):
        rig.client.execute(rig.handle, {'source': 'SELECT 42', 'output_policy': {'firebird_profile': True}})
    rig.cursor.execute.assert_not_called()
