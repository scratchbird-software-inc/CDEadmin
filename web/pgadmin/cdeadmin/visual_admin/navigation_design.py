"""Checked-in native navigation layout; template IDs are never execution IDs."""
import copy
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _design():
    return json.loads(Path(__file__).with_name(
        'navigation_design.json').read_text())


def navigation_design(engine_id, profile_id=''):
    family = 'opensearch' if engine_id == 'opensearch_sql_ppl' else engine_id
    result = copy.deepcopy(_design()['engines'].get(family))
    if not result:
        return None
    if family == 'yugabytedb':
        ycql = 'ycql' in profile_id
        result['root']['children'] = [node for node in result['root']['children']
                                      if ('YCQL' in node['label']) == ycql]
    result['engine_id'] = engine_id
    result['profile_id'] = profile_id
    return result
