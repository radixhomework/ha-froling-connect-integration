## Purpose

Defines how installation data is refreshed inside Home Assistant: the polling
cadence, its configuration, and polite behavior toward a cloud API whose rate
limits are undocumented.

## ADDED Requirements

### Requirement: Single shared refresh
The integration SHALL fetch all data for the installation through one shared
refresh cycle that all entities read from, rather than issuing per-entity
requests.

#### Scenario: One fetch serves all entities
- **WHEN** the installation exposes many entities and a refresh cycle runs
- **THEN** all entities are updated from that single cycle's data
- **AND** no additional requests are made per entity

### Requirement: Default and configurable polling interval
The integration SHALL refresh by default every 60 seconds and SHALL let the
user change the interval through the integration's options, with a minimum
enforced interval of 30 seconds.

#### Scenario: Default interval
- **WHEN** the integration is set up without changing options
- **THEN** data refreshes every 60 seconds

#### Scenario: User-configured interval
- **WHEN** the user sets the interval to 120 seconds in the options
- **THEN** data refreshes every 120 seconds

#### Scenario: Interval below the floor
- **WHEN** the user sets the interval to 10 seconds in the options
- **THEN** the effective interval is clamped to the 30-second minimum

### Requirement: Rate-limit backoff
The integration SHALL treat an HTTP 429 response as a rate-limit signal:
it SHALL lengthen the refresh interval (doubling it up to a 15-minute cap, or
honoring a Retry-After header when the service provides one) until a refresh
succeeds, then restore the configured interval. Repeated rate-limit responses
SHALL produce a single warning in the log, not one per occurrence.

#### Scenario: Rate limit encountered
- **WHEN** a refresh cycle receives an HTTP 429 response
- **THEN** the next refresh waits at least twice the configured interval

#### Scenario: Retry-After honored
- **WHEN** an HTTP 429 response includes a Retry-After of 300 seconds
- **THEN** the next refresh waits at least 300 seconds

#### Scenario: Recovery restores cadence
- **WHEN** a refresh succeeds after a backoff period
- **THEN** the refresh interval returns to the user's configured value

### Requirement: Transient failure behavior
The integration SHALL mark affected entities unavailable while refreshes fail
and SHALL keep retrying with increasing backoff until a refresh succeeds.

#### Scenario: Network outage
- **WHEN** refreshes fail due to a network error
- **THEN** affected entities become unavailable
- **AND** refresh attempts continue with increasing backoff
- **AND** entities become available again with fresh data after recovery

### Requirement: Sequential request pacing
The integration MUST issue requests to the cloud service sequentially, with a
short pause between consecutive requests within one refresh cycle, and MUST
NOT issue parallel bursts of requests.

#### Scenario: Multi-request refresh cycle
- **WHEN** a refresh cycle needs more than one request
- **THEN** the requests are issued one after another with a pause between them
