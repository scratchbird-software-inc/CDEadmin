"""Identifier spelling for the admitted Firebird 5.0.4 query profile.

Catalog names are identities, not SQL tokens: never uppercase or strip them.
An uppercase ASCII regular name can be emitted bare unless it is reserved.
The lexical classifications are captured from the same native version as the
provider, not a generic SQL keyword list or the editor's highlight words.
"""
from functools import lru_cache
import re

from pgadmin.cdeadmin.sdk.browse import SqlNames


@lru_cache(maxsize=1)
def query_names():
    from pgadmin.cdeadmin.engine_contracts import _load_provider_document

    document, _digest = _load_provider_document(
        __name__, 'firebird_dialect_5_0_4.json')
    reserved = frozenset(
        row['native_name'] for row in document['inventories']['lexical_rules']
        if re.fullmatch(r'[A-Z][A-Z0-9_$]*', row['native_name']) and
        row.get('non_reserved') is not True)
    return SqlNames('"', regular=re.compile(r'[A-Z][A-Z0-9_$]*'),
                    reserved=reserved)
