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

import json
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
