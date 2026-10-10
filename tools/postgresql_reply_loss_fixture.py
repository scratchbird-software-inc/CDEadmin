"""Owned loopback PostgreSQL fixture: drop a decoded COMMIT completion.

Plaintext only, explicitly selected for fault injection. No query or parameter
payload is retained. This is not an application transport.
"""
import socket
import threading


class CommitReplyLoss:
    def __init__(self, host, port):
        if host not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('Fault fixture requires a loopback server')
        self.target = (host, port)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(1)
        self.port = self.listener.getsockname()[1]
        self.acknowledged = threading.Event()
        self.stopping = threading.Event()
        self.sockets = []
        self.workers = []
        self.worker = threading.Thread(target=self._accept, daemon=True)
        self.worker.start()

    @staticmethod
    def _exact(sock, length):
        data = bytearray()
        while len(data) < length:
            block = sock.recv(length - len(data))
            if not block:
                raise EOFError
            data.extend(block)
        return bytes(data)

    def _packet(self, sock):
        header = self._exact(sock, 4)
        length = int.from_bytes(header, 'big')
        if not 4 <= length <= 256 * 1024 * 1024:
            raise ValueError('Invalid native packet size')
        return header, self._exact(sock, length - 4)

    def _forward(self, source, destination, client):
        try:
            if client:
                header, startup = self._packet(source)
                if startup[:4] != b'\x00\x03\x00\x00':
                    raise ValueError('Fault fixture requires plaintext v3')
                destination.sendall(header + startup)
            while not self.stopping.is_set():
                kind = self._exact(source, 1)
                header, body = self._packet(source)
                if not client and kind == b'C' and body == b'COMMIT\0':
                    self.acknowledged.set()
                    destination.shutdown(socket.SHUT_RDWR)
                    return
                destination.sendall(kind + header + body)
        except (OSError, EOFError, ValueError):
            return
        finally:
            try:
                destination.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _accept(self):
        try:
            while not self.stopping.is_set():
                try:
                    front, _ = self.listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            self.sockets.append(front)
            back = socket.create_connection(self.target, timeout=5)
            back.settimeout(None)
            self.sockets.append(back)
            for source, target, client in [(front, back, True),
                                           (back, front, False)]:
                worker = threading.Thread(target=self._forward,
                                          args=(source, target, client),
                                          daemon=True)
                self.workers.append(worker)
                worker.start()
        except OSError:
            return

    def close(self):
        self.stopping.set()
        self.listener.close()
        self.worker.join(timeout=6)
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        for worker in self.workers:
            worker.join(timeout=2)
