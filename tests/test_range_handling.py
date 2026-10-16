import json
import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

# Add the src directory to the path so we can import modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import server


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
        self.track_patch.stop()
        self.test_dir.cleanup()

    def _create_range_request(self, range_value=None):
        """Create a mock request with optional Range header."""
        self.handler.request = MockHTTPRequest()
        self.handler.headers = {}
        if range_value is not None:
            self.handler.headers['Range'] = range_value
            print(f"DEBUG: Setting Range header to: {range_value}")
        self.handler.path = f"/audio/{self.mock_track['id']}"
        print(f"DEBUG: Request path set to: {self.handler.path}")
        print(f"DEBUG: Headers: {self.handler.headers}")

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
        print(f"DEBUG: Initial status code: {self.handler._status_code}")
        self._create_range_request("bytes=0-99")
        print(f"DEBUG: Status code after _create_range_request: {self.handler._status_code}")

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


if __name__ == '__main__':
    unittest.main()