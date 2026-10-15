import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
MANIFEST_PATH = Path(__file__).with_name("manifest.json")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/manifest.json":
            self.send_error(404)
            return

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
        body = json.dumps(manifest).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
      
if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    print("Local Music server: http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()