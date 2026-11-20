"""Pure-Python MySQL X Protocol (port 33060 / mysqlx.sock) wire client.

Implements length-prefixed Protobuf framing for Mysqlx.Connection,
Mysqlx.Session, Mysqlx.Sql.StmtExecute (both 'mysqlx' admin namespace and 'sql'
namespace), and Mysqlx.Crud (Document Insert, Find, Update, Delete) directly
over Python sockets/TLS with zero external vendor CLI dependencies.
"""
import hashlib
import json
import re
import socket
import ssl
import struct

# ClientMessages.Type
CLI_CON_CAPABILITIES_GET = 1
CLI_CON_CAPABILITIES_SET = 2
CLI_CON_CLOSE = 3
CLI_SESS_AUTHENTICATE_START = 4
CLI_SESS_AUTHENTICATE_CONTINUE = 5
CLI_SESS_CLOSE = 7
CLI_SQL_STMT_EXECUTE = 12
CLI_CRUD_FIND = 17
CLI_CRUD_INSERT = 18
CLI_CRUD_UPDATE = 19
CLI_CRUD_DELETE = 20

# ServerMessages.Type
SRV_OK = 0
SRV_ERROR = 1
SRV_CONN_CAPABILITIES = 2
SRV_SESS_AUTHENTICATE_CONTINUE = 3
SRV_SESS_AUTHENTICATE_OK = 4
SRV_NOTICE = 11
SRV_RESULTSET_COLUMN_META_DATA = 12
SRV_RESULTSET_ROW = 13
SRV_RESULTSET_FETCH_DONE = 14
SRV_RESULTSET_FETCH_SUSPENDED = 15
SRV_RESULTSET_FETCH_DONE_MORE_RESULTSETS = 16
SRV_SQL_STMT_EXECUTE_OK = 17
SRV_RESULTSET_FETCH_DONE_MORE_OUT_PARAMS = 18


class XProtocolError(Exception):
    def __init__(self, message, *, errno=None, sqlstate=None, severity=0):
        super().__init__(message)
        self.errno = errno
        self.sqlstate = sqlstate
        self.severity = severity


# --- Minimal Protobuf wire primitives ---

def _enc_varint(val):
    if val < 0:
        val += 1 << 64
    out = bytearray()
    while val > 0x7F:
        out.append((val & 0x7F) | 0x80)
        val >>= 7
    out.append(val & 0x7F)
    return bytes(out)


def _dec_varint(buf, pos=0):
    result = 0
    shift = 0
    length = len(buf)
    while pos < length:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            raise XProtocolError('Malformed protobuf varint in X Protocol stream')
    raise XProtocolError('Truncated protobuf varint in X Protocol stream')


def _enc_zigzag64(val):
    return _enc_varint((val << 1) ^ (val >> 63))


def _dec_zigzag64(uval):
    return (uval >> 1) ^ -(uval & 1)


def _f_varint(field_no, val):
    return _enc_varint((field_no << 3) | 0) + _enc_varint(val)


def _f_sint64(field_no, val):
    return _enc_varint((field_no << 3) | 0) + _enc_zigzag64(val)


def _f_double(field_no, val):
    return _enc_varint((field_no << 3) | 1) + struct.pack('<d', float(val))


