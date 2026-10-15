# Architecture

## Overview

A Python application exposes a user's local music collection through a custom BitChord add-on. The project is intended to be open source, with each user running and configuring their own instance.

## Components

### Music library

- Audio files remain in the user's configured folders.
- The scanner extracts track identifiers and metadata.
- Original files are served without transcoding.

### Python server

- Reads settings from local `config.json`, falling back to defaults.
- Scans configured music directories.
- Exposes the manifest, search, stream metadata, and audio endpoints.
- Returns audio bytes and supports HTTP byte-range requests.
- Uses the indexed track IDs rather than accepting arbitrary filesystem paths from requests.

### BitChord add-on

- Exposes the manifest expected by BitChord.
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

`config.json` is local and excluded from Git. It contains the music directories, listening host, port, and advertised base URL.

The listening host controls which local interfaces accept connections. The advertised base URL must be reachable from the BitChord client; it is not necessarily the same as the listening address.

## Remote access

Private remote access has been manually tested using Tailscale on Windows and Android.

The Python server listens on `0.0.0.0:8765`, and the phone accesses it through the laptop's Tailscale IP. The configured base URL must use the user's own Tailscale IP.

The tested direct connection uses HTTP. Both devices must be connected to the same tailnet, the server must be running, and firewall access must be restricted appropriately. This setup is for private testing, not public exposure.

Tailscale Serve and HTTPS proxying are not part of the currently verified setup.

## Deployment assumptions

- The host computer remains powered on and the server remains running.
- The client can reach the advertised base URL.
- Each user supplies their own music directories and remote-access configuration.

## Verification status

Manifest, search, stream metadata, and browser playback of a FLAC track were manually verified from Android over Tailscale.

BitChord client compatibility, client-side seeking, automated tests, and wider format support remain unverified.
