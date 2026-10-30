import json
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.server as server


class MockHTTPRequest:
    """Mock HTTP request object that mimics the socket interface."""
    def __init__(self, data=b""):
        self.data = data

    def makefile(self, mode, bufsize=-1):
        """Return a file-like object for reading request data."""
        return BytesIO(self.data)


class TestArtwork(unittest.TestCase):
    """Test album artwork functionality."""

    def setUp(self):
        """Set up test fixtures for artwork tests."""
        # Create a temporary directory with test audio files
        self.test_dir = tempfile.TemporaryDirectory()
        # Backup original SETTINGS and update music_dirs to include our temporary directory
        self.original_settings = server.SETTINGS.copy()
        server.SETTINGS = {
            **server.SETTINGS,
            "music_dirs": list(server.SETTINGS["music_dirs"]) + [Path(self.test_dir.name).expanduser()]
        }

        # Create a test file
        self.test_file_path = os.path.join(self.test_dir.name, "test.mp3")
        with open(self.test_file_path, 'wb') as f:
            f.write(b'a' * 1000)

        # Create a mock track for this file
        self.mock_track = {
            "id": "test-track-id",
            "title": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "path": Path(os.path.abspath(self.test_file_path)),
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320
        }

        # Patch the TRACKS global in server module to return our mock track
        self.track_patch = patch.object(server, 'TRACKS', [self.mock_track])
        self.track_patch.start()

        # Create a handler instance for testing
        self.handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=('127.0.0.1', 8080),
            server=Mock()
        )
        # Initialize required attributes for BaseHTTPRequestHandler
        self.handler.requestline = ''
        self.handler.raw_requestline = b''
        self.handler.request_version = 'HTTP/1.1'
        self.handler._status_code = 200
        self.handler.headers_sent = {}
        self.handler.wfile = BytesIO()

    def tearDown(self):
        """Clean up test fixtures."""
        # Restore original SETTINGS
        server.SETTINGS = self.original_settings
        self.track_patch.stop()
        self.test_dir.cleanup()

    def _create_get_request(self, path):
        """Create a mock GET request."""
        self.handler.request = MockHTTPRequest()
        self.handler.headers = {}
        self.handler.path = path
        self.handler.command = 'GET'

    def _get_response_body(self):
        """Execute the handler's do_GET method and return the response body."""
        self.handler.wfile = BytesIO()
        self.handler.do_GET()
        response_data = self.handler.wfile.getvalue()
        header_end = response_data.find(b'\r\n\r\n')
        if header_end == -1:
            return response_data
        return response_data[header_end + 4:]

    def test_artwork_endpoint_returns_404_for_unknown_track(self):
        """Test that /artwork/unknown returns 404."""
        self._create_get_request("/artwork/unknown-track")
        self._get_response_body()
        self.assertEqual(self.handler._status_code, 404)

    def test_artwork_endpoint_returns_404_when_no_artwork(self):
        """Test that /artwork/{id} returns 404 when track has no embedded artwork."""
        self._create_get_request("/artwork/test-track-id")
        self._get_response_body()
        self.assertEqual(self.handler._status_code, 404)

    def test_artwork_endpoint_returns_image_when_artwork_exists(self):
        """Test that /artwork/{id} returns image data with correct MIME type when artwork exists."""
        # Mock get_artwork_for_track to return image data
        with patch('src.server.get_artwork_for_track') as mock_get_artwork:
            mock_get_artwork.return_value = (b'fake-image-data', 'image/jpeg')

            self._create_get_request("/artwork/test-track-id")
            body = self._get_response_body()

            self.assertEqual(self.handler._status_code, 200)
            self.assertEqual(self.handler.headers_sent.get('Content-Type'), 'image/jpeg')
            self.assertEqual(self.handler.headers_sent.get('Content-Length'), '15')
            self.assertEqual(body, b'fake-image-data')

    def test_artwork_endpoint_returns_png_when_artwork_is_png(self):
        """Test that /artwork/{id} returns correct MIME type for PNG artwork."""
        with patch('src.server.get_artwork_for_track') as mock_get_artwork:
            mock_get_artwork.return_value = (b'fake-png-data', 'image/png')

            self._create_get_request("/artwork/test-track-id")
            body = self._get_response_body()

            self.assertEqual(self.handler._status_code, 200)
            self.assertEqual(self.handler.headers_sent.get('Content-Type'), 'image/png')
            self.assertEqual(body, b'fake-png-data')

    def test_artwork_endpoint_handles_track_with_no_path(self):
        """Test that /artwork/{id} returns 404 when track has no path."""
        track_no_path = self.mock_track.copy()
        track_no_path["id"] = "no-path-track"
        track_no_path["path"] = None
        server.TRACKS = [track_no_path]

        self._create_get_request("/artwork/no-path-track")
        self._get_response_body()
        self.assertEqual(self.handler._status_code, 404)

    def test_artwork_endpoint_rejects_unsupported_mime_type(self):
        """Test that /artwork/{id} returns 404 for unsupported MIME type (e.g., image/webp)."""
        with patch('src.server.get_artwork_for_track') as mock_get_artwork:
            mock_get_artwork.return_value = (b'fake-webp-data', 'image/webp')

            self._create_get_request("/artwork/test-track-id")
            body = self._get_response_body()

            self.assertEqual(self.handler._status_code, 404)

    def test_artwork_endpoint_rejects_malformed_mime_type(self):
        """Test that /artwork/{id} returns 404 for malformed/non-image MIME type."""
        with patch('src.server.get_artwork_for_track') as mock_get_artwork:
            mock_get_artwork.return_value = (b'fake-data', 'application/octet-stream')

            self._create_get_request("/artwork/test-track-id")
            body = self._get_response_body()

            self.assertEqual(self.handler._status_code, 404)

    def test_artwork_endpoint_rejects_empty_mime_type(self):
        """Test that /artwork/{id} returns 404 for empty/missing MIME type."""
        with patch('src.server.get_artwork_for_track') as mock_get_artwork:
            mock_get_artwork.return_value = (b'fake-data', '')

            self._create_get_request("/artwork/test-track-id")
            body = self._get_response_body()

            self.assertEqual(self.handler._status_code, 404)

    def test_artwork_endpoint_accepts_all_allowed_mime_types(self):
        """Test that /artwork/{id} accepts all MIME types in the allowlist."""
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/bmp"]
        for mime_type in allowed_types:
            with self.subTest(mime_type=mime_type):
                with patch('src.server.get_artwork_for_track') as mock_get_artwork:
                    mock_get_artwork.return_value = (b'fake-data', mime_type)

                    self._create_get_request("/artwork/test-track-id")
                    body = self._get_response_body()

                    self.assertEqual(self.handler._status_code, 200, f"Should accept {mime_type}")
                    self.assertEqual(self.handler.headers_sent.get('Content-Type'), mime_type)

    def test_search_includes_artwork_url_when_base_url_is_https(self):
        """Test that search results include artworkURL when base_url is HTTPS."""
        # Backup original SETTINGS
        original_settings = server.SETTINGS.copy()
        server.SETTINGS = {
            **server.SETTINGS,
            "base_url": "https://example.ts.net"
        }

        try:
            self._create_get_request("/search?q=test")
            body = self._get_response_body()
            response = json.loads(body.decode('utf-8'))

            self.assertEqual(self.handler._status_code, 200)
            self.assertIn("tracks", response)
            self.assertEqual(len(response["tracks"]), 1)
            track = response["tracks"][0]
            self.assertIn("artworkURL", track)
            self.assertEqual(track["artworkURL"], "https://example.ts.net/artwork/test-track-id")
        finally:
            server.SETTINGS = original_settings

    def test_search_excludes_artwork_url_when_base_url_is_http(self):
        """Test that search results exclude artworkURL when base_url is HTTP."""
        # Backup original SETTINGS
        original_settings = server.SETTINGS.copy()
        server.SETTINGS = {
            **server.SETTINGS,
            "base_url": "http://127.0.0.1:8765"
        }

        try:
            self._create_get_request("/search?q=test")
            body = self._get_response_body()
            response = json.loads(body.decode('utf-8'))

            self.assertEqual(self.handler._status_code, 200)
            self.assertIn("tracks", response)
            self.assertEqual(len(response["tracks"]), 1)
            track = response["tracks"][0]
            self.assertNotIn("artworkURL", track)
        finally:
            server.SETTINGS = original_settings

    def test_search_excludes_artwork_url_when_base_url_is_not_https(self):
        """Test that search results exclude artworkURL when base_url is not HTTPS."""
        # Test various non-HTTPS URLs
        test_urls = [
            "http://localhost:8765",
            "http://192.168.1.100:8765",
            "ws://example.com",  # Not HTTP(S) at all
        ]

        for url in test_urls:
            with self.subTest(base_url=url):
                original_settings = server.SETTINGS.copy()
                server.SETTINGS = {
                    **server.SETTINGS,
                    "base_url": url
                }

                try:
                    self._create_get_request("/search?q=test")
                    body = self._get_response_body()
                    response = json.loads(body.decode('utf-8'))

                    track = response["tracks"][0]
                    self.assertNotIn("artworkURL", track, f"artworkURL should not be present for {url}")
                finally:
                    server.SETTINGS = original_settings

    def test_artwork_endpoint_rejects_outside_path(self):
        """Test that artwork endpoint rejects a track whose path escapes music directories."""
        import tempfile
        from pathlib import Path

        # Create a file outside any music directory
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_path = Path(outside_dir)
            outside_file = outside_path / "outside.mp3"
            outside_file.write_bytes(b"outside audio data")

            # Create a mock track with path pointing outside
            mock_track = {
                "id": "outside-track",
                "title": "Outside Track",
                "artist": "Test Artist",
                "album": "Test Album",
                "path": outside_file.resolve(),
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
                # Mock get_artwork_for_track to return image data (simulating file has artwork)
                with patch('src.server.get_artwork_for_track') as mock_get_artwork:
                    mock_get_artwork.return_value = (b'fake-image-data', 'image/jpeg')

                    self._create_get_request("/artwork/outside-track")
                    body = self._get_response_body()

                    # Should be rejected with 404 because path is outside music dirs
                    self.assertEqual(self.handler._status_code, 404)
            finally:
                server.TRACKS = orig_tracks


class TestScannerArtwork(unittest.TestCase):
    """Test the scanner's artwork extraction function."""

    def test_get_artwork_for_track_returns_none_for_missing_file(self):
        """Test that get_artwork_for_track returns (None, None) for missing file."""
        from src.scanner import get_artwork_for_track
        track = {"path": Path("/nonexistent/path.mp3")}
        data, mime = get_artwork_for_track(track)
        self.assertIsNone(data)
        self.assertIsNone(mime)

    def test_get_artwork_for_track_returns_none_for_track_without_path(self):
        """Test that get_artwork_for_track returns (None, None) for track without path."""
        from src.scanner import get_artwork_for_track
        track = {}
        data, mime = get_artwork_for_track(track)
        self.assertIsNone(data)
        self.assertIsNone(mime)

    def test_get_artwork_for_track_returns_none_for_track_with_none_path(self):
        """Test that get_artwork_for_track returns (None, None) for track with None path."""
        from src.scanner import get_artwork_for_track
        track = {"path": None}
        data, mime = get_artwork_for_track(track)
        self.assertIsNone(data)
        self.assertIsNone(mime)


if __name__ == '__main__':
    unittest.main()