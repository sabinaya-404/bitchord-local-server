
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MANIFEST_PATH = Path(__file__).with_name("manifest.json")
TRACKS = []


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request = urlsplit(self.path)

        if request.path == "/manifest.json":
            manifest = json.loads(
                MANIFEST_PATH.read_text(encoding="utf-8-sig")
            )
            self.send_json(manifest)
            return

        if request.path == "/search":
            query = parse_qs(request.query).get("q", [""])[0].strip().casefold()

            tracks = [
                track for track in TRACKS
                if query and query in " ".join([
                    track["title"],
                    track["artist"],
                    track["album"],
                ]).casefold()
            ]

            self.send_json({"tracks": tracks})
            return

        self.send_error(404)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    print("Local Music server: http://127.0.0.1:8765")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
