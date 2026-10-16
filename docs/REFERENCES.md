# References

Sources consulted during development. Documentation describes expected behavior; local testing records what has actually been verified.

## BitChord Add-on Developer Guide

- URL: https://bitchord.kushagrasingh.in/docs
- Consulted: 2026-10-15
- Purpose: Add-on manifest, search and stream endpoints, track metadata, quality negotiation, and playback requirements.
- Status: Used as the protocol reference. BitChord Android search and playback have been manually verified with this project. Broader compatibility remains unverified.

## Tailscale Serve Documentation

- URL: https://tailscale.com/docs/features/tailscale-serve
- Consulted: 2026-10-15
- Purpose: Private HTTPS access to the local Python server from devices in the same tailnet.
- Status: Documentation consulted. Tailscale Serve HTTPS access and BitChord playback were manually verified on Windows and Android.

## Tailscale CLI Reference

- URL: https://tailscale.com/docs/reference/tailscale-cli/serve
- Consulted: 2026-10-15
- Purpose: Configure, inspect, and manage Tailscale Serve.
- Status: Used as a reference for the remote-access setup. The working setup was tested locally.

## Python HTTP Server Documentation

- URL: https://docs.python.org/3/library/http.server.html
- Consulted: 2026-10-15
- Purpose: Understand standard-library HTTP server behavior and security limitations.
- Status: Used as an implementation reference. Security hardening and broader deployment suitability have not been fully verified.

## Reference Add-on Implementation

- Repository: https://github.com/rairulyle/bitchord-selfhosted-addon
- Consulted: 2026-10-15
- Purpose: Inspect manifest handling, search and stream routes, media URL resolution, HTTP Range handling, and response headers.
- Status: Used as a protocol and implementation reference only. Its backend architecture is not part of this project's design. Local BitChord playback works, but full compatibility with all BitChord v1.8 behaviors has not been verified.

## Reference Maintenance

- Record sources when they are actually consulted.
- Prefer official documentation and specific relevant pages.
- Distinguish documented behavior from locally tested behavior.
- Do not claim complete compatibility or security verification based on limited manual tests.
