import json
import os
import sys
import tempfile
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.server as server
import src.scanner as scanner
from src.scanner import get_artwork_for_track, clear_artwork_cache


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
        # Also update TRACKS_BY_ID
        server.TRACKS_BY_ID = {self.mock_track["id"]: self.mock_track}

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
        # Restore TRACKS_BY_ID to original state
        # The patch will restore TRACKS, so we need to rebuild TRACKS_BY_ID
        server.TRACKS_BY_ID = {t["id"]: t for t in server.TRACKS}
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
        server.TRACKS_BY_ID = {track_no_path["id"]: track_no_path}

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
            orig_tracks_by_id = server.TRACKS_BY_ID
            server.TRACKS = [mock_track]
            server.TRACKS_BY_ID = {mock_track["id"]: mock_track}
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
                server.TRACKS_BY_ID = orig_tracks_by_id


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


class TestArtworkCache(unittest.TestCase):
    """Test the artwork caching functionality."""

    def setUp(self):
        """Clear cache before each test."""
        clear_artwork_cache()

    def tearDown(self):
        """Clear cache after each test."""
        clear_artwork_cache()

    def test_cache_hit_same_track_id(self):
        """Test that second request for same track_id returns cached data."""
        with patch('src.scanner.TinyTag.get') as mock_get:
            mock_tag = Mock()
            mock_image = Mock()
            mock_image.data = b'cached-image-data'
            mock_image.mime_type = 'image/jpeg'
            mock_tag.images = Mock()
            mock_tag.images.front_cover = mock_image
            mock_tag.images.any = mock_image
            mock_get.return_value = mock_tag

            track = {
                "id": "test-track-id",
                "path": Path(__file__).parent / "nonexistent.mp3",
            }

            # Create a dummy file for path.exists() check
            track["path"].write_bytes(b'dummy')

            try:
                # First call - should extract
                data1, mime1 = get_artwork_for_track(track)
                # Second call - should hit cache
                data2, mime2 = get_artwork_for_track(track)

                self.assertEqual(data1, b'cached-image-data')
                self.assertEqual(mime1, 'image/jpeg')
                self.assertEqual(data2, b'cached-image-data')
                self.assertEqual(mime2, 'image/jpeg')
                # TinyTag.get should only be called once
                self.assertEqual(mock_get.call_count, 1)
            finally:
                track["path"].unlink(missing_ok=True)

    def test_cache_miss_different_track_ids(self):
        """Test that different track_ids populate separate cache entries."""
        with patch('src.scanner.TinyTag.get') as mock_get:
            mock_tag = Mock()
            mock_image = Mock()
            mock_image.data = b'image-data'
            mock_image.mime_type = 'image/jpeg'
            mock_tag.images = Mock()
            mock_tag.images.front_cover = mock_image
            mock_tag.images.any = mock_image
            mock_get.return_value = mock_tag

            track1 = {"id": "track-1", "path": Path(__file__).parent / "nonexistent1.mp3"}
            track2 = {"id": "track-2", "path": Path(__file__).parent / "nonexistent2.mp3"}

            track1["path"].write_bytes(b'dummy')
            track2["path"].write_bytes(b'dummy')

            try:
                get_artwork_for_track(track1)
                get_artwork_for_track(track2)
                # Both should be extracted (2 calls)
                self.assertEqual(mock_get.call_count, 2)

                # Now call again for track1 - should hit cache
                get_artwork_for_track(track1)
                self.assertEqual(mock_get.call_count, 2)
            finally:
                track1["path"].unlink(missing_ok=True)
                track2["path"].unlink(missing_ok=True)

    def test_cache_fifo_eviction(self):
        """Test FIFO eviction when cache exceeds max entries."""
        with patch('src.scanner.TinyTag.get') as mock_get:
            mock_tag = Mock()
            mock_image = Mock()
            mock_image.data = b'x'
            mock_image.mime_type = 'image/jpeg'
            mock_tag.images = Mock()
            mock_tag.images.front_cover = mock_image
            mock_tag.images.any = mock_image
            mock_get.return_value = mock_tag

            # Fill cache to max (200 entries)
            for i in range(scanner._MAX_CACHE_ENTRIES):
                track = {"id": f"track-{i}", "path": Path(__file__).parent / f"nonexistent{i}.mp3"}
                track["path"].write_bytes(b'dummy')
                try:
                    get_artwork_for_track(track)
                finally:
                    track["path"].unlink(missing_ok=True)

            # Add one more - should evict the first
            track_new = {"id": "track-new", "path": Path(__file__).parent / "nonexistent_new.mp3"}
            track_new["path"].write_bytes(b'dummy')
            try:
                get_artwork_for_track(track_new)
            finally:
                track_new["path"].unlink(missing_ok=True)

            # The first entry should be evicted, new one present
            with scanner._ARTWORK_CACHE_LOCK:
                self.assertNotIn("track-0", scanner._ARTWORK_CACHE)
                self.assertIn("track-new", scanner._ARTWORK_CACHE)
                self.assertEqual(len(scanner._ARTWORK_CACHE), scanner._MAX_CACHE_ENTRIES)

    def test_cache_invalidated_after_refresh(self):
        """Test that cache is cleared after successful refresh."""
        with patch('src.scanner.TinyTag.get') as mock_get:
            mock_tag = Mock()
            mock_image = Mock()
            mock_image.data = b'cached-data'
            mock_image.mime_type = 'image/jpeg'
            mock_tag.images = Mock()
            mock_tag.images.front_cover = mock_image
            mock_tag.images.any = mock_image
            mock_get.return_value = mock_tag

            track = {"id": "test-track", "path": Path(__file__).parent / "nonexistent.mp3"}
            track["path"].write_bytes(b'dummy')

            try:
                # Populate cache
                get_artwork_for_track(track)
                self.assertEqual(mock_get.call_count, 1)

                # Call clear_artwork_cache (simulating refresh)
                clear_artwork_cache()

                # Next call should miss cache and extract again
                get_artwork_for_track(track)
                self.assertEqual(mock_get.call_count, 2)
            finally:
                track["path"].unlink(missing_ok=True)

    def test_old_generation_cannot_populate_cache_after_refresh(self):
        """Test that extraction started before refresh cannot populate new cache generation."""
        with patch('src.scanner.TinyTag.get') as mock_get:
            mock_tag = Mock()
            mock_image = Mock()
            mock_image.data = b'old-data'
            mock_image.mime_type = 'image/jpeg'
            mock_tag.images = Mock()
            mock_tag.images.front_cover = mock_image
            mock_tag.images.any = mock_image
            mock_get.return_value = mock_tag

            track = {"id": "race-track", "path": Path(__file__).parent / "nonexistent_race.mp3"}
            track["path"].write_bytes(b'dummy')

            try:
                # Start extraction (capture generation 0)
                # We simulate this by manually checking the logic
                # First, populate cache at generation 0
                get_artwork_for_track(track)
                self.assertEqual(mock_get.call_count, 1)

                # Now simulate refresh - increment generation
                clear_artwork_cache()

                # Now try to manually insert with old generation (simulating race)
                # This tests that our generation check prevents stale insertion
                with scanner._ARTWORK_CACHE_LOCK:
                    old_generation = scanner._CACHE_GENERATION - 1
                    scanner._ARTWORK_CACHE["race-track"] = (b'stale-data', 'image/jpeg', old_generation)

                # Next call should miss (generation mismatch) and extract fresh
                get_artwork_for_track(track)
                self.assertEqual(mock_get.call_count, 2)

                # Cache should have fresh data with new generation
                with scanner._ARTWORK_CACHE_LOCK:
                    cached = scanner._ARTWORK_CACHE.get("race-track")
                    self.assertEqual(cached[2], scanner._CACHE_GENERATION)
                    self.assertEqual(cached[0], b'old-data')  # same mock data
            finally:
                track["path"].unlink(missing_ok=True)

    def test_missing_artwork_not_cached(self):
        """Test that tracks with no artwork don't pollute cache with None."""
        with patch('src.scanner.TinyTag.get') as mock_get:
            mock_tag = Mock()
            mock_tag.images = None
            mock_get.return_value = mock_tag

            track = {"id": "no-art-track", "path": Path(__file__).parent / "nonexistent_noart.mp3"}
            track["path"].write_bytes(b'dummy')

            try:
                data, mime = get_artwork_for_track(track)
                self.assertIsNone(data)
                self.assertIsNone(mime)

                # Cache should not have entry for this track
                with scanner._ARTWORK_CACHE_LOCK:
                    self.assertNotIn("no-art-track", scanner._ARTWORK_CACHE)
            finally:
                track["path"].unlink(missing_ok=True)

    def test_concurrent_cache_access(self):
        """Test that concurrent access doesn't corrupt cache or generation."""
        results = []
        errors = []

        def worker(track_id):
            try:
                with patch('src.scanner.TinyTag.get') as mock_get:
                    mock_tag = Mock()
                    mock_image = Mock()
                    mock_image.data = f'data-{track_id}'.encode()
                    mock_image.mime_type = 'image/jpeg'
                    mock_tag.images = Mock()
                    mock_tag.images.front_cover = mock_image
                    mock_tag.images.any = mock_image
                    mock_get.return_value = mock_tag

                    track = {
                        "id": track_id,
                        "path": Path(__file__).parent / f"nonexistent_{track_id}.mp3",
                    }
                    track["path"].write_bytes(b'dummy')
                    try:
                        data, mime = get_artwork_for_track(track)
                        results.append((track_id, data, mime))
                    finally:
                        track["path"].unlink(missing_ok=True)
            except Exception as e:
                errors.append((track_id, e))

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(f"concurrent-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors in concurrent access: {errors}")
        self.assertEqual(len(results), 10)

        # Verify cache integrity
        with scanner._ARTWORK_CACHE_LOCK:
            self.assertLessEqual(len(scanner._ARTWORK_CACHE), scanner._MAX_CACHE_ENTRIES)
            for cached in scanner._ARTWORK_CACHE.values():
                self.assertEqual(cached[2], scanner._CACHE_GENERATION)


if __name__ == '__main__':
    unittest.main()