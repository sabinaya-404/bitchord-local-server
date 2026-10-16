import hashlib
import logging
from pathlib import Path

from mutagen import File as AudioFile

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
    ".ape",
    ".wv",
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
                audio = AudioFile(path, easy=True)

                if audio is None or audio.info is None:
                    continue

                title = get_tag(audio, "title", path.stem)
                artist = get_tag(audio, "artist", "Unknown Artist")
                album = get_tag(audio, "album", "Unknown Album")
                duration = audio.info.length
                codec = path.suffix[1:].lower()
                sample_rate = getattr(audio.info, "sample_rate", None)
                bit_depth = getattr(audio.info, "bits_per_sample", None)
                bitrate = getattr(audio.info, "bitrate", None)

                track_id = hashlib.sha256(
                    str(path.resolve()).casefold().encode("utf-8")
                ).hexdigest()[:TRACK_ID_LENGTH]

                tracks.append(
                    {
                        "id": track_id,
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "duration": round(duration),
                        "format": path.suffix[1:].lower(),
                        "codec": codec,
                        "container": path.suffix[1:].lower(),
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