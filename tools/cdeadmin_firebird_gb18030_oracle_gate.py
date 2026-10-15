"""Exhaustive native Firebird conversion evidence and provider equivalence."""
import argparse
import json
from pathlib import Path
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import _create_client  # noqa
from pgadmin.cdeadmin.providers.firebird.attachment_codecs import (
    codec_name,
)

ENCODE = '''EXECUTE BLOCK RETURNS(CP INTEGER, RAW_BYTES VARCHAR(4) CHARACTER
    SET OCTETS) AS
DECLARE I INTEGER=0;
DECLARE U VARCHAR(4) CHARACTER SET OCTETS;
BEGIN WHILE(I<1114112) DO BEGIN
 IF(I NOT BETWEEN 55296 AND 57343) THEN BEGIN
  IF(I<128) THEN U=ASCII_CHAR(I);
  ELSE IF(I<2048) THEN U=ASCII_CHAR(192+BIN_SHR(I,6)) ||
    ASCII_CHAR(128+BIN_AND(I,63));
  ELSE IF(I<65536) THEN U=ASCII_CHAR(224+BIN_SHR(I,12)) ||
    ASCII_CHAR(128+BIN_AND(BIN_SHR(I,6),63)) ||
    ASCII_CHAR(128+BIN_AND(I,63));
  ELSE U=ASCII_CHAR(240+BIN_SHR(I,18)) ||
    ASCII_CHAR(128+BIN_AND(BIN_SHR(I,12),63)) ||
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
 ELSE IF(I<65792) THEN U=ASCII_CHAR(BIN_SHR(I-256,8)) ||
    ASCII_CHAR(BIN_AND(I-256,255));
 ELSE U=ASCII_CHAR(129+(I-65792)/12600) ||
    ASCII_CHAR(48+MOD((I-65792)/1260,10)) ||
    ASCII_CHAR(129+MOD((I-65792)/10,126)) || ASCII_CHAR(48+MOD(I-65792,10));
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
    import hashlib
    with admin.cursor() as cur:
        for charset, codec, count in [('GB18030', 'gb18030', 1653392)]:
            result = {
                'charset': charset,
                'encode_differences': {},
                'decode_differences': {},
                'provider_encode_mismatches': {},
                'provider_decode_mismatches': {}}
            cur.execute(ENCODE.format(charset=charset))
            selected_codec = codec_name(charset)
            encoded = set()
            digest = hashlib.sha256()
            for cp, raw in cur:
                try:
                    actual = chr(cp).encode(selected_codec)
                except UnicodeError:
                    actual = None
                if actual != raw:
                    result['provider_encode_mismatches'][str(cp)] = {
                        'native': raw.hex(), 'provider': actual.hex() if actual is not None else None}
                encoded.add(cp)
                digest.update(cp.to_bytes(4, 'big') + raw)
                try:
                    expected = chr(cp).encode(codec)
                except UnicodeError:
                    expected = None
                if expected != raw:
                    result['encode_differences'][str(cp)] = raw.hex()
            result['encoded_count'] = len(encoded)
            result['encoded_sha256'] = digest.hexdigest()
            result['encode_rejected'] = [cp for cp in range(
                1114112) if not 55296 <= cp <= 57343 and cp not in encoded]
            (evidence / 'encode.json').write_text(
                json.dumps(result, indent=2) + '\n')
            cur.execute(DECODE.format(charset=charset, count=count))
            accepted = set()
            digest = hashlib.sha256()
            for raw, txt in cur:
                try:
                    actual = raw.decode(selected_codec)
                except UnicodeError:
                    actual = None
                if actual != txt:
                    result['provider_decode_mismatches'][raw.hex()] = {'native': txt, 'provider': actual}
                accepted.add(raw)
                digest.update(bytes([len(raw)]) + raw + txt.encode('utf8'))
                try:
                    expected = raw.decode(codec)
                except UnicodeError:
                    expected = None
                if expected != txt:
                    result['decode_differences'][raw.hex()] = txt
            result['decoded_count'] = len(accepted)
            result['decoded_sha256'] = digest.hexdigest()
            result['decode_rejected_python_accepts'] = []
            for i in range(count):
                if i < 256:
                    raw = bytes([i])
                elif i < 65792:
                    raw = (i - 256).to_bytes(2, 'big')
                else:
                    n = i - 65792
                    raw = bytes([129 + n // 12600,
                                 48 + n // 1260 % 10,
                                 129 + n // 10 % 126,
                                 48 + n % 10])
                if raw in accepted:
                    continue
                try:
                    raw.decode(selected_codec)
                except UnicodeDecodeError:
                    pass
                else:
                    result['provider_decode_mismatches'][raw.hex()] = {
                        'native': None, 'provider': raw.decode(selected_codec)}
                try:
                    raw.decode(codec)
                except UnicodeError:
                    continue
                result['decode_rejected_python_accepts'].append(raw.hex())
            (evidence / 'GB18030.json').write_text(
                json.dumps(result, indent=2) + '\n')
            assert not result['provider_encode_mismatches'], 'Native GB18030 encode profile differs; see receipt'
            assert not result['provider_decode_mismatches'], 'Native GB18030 decode profile differs; see receipt'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
