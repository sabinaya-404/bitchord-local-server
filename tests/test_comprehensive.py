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

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.scanner import scan_music, get_tag, normalize
    import src.server as server
    TAG_AVAILABLE = True
except ImportError:
    TAG_AVAILABLE = False
    scan_music = None
    get_tag = None
    normalize = None
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
            import src.scanner as scanner
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
            import src.scanner as scanner
            self.assertTrue(hasattr(scanner, 'scan_music'))
            self.assertTrue(hasattr(scanner, 'get_tag'))
        else:
            self.skipTest("Tag not available")

    def test_server_can_be_imported(self):
        """Test that server module can be imported."""
        if TAG_AVAILABLE:
            # server is already imported as `import src.server as server`
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
            # get_tag is already imported from src.scanner
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

    def test_symlink_inside_music_dir_pointing_inside_allowed(self):
        """Symlink in music dir pointing to another location inside music dirs: allowed."""
        import tempfile
        import os
        from pathlib import Path
        music_dirs = server.SETTINGS.get("music_dirs", [])
        if not music_dirs:
            self.skipTest("No music directories configured")
        with tempfile.TemporaryDirectory(dir=music_dirs[0]) as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Create a real file inside the music directory
            real_file = tmpdir_path / "real.mp3"
            real_file.write_bytes(b"real audio data")
            # Create a symlink pointing to the real file
            link_path = music_dirs[0] / "link_inside.mp3"
            try:
                os.symlink(real_file, link_path)
            except OSError as e:
                self.skipTest(f"Cannot create symlink: {e}")
            try:
                # Scan should find both the real file and the symlink (which resolves to same file)
                tracks = scan_music(music_dirs)
                # Both should resolve to the same path, so only one track (deduplication by path not implemented, but both will have same track_id)
                # At minimum, the symlink should not cause an error and should be indexed
                link_tracks = [t for t in tracks if t.get("path") and real_file.resolve() in t["path"].parents]
                self.assertGreaterEqual(len(link_tracks), 1, "Symlink inside music dir should be indexed")
            finally:
                if link_path.exists():
                    try:
                        link_path.unlink()
                    except OSError:
                        pass

    def test_symlink_inside_music_dir_pointing_outside_rejected_at_scan(self):
        """Symlink in music dir pointing outside all music dirs: rejected during scanning."""
        import tempfile
        import os
        from pathlib import Path
        music_dirs = server.SETTINGS.get("music_dirs", [])
        if not music_dirs:
            self.skipTest("No music directories configured")
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_path = Path(outside_dir)
            outside_file = outside_path / "outside.mp3"
            outside_file.write_bytes(b"outside audio data")
            # Create symlink inside music dir pointing outside
            link_path = music_dirs[0] / "link_outside.mp3"
            try:
                os.symlink(outside_file, link_path)
            except OSError as e:
                self.skipTest(f"Cannot create symlink: {e}")
            try:
                tracks = scan_music(music_dirs)
                # The symlink's resolved path (outside_file) should NOT be under any music dir
                # So it should not appear in tracks
                outside_tracks = [t for t in tracks if t.get("path") == outside_file.resolve()]
                self.assertEqual(len(outside_tracks), 0, "Symlink pointing outside should not be indexed")
            finally:
                if link_path.exists():
                    try:
                        link_path.unlink()
                    except OSError:
                        pass

    def test_symlinked_music_dir_remains_usable(self):
        """A configured music directory that is itself a symlink remains usable."""
        import tempfile
        import os
        from pathlib import Path
        music_dirs = server.SETTINGS.get("music_dirs", [])
        if not music_dirs:
            self.skipTest("No music directories configured")
        with tempfile.TemporaryDirectory() as real_music_dir:
            real_music = Path(real_music_dir)
            real_file = real_music / "real.mp3"
            real_file.write_bytes(b"real audio data")
            # Create a symlink to the real music directory
            link_dir = music_dirs[0] / "symlinked_music"
            try:
                os.symlink(real_music, link_dir, target_is_directory=True)
            except OSError as e:
                self.skipTest(f"Cannot create directory symlink: {e}")
            try:
                # Add the symlinked directory to music_dirs temporarily
                original_music_dirs = server.SETTINGS["music_dirs"]
                server.SETTINGS["music_dirs"] = original_music_dirs + [link_dir]
                try:
                    tracks = scan_music(server.SETTINGS["music_dirs"])
                    # Should find the file through the symlinked directory
                    found = any(t.get("path") and real_file.resolve() == t["path"] for t in tracks)
                    self.assertTrue(found, "Symlinked music directory should be scanned")
                finally:
                    server.SETTINGS["music_dirs"] = original_music_dirs
            finally:
                if link_dir.exists():
                    try:
                        link_dir.unlink()
                    except OSError:
                        pass

    def test_multiple_music_dirs_with_symlinks_between(self):
        """Multiple configured music directories with symlinks between them."""
        import tempfile
        import os
        from pathlib import Path
        music_dirs = server.SETTINGS.get("music_dirs", [])
        if not music_dirs:
            self.skipTest("No music directories configured")
        with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
            music1 = Path(dir1)
            music2 = Path(dir2)
            file1 = music1 / "song1.mp3"
            file1.write_bytes(b"song 1")
            file2 = music2 / "song2.mp3"
            file2.write_bytes(b"song 2")
            # Create symlink from music1 to music2 file
            link_in_1 = music1 / "link_to_song2.mp3"
            try:
                os.symlink(file2, link_in_1)
            except OSError as e:
                self.skipTest(f"Cannot create symlink: {e}")
            try:
                # Configure both directories
                original_music_dirs = server.SETTINGS["music_dirs"]
                server.SETTINGS["music_dirs"] = [music1, music2]
                try:
                    tracks = scan_music(server.SETTINGS["music_dirs"])
                    # Should find both real files and the symlink (which resolves to file2 in music2)
                    # file1 and file2 should be found
                    paths = {t["path"] for t in tracks if t.get("path")}
                    self.assertIn(file1.resolve(), paths)
                    self.assertIn(file2.resolve(), paths)
                    # The symlink in music1 pointing to file2 in music2 should also resolve to file2
                    # So we should have at least file1 and file2
                finally:
                    server.SETTINGS["music_dirs"] = original_music_dirs
            finally:
                if link_in_1.exists():
                    try:
                        link_in_1.unlink()
                    except OSError:
                        pass


