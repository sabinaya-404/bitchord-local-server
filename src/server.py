import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.config import load_settings
from src.scanner import scan_music, get_artwork_for_track, normalize, is_path_under_music_dirs

MANIFEST_PATH = Path(__file__).with_name("manifest.json")
SETTINGS = load_settings()
TRACKS = scan_music(SETTINGS["music_dirs"])
print(f"Indexed {len(TRACKS)} tracks.")

MAX_SEARCH_RESULTS = 50

ALLOWED_SEARCH_FIELDS = {
    "id",
    "title",
    "artist",
    "album",
    "duration",
    "format",
    "codec",
    "container",
    "sampleRate",
    "bitDepth",
    "bitrate",
    "track",
}

_TRACKS_LOCK = threading.Lock()
_REFRESH_LOCK = threading.Lock()


def get_track_by_id(track_id):
    """Find a track by its ID, or return None if not found."""
    return next((track for track in TRACKS if track["id"] == track_id), None)


def refresh_tracks():
    """Scan music directories and atomically replace the track index.
    Returns (success: bool, message: str, new_count: int).
    """
    global TRACKS
    with _REFRESH_LOCK:
        try:
            new_tracks = scan_music(SETTINGS["music_dirs"])
        except Exception as e:
            logging.warning("Library refresh scan failed: %s", e)
            return False, "Scan failed", 0

        with _TRACKS_LOCK:
            TRACKS = new_tracks
    return True, "OK", len(new_tracks)


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


def _is_path_under_music_dirs(path):
    """Check if an absolute path is under any of the configured music directories.
    Resolves symlinks to prevent directory traversal via symlinks.
    """
    return is_path_under_music_dirs(path, SETTINGS.get("music_dirs", []))


def track_quality(track):
    """Return the quality tier for a track: LOSSLESS for FLAC, HIGH for everything else."""
    return "LOSSLESS" if track.get("format") == "flac" else "HIGH"


class Handler(BaseHTTPRequestHandler):
    command = None

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        ua = self.headers.get("User-Agent", "-")
        print(f"{self.log_date_time_string()} {format % args} | UA: {ua}")

    def send_response(self, code, message=None):
        self._status_code = code
        self.log_request(code)
        self.send_response_only(code, message)
        self.send_header("Date", self.date_time_string())

    def send_header(self, keyword, value):
        if not hasattr(self, "headers_sent"):
            self.headers_sent = {}
        self.headers_sent[keyword] = value
        super().send_header(keyword, value)
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
            raw_query = parse_qs(request.query).get("q", [""])[0].strip()
            if not raw_query:
                self.send_json({"tracks": []})
                return

            query_words = normalize(raw_query).split()
            if not query_words:
                self.send_json({"tracks": []})
                return

            tracks = []
            for track in TRACKS:
                search_tokens = track.get("_search")
                if search_tokens is None:
                    # Fallback for tracks without precomputed _search (e.g., mock tracks in tests)
                    search_tokens = normalize(f"{track.get('title', '')} {track.get('artist', '')} {track.get('album', '')}")
                if all(word in search_tokens.split() for word in query_words):
                    tracks.append(track)

            # Limit search results to prevent excessively large responses
            limited_tracks = tracks[:MAX_SEARCH_RESULTS]

            # Include artworkURL only when base_url is HTTPS (required by BitChord add-on contract)
            base_url_https = SETTINGS["base_url"].startswith("https://")

            self.send_json(
                {
                    "tracks": [
                        {
                            **{
                                key: value
                                for key, value in track.items()
                                if key in ALLOWED_SEARCH_FIELDS
                            },
                            "audioQuality": track_quality(track),
                            **(
                                {"artworkURL": f"{SETTINGS['base_url']}/artwork/{track['id']}"}
                                if base_url_https
                                else {}
                            ),
                        }
                        for track in limited_tracks
                    ]
                }
            )
            return

        if route.startswith("/stream/"):
            track_id = route.removeprefix("/stream/")
            requested_quality = (
                parse_qs(request.query)
                .get("quality", ["LOSSLESS"])[0]
                .upper()
            )

            # Log the requested quality for debugging Android app compatibility
            logging.info("Stream request for track %s with requested quality: %s", track_id, requested_quality)

            track = get_track_by_id(track_id)
            if track is None:
                self.send_error(404)
                return

            # Report the file's actual quality regardless of requested quality
            actual_quality = track_quality(track)

            self.send_json(
                {
                    "url": f"{SETTINGS['base_url']}/audio/{track_id}",
                    "format": track["format"],
                    "quality": actual_quality,
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

            track = get_track_by_id(track_id)
            if track is None:
                self.send_error(404)
                return

            if not _is_path_under_music_dirs(track["path"]):
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

                # Open file first to validate it exists and is readable
                audio_file = path.open("rb")
                audio_file.seek(start)

            except OSError:
                self.send_error(404)
                return

            try:
                self.send_response(status)
                self.send_header("Content-Type", get_content_type(path))
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")

                if status == 206:
                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{end}/{file_size}",
                    )

                self.end_headers()

                # Stream in 64 KB chunks
                CHUNK_SIZE = 64 * 1024
                remaining = length

                try:
                    while remaining > 0:
                        chunk = audio_file.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    # Client disconnected - suppress traceback
                    pass
                finally:
                    audio_file.close()

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Client disconnected before/during headers
                audio_file.close()
                return
            return

        _ARTWORK_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/bmp"}

        if route.startswith("/artwork/"):
            track_id = route.removeprefix("/artwork/")

            track = get_track_by_id(track_id)
            if track is None:
                self.send_error(404)
                return

            if not _is_path_under_music_dirs(track["path"]):
                self.send_error(404)
                return

            image_data, mime_type = get_artwork_for_track(track)
            if image_data is None:
                self.send_error(404)
                return

            if mime_type not in _ARTWORK_MIME_TYPES:
                logging.warning("Rejected unsupported artwork MIME type: %s", mime_type)
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(image_data)))
            self.end_headers()
            self.wfile.write(image_data)
            return

        self.send_error(404)

    def do_POST(self):
        request = urlsplit(self.path)
        route = request.path

        if route == "/refresh":
            success, message, count = refresh_tracks()
            if success:
                self.send_json({"status": "ok", "message": message, "tracks": count})
            else:
                self.send_json({"status": "error", "message": message}, status=500)
            return

        self.send_error(404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(
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