import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.config import load_settings
from src.scanner import scan_music

MANIFEST_PATH = Path(__file__).with_name("manifest.json")
SETTINGS = load_settings()
TRACKS = scan_music(SETTINGS["music_dirs"])
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
            query = (
                parse_qs(request.query).get("q", [""])[0].strip().casefold()
            )

            tracks = [
                track
                for track in TRACKS
                if query
                and query
                in " ".join(
                    [
                        track["title"],
                        track["artist"],
                        track["album"],
                    ]
                ).casefold()
            ]

            self.send_json(
                {
                    "tracks": [
                        {
                            **{
                                key: value
                                for key, value in track.items()
                                if key != "path"
                            },
                            "audioQuality": (
                                "LOSSLESS"
                                if track["format"] == "flac"
                                else "HIGH"
                            ),
                        }
                        for track in tracks
                    ]
                }
            )
            return

        if route.startswith("/stream/"):
            track_id = route.removeprefix("/stream/")
            quality = (
                parse_qs(request.query)
                .get("quality", ["LOSSLESS"])[0]
                .upper()
            )

            if quality != "LOSSLESS":
                self.send_error(404)
                return

            track = next(
                (track for track in TRACKS if track["id"] == track_id),
                None,
            )

            if track is None:
                self.send_error(404)
                return

            self.send_json(
                {
                    "url": f"{SETTINGS['base_url']}/audio/{track_id}",
                    "format": track["format"],
                    "quality": "LOSSLESS",
                    "codec": track["codec"],
                    "container": track["container"],
                    "manifest": "none",
                    "encrypted": False,
                    "sampleRate": track["sampleRate"],
                    "bitDepth": track["bitDepth"],
                    "bitrate": track["bitrate"],
                }
            )
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

            path = track["path"]

            try:
                file_size = path.stat().st_size
                range_header = self.headers.get("Range")

                start = 0
                end = file_size - 1
                status = 200

                if range_header:
                    if (
                        not range_header.startswith("bytes=")
                        or "," in range_header
                    ):
                        self.send_response(416)
                        self.send_header(
                            "Content-Range",
                            f"bytes */{file_size}",
                        )
                        self.end_headers()
                        return

                    try:
                        start_text, end_text = range_header[6:].split("-", 1)

                        if not start_text:
                            length = int(end_text)
                            if length <= 0:
                                raise ValueError
                            start = max(0, file_size - length)
                        else:
                            start = int(start_text)
                            if start < 0:
                                raise ValueError

                            if end_text:
                                end = int(end_text)

                        if start >= file_size or start > end:
                            raise ValueError

                        end = min(end, file_size - 1)

                    except ValueError:
                        self.send_response(416)
                        self.send_header(
                            "Content-Range",
                            f"bytes */{file_size}",
                        )
                        self.end_headers()
                        return

                    status = 206

                length = end - start + 1

                with path.open("rb") as audio_file:
                    audio_file.seek(start)
                    data = audio_file.read(length)

            except OSError:
                self.send_error(404)
                return

            self.send_response(status)
            self.send_header("Content-Type", get_content_type(path))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")

            if status == 206:
                self.send_header(
                    "Content-Range",
                    f"bytes {start}-{end}/{file_size}",
                )

            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404)


if __name__ == "__main__":
    server = HTTPServer(
    (SETTINGS["host"], SETTINGS["port"]),
    Handler,
)
    print(f"Local Music server: {SETTINGS['base_url']}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()