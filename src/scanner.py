import hashlib
from pathlib import Path

from mutagen import File as AudioFile


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

                track_id = hashlib.sha256(
                    str(path.resolve()).casefold().encode("utf-8")
                ).hexdigest()[:16]

                tracks.append({
                    "id": track_id,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "duration": round(duration),
                    "format": path.suffix[1:].lower(),
                    "path": path.resolve(),
                })

            except (OSError, ValueError, TypeError, KeyError):
                continue

    return tracks
