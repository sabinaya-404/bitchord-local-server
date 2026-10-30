import hashlib
import logging
import unicodedata
from pathlib import Path

from tinytag import TinyTag

TRACK_ID_LENGTH = 16


def is_path_under_music_dirs(path, music_dirs):
    """Check if a resolved path is under any of the resolved music directories.
    Used by both scanner and server for consistent path-boundary enforcement.
    """
    if path is None:
        return False
    try:
        resolved_path = path.resolve()
    except (OSError, ValueError):
        return False
    for music_dir in music_dirs:
        try:
            resolved_music_dir = music_dir.resolve()
            if resolved_music_dir in resolved_path.parents or resolved_music_dir == resolved_path:
                return True
        except (OSError, ValueError):
            continue
    return False


def normalize(text):
    """Normalize text for search: casefold, remove accents, punctuation -> spaces."""
    if not text:
        return ""
    # NFKD decomposes accented chars; filter out combining marks
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # casefold
    text = text.casefold()
    # punctuation -> spaces
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    # collapse whitespace
    return " ".join(text.split())


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

                resolved_path = path.resolve()
                if not is_path_under_music_dirs(resolved_path, music_dirs):
                    continue

                track_id = hashlib.sha256(
                    str(resolved_path).casefold().encode("utf-8")
                ).hexdigest()[:TRACK_ID_LENGTH]

                search_string = normalize(f"{title} {artist} {album}")

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
                        "track": tag.track,
                        "path": path.resolve(),
                        "_search": search_string,
                    }
                )

            except (OSError, ValueError, TypeError, KeyError) as e:
                logging.warning(f"Skipping unreadable music file {path}: {e}")
                continue

    return tracks


def get_artwork_for_track(track):
    """Extract embedded artwork from an audio file on demand.
    Returns (image_data: bytes, mime_type: str) or (None, None) if no artwork found.
    """
    path = track.get("path")
    if not path or not path.exists():
        return None, None

    try:
        tag = TinyTag.get(path, image=True)
        if tag is None or tag.images is None:
            return None, None

        image = tag.images.front_cover or tag.images.any
        if image is None or not image.data:
            return None, None

        mime_type = image.mime_type
        if not mime_type:
            mime_type = "image/jpeg"

        return image.data, mime_type

    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        logging.warning(f"Failed to extract artwork for {path}: {e}")
        return None, None