class TestScannerTrackField(unittest.TestCase):
    """Test that scanner extracts track number metadata."""

    def setUp(self):
        """Backup original SETTINGS."""
        self.original_settings = server.SETTINGS.copy()

    def tearDown(self):
        """Restore original SETTINGS."""
        server.SETTINGS = self.original_settings

    def test_scan_music_includes_track_field_when_present(self):
        """Test that scan_music includes track field when track metadata exists."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.mp3"
            test_file.write_bytes(b"fake audio data")

            # Scan the directory
            tracks = scan_music([Path(tmpdir)])

            # Should find the track
            self.assertEqual(len(tracks), 1)
            track = tracks[0]

            # Track field should exist in the result
            self.assertIn("track", track)
            # Value should be None (no actual tags in fake file) or an int
            self.assertTrue(track["track"] is None or isinstance(track["track"], int))

    def test_scan_music_includes_track_field_when_absent(self):
        """Test that scan_music includes track field even when metadata is absent."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.mp3"
            test_file.write_bytes(b"fake audio data")

            tracks = scan_music([Path(tmpdir)])

            self.assertEqual(len(tracks), 1)
            track = tracks[0]

            # Track field should always be present
            self.assertIn("track", track)
            # Should be None when no track metadata in file
            self.assertIsNone(track["track"])

    def test_search_response_includes_track_field(self):
        """Test that /search response includes track field from track data."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        # Create mock track with track number
        mock_track = {
            "id": "test-track-id",
            "title": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
            "track": 5,
            "path": Path("/music/test.mp3"),
        }

        orig_tracks = server.TRACKS
        server.TRACKS = [mock_track]
        try:
            # Make a search request
            handler = server.Handler(
                request=MockHTTPRequest(),
                client_address=("127.0.0.1", 8080),
                server=Mock(),
            )
            handler.command = "GET"
            handler.requestline = "GET /search?q=test HTTP/1.0"
            handler.request_version = "HTTP/1.0"
            handler.path = "/search?q=test"
            handler.headers = {}
            handler.wfile = BytesIO()
            handler.do_GET()

            body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
            data = json.loads(body.decode("utf-8"))

            self.assertEqual(handler._status_code, 200)
            self.assertIn("tracks", data)
            self.assertEqual(len(data["tracks"]), 1)

            # Track field should be in the response
            response_track = data["tracks"][0]
            self.assertIn("track", response_track)
            self.assertEqual(response_track["track"], 5)
        finally:
            server.TRACKS = orig_tracks

    def test_search_response_includes_track_field_none(self):
        """Test that /search response includes track field as None when absent."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        # Create mock track without track number
        mock_track = {
            "id": "test-track-id",
            "title": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
            "track": None,
            "path": Path("/music/test.mp3"),
        }

        orig_tracks = server.TRACKS
        server.TRACKS = [mock_track]
        try:
            handler = server.Handler(
                request=MockHTTPRequest(),
                client_address=("127.0.0.1", 8080),
                server=Mock(),
            )
            handler.command = "GET"
            handler.requestline = "GET /search?q=test HTTP/1.0"
            handler.request_version = "HTTP/1.0"
            handler.path = "/search?q=test"
            handler.headers = {}
            handler.wfile = BytesIO()
            handler.do_GET()

            body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
            data = json.loads(body.decode("utf-8"))

            self.assertEqual(handler._status_code, 200)
            self.assertIn("tracks", data)
            self.assertEqual(len(data["tracks"]), 1)

            # Track field should be in the response as None
            response_track = data["tracks"][0]
            self.assertIn("track", response_track)
            self.assertIsNone(response_track["track"])
        finally:
            server.TRACKS = orig_tracks


