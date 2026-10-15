# BitChord Local Music Add-on

A self-hosted Python music server and custom BitChord add-on for streaming a personal music collection.

## Project status

**Phase:** Initial setup  
**Current step:** Step 1 completed; documentation setup in progress  
**Implementation:** Not started

## Goals

- Read audio files directly from configured local music folders.
- Search tracks and expose their metadata through BitChord.
- Stream original audio files without transcoding.
- Support seeking when compatible with the client and audio format.
- Enable secure remote streaming over HTTPS.
- Keep the implementation simple, understandable, and beginner-friendly.

## Planned technologies

- Python
- Python standard library where practical
- BitChord add-on protocol
- Git for version control

Dependencies and hosting services have not yet been finalized.

## Documentation

- [Implementation Log](docs/IMPLEMENTATION_LOG.md)
- [Architecture](docs/ARCHITECTURE.md)
- [References](docs/REFERENCES.md)
- [Decisions](docs/DECISIONS.md)

## Security

The server must not expose arbitrary files or provide unrestricted public access. Remote hosting, authentication, and HTTPS configuration must be reviewed before deployment.

## Audio quality

The server is intended to deliver original audio files without transcoding. Actual playback quality depends on the source file, client support, and transport behavior.

## Development approach

Work in small, verifiable stages. Document commands, file changes, test results, technical decisions, and references as the project progresses. Do not mark untested functionality as complete.