import json
import unittest
from pathlib import Path


class ManifestTests(unittest.TestCase):
    def test_manifest_has_required_fields(self):
        manifest_path = Path(__file__).parent / "src" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], "dev.sabinaya.local-music")
        self.assertEqual(manifest["name"], "Local Music")
        self.assertIn("search", manifest["resources"])
        self.assertIn("stream", manifest["resources"])
        self.assertEqual(manifest["allowDownloads"], 0)
        self.assertEqual(manifest["checkValidLossless"], 0)


if __name__ == "__main__":
    unittest.main()
