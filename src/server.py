
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.config import load_config
from src.scanner import scan_music

MANIFEST_PATH = Path(__file__).with_name("manifest.json")
TRACKS = scan_music(load_config())
print(f"Indexed {len(TRACKS)} tracks.")


def get_content_type(path):
    return {
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".wav": "audio/wav",
    }.get(path.suffix.lower(), "application/octet-stream")


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
        route = request.path

        if route == "/manifest.json":
            manifest = json.loads(
                MANIFEST_PATH.read_text(encoding="utf-8-sig")
            )
            self.send_json(manifest)
            return

        if route == "/search":
            query = parse_qs(request.query).get("q", [""])[0].strip().casefold()

            tracks = [
                track for track in TRACKS
                if query and query in " ".join([
                    track["title"],
                    track["artist"],
                    track["album"],
                ]).casefold()
            ]

            self.send_json({
                "tracks": [
                    {key: value for key, value in track.items() if key != "path"}
                    for track in tracks
                ]
            })
            return

        if route.startswith("/stream/"):
            track_id = route.removeprefix("/stream/")

            track = next(
                (track for track in TRACKS if track["id"] == track_id),
                None,
            )

            if track is None:
                self.send_error(404)
                return

            self.send_json({
                "url": f"http://127.0.0.1:8765/audio/{track_id}",
                "format": track["format"],
                "manifest": "none",
                "encrypted": False,
            })
            return

        if route.startswith("/audio/"):
            track_id = route.removeprefix("/audio/")

            track = next(
                (track for track in TRACKS if track["id"] == track_id),
                None,
            )

            if track is None:
                self.send_error(404)
                return

            try:
                with track["path"].open("rb") as audio_file:
                    data = audio_file.read()
            except OSError:
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", get_content_type(track["path"]))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
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
