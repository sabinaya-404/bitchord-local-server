# BitChord Local Music Add-on

A self-hosted Python server that exposes a personal music library through a custom BitChord add-on.

Each user runs their own server, configures their own music folders, and connects their own BitChord client.

## Current status

- Local library scanning and search implemented.
- Manifest and stream metadata endpoints implemented.
- Original audio files served without transcoding.
- HTTP byte-range requests implemented.
- Lossless stream metadata implemented for supported FLAC tracks.
- Configurable host, port, music directories, and advertised base URL implemented.
- Manual testing of manifest, search, stream metadata, and FLAC playback from an Android phone over Tailscale completed.
- BitChord Android integration and playback verified over Tailscale.

## Requirements

- Python 3.15 was used during development.
- Git
- A music library containing supported audio files
- BitChord for integration testing
- Tailscale for private remote access, if desired

## Setup

### 1. Get the project ready

From the project root, create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Configure your music library

Copy the example configuration:

```powershell
Copy-Item config.example.json config.json
```

Edit `config.json` and set `music_dirs` to folders that contain your music. For example:

```json
{
  "music_dirs": [
    "~/Music",
    "D:/Music"
  ],
  "host": "127.0.0.1",
  "port": 8765,
  "base_url": "http://127.0.0.1:8765"
}
```

Replace the example folders with your own. Keep `host` set to `127.0.0.1` for local access or when using Tailscale Serve.

### 3. Start the server

Run this from the project root:

```powershell
python -m src.server
```

Keep the terminal open while using the add-on.

### 4. Verify the server

Open this URL on the host computer:

`http://127.0.0.1:8765/manifest.json`

You should receive the add-on manifest as JSON.

### 5. Connect BitChord

For local access, the default `base_url` is suitable when the BitChord client can reach the host using that address.

For private Android access, configure Tailscale on both devices and use Tailscale Serve to provide HTTPS access to the local server. Change `base_url` to your own Tailscale Serve HTTPS URL, such as `https://your-machine.your-tailnet.ts.net`. Do not copy another user's hostname.

The server has no authentication. Keep access private and do not expose it directly to the public internet or use Tailscale Funnel.

## Configuration

`config.json` is local and ignored by Git. Configure your own music directories, host, port, and base URL.

- `music_dirs`: folders to scan for music.
- `host`: network interface on which the server listens.
- `port`: server port.
- `base_url`: HTTP base URL advertised in stream metadata. It must be reachable by the BitChord client.

For private remote access, connect both devices to your own Tailscale network. You can use Tailscale Serve to provide HTTPS access to the local Python server.

Keep the Python server bound to `127.0.0.1` when using a local Tailscale Serve proxy. Set `base_url` to your own Tailscale Serve HTTPS URL, without copying another user's hostname.

The server has no user authentication. Keep access restricted to your trusted private network, and do not expose it directly to the public internet.

## Endpoints

- `GET /manifest.json`: add-on manifest.
- `GET /search?q=...`: search indexed tracks.
- `GET /stream/{id}`: stream metadata for a supported quality.
- `GET /audio/{id}`: original audio bytes, including byte-range responses.

## Development verification

Manual tests completed:

- Manifest returned HTTP 200 and valid JSON from the laptop.
- Search returned track data from the Android phone.
- Stream metadata returned FLAC format, LOSSLESS quality, codec, sample rate, bit depth, bitrate, and an absolute audio URL.
- An audio URL returned playable FLAC audio in the phone's browser over Tailscale.

Automated tests have not been added yet. BitChord Android search and playback have been manually verified. Client seeking behavior and broader format compatibility remain to be verified.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation log](docs/IMPLEMENTATION.md)
- [References](docs/REFERENCES.md)

## Security notes

The server has no user authentication. Keep it on a trusted private network and restrict access with appropriate firewall rules. Do not commit `config.json`, personal IP addresses, music paths, or credentials.
