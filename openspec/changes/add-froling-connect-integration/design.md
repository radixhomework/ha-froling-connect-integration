## Context

Greenfield custom integration. The Fröling Connect cloud API is unofficial and
undocumented, but its surface is small and fully understood from
community-captured API fixtures (used as protocol documentation):

- 8 endpoints on `connect-api.froeling.com`: login, user, facility list,
  overview, component list, component, notifications (count/list/one), and
  set-parameter (known but deliberately unused — see read-only rule).
- Login: `POST /connect/v1.0/resources/login` with
  `{"osType": "web", "username": ..., "password": ...}`; the JWT comes back in
  the **`Authorization` response header** (not the body); `userId` is inside
  the JWT payload; `Accept-Language` localizes human-readable texts.
- Two response shapes: `overview` (one request, whole facility, current values
  but **no parameter ids, no `editable` flags**) and `component` (per
  component; parameters carry stable `id`, machine `name`, `editable`,
  `parameterType` (`NumValueObject`/`StringValueObject`), `minVal`/`maxVal`,
  `stringListKeyValues` enum maps). All values are JSON strings ("78",
  "-16000") regardless of type.
- Display labels are localized and inconsistent (German mixed into English
  responses); only `id`/`name` are stable.

Target hardware (and primary test bed): Fröling Pellet PE1 with DHW tank,
heating circuit, buffer tank, pellet storage. Fixture facility (boiler +
circuits + DHW + buffer) is nearly identical.

## Goals / Non-Goals

**Goals:**

- Reliable read-only monitoring that survives cloud-side quirks (string-typed
  values, localized labels, reactive re-auth).
- A client shaped for a single shared refresh (one snapshot call per cycle).
- Polite behavior toward an undocumented API: minimal requests, pacing, 429
  backoff.
- Offline-testable from day one via recorded fixtures.

**Non-Goals:**

- Any write operation (see read-only rule below); generic parameter setting
  does not exist in the client, not even unreferenced.
- Local protocols (Modbus/RS232), push channels, schedule editing.
- Community-scale generalization beyond clean structure (personal first;
  structure must not *block* later generalization).

## Decisions

### D1. Own thin client, in-repo — no pip dependency, no fork
The API is 8 endpoints (~300–500 lines with typed models). Pinning an
unmaintained third-party client package in `manifest.json` would couple
us to upstream fixes we cannot make, for less code than the dependency
management costs. In-repo client designed around one `snapshot()` call.
*Alternatives:* depend on the existing PyPI package (rejected: unmaintained,
beta, can't patch); fork/vendor it (rejected: carries its per-call API shape
that fights the coordinator pattern; we'd rewrite most of it anyway).

### D2. Read-only as an enforced rule, not a skipped feature
The client exposes no generic set-parameter operation at all. Future writes,
if ever, are an explicit allowlist (vacation mode, operating mode) as named,
validated operations behind an options-flow opt-in — never a generic path.
This is the security posture the owner chose: boiler settings belong to
professionals; a generic write surface is the riskiest thing this integration
could ship. The known set-parameter endpoint is documented here but
deliberately unimplemented.

### D3. Schema discovery vs. value polling (hybrid, spike-gated)
Component fetches carry the schema (ids, `editable`, enums, ranges); overview
carries fresh values for everything but lacks identity. Plan: fetch
`componentList` + each `component` once at setup to build the entity mapping
and cache parameter schemas; per refresh cycle, poll `overview` (1
request/cycle) and match values by component + parameter `name`. If the
overview's parameter coverage proves incomplete for the PE1 (spike below),
fall back to polling each component per cycle (~5 sequential requests) —
correctness first, request count second. Parameter schemas are re-fetched
rarely (e.g. on entity-unknown errors), not per cycle.

### D4. Polling policy — default 60 s, options-flow editable, 30 s floor
Heating data is slow-moving; the fastest signals are boiler temperature and
the state enum. 60 s default ≈ app-like traffic (one overview request/minute).
Options flow exposes the interval with a hard 30 s floor (undocumented API;
clamp rather than trust). 429 handling: client raises a distinct rate-limit
error; coordinator doubles its interval up to a 15-minute cap, honors
`Retry-After` when present, restores the configured interval on success, and
logs a warning once. Transient failures raise update-failed so entities go
unavailable while the coordinator's built-in backoff retries. Requests within
a cycle run sequentially with a short pause (~0.5 s, matching observed safe
practice) — no parallel bursts.

### D5. Mapping layer keyed on ids/names, translation catalog kept local
Entities are derived from component + parameter `id`/`name` (stable);
`unique_id` = `"{facility_id}_{component_id}_{parameter_id}"`. Localized
labels (`displayName`, `displayValue`, `stringListKeyValues`) are never used
as identifiers; enum meanings are translated by our own catalogs (raw value
stored as the state's backing data where applicable). Entity classes by
parameter shape: numeric → `sensor` (with `native_unit_of_measurement`,
device class where mappable), on/off → `binary_sensor`, enum → diagnostic
`sensor` showing translated state, `editable` numerics with min/max are
*displayed read-only* (they would become `number` only under the future
allowlisted-write design). Alarm surface: boiler state sensor (fault entries
of its enumeration) plus notifications surfaced on a slower sub-cadence
(every ~5th cycle) on the same coordinator.

### D6. Device model — one device per component, facility device for facility readings
Components (boiler, DHW, circuit, buffer, storage) map naturally to HA
devices; facility-level parameters (outside temperature, notifications) attach
to a facility device. Matches the cloud model and scales to larger
installations later. *Alternative:* single device per installation (simpler,
chosen against: loses per-component organization the app itself uses).

### D7. Storage & layout
`custom_components/froling_connect/` with `client.py` (+ typed models),
`coordinator.py`, mapping, platform modules, config/options flows,
`translations/`. `hacs.json` for HACS. Tests run offline against the recorded
fixtures (login, facility, component list, component, overview, notifications
shapes), extended with PE1-specific fixtures captured during the first real
run.

## Risks / Trade-offs

- [Unofficial API can change without notice] → fixture tests pin known
  shapes; defensive parsing (unknown parameter types ignored with debug log,
  not crashes); re-auth is reactive and cheap.
- [Undocumented rate limits; unknown ban policy] → minimal request design
  (1 request/cycle target), sequential pacing, 30 s floor, 429 backoff with
  cap; personal-scale traffic is below app-like usage.
- [Overview coverage may be incomplete per component type] → D3 fallback to
  per-component polling; decided by the coverage spike, not guessed.
- [PE1 parameter names/ids unknown until first live run] → spike with the
  real facility; pin PE1 fixtures; mapping layer is data-driven so new
  parameters appear without code changes (sensors at minimum).
- [Enum-heavy state sensor with large enumeration] → translated via catalog;
  unknown raw values surface as raw value with a debug log rather than
  dropping the update.

## Migration Plan

Not applicable — greenfield. Rollback = remove the custom component and
config entry; nothing outside `config/custom_components` is modified.

## Open Questions

- Does one `overview` request cover all monitorable PE1 parameters, or must
  components be polled per cycle? (Spike during implementation — changes only
  which D3 branch is active, not the specs.)
- Actual upstream data freshness (boiler→cloud sync latency) — may justify a
  slower-than-60 s default. (Spike; measurable, non-blocking.)
