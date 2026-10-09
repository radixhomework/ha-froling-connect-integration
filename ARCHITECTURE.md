# Architecture

## Stack

- Python, Home Assistant custom integration, asyncio + aiohttp.
- No external pip dependencies at runtime: the cloud client lives in-repo.
- Tests: pytest with pytest-homeassistant-custom-component, run fully offline
  against recorded API fixtures.

## Layout

```
custom_components/froling_connect/
  __init__.py                  integration setup, config entry lifecycle
  config_flow.py               UI setup, facility selection, reauth
  options_flow.py              polling interval (30 s floor)
  client.py                    Fröling Connect cloud client (login/JWT, fetches)
  coordinator.py               single shared update coordinator per config entry
  entity mapping modules       parameter -> entity (id-keyed, translation catalogs)
  sensor.py / binary_sensor.py platforms
  translations/
tests/
  fixtures/                    recorded Fröling Connect API responses
hacs.json                      HACS repository metadata
openspec/                      OpenSpec: proposals, delta specs, design, tasks
```

## External system: Fröling Connect cloud API

- Unofficial and undocumented; 8 known endpoints on `connect-api.froeling.com`.
- Login returns a JWT in the `Authorization` response header (not the body);
  `userId` is inside the JWT payload; on HTTP 401 the client re-logs in once
  and retries, then surfaces an authentication error if that fails too.
- Two response shapes:
  - `overview` — one request covering the whole facility with current values,
    but no parameter ids or permission flags;
  - `component` — per component, with the full parameter schema: stable `id`,
    machine `name`, `editable` flag, `parameterType`, `minVal`/`maxVal`, and
    enum maps (`stringListKeyValues`).
- Every value arrives as a JSON string ("78", "-16000"), including numeric
  fields; parsing coerces by declared type.
- Display labels are localized and inconsistent; entity identity uses only
  `id`/`name`, never labels.

## Core design rules

1. **Read-only client.** No set-parameter operation exists, not even unused.
   Future writes are limited to an allowlist (vacation mode, operating mode)
   as named, validated operations behind an explicit opt-in.
2. **One shared coordinator per config entry.** All entities read from a
   single fetch. Parameter schemas are discovered at setup and cached; values
   are polled per cycle via `overview`, with a per-component polling fallback
   if overview coverage proves incomplete.
3. **Polling policy.** Default 60 s, user-configurable with a 30 s floor;
   HTTP 429 doubles the interval up to a 15-minute cap (honoring
   `Retry-After`) and restores it after success; requests run sequentially
   with short pauses; transient failures mark entities unavailable while the
   coordinator retries with backoff.
4. **Device model.** One device per installation component (boiler, DHW tank,
   heating circuit, buffer tank, pellet storage); facility-level readings
   (outside temperature, notifications) attach to a facility device.
   `unique_id` derives from facility/component/parameter ids.

The full decision log with alternatives lives in the OpenSpec change artifacts
(`openspec/changes/*/design.md`) and in the main specs after archive.

## Quality and CI

- Quality gates: CodeQL, SonarQube, and PR comment review; the review loop is
  capped at 3 autonomous iterations before escalating to the user
  (see AGENTS.md).
- GitHub Actions wiring for CodeQL and SonarQube is planned but not yet in
  place; pytest is the currently enforced gate.
