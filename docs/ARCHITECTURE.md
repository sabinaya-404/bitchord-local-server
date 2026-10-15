# Architecture

## Overview

A Python application will expose a local music collection through a custom BitChord add-on.

The application will run on a host computer, read audio files from explicitly configured music directories, and make supported tracks searchable and playable through BitChord.

## Components

### Music Library
- Audio files stored in local directories.
- Supported formats will depend on BitChord playback compatibility.
- Original files will be served without transcoding.

### Python Server
- Scans configured music directories.
- Extracts track metadata.
- Searches the indexed collection.
- Exposes the endpoints required by BitChord.
- Streams original files and supports HTTP Range requests where required.

### BitChord Add-on
- Provides the manifest expected by BitChord.
- Searches the local collection.
- Resolves tracks to playable media URLs.
- Returns the metadata required by the client.

### Remote Access
- Provides secure HTTPS access from outside the home network.
- Requires appropriate authentication and access controls.
- Must not expose arbitrary filesystem paths or unrestricted directory listings.

## Data Flow

1. BitChord requests a search.
2. The server searches the local music index.
3. The add-on returns matching tracks and metadata.
4. BitChord requests a playable stream.
5. The server delivers the original audio file.

## Deployment

The initial deployment target is Windows 11.

The host must remain powered on, connected to the network, and running the server for remote playback to work.

The remote-access method has not yet been selected.

## Implementation Status

This architecture is provisional. Endpoint details, metadata schemas, authentication, and hosting will be finalized against the verified BitChord protocol before implementation.