class TestTrackQuality(unittest.TestCase):
    """Test track_quality helper function."""

    def setUp(self):
        """Backup original SETTINGS."""
        self.original_settings = server.SETTINGS.copy()

    def tearDown(self):
        """Restore original SETTINGS."""
        server.SETTINGS = self.original_settings

    def test_track_quality_flac_returns_lossless(self):
        """Test that track_quality returns LOSSLESS for FLAC format."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {"format": "flac"}
        self.assertEqual(server.track_quality(mock_track), "LOSSLESS")

    def test_track_quality_mp3_returns_high(self):
        """Test that track_quality returns HIGH for MP3 format."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {"format": "mp3"}
        self.assertEqual(server.track_quality(mock_track), "HIGH")

    def test_track_quality_wav_returns_high(self):
        """Test that track_quality returns HIGH for WAV format."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {"format": "wav"}
        self.assertEqual(server.track_quality(mock_track), "HIGH")

    def test_track_quality_aiff_returns_high(self):
        """Test that track_quality returns HIGH for AIFF format."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {"format": "aiff"}
        self.assertEqual(server.track_quality(mock_track), "HIGH")

    def test_track_quality_unknown_format_returns_high(self):
        """Test that track_quality returns HIGH for unknown formats."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {"format": "unknown"}
        self.assertEqual(server.track_quality(mock_track), "HIGH")


class TestSearchAudioQuality(unittest.TestCase):
    """Test that /search returns correct audioQuality field."""

    def setUp(self):
        """Backup original SETTINGS and TRACKS."""
        self.original_settings = server.SETTINGS.copy()
        self.original_tracks = server.TRACKS

    def tearDown(self):
        """Restore original SETTINGS and TRACKS."""
        server.SETTINGS = self.original_settings
        server.TRACKS = self.original_tracks

    def test_search_returns_audio_quality_lossless_for_flac(self):
        """Test that search response includes LOSSLESS for FLAC tracks."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {
            "id": "flac-track",
            "title": "FLAC Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "flac",
            "codec": "flac",
            "container": "flac",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 1000,
            "path": Path("/music/test.flac"),
        }

        server.TRACKS = [mock_track]
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = "GET"
        handler.requestline = "GET /search?q=track HTTP/1.0"
        handler.request_version = "HTTP/1.0"
        handler.path = "/search?q=track"
        handler.headers = {}
        handler.wfile = BytesIO()
        handler.do_GET()

        body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
        data = json.loads(body.decode("utf-8"))

        self.assertEqual(handler._status_code, 200)
        self.assertIn("tracks", data)
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["audioQuality"], "LOSSLESS")

    def test_search_returns_audio_quality_high_for_mp3(self):
        """Test that search response includes HIGH for MP3 tracks."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {
            "id": "mp3-track",
            "title": "MP3 Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
            "path": Path("/music/test.mp3"),
        }

        server.TRACKS = [mock_track]
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = "GET"
        handler.requestline = "GET /search?q=track HTTP/1.0"
        handler.request_version = "HTTP/1.0"
        handler.path = "/search?q=track"
        handler.headers = {}
        handler.wfile = BytesIO()
        handler.do_GET()

        body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
        data = json.loads(body.decode("utf-8"))

        self.assertEqual(handler._status_code, 200)
        self.assertIn("tracks", data)
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["audioQuality"], "HIGH")


class TestStreamQuality(unittest.TestCase):
    """Test that /stream returns correct quality and handles requested quality."""

    def setUp(self):
        """Backup original SETTINGS and TRACKS."""
        self.original_settings = server.SETTINGS.copy()
        self.original_tracks = server.TRACKS

    def tearDown(self):
        """Restore original SETTINGS and TRACKS."""
        server.SETTINGS = self.original_settings
        server.TRACKS = self.original_tracks

    def test_stream_returns_actual_quality_for_flac(self):
        """Test that stream response includes LOSSLESS for FLAC regardless of requested quality."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {
            "id": "flac-track",
            "title": "FLAC Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "flac",
            "codec": "flac",
            "container": "flac",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 1000,
            "path": Path("/music/test.flac"),
        }

        server.TRACKS = [mock_track]
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = "GET"
        handler.requestline = "GET /stream/flac-track?quality=HIGH HTTP/1.0"
        handler.request_version = "HTTP/1.0"
        handler.path = "/stream/flac-track?quality=HIGH"
        handler.headers = {}
        handler.wfile = BytesIO()
        handler.do_GET()

        body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
        data = json.loads(body.decode("utf-8"))

        self.assertEqual(handler._status_code, 200)
        self.assertIn("quality", data)
        # Should return actual file quality (LOSSLESS) not requested quality (HIGH)
        self.assertEqual(data["quality"], "LOSSLESS")

    def test_stream_returns_actual_quality_for_mp3(self):
        """Test that stream response includes HIGH for MP3 regardless of requested quality."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {
            "id": "mp3-track",
            "title": "MP3 Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
            "path": Path("/music/test.mp3"),
        }

        server.TRACKS = [mock_track]
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = "GET"
        handler.requestline = "GET /stream/mp3-track?quality=LOSSLESS HTTP/1.0"
        handler.request_version = "HTTP/1.0"
        handler.path = "/stream/mp3-track?quality=LOSSLESS"
        handler.headers = {}
        handler.wfile = BytesIO()
        handler.do_GET()

        body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1]
        data = json.loads(body.decode("utf-8"))

        self.assertEqual(handler._status_code, 200)
        self.assertIn("quality", data)
        # Should return actual file quality (HIGH) not requested quality (LOSSLESS)
        self.assertEqual(data["quality"], "HIGH")

    def test_stream_no_longer_rejects_non_lossless_quality(self):
        """Test that stream no longer returns 404 for non-LOSSLESS requested quality."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        mock_track = {
            "id": "mp3-track",
            "title": "MP3 Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
            "path": Path("/music/test.mp3"),
        }

        server.TRACKS = [mock_track]
        handler = server.Handler(
            request=MockHTTPRequest(),
            client_address=("127.0.0.1", 8080),
            server=Mock(),
        )
        handler.command = "GET"
        handler.requestline = "GET /stream/mp3-track?quality=HIGH HTTP/1.0"
        handler.request_version = "HTTP/1.0"
        handler.path = "/stream/mp3-track?quality=HIGH"
        handler.headers = {}
        handler.wfile = BytesIO()
        handler.do_GET()

        # Should return 200, not 404
        self.assertEqual(handler._status_code, 200)


