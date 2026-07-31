# ADR 0003: Direct live preview plus isolated Playwright diagnostics

- Status: Accepted for Phase 4
- Date: 2026-07-31

## Decision

Use option C for the first browser increment: a direct preview URL/iframe for live application interaction, paired with a separate Playwright runner for browser-engine/device-profile sessions, screenshots, and diagnostics.

## Evaluation

| Option | Security | Fidelity | Complexity | Latency/cost |
|---|---|---|---|---|
| Playwright screenshots | Strong isolation | Real engines, not continuous interaction | Low | Low |
| Streamed VNC/WebRTC browser | Strong when isolated | High interactive fidelity | High | Highest |
| Direct preview + Playwright diagnostics | Requires isolated preview domain and framing policy | Live app plus real diagnostic engines | Medium | Moderate |

## Consequences

- The UI must distinguish the live direct preview from Playwright sessions.
- Mobile/tablet choices are labelled **Emulated profile** and never represented as physical devices.
- Resizing an iframe is not claimed to be a browser/device session.
- The browser-runner boundary allows a streamed implementation to replace or supplement this approach later.
