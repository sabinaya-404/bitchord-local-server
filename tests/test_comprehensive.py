import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock


class MockHTTPRequest:
    def makefile(self, mode="rb", bufsize=-1):
        return BytesIO(b"")

# Add the src directory to the path so we can import modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules - we'll handle mutagen availability in tests
try:
    from scanner import scan_music, get_tag
    import server
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    scan_music = None
    get_tag = None
    server = None


class TestConstantsAndHelpers(unittest.TestCase):
    """Test constants and helper functions that don't require mutagen."""

    def test_search_limit_constant_exists(self):
        """Test that MAX_SEARCH_RESULTS constant is defined."""
        if MUTAGEN_AVAILABLE:
            self.assertTrue(hasattr(server, 'MAX_SEARCH_RESULTS'))
            self.assertIsInstance(server.MAX_SEARCH_RESULTS, int)
            self.assertGreater(server.MAX_SEARCH_RESULTS, 0)

    def test_track_id_length_constant_exists(self):
        """Test that TRACK_ID_LENGTH constant is defined in scanner."""
        if MUTAGEN_AVAILABLE:
            import scanner
            self.assertTrue(hasattr(scanner, 'TRACK_ID_LENGTH'))
            self.assertIsInstance(scanner.TRACK_ID_LENGTH, int)
            self.assertGreater(scanner.TRACK_ID_LENGTH, 0)

    def test_get_track_by_id_function_exists(self):
        """Test that get_track_byid helper function exists."""
        if MUTAGEN_AVAILABLE:
            self.assertTrue(hasattr(server, 'get_track_by_id'))
            # Check that it's callable
            self.assertTrue(callable(server.get_track_by_id))


class TestSearchLogic(unittest.TestCase):
    """Test search-related logic that doesn't require full server instantiation."""

    def setUp(self):
        """Set up test data for search tests."""
        self.sample_tracks = [
            {
                "id": "track1",
                "title": "Song One",
                "artist": "Artist A",
                "album": "Album X",
                "path": Path("/music/song1.mp3")
            },
            {
                "id": "track2",
                "title": "Song Two",
                "artist": "Artist B",
                "album": "Album Y",
                "path": Path("/music/song2.flac")
            },
            {
                "id": "track3",
                "title": "Another Song",
                "artist": "Artist A",
                "album": "Album Z",
                "path": Path("/music/song3.mp3")
            }
        ]

    def test_search_result_limiting_logic(self):
        """Test the logic for limiting search results."""
        if not MUTAGEN_AVAILABLE:
            self.skipTest("Mutagen not available")

        # Simulate having more results than the limit
        many_tracks = []
        for i in range(60):  # More than MAX_SEARCH_RESULTS (50)
            many_tracks.append({
                "id": f"track{i}",
                "title": f"Song {i}",
                "artist": "Artist",
                "album": "Album",
                "path": Path(f"/music/song{i}.mp3")
            })

        # Apply the same filtering logic as in the search endpoint
        query = "song"
        tracks = [
            track for track in many_tracks
            if query
            and query in " ".join([
                track["title"],
                track["artist"],
                track["album"],
            ]).lower()
        ]

        # Apply the limit
        limited_tracks = tracks[:server.MAX_SEARCH_RESULTS]

        # Should be limited to MAX_SEARCH_RESULTS
        self.assertEqual(len(limited_tracks), server.MAX_SEARCH_RESULTS)
        self.assertEqual(len(limited_tracks), 50)

    def test_search_case_insensitive_matching(self):
        """Test that search matching is case insensitive."""
        if not MUTAGEN_AVAILABLE:
            self.skipTest("Mutagen not available")

        query = "SONG"
        matches = [
            track for track in self.sample_tracks
            if query
            and query.lower() in " ".join([
                track["title"],
                track["artist"],
                track["album"],
            ]).lower()
        ]
        # All three sample tracks should match "song" (case insensitive)
        self.assertEqual(len(matches), 3)

    def test_search_partial_matching(self):
        """Test that search finds partial matches."""
        if not MUTAGEN_AVAILABLE:
            self.skipTest("Mutagen not available")

        # Search for "one" should match "Song One"
        query = "one"
        matches = [
            track for track in self.sample_tracks
            if query
            and query in " ".join([
                track["title"],
                track["artist"],
                track["album"],
            ]).lower()
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["title"], "Song One")

    def _get_search_json(self, path):
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = "GET"
        handler.requestline = f"GET {path} HTTP/1.0"
        handler.request_version = "HTTP/1.0"
        handler.path = path
        handler.headers = {}
        handler.wfile = BytesIO()
        handler.do_GET()
        body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
        return json.loads(body.decode("utf-8"))

    def test_search_handler_limits_results(self):
        """Test that Handler's /search route actually limits results to MAX_SEARCH_RESULTS."""
        if not MUTAGEN_AVAILABLE:
            self.skipTest("Mutagen not available")

        many_tracks = [
            {
                "id": f"track{i}",
                "title": f"Song {i}",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path(f"/music/song{i}.flac"),
            }
            for i in range(60)
        ]

        orig_tracks = server.TRACKS
        server.TRACKS = many_tracks
        try:
            data = self._get_search_json("/search?q=song")
            self.assertIn("tracks", data)
            self.assertEqual(len(data["tracks"]), server.MAX_SEARCH_RESULTS)
            self.assertEqual(len(data["tracks"]), 50)
            for track in data["tracks"]:
                self.assertNotIn("path", track)
                self.assertEqual(track["audioQuality"], "LOSSLESS")
        finally:
            server.TRACKS = orig_tracks

    def test_search_handler_empty_query_returns_empty_list(self):
        """Test that Handler's /search route with empty or whitespace query returns empty list."""
        if not MUTAGEN_AVAILABLE:
            self.skipTest("Mutagen not available")

        for query_param in ["", "q=", "q=%20%20"]:
            with self.subTest(query=query_param):
                path = f"/search?{query_param}" if query_param else "/search"
                self.assertEqual(self._get_search_json(path), {"tracks": []})


