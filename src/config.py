import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config():
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        music_dirs = config.get("music_dirs")

        if not isinstance(music_dirs, list) or not all(
            isinstance(path, str) and path.strip()
            for path in music_dirs
        ):
            raise ValueError("'music_dirs' must be a list of non-empty paths")
    else:
        music_dirs = ["~/Music"]

    return [Path(path).expanduser() for path in music_dirs]