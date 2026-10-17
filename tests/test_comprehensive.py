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

# Import modules - we'll handle tag availability in tests
try:
    from scanner import scan_music, get_tag
    import server
    TAG_AVAILABLE = True
except ImportError:
    TAG_AVAILABLE = False
    scan_music = None
    get_tag = None
    server = None


class TestConstantsAndHelpers(unittest.TestCase):
    """Test constants and helper functions that don't require the tag library."""

    def test_search_limit_constant_exists(self):
        """Test that MAX_SEARCH_RESULTS constant is defined."""
        if TAG_AVAILABLE:
            self.assertTrue(hasattr(server, 'MAX_SEARCH_RESULTS'))
            self.assertIsInstance(server.MAX_SEARCH_RESULTS, int)
            self.assertGreater(server.MAX_SEARCH_RESULTS, 0)

    def test_track_id_length_constant_exists(self):
        """Test that TRACK_ID_LENGTH constant is defined in scanner."""
        if TAG_AVAILABLE:
            import scanner
            self.assertTrue(hasattr(scanner, 'TRACK_ID_LENGTH'))
            self.assertIsInstance(scanner.TRACK_ID_LENGTH, int)
            self.assertGreater(scanner.TRACK_ID_LENGTH, 0)

    def test_get_track_by_id_function_exists(self):
        """Test that get_track_byid helper function exists."""
        if TAG_AVAILABLE:
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
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

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
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

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
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

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
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

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
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        for query_param in ["", "q=", "q=%20%20"]:
            with self.subTest(query=query_param):
                path = f"/search?{query_param}" if query_param else "/search"
                self.assertEqual(self._get_search_json(path), {"tracks": []})


class TestImportAndBasicStructure(unittest.TestCase):
    """Test that modules can be imported and basic structure is intact."""

    def test_scanner_can_be_imported(self):
        """Test that scanner module can be imported."""
        # This test will pass if tag is available, otherwise we skip
        if TAG_AVAILABLE:
            import scanner
            self.assertTrue(hasattr(scanner, 'scan_music'))
            self.assertTrue(hasattr(scanner, 'get_tag'))
        else:
            self.skipTest("Tag not available")

    def test_server_can_be_imported(self):
        """Test that server module can be imported."""
        if TAG_AVAILABLE:
            import server
            self.assertTrue(hasattr(server, 'SETTINGS'))
            self.assertTrue(hasattr(server, 'TRACKS'))
            self.assertTrue(hasattr(server, 'MANIFEST_PATH'))
            self.assertTrue(hasattr(server, 'get_track_by_id'))
            self.assertTrue(hasattr(server, 'MAX_SEARCH_RESULTS'))
        else:
            self.skipTest("Tag not available")

    def test_get_tag_function_exists(self):
        """Test that get_tag function exists and works."""
        if TAG_AVAILABLE:
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
            self.skipTest("Tag not available")


class TestSymlinkProtection(unittest.TestCase):
    """Test symlink protection function."""

    def setUp(self):
        """Backup original SETTINGS."""
        self.original_settings = server.SETTINGS.copy()

    def tearDown(self):
        """Restore original SETTINGS."""
        server.SETTINGS = self.original_settings

    def test_path_under_music_dirs_returns_true(self):
        """Test that a path under a music directory returns True."""
        # Create a temporary directory inside the first music directory
        import tempfile
        from pathlib import Path
        music_dirs = server.SETTINGS.get("music_dirs", [])
        if not music_dirs:
            self.skipTest("No music directories configured")
        # Use the first music directory
        base_dir = music_dirs[0]
        with tempfile.TemporaryDirectory(dir=base_dir) as tmpdir:
            test_path = Path(tmpdir) / "test.mp3"
            test_path.touch()
            self.assertTrue(server._is_path_under_music_dirs(test_path))

    def test_path_outside_music_dirs_returns_false(self):
        """Test that a path outside all music directories returns False."""
        # Create a temporary directory in a temporary location (not under any music dir)
        import tempfile
        from pathlib import Path
        # We'll create a temp dir in the system temp, which is unlikely to be under music dirs
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "test.mp3"
            test_path.touch()
            # Ensure the test path is not under any music directory (by construction)
            music_dirs = server.SETTINGS.get("music_dirs", [])
            under_any = any(
                test_path.resolve().is_relative_to(music_dir.resolve())
                for music_dir in music_dirs
            )
            # If by chance it is under, we skip the assertion (but we can still test the function)
            # We'll just assert that the function returns False; if it's actually under, the test may fail.
            # To avoid false failure, we can check and skip if under.
            if under_any:
                self.skipTest("Temporary directory accidentally under a music directory")
            self.assertFalse(server._is_path_under_music_dirs(test_path))

    def test_symlink_outside_music_dirs_returns_false(self):
        """Test that a symlink pointing outside music directories returns False."""
        import tempfile
        import os
        from pathlib import Path
        music_dirs = server.SETTINGS.get("music_dirs", [])
        if not music_dirs:
            self.skipTest("No music directories configured")
        # Create a temporary directory outside music dirs
        with tempfile.TemporaryDirectory() as tmpdir:
            outside_dir = Path(tmpdir)
            # Create a symlink inside the first music directory pointing to outside_dir
            link_path = music_dirs[0] / "symlink_outside"
            try:
                os.symlink(outside_dir, link_path)
            except OSError as e:
                # On Windows, creating symlinks may require special privileges.
                # Skip the test if we cannot create a symlink.
                self.skipTest(f"Cannot create symlink: {e}")
            try:
                # The symlink itself is under the music directory, but its target is outside.
                # The function should resolve the symlink and check the target.
                # We'll test the path of a file inside the symlink directory.
                test_file = link_path / "test.mp3"
                test_file.touch()
                # The resolved path will be outside_dir/test.mp3, which is outside music dirs.
                self.assertFalse(server._is_path_under_music_dirs(test_file))
            finally:
                if link_path.exists():
                    try:
                        link_path.unlink()
                    except OSError:
                        pass


if __name__ == '__main__':
    unittest.main()