class TestImportAndBasicStructure(unittest.TestCase):
    """Test that modules can be imported and basic structure is intact."""

    def test_scanner_can_be_imported(self):
        """Test that scanner module can be imported."""
        # This test will pass if mutagen is available, otherwise we skip
        if MUTAGEN_AVAILABLE:
            import scanner
            self.assertTrue(hasattr(scanner, 'scan_music'))
            self.assertTrue(hasattr(scanner, 'get_tag'))
        else:
            self.skipTest("Mutagen not available")

    def test_server_can_be_imported(self):
        """Test that server module can be imported."""
        if MUTAGEN_AVAILABLE:
            import server
            self.assertTrue(hasattr(server, 'SETTINGS'))
            self.assertTrue(hasattr(server, 'TRACKS'))
            self.assertTrue(hasattr(server, 'MANIFEST_PATH'))
            self.assertTrue(hasattr(server, 'get_track_by_id'))
            self.assertTrue(hasattr(server, 'MAX_SEARCH_RESULTS'))
        else:
            self.skipTest("Mutagen not available")

    def test_get_tag_function_exists(self):
        """Test that get_tag function exists and works."""
        if MUTAGEN_AVAILABLE:
            from scanner import get_tag
            # Test basic functionality
            tags = {"title": ["Test Song"]}
            result = get_tag(tags, "title", "Fallback")
            self.assertEqual(result, "Test Song")

            # Test fallback
            tags = {}
            result = get_tag(tags, "title", "Fallback")
            self.assertEqual(result, "Fallback")

            # Test empty list
            tags = {"title": []}
            result = get_tag(tags, "title", "Fallback")
            self.assertEqual(result, "Fallback")
        else:
            self.skipTest("Mutagen not available")


if __name__ == '__main__':
    unittest.main()