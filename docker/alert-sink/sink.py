"""Local stand-in for a chat webhook: logs every POST body, serves the last 50 on GET."""

import json
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

LAST = deque(maxlen=50)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode(
            "utf-8", "replace"
        )
        LAST.append({"path": self.path, "body": body})
        print(f"ALERT-SINK {self.path} {body}", flush=True)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(list(LAST)).encode())

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
