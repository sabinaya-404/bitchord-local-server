import hashlib
import logging
from pathlib import Path

from tinytag import TinyTag

TRACK_ID_LENGTH = 16


AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
    ".aiff",
    ".aif",
}


def get_tag(tags, name, fallback):
    values = tags.get(name, []) if tags else []
    return str(values[0].strip() if values else fallback)


def scan_music(music_dirs):
    tracks = []

    for music_dir in music_dirs:
        if not music_dir.is_dir():
            continue

        for path in music_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue

            try:
                tag = TinyTag.get(path, tags=True, duration=True, image=False)
                if tag is None:
                    continue

                title = tag.title or path.stem
                artist = tag.artist or "Unknown Artist"
                album = tag.album or "Unknown Album"
                duration = round(tag.duration) if tag.duration is not None else 0
                format_ = path.suffix[1:].lower()
                codec = format_
                container = format_
                sample_rate = tag.samplerate
                bit_depth = tag.bitdepth
                bitrate = int(tag.bitrate * 1000) if tag.bitrate is not None else None

                track_id = hashlib.sha256(
                    str(path.resolve()).casefold().encode("utf-8")
                ).hexdigest()[:TRACK_ID_LENGTH]

                tracks.append(
                    {
                        "id": track_id,
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "duration": duration,
                        "format": format_,
                        "codec": codec,
                        "container": container,
                        "sampleRate": sample_rate,
                        "bitDepth": bit_depth,
                        "bitrate": bitrate,
                        "path": path.resolve(),
                    }
                )

            except (OSError, ValueError, TypeError, KeyError) as e:
                logging.warning(f"Skipping unreadable music file {path}: {e}")
                continue

    return tracks