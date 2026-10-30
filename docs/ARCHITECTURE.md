# Architecture

## Overview

A Python application exposes a user's local music collection through a custom BitChord add-on. The project is intended to be open source, with each user running and configuring their own instance.

## Components

### Music library

- Audio files remain in the user's configured folders.
- The scanner extracts track identifiers and metadata.
- Original files are served without transcoding.

### Python server

- Reads settings from local `config.json`, falling back to defaults when the file is missing.
- Scans configured music directories at startup.
- Exposes the manifest, search, stream metadata, and audio endpoints.
- Returns audio bytes and supports HTTP byte-range requests.
- Uses indexed track IDs rather than accepting arbitrary filesystem paths from requests.

### BitChord add-on

- Provides the manifest expected by BitChord.
- Searches the indexed music library.
- Resolves tracks to absolute media URLs.
- Returns stream metadata for supported requests.

## Data flow

1. BitChord requests a track search.
2. The server searches the indexed library.
3. The server returns matching tracks and metadata.
4. BitChord requests stream metadata for a track.
5. The server returns the advertised audio URL and format metadata.
6. The client requests audio bytes from the audio endpoint.

## Configuration

`config.json` is local and excluded from Git. Each user creates it from `config.example.json` and configures their own music directories, listening host, port, and advertised base URL.

- `music_dirs`: Directories scanned for supported audio files.
- `host`: Network interface on which the Python server listens.
- `port`: Port used by the Python server.
- `base_url`: Base URL advertised in stream metadata. It must be reachable by the BitChord client.

The listening host determines which network interfaces accept connections. The advertised base URL determines the address included in stream responses. These values serve different purposes and do not have to be identical.

For local use, the default configuration uses `127.0.0.1:8765`. For private remote access through Tailscale Serve, the Python server can remain bound to `127.0.0.1`, while `base_url` uses the user's own Tailscale Serve HTTPS URL.

## Remote access

Private remote access has been manually tested using Tailscale on Windows and Android, with Tailscale Serve providing HTTPS access.

The Python server listens on `127.0.0.1:8765`. Tailscale Serve proxies HTTPS requests from the user's private Tailscale network to the local Python server.

The configured `base_url` must be the user's own Tailscale Serve HTTPS URL so that the audio URLs returned to BitChord are reachable by the client. Each user must configure their own Tailscale network and Serve address.

Both devices must be connected to the same tailnet, Tailscale Serve must be configured, and the Python server must be running.

The server has no user authentication. Keep access restricted to a trusted private network. Do not expose the Python server directly to the public internet or configure public Tailscale Funnel access.

## Filesystem access and symlink policy

The server enforces path-boundary checks to prevent directory traversal and symlink-based escape from configured music directories.

- **Track indexing**: During library scan, each discovered audio file is resolved to its absolute path. If the resolved path falls outside every configured music directory, the file is skipped and not indexed.
- **Track IDs**: Generated as deterministic SHA-256 hashes of the resolved absolute path (truncated to 16 characters). This ensures identical files produce the same ID regardless of which symlink was used to discover them.
- **Audio streaming (`/audio/{id}`)**: Before serving audio bytes, the server validates that the track's stored resolved path is under a configured music directory (after resolving both). Requests for tracks outside the boundary receive 404.
- **Artwork retrieval (`/artwork/{id}`)**: Performs the same path-boundary validation as the audio endpoint before extracting embedded artwork. Extracted artwork is cached in memory (max 200 entries, FIFO eviction). The cache is cleared on successful `/refresh`.
- **Symlinks inside music directories**: Followed during scanning. If the symlink's resolved target remains inside any configured music directory, the file is indexed and playable. If the resolved target escapes all configured music directories, the file is rejected at scan time.
- **Symlinked music directories**: A configured `music_dirs` entry that is itself a symlink is resolved and scanned normally. The user should ensure the resolved path is intended to be accessible.
- **Multiple music directories**: Each configured directory is validated independently. Symlinks pointing between configured music directories are allowed (the resolved target is inside another configured directory).

## Deployment assumptions

- The host computer remains powered on while the server is needed.
- The Python server remains running during playback.
- The client can reach the advertised base URL.
- Each user supplies their own music directories and remote-access configuration.
- The original music files remain accessible on the host computer.

## Verification status

The following have been manually verified:

- The manifest returns valid JSON.
- Search returns matching track data from Android.
- Stream metadata includes format and audio information for supported FLAC tracks.
- Audio URLs return playable FLAC audio.
- BitChord Android search and playback work through Tailscale Serve over HTTPS.

Automated tests have not been added yet. Client-side seeking behavior and broader audio-format compatibility remain to be verified.
