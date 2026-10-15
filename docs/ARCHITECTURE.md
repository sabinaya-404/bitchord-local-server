# Architecture

## Overview

A Python application will expose a user's local music collection through a custom BitChord add-on.

The project will be open source. Each user runs their own instance, configures their own music directories, and connects their own BitChord client.

## Components

### Music Library
- Audio files remain on the user's computer.
- Supported formats depend on BitChord playback compatibility.
- Original audio files are streamed without transcoding.

### Python Server
- Scans explicitly configured music directories.
- Extracts track metadata.
- Searches the indexed collection.
- Implements the endpoints required by BitChord.
- Streams original audio files and supports HTTP Range requests where needed.
- Does not expose arbitrary filesystem paths or unrestricted directory listings.

### BitChord Add-on
- Provides the manifest expected by BitChord.
- Searches the local music collection.
- Resolves tracks to playable media URLs.
- Returns the metadata required by the client.

### Remote Access
- Tailscale Serve is the planned remote-access method.
- The Python server will listen on localhost, behind Tailscale Serve.
- Remote access requires the user's PC and Android device to be connected to the same Tailscale network.
- HTTPS and tailnet access controls are handled through Tailscale.
- Compatibility with BitChord's actual client and stream URL handling must be tested.

## Data Flow

1. BitChord requests a search.
2. The Python server searches the indexed music collection.
3. The server returns matching tracks and metadata.
4. BitChord requests a playable stream.
5. The server streams the original audio file.

## Deployment

- Initial host: Windows 11.
- Language: Python.
- The host must remain powered on, connected to the internet, and running the server for remote playback.
- Each user configures their own music directory and Tailscale setup.

## Implementation Status

This architecture is provisional.

Before implementing the server, verify the BitChord add-on protocol, required metadata, stream URL format, and playback compatibility. Test remote access and audio streaming before considering the architecture complete.
