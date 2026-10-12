"""Derive conversion facts from an owned Firebird 5.0.4 engine."""
import argparse
import json
from pathlib import Path
from tools.cdeadmin_firebird_local_fixture import run_local


def qualify(native, admin, route, accounts, evidence, root):
    for charset in ('NEXT', 'TIS620', 'CYRL', 'CP943C'):
        result = {'charset': charset, 'decode': {}, 'encode': {},
                  'decode_rejected': 0, 'encode_rejected': 0}
        with admin.cursor() as cur:
            candidates = [bytes([x]) for x in range(256)]
            if charset == 'CP943C':
                leads = (*range(0x81, 0xa0), *range(0xe0, 0xfd))
                candidates += [bytes([a, b])
                               for a in leads for b in range(256)]
            for raw in candidates:
                try:
                    cur.execute(
                        f"SELECT CAST(CAST(x'{raw.hex()}' AS VARCHAR(2) "
                        f"CHARACTER SET {charset}) AS VARCHAR(8) "
                        "CHARACTER SET UTF8) FROM RDB$DATABASE")
                    value = cur.fetchone()[0]
                    assert len(value) == 1, (charset, raw, value)
                    result['decode'][raw.hex()] = ord(value)
                except native.DatabaseError:
                    result['decode_rejected'] += 1
            # All BMP codepoints include aliases not emitted by decoding.
            for code in range(65536):
                if 0xd800 <= code <= 0xdfff:
                    continue
                raw = chr(code).encode('utf8')
                try:
                    cur.execute(
                        f"SELECT CAST(CAST(CAST(x'{raw.hex()}' AS VARCHAR(4) "
                        "CHARACTER SET UTF8) AS VARCHAR(2) "
                        f"CHARACTER SET {charset}) AS VARCHAR(4) "
                        "CHARACTER SET OCTETS) FROM RDB$DATABASE")
                    value = cur.fetchone()[0]
                    assert isinstance(value, bytes), type(value)
                    result['encode'][str(code)] = value.hex()
                except native.DatabaseError:
                    result['encode_rejected'] += 1
        (evidence/(charset+'.json')
         ).write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
