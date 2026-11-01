"""Bounded, read-only transfer of one verified package over the board USB network."""
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "results/p06-board-runtime-20261011"
PACKAGE = EVIDENCE / "arm-fir-check-20261011-1302.tar.gz"
BIND = "192.168.2.10"
BOARD = "192.168.2.1"
PORT = 8765
MAX_SECONDS = 1800


def event(item):
    item["at_utc"] = datetime.now(timezone.utc).isoformat()
    with (EVIDENCE / "transfer-events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(item) + "\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.connection.settimeout(10)
        if self.client_address[0] != BOARD:
            self.send_error(403)
            return
        if self.path != "/" + PACKAGE.name:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Length", str(len(self.server.payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(self.server.payload)
            self.wfile.flush()
            event({"event": "package_sent", "peer": BOARD, "bytes": len(self.server.payload),
                   "sha256": self.server.sha256, "board_checksum_verified": False})
            print("Package sent; board checksum and execution remain pending.", flush=True)
        except (OSError, TimeoutError) as error:
            event({"event": "transfer_error", "peer": BOARD, "error": str(error)})


def main():
    manifest = json.loads((EVIDENCE / "transfer-package.json").read_text())
    payload = PACKAGE.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != manifest["sha256"] or len(payload) != manifest["bytes"]:
        raise RuntimeError("Package changed since preparation")
    with HTTPServer((BIND, PORT), Handler) as server:
        server.timeout = 1
        server.payload = payload
        server.sha256 = actual
        event({"event": "server_started", "bind": BIND, "port": PORT,
               "allowed_peer": BOARD, "allowed_package": PACKAGE.name,
               "max_seconds": MAX_SECONDS, "writes_supported": False})
        print(f"Ready: http://{BIND}:{PORT}/{PACKAGE.name}; only {BOARD} may download.", flush=True)
        start = time.monotonic()
        while time.monotonic() - start < MAX_SECONDS:
            server.handle_request()
        event({"event": "server_stopped", "reason": "time_limit"})


if __name__ == "__main__":
    main()
