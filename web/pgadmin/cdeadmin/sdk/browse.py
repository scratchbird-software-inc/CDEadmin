##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Browse data text helpers (owner direction 2026-11-06).

Browse data puts text in a connector's query editor that reads every record
of one resource; it is never run by CDEadmin. Each provider decides the form
in its own language. These helpers keep the shared parts (finding a
relation's columns in the cached catalog, SQL quoting and layout) in one
place, so no provider re-derives them.
"""

from __future__ import annotations

import functools
import json
import re
from typing import Any, Callable, Iterable, Mapping, Sequence


class BrowseUnavailable(ValueError):
    """The resource cannot be read from the connector's editor."""


def native_of(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    """Native metadata of a raw client resource or an admitted one."""
    if isinstance(resource.get('native'), Mapping):
        return resource['native']
    for value in (resource.get('extensions') or {}).values():
        if isinstance(value, Mapping) and isinstance(
                value.get('native'), Mapping):
            return value['native']
    return {}


def _position(native: Mapping[str, Any]):
    for value in (native.get('ordinal_position'), native.get('position'),
                  (native.get('catalog_metadata') or {}).get(
                      'ordinal_position')):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def path_columns(
    resource: Mapping[str, Any], catalog: Iterable[Mapping[str, Any]], *,
    kind: str = 'column',
    exclude: Callable[[Mapping[str, Any]], bool] | None = None,
) -> list[str]:
    """Column names of a relation, in table order.

    Columns are the catalog's ``kind`` resources whose display path is the
    relation's path plus the column name. They are ordered by their
    ordinal position when every column carries one, otherwise in catalog
    order (the catalog query's own ordering).
    """
    path = list(resource.get('display_path') or ())
    found = [item for item in catalog
             if item.get('resource_kind') == kind and
             list(item.get('display_path') or ())[:-1] == path and
             not (exclude and exclude(native_of(item)))]
    positions = [_position(native_of(item)) for item in found]
    if found and all(position is not None for position in positions):
        found = [item for _position_value, _index, item in sorted(
            zip(positions, range(len(found)), found))]
    return [str(item.get('display_name')) for item in found]


def quote(name: str, open_quote: str = '"',
          close_quote: str | None = None) -> str:
    """A delimited identifier; the closing quote is doubled inside it."""
    close_quote = close_quote or open_quote
    return open_quote + str(name).replace(
        close_quote, close_quote * 2) + close_quote


class SqlNames:
    """Writes the names of one SQL dialect, delimiting only those that need it.

    Owner direction 2026-11-06: quote only names that need it. A name is
    written bare when the dialect reads it back as the same name: it
    matches ``regular``, the dialect's undelimited identifier form in the
    case the dialect folds undelimited names to, and it is not one of the
    ``reserved`` keywords (upper case; compared without regard to case).
    Every other name is delimited. Without a keyword list (``reserved`` is
    None) every name is delimited, since any of them could be a keyword.
    """

    def __init__(self, open_quote: str = '"',
                 close_quote: str | None = None, *,
                 regular: re.Pattern | None = None,
                 reserved: frozenset[str] | None = None):
        self.open_quote = open_quote
        self.close_quote = close_quote or open_quote
        self.regular = regular
        self.reserved = reserved

    def bare(self, name: str) -> bool:
        """Whether ``name`` can be written without delimiters."""
        return (self.regular is not None and self.reserved is not None and
                self.regular.fullmatch(name) is not None and
                name.upper() not in self.reserved)

    def __call__(self, name: str) -> str:
        name = str(name)
        if self.bare(name):
            return name
        return quote(name, self.open_quote, self.close_quote)


_KEYWORD = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*')


def contract_keywords(
    provider: Any, select: Callable[[Mapping[str, Any]], bool],
) -> frozenset[str] | None:
    """Keywords of the provider's dialect contract that ``select`` picks.

    The words come from the contract's lexical rules, upper case; rows that
    are operators or punctuation are skipped. None when the provider has
    no dialect contract or the contract lists no keywords.
    """
    filename = getattr(getattr(provider, 'profile', None),
                       'dialect_contract_file', None)
    if not filename:
        return None
    return _contract_keywords(type(provider).__module__, filename, select)


@functools.lru_cache(maxsize=None)
def _contract_keywords(provider_module, filename, select):
    # Imported where used, as actual_engine imports it.
    from pgadmin.cdeadmin.engine_contracts import _load_provider_document
    document, _digest = _load_provider_document(provider_module, filename)
    rows = (document.get('inventories') or {}).get('lexical_rules')
    if not isinstance(rows, list) or not rows:
        return None
    return frozenset(
        str(row['native_name']).upper() for row in rows
        if isinstance(row, Mapping) and
        _KEYWORD.fullmatch(str(row.get('native_name') or '')) and
        select(row))


def sql_select(columns: Sequence[str], relation: Sequence[str],
               identifier: Callable[[str], str]) -> str:
    """``SELECT <columns>`` / ``FROM <relation>``; ``*`` with no columns."""
    if not relation:
        raise BrowseUnavailable('The object has no name to read from.')
    listed = ', '.join(identifier(name) for name in columns) or '*'
    return 'SELECT {0}\nFROM {1}'.format(
        listed, '.'.join(identifier(part) for part in relation))


def json_source(value: Mapping[str, Any]) -> str:
    """A JSON command for editors whose language is JSON."""
    return json.dumps(value, ensure_ascii=False, indent=2)
