"""Loopback TCP to a private outbound WebSocket; no public database endpoint."""

import socket
import socketserver
import threading

from .config import settings


class BridgeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        import websocket

        upstream = None
        try:
            upstream = websocket.create_connection(
                settings.mysql_bridge_url,
                timeout=135,
                enable_multithread=True,
                http_proxy_host=None,
            )
            self.request.settimeout(135)

            def receive():
                try:
                    while data := upstream.recv():
                        if not isinstance(data, bytes):
                            break
                        self.request.sendall(data)
                except (OSError, websocket.WebSocketException):
                    pass
                finally:
                    try:
                        self.request.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

            reader = threading.Thread(target=receive, daemon=True)
            reader.start()
            while True:
                data = self.request.recv(65536)
                if not data:
                    break
                upstream.send_binary(data)
        except (OSError, websocket.WebSocketException):
            # Never log packets, credentials, exception messages or query values.
            pass
        finally:
            if upstream:
                upstream.close()
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class BridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


def start_bridge():
    if not settings.mysql_bridge_url:
        return None
    server = BridgeServer(("127.0.0.1", settings.mysql_port), BridgeHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="mysql-vpc").start()
    return server
