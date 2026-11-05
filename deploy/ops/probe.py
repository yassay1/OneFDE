"""Offline connectivity fixture; no model API and no external network."""

import socketserver


class Probe(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.sendall(b"onefde-offline-probe\n")


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("0.0.0.0", 443), Probe) as server:
    server.serve_forever()
