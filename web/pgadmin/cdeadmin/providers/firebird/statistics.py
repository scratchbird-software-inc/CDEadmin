"""Native Firebird5 statistics section admission shared by both transports."""
from collections.abc import Mapping
from ...sdk import RelationalClientError

FLAGS=frozenset({'DATA_PAGES','HDR_PAGES','IDX_PAGES','SYS_RELATIONS',
    'RECORD_VERSIONS','NOCREATION','ENCRYPTION','DEFAULT','NONE'})


def validate_options(options):
    if not isinstance(options,Mapping):raise RelationalClientError('Select typed statistics options')
    flags=options.get('statistics_flags')
    if flags is not None and (not isinstance(flags,list) or
            any(not isinstance(flag,str) or flag not in FLAGS for flag in flags)):
        raise RelationalClientError('Select supported native Firebird5 statistics sections; DB_LOG is obsolete')
