import config  # Initialize application configuration before ORM imports.
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider, PROFILE
from pgadmin.cdeadmin.providers.firebird.embedded_provider import PROFILE as EMBEDDED_PROFILE
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('profile, filename', [(PROFILE, 'provider_manifest.json'), (EMBEDDED_PROFILE, 'embedded_provider_manifest.json')])
def test_native_identity_exactly_matches_admitted_manifest(profile, filename):
    provider = object.__new__(FirebirdProvider)
    provider.profile = profile
    package = Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/providers/firebird'
    assert provider._identity() == json.loads((package / filename).read_text())['identity']
    provider.profile = replace(profile, exact_version='unqualified')
    with pytest.raises(RelationalClientError):
        provider._identity()
