"""Retained Neo4j transaction ownership and lossless Bolt values."""
import base64
import json
import math

from .client import Neo4jClient, Neo4jClientError
from ..native_distributed import NativeResult
from ..retained_native import RetainedNativeClient


def exact(value):
    from neo4j.graph import Node, Relationship, Path
    from neo4j.spatial import Point
    from neo4j.time import Date, DateTime, Time, Duration
    from neo4j.vector import Vector

    if isinstance(value, Node):
        return {
            'kind': 'node',
            'element_id': value.element_id,
            'labels': sorted(
                value.labels),
            'properties': exact(
                dict(value))}
    if isinstance(value, Relationship):
        return {'kind': 'relationship', 'element_id': value.element_id,
                'type': value.type, 'properties': exact(dict(value)),
                'start_node_element_id': value.start_node.element_id,
                'end_node_element_id': value.end_node.element_id}
    if isinstance(value, Path):
        return {'kind': 'path', 'nodes': [exact(n) for n in value.nodes],
                'relationships': [exact(r) for r in value.relationships]}
    if isinstance(value, Point):
        return {'$neo4j_point': {'srid': value.srid,
                                 'coordinates': list(value)}}
    if isinstance(value, (Date, DateTime, Time, Duration)):
        return {'$neo4j_temporal': {'type': type(value).__name__,
                                    'value': value.iso_format()}}
    if isinstance(value, Vector):
        return {
            '$neo4j_vector': {
                'dtype': value.dtype.value,
                'data': base64.b64encode(
                    value.raw()).decode()}}
    if isinstance(value, (bytes, bytearray)):
        return {'$binary': base64.b64encode(value).decode()}
    if type(value) is int and abs(value) > 2**53 - 1:
        return {'$integer': str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        return {'$float': str(value)}
    if isinstance(value, dict):
        return {k: exact(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [exact(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise Neo4jClientError('Bolt value has no lossless representation')


def parameters_native(value):
    from neo4j.spatial import CartesianPoint, WGS84Point
    from neo4j.time import Date, DateTime, Time, Duration
    from neo4j.vector import Vector

    if isinstance(value, dict):
        if set(value) == {'$integer'}:
            text = value['$integer']
            number = int(text)
            if str(number) != text or not -(2**63) <= number < 2**63:
                raise Neo4jClientError('Bolt integer is invalid')
            return number
        if set(value) == {'$binary'}:
            return bytearray(base64.b64decode(value['$binary'], validate=True))
        if set(value) == {'$float'}:
            if value['$float'] not in {'nan', 'inf', '-inf'}:
                raise Neo4jClientError('Bolt float is invalid')
            return float(value['$float'])
        if set(value) == {'$neo4j_temporal'}:
            native = value['$neo4j_temporal']
            types = {'Date': Date, 'DateTime': DateTime, 'Time': Time,
                     'Duration': Duration}
            return types[native['type']].from_iso_format(native['value'])
        if set(value) == {'$neo4j_point'}:
            native = value['$neo4j_point']
            srid = native['srid']
            if srid not in {7203, 9157, 4326, 4979}:
                raise Neo4jClientError('Bolt point SRID invalid')
            cls = CartesianPoint if srid in {7203, 9157} else WGS84Point
            result = cls(native['coordinates'])
            if result.srid != srid:
                raise Neo4jClientError('Bolt point dimensions invalid')
            return result
        if set(value) == {'$neo4j_vector'}:
            native = value['$neo4j_vector']
            return Vector.from_bytes(base64.b64decode(native['data'],
                                                      validate=True),
                                     native['dtype'])
        return {k: parameters_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [parameters_native(v) for v in value]
    return value


class Neo4jDriverBackend(Neo4jClient):
    def iterate(self, owner, source, parameters):
        if not isinstance(source, str):
            raise Neo4jClientError('Cypher source must be text')
        if parameters is not None and not isinstance(parameters, dict):
            raise Neo4jClientError('Cypher parameters must be named')
        runner = owner.transaction or owner.session
        result = runner.run(source, parameters_native(parameters or {}))
        names = list(result.keys())
        columns = [{'name': name, 'type': 'neo4j-value', 'ordinal': i}
                   for i, name in enumerate(names)]
        rows, size, offset = [], 0, 0
        for record in result:
            # Record.data() flattens Nodes and drops labels/element IDs.
            row = [exact(v) for v in record.values()]
            length = len(json.dumps(row).encode())
            if rows and (len(rows) >= 256 or size + length > 1048576):
                yield self._page(rows, names, columns, offset)
                offset += len(rows)
                rows, size = [], 0
            rows.append(row)
            size += length
        summary = self._summary(result.consume())
        summary['bookmarks'] = sorted(
            owner.session.last_bookmarks().raw_values)
        yield self._page(rows, names, columns, offset, summary)

    @staticmethod
    def _page(rows, names, columns, offset, summary=None):
        return NativeResult('graph', 'graphs',
                            [dict(zip(names, row)) for row in rows],
                            {'columns': columns, 'summary': summary},
                            {'row_offset': offset, 'result_set_index': 0,
                             'ordinal_rows': rows, 'summary': summary})

    def close_session(self, owner, unknown=False):
        # The synchronous driver has no public Session.cancel(). Its close
        # owns cleanup (including consumption of an auto-commit result).
        # This never resolves an outcome that the provider marked unknown.
        owner.session.close()
        owner.driver.close()
        owner.closed = True
        if owner in self._sessions:
            self._sessions.remove(owner)
        if owner.driver in self._drivers:
            self._drivers.remove(owner.driver)

    def close(self):
        for owner in list(self._sessions):
            self.close_session(owner, True)
        super().close()

    @staticmethod
    def complete(_request):
        return []


class Neo4jDriver(RetainedNativeClient):
    transaction_actions = ('begin', 'commit', 'rollback')

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

    def describe_transaction(self, session):
        with session.lock:
            if session.active is None and not session.blocked:
                session.observation = session.worker.submit(
                    self.backend.describe_transaction, session.handle).result()
            return super().describe_transaction(session)
