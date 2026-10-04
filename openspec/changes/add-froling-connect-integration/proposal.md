## Why

Fröling heating systems are reachable from Home Assistant today only through an
unmaintained, beta-quality custom integration or through local Modbus
wiring that requires opening the boiler — not an option for most owners. This
project needs reliable, read-only monitoring of a Fröling Pellet PE1 (with DHW
tank, heating circuit, buffer, and pellet storage) through the same cloud API
the official Fröling Connect app uses; the exploration phase has already pinned
down that API's endpoints, authentication flow, and response shapes from
recorded fixtures.

## What Changes

- Add a new custom integration `froling_connect` for Home Assistant:
  - UI config flow (email + password) with reauthentication support.
  - A thin in-repo async client for the 8 known Fröling Connect cloud
    endpoints — no external pip dependencies.
  - A single `DataUpdateCoordinator` per config entry polling facility data
    (default 60 s, user-configurable with a 30 s floor, 429-aware backoff).
  - A mapping layer that turns the cloud parameter model into read-only HA
    entities (sensors, binary sensors, alarm surface) keyed on stable
    parameter ids/names, never localized labels.
  - Offline tests built on recorded API response fixtures from day one.
- **Read-only by design**: the integration performs no parameter writes; the
  client exposes no generic set-parameter method. Future write support, if
  ever, is limited to an explicit allowlist (vacation mode, operating mode)
  designed as named operations behind an opt-in.
- Non-goals: parameter writes, local Modbus/RS232 protocols, push/websocket
  channels, schedule editing.

## Capabilities

### New Capabilities

- `froling-connect-client`: Thin async client for the unofficial Fröling
  Connect cloud API — login/JWT session, data fetching, parsing of the
  string-typed parameter model, and a strictly read-only surface (no generic
  parameter-write path).
- `froling-connect-data-refresh`: How the integration refreshes data in Home
  Assistant — single shared coordinator fetch, polling interval defaults and
  clamps, rate-limit (HTTP 429) backoff policy, transient-failure behavior.
- `froling-connect-monitoring`: The user-facing monitoring surface — config
  flow and reauthentication, read-only entity mapping (sensors, binary
  sensors, boiler state, notifications), device grouping, and alarm visibility.

### Modified Capabilities

(none — greenfield project, no existing specs)

## Impact

- New code: `custom_components/froling_connect/` (client, coordinator, entity
  mapping, platforms, config/options flows) plus `tests/` with fixture-based
  offline tests.
- New metadata: `manifest.json`, `hacs.json`, translation catalogs.
- External systems: polls the unofficial Fröling Connect cloud API
  (`connect-api.froeling.com`) with the user's account credentials; nothing
  else is touched and no data is sent anywhere.
- Dependencies: none beyond Home Assistant core (`aiohttp`); no new pip
  requirements shipped to users.
- Risks: the unofficial API may change without notice (mitigated by fixture
  tests and defensive error handling); cloud rate limits are undocumented
  (mitigated by the polling policy defined in `froling-connect-data-refresh`).
