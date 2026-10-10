"""Owned plaintext loopback YCQL fixture dropping one mutation result."""
import socket
import threading


class YCQLReplyLoss:
    def __init__(self, host, port, statement):
        if host not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('YCQL fault fixture requires loopback')
        self.target = (host, port)
        self.statement = statement.encode('utf-8')
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(10)
        self.listener.settimeout(.2)
        self.port = self.listener.getsockname()[1]
        self.stopping = threading.Event()
        self.acknowledged = threading.Event()
        self.dispatches = 0
        self.lock = threading.Lock()
        self.sockets, self.workers = [], []
        self.worker = threading.Thread(target=self._accept, daemon=True)
        self.worker.start()

    @staticmethod
    def exact(sock, length):
        value = bytearray()
        while len(value) < length:
            part = sock.recv(length - len(value))
            if not part:
                raise EOFError
            value.extend(part)
        return bytes(value)

    def _forward(self, source, target, client, streams):
        try:
            while not self.stopping.is_set():
                header = self.exact(source, 9)
                length = int.from_bytes(header[5:9], 'big')
                if length > 256 * 1024 * 1024 or header[1] & 1:
                    raise ValueError('Fault fixture requires uncompressed v4')
                body = self.exact(source, length)
                stream = header[2:4]
                if client and header[4] == 7:
                    size = int.from_bytes(body[:4], 'big')
                    if body[4:4 + size] == self.statement:
                        with self.lock:
                            streams.add(stream)
                            self.dispatches += 1
                if not client and header[4] == 8 and stream in streams:
                    assert int.from_bytes(body[:4], 'big') == 1
                    self.acknowledged.set()
                    return
                target.sendall(header + body)
        except (OSError, EOFError, ValueError, AssertionError):
            return
        finally:
            for sock in (source, target):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def _accept(self):
        while not self.stopping.is_set():
            try:
                front, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                back = socket.create_connection(self.target, timeout=5)
                back.settimeout(None)
            except OSError:
                front.close()
                continue
            self.sockets.extend([front, back])
            streams = set()
            for source, target, client in [(front, back, True),
                                           (back, front, False)]:
                worker = threading.Thread(target=self._forward,
                                          args=(source, target, client,
                                                streams),
                                          daemon=True)
                self.workers.append(worker)
                worker.start()

    def close(self):
        self.stopping.set()
        self.listener.close()
        self.worker.join(6)
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        for worker in self.workers:
            worker.join(2)
