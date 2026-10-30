import json
import os
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
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


class TestRangeHandling(unittest.TestCase):
    """Test HTTP range request handling for audio streaming."""

    def setUp(self):
        """Set up test fixtures for range handling tests."""
        # Create a temporary directory with a test audio file
        self.test_dir = tempfile.TemporaryDirectory()
        # Backup original SETTINGS and update music_dirs to include our temporary directory
        self.original_settings = server.SETTINGS.copy()
        server.SETTINGS = {
            **server.SETTINGS,
            "music_dirs": list(server.SETTINGS["music_dirs"]) + [Path(self.test_dir.name).expanduser()]
        }
        self.test_file_path = os.path.join(self.test_dir.name, "test.mp3")

        # Create a test file with known content
        with open(self.test_file_path, 'wb') as f:
            # Create a file with 1000 bytes of known data
            f.write(b'a' * 1000)  # 1000 bytes of 'a'

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
        # Initialize tracking variables
        self.handler._status_code = 200
        self.handler.headers_sent = {}
        # Override the wfile to capture output
        self.handler.wfile = BytesIO()

    def tearDown(self):
        """Clean up test fixtures."""
        # Restore original SETTINGS
        server.SETTINGS = self.original_settings
        self.track_patch.stop()
        self.test_dir.cleanup()

    def _create_range_request(self, range_value=None):
        """Create a mock request with optional Range header."""
        self.handler.request = MockHTTPRequest()
        self.handler.headers = {}
        if range_value is not None:
            self.handler.headers['Range'] = range_value
        self.handler.path = f"/audio/{self.mock_track['id']}"

    def _get_response(self):
        """Execute the handler's do_GET method and return the response."""
        self.handler.wfile = BytesIO()
        self.handler.do_GET()
        # Get the response data from wfile
        response_data = self.handler.wfile.getvalue()
        # Parse the response to get status, headers, and body
        # Find the end of headers (blank line)
        header_end = response_data.find(b'\r\n\r\n')
        if header_end == -1:
            # No headers found, return everything as body
            return response_data
        # Return just the body (after headers)
        return response_data[header_end + 4:]

    def test_normal_range_request(self):
        """Test normal range request like bytes=0-99."""
        self._create_range_request("bytes=0-99")

        # Process the request to get the response
        response_body = self._get_response()

        # Check that we got a 206 Partial Content response
        self.assertEqual(self.handler._status_code, 206)
        # Check that we got the right content range
        self.assertIn('Content-Range', self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent['Content-Range'], 'bytes 0-99/1000')
        # Check that we got 100 bytes of data
        self.assertEqual(len(response_body), 100)

    def test_open_ended_range_request(self):
        """Test open-ended range request like bytes=500-."""
        self._create_range_request("bytes=500-")

        # Process the request to get the response
        response_body = self._get_response()

        # Check that we got a 206 Partial Content response
        self.assertEqual(self.handler._status_code, 206)
        # Check that we got the right content range
        self.assertIn('Content-Range', self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent['Content-Range'], 'bytes 500-999/1000')
        # Check that we got 500 bytes of data
        self.assertEqual(len(response_body), 500)

    def test_suffix_range_request(self):
        """Test suffix range request like bytes=-100."""
        self._create_range_request("bytes=-100")

        # Process the request to get the response
        response_body = self._get_response()

        # Check that we got a 206 Partial Content response
        self.assertEqual(self.handler._status_code, 206)
        # Check that we got the right content range
        self.assertIn('Content-Range', self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent['Content-Range'], 'bytes 900-999/1000')
        # Check that we got 100 bytes of data
        self.assertEqual(len(response_body), 100)

    def test_oversized_suffix_range(self):
        """Test oversized suffix like bytes=-2000 on 1000-byte file."""
        self._create_range_request("bytes=-2000")

        # Process the request to get the response
        response_body = self._get_response()

        # Check that we got a 206 Partial Content response (entire file with range header)
        self.assertEqual(self.handler._status_code, 206)
        # Check that we got the right content range
        self.assertIn('Content-Range', self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent['Content-Range'], 'bytes 0-999/1000')
        # Check that we got 1000 bytes of data
        self.assertEqual(len(response_body), 1000)

    def test_invalid_range_request(self):
        """Test invalid range like bytes=200-100."""
        self._create_range_request("bytes=200-100")

        # Process the request to get the response
        self._get_response()

        # Check that we got a 416 Range Not Satisfiable response
        self.assertEqual(self.handler._status_code, 416)
        # Check that we got the right content range
        self.assertIn('Content-Range', self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent['Content-Range'], 'bytes */1000')

    def test_out_of_bounds_range(self):
        """Test out-of-bounds range like bytes=2000-3000."""
        self._create_range_request("bytes=2000-3000")

        # Process the request to get the response
        self._get_response()

        # Check that we got a 416 Range Not Satisfiable response
        self.assertEqual(self.handler._status_code, 416)
        # Check that we got the right content range
        self.assertIn('Content-Range', self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent['Content-Range'], 'bytes */1000')

    def test_zero_length_file_range(self):
        """Test range requests on zero-length file return 416."""
        # Create a zero-length file
        zero_file_path = Path(self.test_dir.name) / "zero.mp3"
        zero_file_path.touch()

        # Create a track for the zero-length file
        zero_track = self.mock_track.copy()
        zero_track["id"] = "zero-track"
        zero_track["path"] = zero_file_path

        # Update the patched tracks
        server.TRACKS = [zero_track]

        self.handler.path = f"/audio/{zero_track['id']}"
        self.handler.headers = {"Range": "bytes=0-0"}

        # Process the request to get the response
        self._get_response()

        # Check that we got a 416 Range Not Satisfiable response
        self.assertEqual(self.handler._status_code, 416)
        self.assertIn("Content-Range", self.handler.headers_sent)
        self.assertEqual(self.handler.headers_sent["Content-Range"], "bytes */0")

    def test_zero_length_file_without_range(self):
        """Test request on zero-length file without range returns 200 with 0 bytes."""
        zero_file_path = Path(self.test_dir.name) / "zero_empty.mp3"
        zero_file_path.touch()

        zero_track = self.mock_track.copy()
        zero_track["id"] = "zero-empty-track"
        zero_track["path"] = zero_file_path

        server.TRACKS = [zero_track]

        self.handler.path = f"/audio/{zero_track['id']}"
        self.handler.headers = {}

        response_body = self._get_response()

        self.assertEqual(self.handler._status_code, 200)
        self.assertEqual(self.handler.headers_sent["Content-Length"], "0")
        self.assertEqual(len(response_body), 0)

    def test_nonexistent_track_returns_404(self):
        """Test request for nonexistent track returns 404."""
        self.handler.path = "/audio/nonexistent-track-id"
        self.handler.headers = {}
        self._get_response()
        self.assertEqual(self.handler._status_code, 404)


