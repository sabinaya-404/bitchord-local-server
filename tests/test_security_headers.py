import email
from email import policy
from io import BytesIO
import json
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import src.server as server


class MockHTTPRequest:
    def __init__(self, data=b""):
        self.data = data

    def makefile(self, mode, bufsize=-1):
        return BytesIO(self.data)


class TestSecurityHeaders(unittest.TestCase):
    """Focused tests for SEC-02: suppressing Server header in all responses."""

    def _create_handler(self, path="/", command="GET"):
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = command
        handler.requestline = f"{command} {path} HTTP/1.0"
        handler.raw_requestline = handler.requestline.encode("latin-1")
        handler.request_version = "HTTP/1.0"
        handler.path = path
        handler.headers = {}
        handler.wfile = BytesIO()
        return handler

    def _parse_response(self, handler):
        raw = handler.wfile.getvalue()
        parts = raw.split(b"\r\n\r\n", 1)
        header_bytes = parts[0]
        body = parts[1] if len(parts) > 1 else b""
        lines = header_bytes.split(b"\r\n", 1)
        status_line = lines[0].decode("latin-1")
        headers_part = lines[1] if len(lines) > 1 else b""
        msg = email.message_from_bytes(headers_part, policy=policy.default)
        return status_line, msg, body

    def test_successful_manifest_response_suppresses_server_header(self):
        handler = self._create_handler("/manifest.json")
        handler.do_GET()

        status_line, headers, body = self._parse_response(handler)
        self.assertTrue(status_line.startswith("HTTP/1.0 200"))
        self.assertNotIn("Server", headers)
        self.assertIn("Date", headers)
        self.assertIn("application/json", headers.get("Content-Type"))
        self.assertIn("utf-8", headers.get("Content-Type"))
        self.assertEqual(int(headers.get("Content-Length")), len(body))
        manifest = json.loads(body.decode("utf-8"))
        self.assertEqual(manifest["id"], "dev.sabinaya.local-music")

    def test_successful_search_response_suppresses_server_header(self):
        handler = self._create_handler("/search?q=test")
        handler.do_GET()

        status_line, headers, body = self._parse_response(handler)
        self.assertTrue(status_line.startswith("HTTP/1.0 200"))
        self.assertNotIn("Server", headers)
        self.assertIn("Date", headers)
        self.assertIn("application/json", headers.get("Content-Type"))
        self.assertIn("utf-8", headers.get("Content-Type"))
        self.assertEqual(int(headers.get("Content-Length")), len(body))

    def test_error_404_route_suppresses_server_header_and_has_valid_body(self):
        handler = self._create_handler("/nonexistent-endpoint")
        handler.do_GET()

        status_line, headers, body = self._parse_response(handler)
        self.assertTrue(status_line.startswith("HTTP/1.0 404"))
        self.assertNotIn("Server", headers)
        self.assertIn("Date", headers)
        self.assertEqual(headers.get("Connection"), "close")
        self.assertEqual(int(headers.get("Content-Length")), len(body))
        self.assertIn(b"404", body)

    def test_send_error_direct_calls_suppress_server_header(self):
        for code in [400, 401, 403, 404, 500]:
            with self.subTest(code=code):
                handler = self._create_handler(f"/error-{code}")
                handler.send_error(code)

                status_line, headers, body = self._parse_response(handler)
                self.assertTrue(status_line.startswith(f"HTTP/1.0 {code}"))
                self.assertNotIn("Server", headers)
                self.assertIn("Date", headers)
                self.assertEqual(headers.get("Connection"), "close")
                self.assertEqual(int(headers.get("Content-Length")), len(body))

    def test_audio_and_stream_responses_suppress_server_header(self):
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"abcdefghij" * 10)  # 100 bytes
            temp_path = Path(f.name)

        # Backup original SETTINGS and update music_dirs to include the temporary file's directory
        original_settings = server.SETTINGS.copy()
        server.SETTINGS = {
            **server.SETTINGS,
            "music_dirs": list(server.SETTINGS["music_dirs"]) + [Path(temp_path.parent).expanduser()]
        }

        mock_track = {
            "id": "sec02-track",
            "title": "SEC02 Track",
            "artist": "SEC02 Artist",
            "album": "SEC02 Album",
            "path": temp_path,
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
        }
        orig_tracks = server.TRACKS
        server.TRACKS = [mock_track]

        try:
            # 1. Stream metadata (200)
            handler = self._create_handler("/stream/sec02-track")
            handler.do_GET()
            status_line, headers, body = self._parse_response(handler)
            self.assertTrue(status_line.startswith("HTTP/1.0 200"))
            self.assertNotIn("Server", headers)
            self.assertIn("Date", headers)

            # 2. Audio full (200)
            handler = self._create_handler("/audio/sec02-track")
            handler.do_GET()
            status_line, headers, body = self._parse_response(handler)
            self.assertTrue(status_line.startswith("HTTP/1.0 200"))
            self.assertNotIn("Server", headers)
            self.assertIn("Date", headers)
            self.assertEqual(headers.get("Accept-Ranges"), "bytes")
            self.assertEqual(int(headers.get("Content-Length")), 100)

            # 3. Audio partial range (206)
            handler = self._create_handler("/audio/sec02-track")
            handler.headers["Range"] = "bytes=0-9"
            handler.do_GET()
            status_line, headers, body = self._parse_response(handler)
            self.assertTrue(status_line.startswith("HTTP/1.0 206"))
            self.assertNotIn("Server", headers)
            self.assertIn("Date", headers)
            self.assertEqual(headers.get("Content-Range"), "bytes 0-9/100")
            self.assertEqual(int(headers.get("Content-Length")), 10)

            # 4. Audio invalid range (416)
            handler = self._create_handler("/audio/sec02-track")
            handler.headers["Range"] = "invalid-range"
            handler.do_GET()
            status_line, headers, body = self._parse_response(handler)
            self.assertTrue(status_line.startswith("HTTP/1.0 416"))
            self.assertNotIn("Server", headers)
            self.assertIn("Date", headers)
            self.assertEqual(headers.get("Content-Range"), "bytes */100")
        finally:
            server.TRACKS = orig_tracks
            # Restore original SETTINGS
            server.SETTINGS = original_settings
            try:
                temp_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
