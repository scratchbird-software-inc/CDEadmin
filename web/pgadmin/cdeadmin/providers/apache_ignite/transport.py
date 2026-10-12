"""Per-client TLS and non-replaying pyignite connection composition."""
import socket
import ssl


def connect(module, route, secrets):
    from pyignite.connection import Connection
    from pyignite.connection.handshake import (
        HandshakeRequest, HandshakeResponse,
    )
    from pyignite.stream import BinaryStream

    context = None
    if route['tls_mode'] != 'disabled':
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = route['tls_mode'] == 'verify-full'
        context.verify_mode = (ssl.CERT_NONE if route['tls_mode'] == 'required'
                               else ssl.CERT_REQUIRED)
        minimum = route.get('tls_min_version', '1.2').replace('.', '_')
        context.minimum_version = getattr(ssl.TLSVersion, 'TLSv'+minimum)
        if route.get('tls_ca_file'):
            context.load_verify_locations(route['tls_ca_file'])
        else:
            context.load_default_certs()
        if route.get('tls_certificate_file'):
            context.load_cert_chain(route['tls_certificate_file'],
                                    route['tls_key_file'],
                                    secrets.get('tls_private_key_password'))
        if route.get('tls_ciphers'):
            context.set_ciphers(route['tls_ciphers'])

    class NativeConnection(Connection):
        def _connect_version(self):
            raw = socket.create_connection((self.host, self.port),
                                           self.handshake_timeout)
            try:
                self._socket = (context.wrap_socket(raw,
                                                    server_hostname=self.host)
                                if context else raw)
            except BaseException:
                raw.close()
                raise
            with BinaryStream(self.client) as stream:
                HandshakeRequest(self.client.protocol_context,
                                 self.username, self.password).from_python(
                                     stream)
                self.send(stream.getvalue(), reconnect=False)
            response = self.recv(reconnect=False)
            with BinaryStream(self.client, response) as stream:
                reply = HandshakeResponse.parse(stream, self.protocol_context)
                if reply.op_code == 0:
                    self.close()
                    self._process_handshake_error(reply)
                return reply

        def send(self, data, flags=None, reconnect=False):
            return super().send(data, flags, reconnect=False)

        def recv(self, flags=None, reconnect=False):
            return super().recv(flags, reconnect=False)

    class NativeClient(module.Client):
        def _connect(self, nodes):
            errors = []
            for host, port in nodes:
                connection = NativeConnection(self, host, port,
                                              **self._connection_args)
                try:
                    connection.connect()
                except Exception as exc:
                    connection.close()
                    errors.append(exc)
                    continue
                self._nodes.append(connection)
                if not self.partition_aware:
                    self._current_node = 0
                    break
            if not self._nodes:
                raise errors[-1] if errors else OSError('No Ignite endpoints')

    options = dict(timeout=route['timeout'],
                   handshake_timeout=route['handshake_timeout'],
                   partition_aware=route['partition_aware'],
                   compact_footer=route['compact_footer'])
    if route['auth_mode'] == 'username-password':
        options.update(username=route['username'],
                       password=secrets['database_password'])
    client = NativeClient(**options)
    try:
        client.connect(route['contact_points'])
    except BaseException:
        client.close()
        raise
    client._cdeadmin_route = route
    return client
