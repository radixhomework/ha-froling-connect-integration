## 1. Project Scaffolding

- [x] 1.1 Create `custom_components/froling_connect/` skeleton: `manifest.json` (domain `froling_connect`, no requirements, `iot_class: cloud_polling`), `const.py`, empty `__init__.py`; verify HA loads the directory structure with `hass --config` smoke check or a unit import test
- [x] 1.2 Add `hacs.json`, `strings.json`, and `translations/en.json` placeholders; verify JSON validity
- [x] 1.3 Set up pytest with `pytest-homeassistant-custom-component`, place the community-captured API fixtures into `tests/fixtures/` (login, facility, component list, component, overview, notifications); verify `pytest` runs green on an empty test

## 2. Cloud Client (spec: froling-connect-client)

- [x] 2.1 Implement typed data models for facility, component, and parameter (raw string values, `parameterType`, `editable`, `minVal`/`maxVal`, `stringListKeyValues`), with tolerant parsing (unknown shapes logged at debug, never crash); verify against fixture files with unit tests
- [x] 2.2 Implement login (JWT from `Authorization` response header, `userId` extracted from the JWT payload, `Accept-Language` header) and raise a distinct auth error on failure; verify with `login.json` / `login_bad_creds.json` fixtures
- [x] 2.3 Implement 401 → re-login once → retry, and auth error on a second 401; verify with a mock session replaying the two-failure scenario
- [x] 2.4 Implement data fetches: facility list, component list, component, overview, notifications (count/list) — sequential, returning typed models; verify each against its fixture
- [x] 2.5 Implement value coercion by declared type (numeric string → float, enum string kept raw with its map); verify unit tests for both branches
- [x] 2.6 Confirm the client exposes no write operation (no set-parameter method exists); verify by a code-structure test asserting the public client surface

## 3. Config and Options Flows (spec: froling-connect-monitoring)

- [x] 3.1 Implement config flow (email + password → login → facility list → facility pick when multiple → create entry); verify with `pytest-homeassistant-custom-component` flow tests for success, bad credentials, and multi-facility paths
- [x] 3.2 Implement reauthentication: stored-credentials failure on re-login surfaces `ConfigEntryAuthFailed` and offers reauth; verify with a flow test
- [x] 3.3 Implement options flow for the polling interval with a 30 s floor; verify 10 s input clamps to 30 s and 120 s is kept

## 4. Coordinator (spec: froling-connect-data-refresh)

- [x] 4.1 Implement a single coordinator per config entry: setup-time schema discovery (component list + component fetches, cached) and per-cycle value fetch via overview, matching values to cached parameter schemas by component + parameter name; verify with fixture-based tests that one cycle issues exactly the expected request sequence
- [x] 4.2 Implement the per-component polling fallback for the case where overview coverage is incomplete (design D3), switchable by an internal flag; verify both branches with fixtures
- [x] 4.3 Implement sequential pacing (short pause between requests in a cycle, no parallel bursts); verify by asserting request timestamps/order in a test
- [x] 4.4 Implement 429 handling: distinct rate-limit error → interval doubling up to a 15-minute cap, `Retry-After` honored, restored after success, single warning log; verify each sub-behavior with a mock
- [x] 4.5 Implement transient-failure behavior (update-failed → entities unavailable, coordinator keeps retrying with backoff); verify availability transitions in a test

## 5. Entity Mapping and Platforms (spec: froling-connect-monitoring)

- [x] 5.1 Implement the mapping layer: parameter shape → entity kind (numeric → sensor with unit/device class, on/off → binary sensor, enum → diagnostic sensor with translated state), `unique_id` = facility/component/parameter ids, identities never derived from localized labels; verify with mapping unit tests on PE1-like fixtures
- [x] 5.2 Implement the `sensor` platform (including boiler state via its enumeration, temperatures, percent charges, operating hours) and the `binary_sensor` platform (pumps and other on/off states); verify entities created from fixtures with snapshot tests
- [x] 5.3 Implement device grouping: one device per component, facility device for facility-level readings (outside temperature, notifications); verify device registry contents in a test
- [x] 5.4 Add translation catalogs for entity names and enum states (raw values never shown untranslated as identifiers); verify `strings.json`/`translations/en.json` cover the keys used

## 6. Alarm Surface (spec: froling-connect-monitoring)

- [x] 6.1 Verify the boiler state sensor reflects fault entries of its enumeration (fixture with a fault value); add a test if not already covered by 5.2
- [x] 6.2 Implement notification surfacing on a slower sub-cadence (every ~5th cycle) on the same coordinator; verify a test showing notifications update within a few cycles and don't add per-cycle requests

## 7. Spikes, Live Validation, and Wrap-up

- [x] 7.1 Coverage spike against the real PE1 facility: log which parameters the overview returns vs. cached component schemas; record the decision (overview branch vs. per-component fallback) in design.md and remove the losing branch if it is dead code
- [ ] 7.2 Freshness spike: timestamp when a changing value (e.g. boiler temperature) updates upstream; note the observed boiler→cloud sync latency in design.md and reconsider the 60 s default if it justifies slower
- [ ] 7.3 Capture PE1-specific API responses as additional fixtures (sanitized) and pin mapping tests to them; verify the full entity surface for the real facility
- [ ] 7.4 Run a 24 h soak on the real installation: no 429s at default cadence, entities stable, re-auth survives a token expiry; record results
- [x] 7.5 Write README (setup, HACS install, read-only statement), run `openspec validate --strict`, and confirm all spec scenarios have a corresponding passing test
