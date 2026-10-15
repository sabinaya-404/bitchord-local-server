import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_settings():
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        config = {}

    music_dirs = config.get("music_dirs", ["~/Music"])
    host = config.get("host", "127.0.0.1")
    port = config.get("port", 8765)
    base_url = config.get("base_url", f"http://127.0.0.1:{port}")

    if not isinstance(music_dirs, list) or not all(
        isinstance(path, str) and path.strip()
        for path in music_dirs
    ):
        raise ValueError("'music_dirs' must be a list of non-empty paths")

    if not isinstance(host, str) or not host.strip():
        raise ValueError("'host' must be a non-empty string")

    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("'port' must be between 1 and 65535")

    if not isinstance(base_url, str) or not base_url.startswith("http"):
        raise ValueError("'base_url' must be an HTTP URL")

    return {
        "music_dirs": [Path(path).expanduser() for path in music_dirs],
        "host": host,
        "port": port,
        "base_url": base_url.rstrip("/"),
    }


def load_config():
    return load_settings()["music_dirs"]