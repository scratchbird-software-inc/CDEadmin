"""Bounded, session-owned ARRAY parameter files; no native work at staging."""
import json
import math

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .result_stream import BlobUpload, PAGE_BYTES

FORMAT = 'cdeadmin.firebird-array.v1'
HEADER_KEYS = {'format', 'bounds', 'element_count', 'native_element_type',
               'scale', 'subtype', 'charset_id'}


def coordinates(bounds, offset):
    result = [0] * len(bounds)
    for index in range(len(bounds)-1, -1, -1):
        offset, position = divmod(offset, bounds[index][1]-bounds[index][0]+1)
        result[index] = bounds[index][0] + position
    return result


def invalid():
    raise RelationalClientError('Invalid or incomplete ARRAY parameter file')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            invalid()
        result[key] = value
    return result


class ArrayUpload(BlobUpload):
    kind = 'array'

    def _record(self):
        line = self.file.readline(PAGE_BYTES + 1)
        if not line or len(line) > PAGE_BYTES:
            invalid()
        try:
            value = json.loads(line.decode('utf8'),
                               object_pairs_hook=unique_object,
                               parse_constant=lambda _: invalid())
        except (ValueError, UnicodeError, RecursionError):
            invalid()
        if not isinstance(value, dict):
            invalid()
        return value

    def _header(self):
        value = self._record()
        if set(value) != HEADER_KEYS or value['format'] != FORMAT:
            invalid()
        bounds = value['bounds']
        if (not isinstance(bounds, list) or not 1 <= len(bounds) <= 16 or
                any(not isinstance(pair, list) or len(pair) != 2 or
                    any(type(n) is not int or not -(2**31) <= n < 2**31
                        for n in pair) or pair[1] < pair[0]
                    for pair in bounds)):
            invalid()
        count = math.prod(high-low+1 for low, high in bounds)
        if (type(value['element_count']) is not int or
                value['element_count'] != count or not 1 <= count < 2**31 or
                any(type(value[key]) is not int for key in (
                    'native_element_type', 'scale', 'subtype')) or
                (value['charset_id'] is not None and
                 type(value['charset_id']) is not int)):
            invalid()
        return value

    def _body(self, header):
        offset = 0
        while True:
            record = self._record()
            if set(record) == {'complete', 'element_count'}:
                if (record['complete'] is not True or
                        type(record['element_count']) is not int or
                        record['element_count'] != offset or
                        offset != header['element_count'] or
                        self.file.read(1)):
                    invalid()
                return
            if set(record) != {'offset', 'coordinates', 'values'}:
                invalid()
            values = record['values']
            point = coordinates(header['bounds'], offset)
            if (type(record['offset']) is not int or
                    record['offset'] != offset or
                    not isinstance(record['coordinates'], list) or
                    any(type(n) is not int for n in record['coordinates']) or
                    record['coordinates'] != point or
                    not isinstance(values, list) or not 1 <= len(values) <= 256
                    or len(values) > header['bounds'][-1][1] - point[-1] + 1
                    or offset + len(values) > header['element_count']):
                invalid()
            yield offset, values
            offset += len(values)

    def finish(self):
        self._check_usable()
        try:
            self.file.flush()
            self.file.seek(0)
            header = self._header()
            for _ in self._body(header):
                pass
            self.header = header
            self.ready = True
            self.file.seek(0)
            return self
        except BaseException:
            self.failed = True
            self.ready = False
            raise

    def chunks(self):
        self._check_usable()
        if not self.ready:
            invalid()
        self.file.seek(0)
        if self._header() != self.header:
            invalid()
        yield from self._body(self.header)
