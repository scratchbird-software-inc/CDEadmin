"""Select a qualified conversion profile from the actual attached engine.

Firebird's GB18030 conversion depends on its loaded ICU data. The client OS
does not establish the server's conversion behavior. Observe the distinguishing
native mappings in a separate read-only transaction and cache on this attachment.
"""
from .attachment_codecs import codec_name, tables
from ...sdk.relational import RelationalClientError

PROFILES = ('GB18030', 'GB18030_LEGACY')


def probes():
    decoding, encoding = tables('GB18030')
    result = []
    for cp in sorted(encoding):
        utf8 = chr(cp).encode('utf8').hex()
        result.append(('encode', cp, 'CAST(CAST(CAST(x\'' + utf8 +
            "' AS VARCHAR(4) CHARACTER SET UTF8) AS VARCHAR(4) CHARACTER SET GB18030) "
            'AS VARCHAR(8) CHARACTER SET OCTETS)'))
    for raw in sorted(decoding):
        result.append(('decode', raw, 'CAST(CAST(CAST(x\'' + raw.hex() +
            "' AS VARCHAR(4) CHARACTER SET GB18030) AS VARCHAR(8) CHARACTER SET UTF8) "
            'AS VARCHAR(8) CHARACTER SET OCTETS)'))
    return tuple(result)


def query():
    parts = ['EXECUTE BLOCK RETURNS (K INTEGER, B VARCHAR(8) CHARACTER SET OCTETS) AS BEGIN']
    for index, (_, _, expression) in enumerate(probes()):
        parts.append(f'K={index}; B=NULL; BEGIN B={expression}; '
            'WHEN ANY DO BEGIN IF (GDSCODE NOT IN (335544321,335544849)) THEN EXCEPTION; END END SUSPEND;')
    return '\n'.join([*parts, 'END'])


def select(rows):
    observed = dict(rows)
    cases = probes()
    if set(observed) != set(range(len(cases))) or len(rows) != len(cases):
        raise RelationalClientError('Native GB18030 conversion observation is incomplete')
    for profile in PROFILES:
        name = codec_name(profile)
        expected = {}
        for index, (kind, value, _) in enumerate(cases):
            try:
                expected[index] = (chr(value).encode(name) if kind == 'encode'
                                   else value.decode(name).encode('utf8'))
            except UnicodeError:
                expected[index] = None
        if observed == expected:
            return name
    raise RelationalClientError('Native GB18030 conversion profile is not qualified')


def encoding(connection):
    cached = getattr(connection, '_cdeadmin_gb18030_encoding', None)
    if isinstance(cached, str):
        return cached
    from firebird.driver import tpb, Isolation, TraAccessMode
    manager = connection.transaction_manager(tpb(isolation=Isolation.READ_COMMITTED_RECORD_VERSION,
                                               access_mode=TraAccessMode.READ, lock_timeout=5))
    try:
        manager.begin()
        with manager.cursor() as cursor:
            cursor.execute(query())
            rows = cursor.fetchall()
        manager.rollback()
    finally:
        try:
            manager.close()
        except BaseException as error:
            failure = RelationalClientError('Native charset probe cleanup did not complete')
            failure.diagnostic_cleanup_failed = True
            raise failure from error
    selected = select(rows)
    connection._cdeadmin_gb18030_encoding = selected
    return selected