class TestSearchMatching(unittest.TestCase):
    """Test improved search matching with normalize, word-based matching, and precomputed _search."""

    def setUp(self):
        """Backup original SETTINGS and TRACKS."""
        self.original_settings = server.SETTINGS.copy()
        self.original_tracks = server.TRACKS

    def tearDown(self):
        """Restore original SETTINGS and TRACKS."""
        server.SETTINGS = self.original_settings
        server.TRACKS = self.original_tracks

    def _make_handler(self, path):
        """Create a handler for testing /search endpoint."""
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
        return handler, json.loads(body.decode("utf-8"))

    def test_search_multi_word_match(self):
        """Test multi-word search: all words must match regardless of order."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Song One",
                "artist": "Artist A",
                "album": "Album X",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/song1.flac"),
                "_search": normalize("Song One Artist A Album X"),
            },
            {
                "id": "t2",
                "title": "Another Song",
                "artist": "Artist B",
                "album": "Album Y",
                "format": "mp3",
                "codec": "mp3",
                "container": "mp3",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 320,
                "path": Path("/music/song2.mp3"),
                "_search": normalize("Another Song Artist B Album Y"),
            },
        ]
        server.TRACKS = tracks

        # "artist a song" should match only t1 (has "a" which is unique to t1)
        handler, data = self._make_handler("/search?q=artist+a+song")
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["id"], "t1")

        # "song artist" matches BOTH t1 and t2 (both have "song" and "artist" as words)
        handler, data = self._make_handler("/search?q=song+artist")
        self.assertEqual(len(data["tracks"]), 2)
        result_ids = {t["id"] for t in data["tracks"]}
        self.assertEqual(result_ids, {"t1", "t2"})

        # "artist b another" should match only t2 (has "b" and "another" unique to t2)
        handler, data = self._make_handler("/search?q=artist+b+another")
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["id"], "t2")

    def test_search_accent_normalization(self):
        """Test that accented characters are normalized in search."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Café",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/cafe.flac"),
                "_search": normalize("Café Artist Album"),
            },
        ]
        server.TRACKS = tracks

        # Search without accent should match accented track
        handler, data = self._make_handler("/search?q=cafe")
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["title"], "Café")

        # Search with accent should also match
        handler, data = self._make_handler("/search?q=café")
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["title"], "Café")

    def test_search_punctuation_normalization(self):
        """Test that punctuation is converted to spaces in search."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Song-Title",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/song-title.flac"),
                "_search": normalize("Song-Title Artist Album"),
            },
        ]
        server.TRACKS = tracks

        # Search with space instead of hyphen should match
        handler, data = self._make_handler("/search?q=song+title")
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["title"], "Song-Title")

        # Search with punctuation should also work
        handler, data = self._make_handler("/search?q=song-title")
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["title"], "Song-Title")

    def test_search_order_independence(self):
        """Test that word order doesn't matter in search."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Track One",
                "artist": "Artist Two",
                "album": "Album Three",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/track.flac"),
                "_search": normalize("Track One Artist Two Album Three"),
            },
        ]
        server.TRACKS = tracks

        queries = [
            "track one artist two",
            "artist two track one",
            "one track two artist",
            "album three track one",
        ]
        for query in queries:
            with self.subTest(query=query):
                handler, data = self._make_handler(f"/search?q={query.replace(' ', '+')}")
                self.assertEqual(len(data["tracks"]), 1, f"Failed for query: {query}")
                self.assertEqual(data["tracks"][0]["id"], "t1")

    def test_search_partial_word_rejection(self):
        """Test that partial word matches are rejected (whole-word matching)."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Love Song",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/love.flac"),
                "_search": normalize("Love Song Artist Album"),
            },
        ]
        server.TRACKS = tracks

        # "lo" should NOT match "love" (substring match rejected)
        handler, data = self._make_handler("/search?q=lo")
        self.assertEqual(len(data["tracks"]), 0)

        # "lov" should NOT match "love"
        handler, data = self._make_handler("/search?q=lov")
        self.assertEqual(len(data["tracks"]), 0)

        # "love" SHOULD match
        handler, data = self._make_handler("/search?q=love")
        self.assertEqual(len(data["tracks"]), 1)

        # "song" SHOULD match
        handler, data = self._make_handler("/search?q=song")
        self.assertEqual(len(data["tracks"]), 1)

    def test_search_empty_query_returns_empty(self):
        """Test that empty or whitespace-only queries return empty results."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Track",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/track.flac"),
                "_search": normalize("Track Artist Album"),
            },
        ]
        server.TRACKS = tracks

        empty_queries = ["", "   ", "\t\n", "  \t  "]
        for query in empty_queries:
            with self.subTest(query=repr(query)):
                handler, data = self._make_handler(f"/search?q={query}")
                self.assertEqual(data["tracks"], [], f"Expected empty for query: {repr(query)}")

    def test_search_punctuation_only_query_returns_empty(self):
        """Test that punctuation-only queries return empty results."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Track",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/track.flac"),
                "_search": normalize("Track Artist Album"),
            },
        ]
        server.TRACKS = tracks

        punct_queries = ["...", "!!!", "???", ".,;:", "!@#$%"]
        for query in punct_queries:
            with self.subTest(query=query):
                handler, data = self._make_handler(f"/search?q={query}")
                self.assertEqual(data["tracks"], [], f"Expected empty for query: {query}")

    def test_search_preserves_max_results_limit(self):
        """Test that MAX_SEARCH_RESULTS limit is preserved."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        # Create more tracks than MAX_SEARCH_RESULTS
        tracks = []
        for i in range(60):
            tracks.append({
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
                "_search": normalize(f"Song {i} Artist Album"),
            })
        server.TRACKS = tracks

        handler, data = self._make_handler("/search?q=song")
        self.assertEqual(len(data["tracks"]), server.MAX_SEARCH_RESULTS)
        self.assertEqual(len(data["tracks"]), 50)

    def test_search_no_internal_fields_in_response(self):
        """Test that _search and path are never exposed in search response."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Track",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/track.flac"),
                "_search": normalize("Track Artist Album"),
            },
        ]
        server.TRACKS = tracks

        handler, data = self._make_handler("/search?q=track")
        self.assertEqual(len(data["tracks"]), 1)
        response_track = data["tracks"][0]
        self.assertNotIn("path", response_track)
        self.assertNotIn("_search", response_track)

    def test_search_response_allowlist_contains_approved_fields(self):
        """Test that all approved metadata fields are present in search response."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Test Track",
                "artist": "Test Artist",
                "album": "Test Album",
                "duration": 180,
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "track": 5,
                "path": Path("/music/track.flac"),
                "_search": normalize("Test Track Test Artist Test Album"),
            },
        ]
        server.TRACKS = tracks

        handler, data = self._make_handler("/search?q=test")
        self.assertEqual(len(data["tracks"]), 1)
        response_track = data["tracks"][0]

        allowed_fields = {
            "id", "title", "artist", "album", "duration",
            "format", "codec", "container", "sampleRate", "bitDepth", "bitrate", "track"
        }
        for field in allowed_fields:
            self.assertIn(field, response_track, f"Missing allowed field: {field}")

        # Verify values are correct
        self.assertEqual(response_track["id"], "t1")
        self.assertEqual(response_track["title"], "Test Track")
        self.assertEqual(response_track["artist"], "Test Artist")
        self.assertEqual(response_track["album"], "Test Album")
        self.assertEqual(response_track["duration"], 180)
        self.assertEqual(response_track["format"], "flac")
        self.assertEqual(response_track["codec"], "flac")
        self.assertEqual(response_track["container"], "flac")
        self.assertEqual(response_track["sampleRate"], 44100)
        self.assertEqual(response_track["bitDepth"], 16)
        self.assertEqual(response_track["bitrate"], 1000)
        self.assertEqual(response_track["track"], 5)

    def test_search_response_excludes_internal_and_unknown_fields(self):
        """Test that path, _search, and arbitrary new fields are excluded."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Test Track",
                "artist": "Test Artist",
                "album": "Test Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/track.flac"),
                "_search": normalize("Test Track Test Artist Test Album"),
                "unknown_field": "should_not_appear",
                "another_new_field": 123,
            },
        ]
        server.TRACKS = tracks

        handler, data = self._make_handler("/search?q=test")
        self.assertEqual(len(data["tracks"]), 1)
        response_track = data["tracks"][0]

        self.assertNotIn("path", response_track)
        self.assertNotIn("_search", response_track)
        self.assertNotIn("unknown_field", response_track)
        self.assertNotIn("another_new_field", response_track)

    def test_search_response_includes_audio_quality(self):
        """Test that audioQuality computed field is always present."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        flac_track = {
            "id": "flac1",
            "title": "FLAC Track",
            "artist": "Artist",
            "album": "Album",
            "format": "flac",
            "codec": "flac",
            "container": "flac",
            "sampleRate": 44100,
            "bitDepth": 24,
            "bitrate": 2000,
            "path": Path("/music/flac.flac"),
            "_search": normalize("FLAC Track Artist Album"),
        }
        mp3_track = {
            "id": "mp31",
            "title": "MP3 Track",
            "artist": "Artist",
            "album": "Album",
            "format": "mp3",
            "codec": "mp3",
            "container": "mp3",
            "sampleRate": 44100,
            "bitDepth": 16,
            "bitrate": 320,
            "path": Path("/music/mp3.mp3"),
            "_search": normalize("MP3 Track Artist Album"),
        }
        server.TRACKS = [flac_track, mp3_track]

        handler, data = self._make_handler("/search?q=track")
        self.assertEqual(len(data["tracks"]), 2)

        for track in data["tracks"]:
            self.assertIn("audioQuality", track)
            if track["id"] == "flac1":
                self.assertEqual(track["audioQuality"], "LOSSLESS")
            elif track["id"] == "mp31":
                self.assertEqual(track["audioQuality"], "HIGH")

    def test_search_response_artwork_url_conditional_on_https(self):
        """Test that artworkURL is only included when base_url is HTTPS."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        tracks = [
            {
                "id": "t1",
                "title": "Test Track",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path("/music/track.flac"),
                "_search": normalize("Test Track Artist Album"),
            },
        ]
        server.TRACKS = tracks

        # Test with HTTPS base_url
        original_base_url = server.SETTINGS["base_url"]
        server.SETTINGS["base_url"] = "https://example.ts.net"
        try:
            handler, data = self._make_handler("/search?q=test")
            self.assertEqual(len(data["tracks"]), 1)
            self.assertIn("artworkURL", data["tracks"][0])
            self.assertEqual(data["tracks"][0]["artworkURL"], "https://example.ts.net/artwork/t1")
        finally:
            server.SETTINGS["base_url"] = original_base_url

        # Test with HTTP base_url
        server.SETTINGS["base_url"] = "http://127.0.0.1:8765"
        try:
            handler, data = self._make_handler("/search?q=test")
            self.assertEqual(len(data["tracks"]), 1)
            self.assertNotIn("artworkURL", data["tracks"][0])
        finally:
            server.SETTINGS["base_url"] = original_base_url

    def test_search_preserves_ordering_and_limit(self):
        """Test that response ordering matches track list and MAX_SEARCH_RESULTS is respected."""
        if not TAG_AVAILABLE:
            self.skipTest("Tag not available")

        # Create more tracks than MAX_SEARCH_RESULTS (50)
        tracks = []
        for i in range(55):
            tracks.append({
                "id": f"track{i:02d}",
                "title": f"Song {i:02d}",
                "artist": "Artist",
                "album": "Album",
                "format": "flac",
                "codec": "flac",
                "container": "flac",
                "sampleRate": 44100,
                "bitDepth": 16,
                "bitrate": 1000,
                "path": Path(f"/music/song{i:02d}.flac"),
                "_search": normalize(f"Song {i:02d} Artist Album"),
            })
        server.TRACKS = tracks

        handler, data = self._make_handler("/search?q=song")
        self.assertEqual(len(data["tracks"]), server.MAX_SEARCH_RESULTS)
        self.assertEqual(len(data["tracks"]), 50)

        # Verify ordering preserved (first 50 tracks)
        for i, track in enumerate(data["tracks"]):
            self.assertEqual(track["id"], f"track{i:02d}")


class TestNormalizeFunction(unittest.TestCase):
    """Test the normalize helper function directly."""

    def test_normalize_basic(self):
        """Test basic normalization."""
        self.assertEqual(normalize("Hello World"), "hello world")
        self.assertEqual(normalize("HELLO WORLD"), "hello world")
        self.assertEqual(normalize("  hello   world  "), "hello world")

    def test_normalize_accents(self):
        """Test accent removal."""
        self.assertEqual(normalize("café"), "cafe")
        self.assertEqual(normalize("naïve"), "naive")
        self.assertEqual(normalize("résumé"), "resume")
        self.assertEqual(normalize("piñata"), "pinata")

    def test_normalize_punctuation(self):
        """Test punctuation converted to spaces."""
        self.assertEqual(normalize("song-title"), "song title")
        self.assertEqual(normalize("artist,title"), "artist title")
        self.assertEqual(normalize("album (remix)"), "album remix")
        self.assertEqual(normalize("hello!@#$world"), "hello world")

    def test_normalize_empty(self):
        """Test empty/None handling."""
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")
        self.assertEqual(normalize("   "), "")
        self.assertEqual(normalize("!!!"), "")

    def test_normalize_casefold(self):
        """Test casefold for unicode."""
        self.assertEqual(normalize("Straße"), "strasse")  # German sharp S
        self.assertEqual(normalize("MASS"), "mass")


if __name__ == '__main__':
    unittest.main()