def _f_bytes(field_no, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return _enc_varint((field_no << 3) | 2) + _enc_varint(len(data)) + data


def _parse_pb(buf):
    fields = {}
    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _dec_varint(buf, pos)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:
            val, pos = _dec_varint(buf, pos)
        elif wire_type == 1:
            if pos + 8 > end:
                raise XProtocolError('Truncated 64-bit protobuf field')
            val = buf[pos:pos + 8]
            pos += 8
        elif wire_type == 2:
            ln, pos = _dec_varint(buf, pos)
            if pos + ln > end:
                raise XProtocolError('Truncated length-delimited protobuf field')
            val = buf[pos:pos + ln]
            pos += ln
        elif wire_type == 5:
            if pos + 4 > end:
                raise XProtocolError('Truncated 32-bit protobuf field')
            val = buf[pos:pos + 4]
            pos += 4
        else:
            raise XProtocolError(f'Unsupported protobuf wire type {wire_type}')
        fields.setdefault(field_no, []).append(val)
    return fields


# --- Mysqlx.Datatypes encoders ---

def encode_scalar(val, *, json_octets=False):
    # Mysqlx.Datatypes.Scalar:
    # type=1 (V_SINT=1, V_UINT=2, V_NULL=3, V_OCTETS=4, V_DOUBLE=5, V_BOOL=7, V_STRING=8)
    # v_signed_int=2, v_unsigned_int=3, v_octets=5, v_double=6, v_bool=8, v_string=9
    if val is None:
        return _f_varint(1, 3)
    if isinstance(val, bool):
        return _f_varint(1, 7) + _f_varint(8, 1 if val else 0)
    if isinstance(val, int):
        if val >= 0:
            return _f_varint(1, 2) + _f_varint(3, val)
        return _f_varint(1, 1) + _f_sint64(2, val)
    if isinstance(val, float):
        return _f_varint(1, 5) + _f_double(6, val)
    if isinstance(val, (bytes, bytearray)):
        octets_msg = _f_bytes(1, bytes(val)) + (_f_varint(2, 2) if json_octets else b'')
        return _f_varint(1, 4) + _f_bytes(5, octets_msg)
    if isinstance(val, str):
        if json_octets:
            octets_msg = _f_bytes(1, val.encode('utf-8')) + _f_varint(2, 2)
            return _f_varint(1, 4) + _f_bytes(5, octets_msg)
        str_msg = _f_bytes(1, val.encode('utf-8'))
        return _f_varint(1, 8) + _f_bytes(9, str_msg)
    raise XProtocolError(f'Unsupported X Protocol scalar type: {type(val).__name__}')


def encode_any(val):
    # Mysqlx.Datatypes.Any: type=1 (SCALAR=1, OBJECT=2, ARRAY=3), scalar=2, obj=3, array=4
    if isinstance(val, dict):
        flds = b''.join(
            _f_bytes(1, _f_bytes(1, str(k)) + _f_bytes(2, encode_any(v)))
            for k, v in val.items()
        )
        return _f_varint(1, 2) + _f_bytes(3, flds)
    if isinstance(val, (list, tuple)):
        items = b''.join(_f_bytes(1, encode_any(item)) for item in val)
        return _f_varint(1, 3) + _f_bytes(4, items)
    return _f_varint(1, 1) + _f_bytes(2, encode_scalar(val))


# --- Mysqlx.Expr encoders for Document CRUD ---

_DOC_PATH_RE = re.compile(r'\.([A-Za-z0-9_$-]+)|\[([0-9]+)\]')


def parse_document_path(path):
    """Parse a JSON path like '$.status' or 'status' or '$.items[0].price' into DocumentPathItem list."""
    if not isinstance(path, str) or not path or '\x00' in path or len(path) > 256:
        raise XProtocolError('Document path requires 1 to 256 characters without NUL')
    text = path[1:] if path.startswith('$') else ('.' + path if not path.startswith(('.', '[')) else path)
    if not text:
        # Root '$' path
        return []
    pos = 0
    items = []
    while pos < len(text):
        m = _DOC_PATH_RE.match(text, pos)
        if not m:
            raise XProtocolError(f'Invalid X document member path: {path}')
        if m.group(1) is not None:
            # DocumentPathItem: type=1 (MEMBER=1), value=2
            items.append(_f_varint(1, 1) + _f_bytes(2, m.group(1)))
        else:
            # DocumentPathItem: type=1 (ARRAY_INDEX=3), index=3
            items.append(_f_varint(1, 3) + _f_varint(3, int(m.group(2))))
        pos = m.end()
    return items


def encode_doc_column_identifier(path):
    # ColumnIdentifier: repeated DocumentPathItem document_path = 1
    if path == '_id' or path == '$._id':
        return _f_bytes(1, _f_varint(1, 1) + _f_bytes(2, '_id'))
    items = parse_document_path(path)
    return b''.join(_f_bytes(1, item) for item in items)


def encode_expr_literal(val, *, json_octets=False):
    # Expr: type=1 (LITERAL=2), literal=4
    return _f_varint(1, 2) + _f_bytes(4, encode_scalar(val, json_octets=json_octets))


def encode_expr_placeholder(position):
    # Expr: type=1 (PLACEHOLDER=6), position=7
    return _f_varint(1, 6) + _f_varint(7, position)


def encode_expr_doc_ident(path):
    # Expr: type=1 (IDENT=1), identifier=2
    return _f_varint(1, 1) + _f_bytes(2, encode_doc_column_identifier(path))


def encode_expr_operator(op_name, *exprs):
    # Operator: name=1, repeated Expr param=2
    op_msg = _f_bytes(1, op_name) + b''.join(_f_bytes(2, e) for e in exprs)
    # Expr: type=1 (OPERATOR=5), operator=6
    return _f_varint(1, 5) + _f_bytes(6, op_msg)


ALLOWED_FILTER_OPS = {
    '==': '==',
    '=': '==',
    '!=': '!=',
    '<>': '!=',
    '<': '<',
    '<=': '<=',
    '>': '>',
    '>=': '>=',
}


def build_criteria_expr(predicates, combinator='AND'):
    """Build a parameterized Mysqlx.Expr.Expr + Scalar args tuple from typed predicates."""
    if not predicates:
        return None, ()
    if combinator not in {'AND', 'OR'}:
        raise XProtocolError('Filter combinator must be AND or OR')
    args = []
    clauses = []
    for pred in predicates:
        field_path = pred['path']
        op = ALLOWED_FILTER_OPS.get(pred.get('operator', '=='))
        if op is None:
            raise XProtocolError(f"Unsupported filter operator: {pred.get('operator')}")
        left = encode_expr_doc_ident(field_path)
        val = pred.get('value')
        if val is None and op in {'==', '!='}:
            clauses.append(encode_expr_operator('is' if op == '==' else 'is_not', left, encode_expr_literal(None)))
        else:
            pos = len(args)
            args.append(encode_scalar(val))
            clauses.append(encode_expr_operator(op, left, encode_expr_placeholder(pos)))
    expr = clauses[0]
    join_op = '&&' if combinator == 'AND' else '||'
    for nxt in clauses[1:]:
        expr = encode_expr_operator(join_op, expr, nxt)
    return expr, tuple(args)


def _decode_row_cell(raw, col_type):
    if len(raw) == 0:
        return None
    if col_type == 1:  # SINT
        uval, _ = _dec_varint(raw, 0)
        return _dec_zigzag64(uval)
    if col_type == 2:  # UINT
        uval, _ = _dec_varint(raw, 0)
        return uval
    if col_type == 5:  # DOUBLE
        return struct.unpack('<d', raw[:8])[0]
    if col_type == 6:  # FLOAT
        return struct.unpack('<f', raw[:4])[0]
    if col_type in (7, 16):  # BYTES / ENUM (trailing \x00 terminator)
        payload = raw[:-1] if raw.endswith(b'\x00') else raw
        try:
            return payload.decode('utf-8')
        except UnicodeDecodeError:
            return payload.hex()
    return raw.hex()


def _mysql41_scramble(password_bytes, salt):
    if not password_bytes:
        return b''
    h1 = hashlib.sha1(password_bytes).digest()
    h2 = hashlib.sha1(h1).digest()
    h3 = hashlib.sha1(salt + h2).digest()
    return bytes(a ^ b for a, b in zip(h1, h3))


def _sha256_memory_scramble(password_bytes, salt):
    if not password_bytes:
        return b''
    h1 = hashlib.sha256(password_bytes).digest()
    h2 = hashlib.sha256(h1).digest()
    h3 = hashlib.sha256(h2 + salt).digest()
    return bytes(a ^ b for a, b in zip(h1, h3)).hex().upper().encode('ascii')


class XProtocolSession:
    """Dedicated single-operation MySQL X Protocol session."""

    def __init__(self, sock):
        self._sock = sock
        self.closed = False

    @classmethod
    def connect(
        cls,
        *,
        host='127.0.0.1',
        port=33060,
        unix_socket=None,
        user='root',
        password='',
        schema='',
        timeout=10.0,
        use_tls=True,
        ssl_ca=None,
        ssl_verify_cert=False,
    ):
        raw_sock = None
        try:
            if unix_socket:
                raw_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                raw_sock.settimeout(timeout)
                raw_sock.connect(unix_socket)
                is_secure = True
            else:
                raw_sock = socket.create_connection((host, int(port)), timeout=timeout)
                raw_sock.settimeout(timeout)
                is_secure = False
            sess = cls(raw_sock)
            if not unix_socket and use_tls:
                # Request TLS upgrade via CapabilitiesSet(tls=True)
                cap_tls = _f_bytes(1, 'tls') + _f_bytes(2, encode_any(True))
                caps = _f_bytes(1, cap_tls)
                sess._send(CLI_CON_CAPABILITIES_SET, _f_bytes(1, caps))
                msg_type, payload = sess._recv_non_notice()
                if msg_type == SRV_ERROR:
                    sess._raise_error(payload)
                if msg_type != SRV_OK:
                    raise XProtocolError(f'Unexpected X TLS capability reply type {msg_type}')
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                if ssl_ca:
                    ctx.load_verify_locations(cafile=ssl_ca)
                if ssl_verify_cert:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_REQUIRED
                else:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                sess._sock = ctx.wrap_socket(sess._sock, server_hostname=host)
                is_secure = True
            sess._authenticate(user=user, password=password or '', schema=schema or '', is_secure=is_secure)
            return sess
        except BaseException:
            if raw_sock is not None:
                try:
                    raw_sock.close()
                except Exception:
                    pass
            raise

    def _authenticate(self, *, user, password, schema, is_secure):
        pw_bytes = password.encode('utf-8') if isinstance(password, str) else bytes(password)
        if is_secure:
            auth_data = (
                schema.encode('utf-8')
                + b'\x00'
                + user.encode('utf-8')
                + b'\x00'
                + pw_bytes
            )
            self._send(
                CLI_SESS_AUTHENTICATE_START,
                _f_bytes(1, 'PLAIN') + _f_bytes(2, auth_data),
            )
            msg_type, payload = self._recv_non_notice()
            if msg_type == SRV_SESS_AUTHENTICATE_OK:
                return
            if msg_type == SRV_ERROR:
                self._raise_error(payload)
            raise XProtocolError(f'Unexpected X PLAIN authentication response {msg_type}')

        last_err = None
        for mech, scrambler in (('SHA256_MEMORY', _sha256_memory_scramble), ('MYSQL41', _mysql41_scramble)):
            self._send(CLI_SESS_AUTHENTICATE_START, _f_bytes(1, mech))
            msg_type, payload = self._recv_non_notice()
            if msg_type == SRV_ERROR:
                try:
                    self._raise_error(payload)
                except XProtocolError as exc:
                    last_err = exc
                    continue
            if msg_type != SRV_SESS_AUTHENTICATE_CONTINUE:
                raise XProtocolError(f'Expected AuthenticateContinue for {mech}, got {msg_type}')
            challenge = _parse_pb(payload).get(1, [b''])[0]
            scramble = scrambler(pw_bytes, challenge)
            resp = (
                schema.encode('utf-8')
                + b'\x00'
                + user.encode('utf-8')
                + b'\x00'
                + (b'*' + scramble.hex().upper().encode('ascii') if mech == 'MYSQL41' and scramble else scramble)
            )
            self._send(CLI_SESS_AUTHENTICATE_CONTINUE, _f_bytes(1, resp))
            msg_type, payload = self._recv_non_notice()
            if msg_type == SRV_SESS_AUTHENTICATE_OK:
                return
            if msg_type == SRV_ERROR:
                try:
                    self._raise_error(payload)
                except XProtocolError as exc:
                    last_err = exc
        if last_err is not None:
            raise last_err
        raise XProtocolError('MySQL X Protocol authentication failed')

    def _read_exact(self, n):
        chunks = bytearray()
        while len(chunks) < n:
            chunk = self._sock.recv(n - len(chunks))
            if not chunk:
                raise XProtocolError('MySQL X Protocol connection closed unexpectedly')
            chunks.extend(chunk)
        return bytes(chunks)

    def _send(self, msg_type, payload=b''):
        header = struct.pack('<IB', len(payload) + 1, msg_type)
        self._sock.sendall(header + payload)

    def _recv_frame(self):
        header = self._read_exact(5)
        length, msg_type = struct.unpack('<IB', header)
        if length < 1 or length > 32 * 1024 * 1024:
            raise XProtocolError(f'Invalid MySQL X Protocol frame length {length}')
        payload = self._read_exact(length - 1) if length > 1 else b''
        return msg_type, payload

    def _recv_non_notice(self):
        while True:
            msg_type, payload = self._recv_frame()
            if msg_type == SRV_NOTICE:
                continue
            return msg_type, payload

    @staticmethod
    def _raise_error(payload):
        parsed = _parse_pb(payload)
        severity = parsed.get(1, [0])[0]
        code = parsed.get(2, [None])[0]
        msg = parsed.get(3, [b'MySQL X Protocol error'])[0].decode('utf-8', errors='replace')
        sqlstate = parsed.get(4, [b'HY000'])[0].decode('ascii', errors='replace')
        raise XProtocolError(msg, errno=code, sqlstate=sqlstate, severity=severity)

    def _consume_execution_result(self, *, max_rows=1000):
        columns = []
        rows = []
        warnings = []
        rows_affected = 0
        generated_ids = []
        truncated = False
        while True:
            msg_type, payload = self._recv_frame()
            if msg_type == SRV_ERROR:
                self._raise_error(payload)
            if msg_type == SRV_NOTICE:
                frame = _parse_pb(payload)
                ntype = frame.get(1, [0])[0]
                npayload = frame.get(3, [b''])[0]
                if ntype == 1:  # Warning
                    w = _parse_pb(npayload)
                    level_num = w.get(1, [2])[0]
                    level = {1: 'Note', 2: 'Warning', 3: 'Error'}.get(level_num, 'Warning')
                    warnings.append({
                        'level': level,
                        'code': w.get(2, [0])[0],
                        'message': w.get(3, [b''])[0].decode('utf-8', errors='replace'),
                    })
                elif ntype == 3:  # SessionStateChanged
                    sc = _parse_pb(npayload)
                    param = sc.get(1, [0])[0]
                    vals = sc.get(2, [])
                    if param == 4 and vals:  # ROWS_AFFECTED
                        sv = _parse_pb(vals[0])
                        rows_affected = sv.get(3, [0])[0]
                    elif param == 12:  # GENERATED_DOCUMENT_IDS
                        for raw_scalar in vals:
                            sv = _parse_pb(raw_scalar)
                            octs = _parse_pb(sv.get(5, [b''])[0]).get(1, [b''])[0]
                            if not octs:
                                octs = _parse_pb(sv.get(9, [b''])[0]).get(1, [b''])[0]
                            if octs:
                                generated_ids.append(octs.decode('utf-8', errors='replace'))
                continue
            if msg_type == SRV_RESULTSET_COLUMN_META_DATA:
                cm = _parse_pb(payload)
                col_type = cm.get(1, [7])[0]
                col_name = cm.get(2, [b''])[0].decode('utf-8', errors='replace')
                content_type = cm.get(12, [0])[0]
                columns.append({'name': col_name, 'type': col_type, 'content_type': content_type})
                continue
            if msg_type == SRV_RESULTSET_ROW:
                if len(rows) < max_rows:
                    rp = _parse_pb(payload)
                    raw_fields = rp.get(1, [])
                    decoded = []
                    for idx, col in enumerate(columns):
                        raw_cell = raw_fields[idx] if idx < len(raw_fields) else b''
                        decoded.append(_decode_row_cell(raw_cell, col['type']))
                    rows.append(decoded)
                else:
                    truncated = True
                continue
            if msg_type in (
                SRV_RESULTSET_FETCH_DONE,
                SRV_RESULTSET_FETCH_DONE_MORE_RESULTSETS,
                SRV_RESULTSET_FETCH_DONE_MORE_OUT_PARAMS,
            ):
                if msg_type == SRV_RESULTSET_FETCH_DONE_MORE_RESULTSETS:
                    columns = []
                continue
            if msg_type in (SRV_SQL_STMT_EXECUTE_OK, SRV_OK):
                break
        return {
            'columns': [c['name'] for c in columns],
            'rows': rows,
            'rows_affected': rows_affected,
            'generated_document_ids': generated_ids,
            'warnings': warnings,
            'truncated': truncated,
        }

    def execute_admin(self, command, arguments_obj=None):
        payload = _f_bytes(1, command) + _f_bytes(3, 'mysqlx')
        if arguments_obj is not None:
            payload += _f_bytes(2, encode_any(arguments_obj))
        self._send(CLI_SQL_STMT_EXECUTE, payload)
        return self._consume_execution_result()

    def execute_sql(self, sql, args=()):
        payload = _f_bytes(1, sql) + _f_bytes(3, 'sql')
        for arg in args:
            payload += _f_bytes(2, encode_any(arg))
        self._send(CLI_SQL_STMT_EXECUTE, payload)
        return self._consume_execution_result()

    def crud_insert_documents(self, schema, collection, documents, *, upsert=False):
        # Mysqlx.Crud.Insert: collection=1, data_model=2(DOCUMENT=1), row=4, upsert=6
        coll_msg = _f_bytes(1, collection) + _f_bytes(2, schema)
        msg = _f_bytes(1, coll_msg) + _f_varint(2, 1)
        for doc in documents:
            doc_text = json.dumps(doc, ensure_ascii=False, separators=(',', ':')) if isinstance(doc, dict) else str(doc)
            # Validate valid JSON object before sending
            parsed_doc = json.loads(doc_text)
            if not isinstance(parsed_doc, dict):
                raise XProtocolError('Each X collection document must be a JSON object')
            expr = encode_expr_literal(doc_text, json_octets=True)
            typed_row = _f_bytes(1, expr)
            msg += _f_bytes(4, typed_row)
        if upsert:
            msg += _f_varint(6, 1)
        self._send(CLI_CRUD_INSERT, msg)
        return self._consume_execution_result()

    def crud_find_documents(self, schema, collection, *, predicates=(), combinator='AND', limit=100, offset=0, sort_path=None, sort_direction='ASC'):
        # Mysqlx.Crud.Find: collection=2, data_model=3(DOCUMENT=1), criteria=5, limit=6, order=7, args=11
        coll_msg = _f_bytes(1, collection) + _f_bytes(2, schema)
        msg = _f_bytes(2, coll_msg) + _f_varint(3, 1)
        criteria, args = build_criteria_expr(predicates, combinator)
        if criteria is not None:
            msg += _f_bytes(5, criteria)
        limit_msg = _f_varint(1, int(limit)) + (_f_varint(2, int(offset)) if offset else b'')
        msg += _f_bytes(6, limit_msg)
        if sort_path:
            order_msg = _f_bytes(1, encode_expr_doc_ident(sort_path)) + _f_varint(
                2, 2 if sort_direction == 'DESC' else 1
            )
            msg += _f_bytes(7, order_msg)
        for scalar in args:
            msg += _f_bytes(11, scalar)
        self._send(CLI_CRUD_FIND, msg)
        res = self._consume_execution_result(max_rows=limit)
        docs = []
        for row in res['rows']:
            if row and isinstance(row[0], str):
                try:
                    docs.append(json.loads(row[0]))
                except ValueError:
                    docs.append(row[0])
        res['documents'] = docs
        return res

    def crud_modify_documents(self, schema, collection, *, predicates, combinator='AND', operations, limit=None):
        if not predicates:
            raise XProtocolError('Document modify requires at least one explicit filter predicate')
        if not operations:
            raise XProtocolError('Document modify requires at least one update operation')
        # Mysqlx.Crud.Update: collection=2, data_model=3(DOCUMENT=1), criteria=4, limit=5, operation=7, args=8
        coll_msg = _f_bytes(1, collection) + _f_bytes(2, schema)
        msg = _f_bytes(2, coll_msg) + _f_varint(3, 1)
        criteria, args_tuple = build_criteria_expr(predicates, combinator)
        args = list(args_tuple)
        msg += _f_bytes(4, criteria)
        if limit is not None:
            msg += _f_bytes(5, _f_varint(1, int(limit)))
        op_map = {
            'ITEM_SET': 3,
            'ITEM_REMOVE': 2,
            'ITEM_REPLACE': 4,
            'ARRAY_APPEND': 7,
            'MERGE_PATCH': 8,
        }
        for op in operations:
            op_type_name = op.get('operation', 'ITEM_SET')
            if op_type_name not in op_map:
                raise XProtocolError(f'Unsupported X document update operation: {op_type_name}')
            op_code = op_map[op_type_name]
            path = '$' if op_type_name == 'MERGE_PATCH' and not op.get('path') else op.get('path')
            col_id = encode_doc_column_identifier(path)
            uop = _f_bytes(1, col_id) + _f_varint(2, op_code)
            if op_type_name != 'ITEM_REMOVE':
                val = op.get('value')
                if op_type_name == 'MERGE_PATCH':
                    patch_text = json.dumps(val, ensure_ascii=False, separators=(',', ':')) if isinstance(val, dict) else str(val)
                    parsed_patch = json.loads(patch_text)
                    if not isinstance(parsed_patch, dict):
                        raise XProtocolError('MERGE_PATCH value must be a JSON object')
                    uop += _f_bytes(3, encode_expr_literal(patch_text, json_octets=True))
                elif isinstance(val, (dict, list)):
                    uop += _f_bytes(3, encode_expr_literal(json.dumps(val, ensure_ascii=False, separators=(',', ':')), json_octets=True))
                else:
                    pos = len(args)
                    args.append(encode_scalar(val))
                    uop += _f_bytes(3, encode_expr_placeholder(pos))
            msg += _f_bytes(7, uop)
        for scalar in args:
            msg += _f_bytes(8, scalar)
        self._send(CLI_CRUD_UPDATE, msg)
        return self._consume_execution_result()

    def crud_remove_documents(self, schema, collection, *, predicates, combinator='AND', limit=None):
        if not predicates:
            raise XProtocolError('Document remove requires at least one explicit filter predicate')
        # Mysqlx.Crud.Delete: collection=1, data_model=2(DOCUMENT=1), criteria=3, limit=4, args=6
        coll_msg = _f_bytes(1, collection) + _f_bytes(2, schema)
        msg = _f_bytes(1, coll_msg) + _f_varint(2, 1)
        criteria, args = build_criteria_expr(predicates, combinator)
        msg += _f_bytes(3, criteria)
        if limit is not None:
            msg += _f_bytes(4, _f_varint(1, int(limit)))
        for scalar in args:
            msg += _f_bytes(6, scalar)
        self._send(CLI_CRUD_DELETE, msg)
        return self._consume_execution_result()

    def close(self):
        if self.closed:
            return True
        self.closed = True
        try:
            self._send(CLI_CON_CLOSE, b'')
        except Exception:
            pass
        try:
            self._sock.close()
            return True
        except Exception:
            return False
