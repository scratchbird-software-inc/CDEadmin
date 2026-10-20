"""Both native transports share only exactly identical, unbound SQL contracts."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.data_studio import DataStudioService,DataStudioError
from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider,PROFILE
from pgadmin.cdeadmin.providers.firebird.embedded_provider import EmbeddedFirebirdProvider,PROFILE as EMBEDDED


def binding(profile,cls):
    provider=object.__new__(cls);provider.profile=profile
    provider.client=SimpleNamespace(transaction_actions=frozenset({'commit','rollback','autocommit_on','autocommit_off'}))
    return SimpleNamespace(instance=provider,manifest={'identity':provider._identity()})


@pytest.mark.parametrize('embedded_first',[False,True])
def test_identical_native_language_ports_are_shared_in_both_orders(embedded_first):
    service=DataStudioService(Mock())
    ports=[binding(PROFILE,FirebirdProvider),binding(EMBEDDED,EmbeddedFirebirdProvider)]
    if embedded_first:ports.reverse()
    for port in ports:service._ensure_contributions(port)
    assert len(service.contributions.languages())==1
    assert len(service._contributed_providers)==2
    for port in ports:
        key=(port.manifest['identity']['provider_id'],port.manifest['identity']['provider_version'])
        assert service._provider_languages[key]==('firebird-sql',)
    assert getattr(service.contributions.session('firebird-sql').open_session,'__self__',None) is None


def test_conflicting_provider_bundle_leaves_no_partial_contributions():
    service=DataStudioService(Mock())
    first=binding(PROFILE,FirebirdProvider);service._ensure_contributions(first)
    before={key:dict(getattr(service.contributions,'_'+key)) for key in ('languages','completions','sessions','executions')}
    other=binding(EMBEDDED,EmbeddedFirebirdProvider)
    payload=other.instance.data_studio_contributions()
    payload['languages']=(replace(payload['languages'][0],language_profile='owned-new-language'),)
    payload['executions']=(replace(payload['executions'][0],contribution_id='conflicting-native-port'),)
    other.instance.data_studio_contributions=lambda:payload
    with pytest.raises(DataStudioError,match='Conflicting'):service._ensure_contributions(other)
    for key,value in before.items():assert getattr(service.contributions,'_'+key)==value
    assert len(service._contributed_providers)==1
