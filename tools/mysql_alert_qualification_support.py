"""Owned loopback TLS SMTP sink for actual alert transport acceptance."""
import base64
from contextlib import contextmanager
import os
from pathlib import Path
import socketserver
import ssl
import subprocess
import threading


@contextmanager
def smtp_sink(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True, mode=0o700)
    cert, key = output/'cert.pem', output/'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True,
        env={key: value for key, value in os.environ.items() if key != 'LD_LIBRARY_PATH'})
    key.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
    messages = []; modes = {'drop_after_data': False}
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            def reply(value): self.wfile.write(value + b'\r\n'); self.wfile.flush()
            reply(b'220 owned.local ESMTP')
            authenticated = False
            while True:
                line = self.rfile.readline(16384)
                if not line: return
                command = line.strip().split(b' ', 1)[0].upper()
                if command == b'EHLO': reply(b'250-owned.local\r\n250 AUTH PLAIN')
                elif command == b'AUTH':
                    assert base64.b64decode(line.strip().split(b' ')[-1]) == b'\0owned\0owned-secret'
                    authenticated = True; reply(b'235 authenticated')
                elif command in {b'MAIL', b'RCPT'}:
                    assert authenticated
                    if command == b'RCPT': assert line.strip().upper() == b'RCPT TO:<OPS@LOCALHOST>'
                    reply(b'250 accepted')
                elif command == b'DATA':
                    assert authenticated; reply(b'354 end with dot')
                    body = bytearray()
                    while True:
                        row = self.rfile.readline(16384)
                        if row == b'.\r\n': break
                        if not row or len(body) > 1024*1024: raise ValueError('Unbounded message')
                        body.extend(row)
                    messages.append(bytes(body))
                    if modes['drop_after_data']: return
                    reply(b'250 queued')
                elif command == b'QUIT': reply(b'221 closing'); return
                else: reply(b'250 ok')
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(10)
            return context.wrap_socket(sock, server_side=True), address
    server = Server(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    previous = os.environ.get('SSL_CERT_FILE'); os.environ['SSL_CERT_FILE'] = str(cert)
    try:
        yield {'host': 'localhost', 'port': server.server_address[1], 'kind': 'smtp', 'use_ssl': True,
            'username': 'owned', 'password': 'owned-secret', 'sender': 'sender@localhost',
            'allowed_recipients': ['ops@localhost'], 'allowed_formats': ['json'], 'timeout_seconds': 5}, messages, modes
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        if previous is None: os.environ.pop('SSL_CERT_FILE', None)
        else: os.environ['SSL_CERT_FILE'] = previous
