"""Conservative per-execution admission before whole-value materialization."""
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


MAX_CHARGE = 16 * 1024 * 1024
MAX_NODES = 100000
MESSAGE = ('Firebird materialized result exceeds the application budget. '
           'Use Run streaming or an explicitly smaller projection. '
           'The statement is not replayed, committed or rolled back; '
           'inspect the current transaction before deciding its outcome.')


class Budget:
    def __init__(self):
        self.charge = self.nodes = 0
        self.failed = False

    def reserve(self, charge, nodes=0):
        if (self.failed or charge < 0 or nodes < 0 or
                self.charge + charge > MAX_CHARGE or
                self.nodes + nodes > MAX_NODES):
            self.failed = True
            raise RelationalClientError(MESSAGE)
        self.charge += charge
        self.nodes += nodes

    def before(self, cursor):
        from firebird.driver.types import SQLDataType
        from .array_stream import ArrayReader
        self.reserve(64, 1)  # The row container itself.
        for desc in cursor._stmt._out_desc:
            self.reserve(256, 1)
            if cursor._stmt._out_buffer[desc.null_offset] != b'\0':
                continue
            if desc.datatype == SQLDataType.ARRAY:
                reader = ArrayReader(cursor, desc)
                try:
                    containers, count = 0, 1
                    for size in reader.dimensions:
                        containers += count
                        count *= size
                    self.reserve(count * (256 + reader.width * 6) +
                                 containers * 64, count + containers)
                finally:
                    reader.close()
            else:
                self.reserve(desc.length * 6)

    def after(self, values, blob_type):
        readers = [value for value in values if isinstance(value, blob_type)]
        result = list(values)
        try:
            for index, value in enumerate(values):
                if isinstance(value, blob_type):
                    self.reserve(value.length * 6)
                    if value.tell() != 0:
                        raise RelationalClientError(
                            'Firebird materialization requires an unread BLOB')
                    result[index] = value.read()
                    if value.tell() != value.length:
                        raise RelationalClientError(
                            'Firebird materialized BLOB read was incomplete')
            return tuple(result)
        finally:
            failure = None
            for reader in readers:
                try:
                    reader.close()
                except Exception as error:
                    if failure is None:
                        failure = error
            if failure is not None:
                raise failure
