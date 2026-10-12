"""Exhaustive native Firebird conversion evidence and provider equivalence."""
import argparse
import json
import time
from pathlib import Path
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import _create_client  # noqa
from pgadmin.cdeadmin.providers.firebird.attachment_codecs import (
    PRIVATE_CHARSETS, codec_name,
)
from firebird.driver.core import CHARSET_MAP

ENCODE = '''EXECUTE BLOCK RETURNS(CP INTEGER, RAW_BYTES VARCHAR(4) CHARACTER
    SET OCTETS) AS
DECLARE I INTEGER=0;
DECLARE U VARCHAR(4) CHARACTER SET OCTETS;
BEGIN WHILE(I<65536) DO BEGIN
 IF(I NOT BETWEEN 55296 AND 57343) THEN BEGIN
  IF(I<128) THEN U=ASCII_CHAR(I);
  ELSE IF(I<2048) THEN U=ASCII_CHAR(192+BIN_SHR(I,6)) ||
    ASCII_CHAR(128+BIN_AND(I,63));
  ELSE U=ASCII_CHAR(224+BIN_SHR(I,12)) ||
    ASCII_CHAR(128+BIN_AND(BIN_SHR(I,6),63)) ||
    ASCII_CHAR(128+BIN_AND(I,63));
  BEGIN
   CP=I;
   RAW_BYTES=CAST(CAST(CAST(U AS VARCHAR(4) CHARACTER SET UTF8) AS
    VARCHAR(4) CHARACTER SET {charset}) AS VARCHAR(4) CHARACTER SET OCTETS);
   SUSPEND;
   WHEN ANY DO BEGIN IF(GDSCODE NOT IN (335544321,335544849)) THEN
    EXCEPTION; END
  END
 END
 I=I+1;
END END'''
DECODE = '''EXECUTE BLOCK RETURNS(RAW_BYTES VARCHAR(4) CHARACTER SET OCTETS,
    TXT VARCHAR(8) CHARACTER SET UTF8) AS
DECLARE I INTEGER=0;
DECLARE U VARCHAR(4) CHARACTER SET OCTETS;
BEGIN WHILE(I<{count}) DO BEGIN
 IF(I<256) THEN U=ASCII_CHAR(I);
 ELSE U=ASCII_CHAR(BIN_SHR(I-256,8)) || ASCII_CHAR(BIN_AND(I-256,255));
 BEGIN
  RAW_BYTES=U;
  TXT=CAST(CAST(U AS VARCHAR(4) CHARACTER SET {charset}) AS VARCHAR(8)
    CHARACTER SET UTF8);
  SUSPEND;
  WHEN ANY DO BEGIN IF(GDSCODE NOT IN (335544321,335544849)) THEN EXCEPTION;
    END
 END
 I=I+1;
END END'''


def qualify(native, admin, route, accounts, evidence, root):
    checks = []
    with admin.cursor() as cur:
        cur.execute(
            'SELECT RDB$CHARACTER_SET_ID, TRIM(RDB$CHARACTER_SET_NAME), '
            'RDB$BYTES_PER_CHARACTER FROM RDB$CHARACTER_SETS ORDER BY 1')
        charsets = cur.fetchall()
        for identifier, name, width in charsets:
            if name in ('NONE', 'OCTETS', 'UTF8', 'UNICODE_FSS', 'GB18030'):
                continue
            start = time.monotonic()
            cur.execute(ENCODE.format(charset=name))
            encoding = {str(cp): raw.hex() for cp, raw in cur.fetchall()}
            try:
                cur.execute(
                    DECODE.format(
                        charset=name,
                        count=256 if width == 1 else 65792))
            except Exception as error:
                print(name, type(error).__name__, flush=True)
                raise
            try:
                decoded = {raw.hex(): txt for raw, txt in cur.fetchall()}
            except Exception as error:
                print(name, type(error).__name__, flush=True)
                raise
            # Sequences that decode to two ordinary single-byte characters
            # are compositions, not an additional indivisible character.
            decoding = {
                raw: ord(txt) for raw,
                txt in decoded.items() if len(txt) == 1}
            codec = codec_name(
                name) if name in PRIVATE_CHARSETS else CHARSET_MAP[name]
            for raw, text in decoded.items():
                assert bytes.fromhex(raw).decode(codec) == text, (name, raw)
            for cp in range(65536):
                try:
                    actual = chr(cp).encode(codec).hex()
                except UnicodeEncodeError:
                    actual = None
                assert actual == encoding.get(str(cp)), (name, cp)
            compositions = 0
            for raw, text in decoded.items():
                if len(text) != 1:
                    data = bytes.fromhex(raw)
                    assert len(data) == 2
                    expected = (chr(decoding[data[:1].hex()]) +
                                chr(decoding[data[1:].hex()]))
                    assert text == expected, (name, raw, text)
                    compositions += 1
            result = {
                'charset': name,
                'id': identifier,
                'width': width,
                'decode': decoding,
                'encode': encoding,
                'native_compositions': compositions,
                'native_sequences_accepted': len(decoded),
                'native_sequences_tested': 256 if width == 1 else 65792,
                'elapsed_seconds': time.monotonic() - start}
            (evidence / (name + '.json')
             ).write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
            checks.append(
                {
                    key: result[key] for key in (
                        'charset',
                        'id',
                        'width',
                        'native_compositions',
                        'native_sequences_accepted',
                        'native_sequences_tested',
                        'elapsed_seconds')})
            (evidence / 'checks.json').write_text(
                json.dumps(checks, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