class TestSymlinkProtectionIntegration(unittest.TestCase):
    """Integration test for symlink protection blocking access to files outside music directories."""

    def setUp(self):
        """Set up test fixtures with a temporary file outside music directories."""
        # Create a temporary directory outside configured music directories
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_file_path = Path(self.test_dir.name) / "test.mp3"

        # Create a test file with known content
        with open(self.test_file_path, 'wb') as f:
            f.write(b'a' * 1000)  # 1000 bytes of 'a'

        # Create a mock track for this file
        self.mock_track = {
            "id": "test-track-outside",
            "title": "Test Track Outside",
            "artist": "Test Artist",
            "album": "Test Album",
            "path": self.test_file_path.resolve(),
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
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
        # Initialize tracking variables
        self.handler._status_code = 200
        self.handler.headers_sent = {}
        # Override the wfile to capture output
        self.handler.wfile = BytesIO()

    def tearDown(self):
        """Clean up test fixtures."""
        self.track_patch.stop()
        self.test_dir.cleanup()

    def _create_range_request(self, range_value=None):
        """Create a mock request with optional Range header."""
        self.handler.request = MockHTTPRequest()
        self.handler.headers = {}
        if range_value is not None:
            self.handler.headers['Range'] = range_value
        self.handler.path = f"/audio/{self.mock_track['id']}"

    def _get_response(self):
        """Execute the handler's do_GET method and return the response."""
        self.handler.wfile = BytesIO()
        self.handler.do_GET()
        # Get the response data from wfile
        response_data = self.handler.wfile.getvalue()
        # Parse the response to get status, headers, and body
        # Find the end of headers (blank line)
        header_end = response_data.find(b'\r\n\r\n')
        if header_end == -1:
            # No headers found, return everything as body
            return response_data
        # Return just the body (after headers)
        return response_data[header_end + 4:]

    def test_outside_path_blocked_normal_range(self):
        """Test that a file outside music directories is blocked for normal range request."""
        self._create_range_request("bytes=0-99")
        response_body = self._get_response()
        # Should be blocked by symlink protection, returning 404
        self.assertEqual(self.handler._status_code, 404)

    def test_outside_path_blocked_open_ended_range(self):
        """Test that a file outside music directories is blocked for open-ended range request."""
        self._create_range_request("bytes=500-")
        response_body = self._get_response()
        self.assertEqual(self.handler._status_code, 404)

    def test_outside_path_blocked_suffix_range(self):
        """Test that a file outside music directories is blocked for suffix range request."""
        self._create_range_request("bytes=-100")
        response_body = self._get_response()
        self.assertEqual(self.handler._status_code, 404)

    def test_outside_path_blocked_invalid_range(self):
        """Test that a file outside music directories is blocked for invalid range request."""
        self._create_range_request("bytes=200-100")
        self._get_response()
        self.assertEqual(self.handler._status_code, 404)

    def test_outside_path_blocked_out_of_bounds_range(self):
        """Test that a file outside music directories is blocked for out-of-bounds range request."""
        self._create_range_request("bytes=2000-3000")
        self._get_response()
        self.assertEqual(self.handler._status_code, 404)

    def test_outside_path_blocked_zero_length_file_range(self):
        """Test that a zero-length file outside music directories is blocked."""
        # Create a zero-length file
        zero_file_path = Path(self.test_dir.name) / "zero.mp3"
        zero_file_path.touch()

        # Create a track for the zero-length file
        zero_track = self.mock_track.copy()
        zero_track["id"] = "zero-track-outside"
        zero_track["path"] = zero_file_path.resolve()

        # Update the patched tracks
        server.TRACKS = [zero_track]

        self.handler.path = f"/audio/{zero_track['id']}"
        self.handler.headers = {"Range": "bytes=0-0"}

        # Process the request to get the response
        self._get_response()

        # Check that we got a 404 (blocked) not 416
        self.assertEqual(self.handler._status_code, 404)

    def test_outside_path_blocked_zero_length_file_without_range(self):
        """Test that a zero-length file outside music directories without range is blocked."""
        zero_file_path = Path(self.test_dir.name) / "zero_empty.mp3"
        zero_file_path.touch()

        zero_track = self.mock_track.copy()
        zero_track["id"] = "zero-empty-track-outside"
        zero_track["path"] = zero_file_path.resolve()

        server.TRACKS = [zero_track]

        self.handler.path = f"/audio/{zero_track['id']}"
        self.handler.headers = {}

        response_body = self._get_response()

        self.assertEqual(self.handler._status_code, 404)

    def test_symlink_inside_music_dir_pointing_outside_blocked_via_audio_endpoint(self):
        """Test that a symlink inside an allowed music directory pointing to a file outside is blocked via audio endpoint."""
        with tempfile.TemporaryDirectory() as music_dir:
            music_dir_path = Path(music_dir)
            with tempfile.TemporaryDirectory() as outside_dir:
                outside_dir_path = Path(outside_dir)
                # Create the target file outside
                target_file = outside_dir_path / "target.mp3"
                target_file.write_bytes(b'a' * 1000)
                # Inside the music directory, create a symlink pointing to the target file
                symlink_path = music_dir_path / "link.mp3"
                try:
                    os.symlink(target_file, symlink_path)
                except OSError as e:
                    self.skipTest(f"Cannot create symlink: {e}")
                else:
                    # Backup original SETTINGS and TRACKS
                    original_settings = server.SETTINGS.copy()
                    original_tracks = server.TRACKS
                    try:
                        # Set music_dirs to only our music directory (to isolate)
                        server.SETTINGS = {
                            **server.SETTINGS,
                            "music_dirs": [music_dir_path]
                        }
                        # Scan the music directory to populate TRACKS
                        tracks = scan_music([music_dir_path])
                        server.TRACKS = tracks
                        # Find the track for the symlink (should be one track)
                        self.assertEqual(len(tracks), 1)
                        track = tracks[0]
                        # The track's path should be the resolved path (i.e., target_file)
                        self.assertEqual(track["path"], target_file.resolve())
                        # Create a handler for this track
                        handler = server.Handler(
                            request=MockHTTPRequest(),
                            client_address=('127.0.0.1', 8080),
                            server=Mock()
                        )
                        handler.requestline = ''
                        handler.raw_requestline = b''
                        handler.request_version = 'HTTP/1.1'
                        handler._status_code = 200
                        handler.headers_sent = {}
                        handler.wfile = BytesIO()
                        # Make a request to the audio endpoint for this track
                        handler.path = f"/audio/{track['id']}"
                        handler.headers = {}
                        # Process the request
                        handler.do_GET()
                        # Should be blocked because the resolved path is outside music directories
                        self.assertEqual(handler._status_code, 404)
                    finally:
                        # Restore SETTINGS and TRACKS
                        server.SETTINGS = original_settings
                        server.TRACKS = original_tracks


if __name__ == '__main__':
    unittest.main()