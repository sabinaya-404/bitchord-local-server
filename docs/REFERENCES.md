# References

Sources consulted for the project. Record the purpose, date, and verification status of each source.

## BitChord Add-on Developer Guide

- URL: https://bitchord.kushagrasingh.in/docs
- Consulted: 2026-10-15
- Purpose: Add-on manifest, search and stream endpoints, track metadata, quality negotiation, and playback requirements.
- Status: Initial protocol reference. Must be tested against the installed BitChord client before implementation is considered compatible.

## Tailscale Serve Documentation

- URL: https://tailscale.com/docs/features/tailscale-serve
- Consulted: 2026-10-15
- Purpose: Private HTTPS access to the local Python server from devices in the same tailnet.
- Status: Official documentation reviewed. Integration with BitChord remains untested.

## Tailscale CLI Reference

- URL: https://tailscale.com/docs/reference/tailscale-cli/serve
- Consulted: 2026-10-15
- Purpose: Configure, inspect, and manage Tailscale Serve.
- Status: Official documentation reviewed. Commands will be verified on the target Windows machine before deployment.

## Python HTTP Server Documentation

- URL: https://docs.python.org/3/library/http.server.html
- Consulted: 2026-10-15
- Purpose: Understand standard-library HTTP server behavior and security limitations.
- Status: Reference reviewed. The final server design must account for filesystem access, request validation, and safe response handling.

## Reference Maintenance

- Record sources when they are actually consulted.
- Prefer official documentation and specific relevant pages.
- Distinguish documented behavior from locally tested behavior.
- Never claim compatibility or security has been verified until it has been tested.

## Reference Add-on Implementation

- Repository: https://github.com/rairulyle/bitchord-selfhosted-addon
- Consulted: 2026-10-15
- Purpose: Inspect manifest handling, search and stream routes, media URL resolution, HTTP Range forwarding, and response headers.
- Status: Used as a protocol and implementation reference only. Its backend architecture is not part of this project's design. Compatibility with BitChord v1.8 remains unverified.