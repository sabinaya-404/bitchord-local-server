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
- BitChord client integration has not yet been verified.

## Requirements

- Python 3.15 was used during development.
- Git
- A music library containing supported audio files
- BitChord for integration testing
- Tailscale for private remote access, if desired

## Setup

1. Create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Copy `config.example.json` to `config.json` and edit the settings.

4. Start the server from the project root:

   ```powershell
   python -m src.server
   ```

5. Open `http://127.0.0.1:8765/manifest.json` on the host to verify the manifest.

## Configuration

`config.json` is local and ignored by Git. Configure your own music directories, host, port, and base URL.

- `music_dirs`: folders to scan for music.
- `host`: network interface on which the server listens.
- `port`: server port.
- `base_url`: HTTP base URL advertised in stream metadata. It must be reachable by the BitChord client.

For remote testing over Tailscale, both devices must be connected to the same tailnet. The server can listen on `0.0.0.0`, while `base_url` uses the host's Tailscale IP and port. Use your own address; never copy another user's address from this repository.

The current direct Tailscale setup uses HTTP between the phone and Python server. Keep it restricted to your private tailnet and firewall rules. Do not expose this server directly to the public internet.

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

Automated tests have not been added yet. BitChord client integration, client seeking behavior, and broader format compatibility remain to be verified.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation log](docs/IMPLEMENTATION.md)
- [References](docs/REFERENCES.md)

## Security notes

The server has no user authentication. Keep it on a trusted private network and restrict access with appropriate firewall rules. Do not commit `config.json`, personal IP addresses, music paths, or credentials.
