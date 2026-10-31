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


class MockHTTPRequest:
    """Mock HTTP request object that mimics the socket interface."""
    def __init__(self, data=b""):
        self.data = data
        self.position = 0

    def makefile(self, mode, bufsize=-1):
        """Return a file-like object for reading request data."""
        return BytesIO(self.data)


class TestRefresh(unittest.TestCase):
    """Test library refresh functionality."""

    def setUp(self):
        """Set up test fixtures for refresh tests."""
        # Create a temporary directory with test audio files
        self.test_dir = tempfile.TemporaryDirectory()
        # Backup original SETTINGS and replace music_dirs with only our temporary directory
        self.original_settings = server.SETTINGS.copy()
        server.SETTINGS = {
            **server.SETTINGS,
            "music_dirs": [Path(self.test_dir.name).expanduser()]
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
        # Also patch TRACKS_BY_ID for get_track_by_id() lookups
        self.tracks_by_id_patch = patch.object(server, 'TRACKS_BY_ID', {self.mock_track["id"]: self.mock_track})
        self.tracks_by_id_patch.start()

        # Create a handler instance for testing
        self.handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=('127.0.0.1', 8080),
            server=Mock()
        )

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
        self.tracks_by_id_patch.stop()
        self.test_dir.cleanup()

    def _create_post_request(self, path="/refresh"):
        """Create a mock POST request."""
        self.handler.request = MockHTTPRequest()
        self.handler.headers = {'Content-Length': '0'}
        self.handler.path = path
        self.handler.command = 'POST'

    def _get_response_json(self):
        """Execute the handler's do_POST method and return parsed JSON response."""
        self.handler.wfile = BytesIO()
        self.handler.do_POST()
        response_data = self.handler.wfile.getvalue()

        header_end = response_data.find(b'\r\n\r\n')
        if header_end == -1:
            return None
        body = response_data[header_end + 4:]
        return json.loads(body.decode('utf-8'))

    def test_refresh_success(self):
        """Test successful refresh returns 200 with track count."""
        self._create_post_request("/refresh")
        response = self._get_response_json()

        self.assertEqual(self.handler._status_code, 200)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["message"], "OK")
        self.assertEqual(response["tracks"], 1)

    def test_refresh_updates_track_index(self):
        """Test that refresh actually updates the global TRACKS."""
        # Initial track count
        initial_count = len(server.TRACKS)

        # Add a new file to the music directory
        new_file = Path(self.test_dir.name) / "new_track.mp3"
        new_file.write_bytes(b'b' * 500)

        # Trigger refresh
        self._create_post_request("/refresh")
        response = self._get_response_json()

        self.assertEqual(self.handler._status_code, 200)
        self.assertEqual(response["status"], "ok")
        # Track count should increase
        self.assertEqual(response["tracks"], initial_count + 1)

    def test_refresh_removes_deleted_files(self):
        """Test that refresh removes tracks for deleted files."""
        # Remove the test file
        os.remove(self.test_file_path)

        # Trigger refresh
        self._create_post_request("/refresh")
        response = self._get_response_json()

        self.assertEqual(self.handler._status_code, 200)
        self.assertEqual(response["status"], "ok")
        # Track count should decrease to 0
        self.assertEqual(response["tracks"], 0)

    def test_refresh_scan_failure_preserves_existing_index(self):
        """Test that a scan failure preserves the existing track index."""
        # Backup original scan_music
        original_scan = server.scan_music

        # Make scan_music raise an exception
        def failing_scan(*args, **kwargs):
            raise OSError("Simulated scan failure")

        server.scan_music = failing_scan
        try:
            original_count = len(server.TRACKS)

            self._create_post_request("/refresh")
            response = self._get_response_json()

            # Should return 500 error
            self.assertEqual(self.handler._status_code, 500)
            self.assertEqual(response["status"], "error")
            self.assertIn("Scan failed", response["message"])

            # TRACKS should be unchanged
            self.assertEqual(len(server.TRACKS), original_count)
            self.assertEqual(server.TRACKS[0]["id"], "test-track-id")
        finally:
            server.scan_music = original_scan

    def test_refresh_nonexistent_endpoint_returns_404(self):
        """Test that POST to unknown endpoint returns 404."""
        self._create_post_request("/unknown")
        self.handler.wfile = BytesIO()
        self.handler.do_POST()
        self.assertEqual(self.handler._status_code, 404)

    def test_concurrent_read_during_refresh(self):
        """Test that concurrent GET requests don't see partial state during refresh."""
        # This test verifies the atomic swap behavior
        # We'll do multiple rapid refreshes and concurrent reads

        errors = []
        read_results = []

        def reader():
            """Simulate concurrent read requests."""
            for _ in range(50):

                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'GET /search?q=test HTTP/1.0'
                h.raw_requestline = b'GET /search?q=test HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/search?q=test'
                h.headers = {}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'GET'

                try:
                    h.do_GET()
                    # Should always get a valid response (200)
                    if h._status_code != 200:
                        errors.append(f"Read got status {h._status_code}")
                except Exception as e:
                    errors.append(f"Read error: {e}")

        def refresher():
            """Simulate concurrent refresh requests."""
            for _ in range(10):
                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'POST /refresh HTTP/1.0'
                h.raw_requestline = b'POST /refresh HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/refresh'
                h.headers = {'Content-Length': '0'}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'POST'

                try:
                    h.do_POST()
                    if h._status_code not in (200, 500):
                        errors.append(f"Refresh got status {h._status_code}")
                except Exception as e:
                    errors.append(f"Refresh error: {e}")

        # Run readers and refreshers concurrently
        threads = []
        for _ in range(3):
            t = threading.Thread(target=reader)
            threads.append(t)
        for _ in range(2):
            t = threading.Thread(target=refresher)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # No errors should occur
        self.assertEqual(errors, [], f"Concurrent access errors: {errors}")

    def test_concurrent_refreshes_serialized_scan(self):
        """Multiple concurrent refreshes never execute scan_music simultaneously."""
        original_scan = server.scan_music
        scan_counter = {"current": 0, "max": 0}
        scan_counter_lock = threading.Lock()
        scan_started = threading.Event()
        scan_continues = threading.Event()

        def counting_scan(*args, **kwargs):
            with scan_counter_lock:
                scan_counter["current"] += 1
                scan_counter["max"] = max(scan_counter["max"], scan_counter["current"])
            scan_started.set()
            scan_continues.wait(timeout=5)
            with scan_counter_lock:
                scan_counter["current"] -= 1
            return original_scan(*args, **kwargs)

        server.scan_music = counting_scan
        try:
            # Fire multiple concurrent refreshes
            threads = []
            results = []

            def do_refresh():
                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'POST /refresh HTTP/1.0'
                h.raw_requestline = b'POST /refresh HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/refresh'
                h.headers = {'Content-Length': '0'}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'POST'
                h.do_POST()
                results.append(h._status_code)

            for _ in range(3):
                t = threading.Thread(target=do_refresh)
                threads.append(t)

            for t in threads:
                t.start()


            scan_started.wait(timeout=2)
            scan_continues.set()

            for t in threads:
                t.join(timeout=5)

            # All refreshes should succeed
            self.assertTrue(all(s == 200 for s in results), f"Refresh statuses: {results}")
            # Maximum concurrent scans should be 1 (serialized)
            self.assertEqual(scan_counter["max"], 1, "scan_music ran concurrently")
        finally:
            server.scan_music = original_scan

    def test_second_refresh_waits_for_first(self):
        """A second refresh waits until the first scan finishes."""
        original_scan = server.scan_music
        first_scan_done = threading.Event()
        second_scan_started = threading.Event()

        def slow_scan(*args, **kwargs):
            if not first_scan_done.is_set():
                first_scan_done.set()
                # Hold first scan briefly
                time.sleep(0.1)
            else:
                second_scan_started.set()
            return original_scan(*args, **kwargs)

        server.scan_music = slow_scan
        try:
            results = []

            def do_refresh():
                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'POST /refresh HTTP/1.0'
                h.raw_requestline = b'POST /refresh HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/refresh'
                h.headers = {'Content-Length': '0'}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'POST'
                h.do_POST()
                results.append(h._status_code)

            # Start first refresh
            t1 = threading.Thread(target=do_refresh)
            t1.start()

            # First scan should start
            first_scan_done.wait(timeout=2)

            # Start second refresh while first is still scanning
            t2 = threading.Thread(target=do_refresh)
            t2.start()

            # Second scan should not start until first completes
            # Give it a moment to potentially start (it shouldn't)
            time.sleep(0.05)
            self.assertFalse(second_scan_started.is_set(), "Second scan started before first finished")


            t1.join(timeout=5)
            t2.join(timeout=5)

            second_scan_started.wait(timeout=2)
            self.assertTrue(all(s == 200 for s in results), f"Refresh statuses: {results}")
        finally:
            server.scan_music = original_scan

    def test_refresh_lock_released_on_scan_failure(self):
        """A scan failure releases _REFRESH_LOCK, allowing a subsequent refresh."""
        original_scan = server.scan_music
        fail_first = {"value": True}

        def failing_then_ok_scan(*args, **kwargs):
            if fail_first["value"]:
                fail_first["value"] = False
                raise OSError("Simulated scan failure")
            return original_scan(*args, **kwargs)

        server.scan_music = failing_then_ok_scan
        try:
            # First refresh fails
            self._create_post_request("/refresh")
            response = self._get_response_json()
            self.assertEqual(self.handler._status_code, 500)

            # Second refresh should succeed (lock was released)
            self._create_post_request("/refresh")
            response = self._get_response_json()
            self.assertEqual(self.handler._status_code, 200)
            self.assertEqual(response["status"], "ok")
        finally:
            server.scan_music = original_scan

    def test_readers_see_consistent_index_during_refresh(self):
        """Readers remain functional and see complete old or new indexes during refresh."""
        original_scan = server.scan_music
        scan_ready = threading.Event()
        scan_continues = threading.Event()
        original_count = len(server.TRACKS)

        def slow_scan(*args, **kwargs):
            scan_ready.set()
            scan_continues.wait(timeout=5)
            return original_scan(*args, **kwargs)

        server.scan_music = slow_scan
        try:
            read_counts = []
            read_errors = []

            def reader():
                for _ in range(20):
                    h = server.Handler(
                        request=MockHTTPRequest(),
                        client_address=('127.0.0.1', 8080),
                        server=Mock()
                    )
                    h.requestline = 'GET /search?q=test HTTP/1.0'
                    h.raw_requestline = b'GET /search?q=test HTTP/1.0'
                    h.request_version = 'HTTP/1.0'
                    h.path = '/search?q=test'
                    h.headers = {}
                    h._status_code = 200
                    h.headers_sent = {}
                    h.wfile = BytesIO()
                    h.command = 'GET'
                    try:
                        h.do_GET()
                        if h._status_code != 200:
                            read_errors.append(f"Status {h._status_code}")
                        else:
                            body = h.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
                            data = json.loads(body.decode("utf-8"))
                            read_counts.append(len(data["tracks"]))
                    except Exception as e:
                        read_errors.append(f"Error: {e}")

            # Start reader threads
            reader_threads = [threading.Thread(target=reader) for _ in range(2)]
            for t in reader_threads:
                t.start()

            # Start refresh in background
            def do_refresh():
                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'POST /refresh HTTP/1.0'
                h.raw_requestline = b'POST /refresh HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/refresh'
                h.headers = {'Content-Length': '0'}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'POST'
                h.do_POST()

            refresh_thread = threading.Thread(target=do_refresh)
            refresh_thread.start()


            scan_ready.wait(timeout=2)
            scan_continues.set()

            refresh_thread.join(timeout=5)
            for t in reader_threads:
                t.join(timeout=5)

            # All reads should succeed
            self.assertEqual(read_errors, [], f"Read errors: {read_errors}")
            # All read counts should be either old count or new count (1), never partial/invalid
            expected_counts = {original_count, 1}
            for c in read_counts:
                self.assertIn(c, expected_counts, f"Invalid track count seen: {c}")
        finally:
            server.scan_music = original_scan

    def test_search_not_blocked_during_refresh_scan(self):
        """Search requests do not block while a refresh scan is running."""
        original_scan = server.scan_music
        scan_started = threading.Event()
        scan_continues = threading.Event()
        search_completed = threading.Event()

        def slow_scan(*args, **kwargs):
            scan_started.set()
            scan_continues.wait(timeout=5)
            return original_scan(*args, **kwargs)

        server.scan_music = slow_scan
        try:
            search_status = {"value": None}

            def do_search():
                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'GET /search?q=test HTTP/1.0'
                h.raw_requestline = b'GET /search?q=test HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/search?q=test'
                h.headers = {}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'GET'
                h.do_POST = lambda: None  # Not used
                h.do_GET()
                search_status["value"] = h._status_code
                search_completed.set()

            # Start refresh (will hold _REFRESH_LOCK during scan)
            def do_refresh():
                h = server.Handler(
                    request=MockHTTPRequest(),
                    client_address=('127.0.0.1', 8080),
                    server=Mock()
                )
                h.requestline = 'POST /refresh HTTP/1.0'
                h.raw_requestline = b'POST /refresh HTTP/1.0'
                h.request_version = 'HTTP/1.0'
                h.path = '/refresh'
                h.headers = {'Content-Length': '0'}
                h._status_code = 200
                h.headers_sent = {}
                h.wfile = BytesIO()
                h.command = 'POST'
                h.do_POST()

            refresh_thread = threading.Thread(target=do_refresh)
            refresh_thread.start()


            scan_started.wait(timeout=2)

            # Fire search while scan is running
            search_thread = threading.Thread(target=do_search)
            search_thread.start()

            # Search should complete quickly (not wait for scan to finish)
            search_completed.wait(timeout=2)
            self.assertEqual(search_status["value"], 200, "Search blocked during refresh scan")

            # Now let scan complete
            scan_continues.set()
            refresh_thread.join(timeout=5)
            search_thread.join(timeout=2)
        finally:
            server.scan_music = original_scan


if __name__ == '__main__':
    unittest.main()