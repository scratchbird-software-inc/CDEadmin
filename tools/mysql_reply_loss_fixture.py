"""Loopback-only fixture that withholds one successful COMMIT response."""
import socket
import threading


class CommitReplyLoss:
    def __init__(self, host, port):
        self.target = (host, port)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.commit_sent = threading.Event()
        self.commit_acknowledged = threading.Event()
        self.sockets = []
        self.workers = []
        self.worker = threading.Thread(target=self._accept, daemon=True)
        self.worker.start()

    @staticmethod
    def _exact(sock, length):
        data = bytearray()
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise EOFError()
            data.extend(chunk)
        return bytes(data)

    def _forward(self, source, destination, client):
        try:
            while True:
                header = self._exact(source, 4)
                body = self._exact(
                    source, int.from_bytes(header[:3], 'little'))
                if client and header[3] == 0 and body in (
                        b'\x03COMMIT', b'\x03\x00\x01COMMIT'):
                    self.commit_sent.set()
                if not client and self.commit_sent.is_set():
                    if body[:1] == b'\x00':
                        self.commit_acknowledged.set()
                    destination.shutdown(socket.SHUT_RDWR)
                    return
                destination.sendall(header + body)
        except (OSError, EOFError):
            return

    def _accept(self):
        try:
            front, _ = self.listener.accept()
            back = socket.create_connection(self.target, timeout=5)
            back.settimeout(None)
            self.sockets.extend([front, back])
            for source, dest, client in [(front, back, True),
                                         (back, front, False)]:
                worker = threading.Thread(
                    target=self._forward, args=(source, dest, client),
                    daemon=True)
                self.workers.append(worker)
                worker.start()
        except OSError:
            return

    def close(self):
        self.listener.close()
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        self.worker.join(timeout=2)
        for worker in self.workers:
            worker.join(timeout=2)
