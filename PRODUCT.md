# Product

ha-froling-connect-integration is a Home Assistant custom integration that
monitors a Fröling heating installation through the same cloud API the official
Fröling Connect mobile app uses.

## Who it is for

- First: the owner of a Fröling Pellet PE1 pellet boiler with a DHW tank, a
  heating circuit, a buffer tank, and pellet storage.
- Nothing in the design prevents later use with other Fröling installations
  supported by Fröling Connect, but generalization is not the priority.

## What it does

- Read-only monitoring in Home Assistant:
  - sensors (temperatures, charge percentages, operating hours, boiler state),
  - binary sensors (pumps and other on/off signals),
  - alarm visibility (boiler fault states and cloud notifications).
- Setup entirely through the Home Assistant UI: email + password, facility
  selection when the account has several installations, reauthentication when
  credentials stop working.

## What it deliberately does not do

- **No write operations.** Boiler settings belong to the owner and their
  installer; a generic "set any parameter" surface is the biggest risk this
  integration could carry. The integration performs no parameter writes and
  the client exposes no write path at all.
- If write support is ever added, it will be a closed allowlist — vacation
  mode and operating mode only — implemented as named, validated operations
  behind an explicit opt-in.
- No local protocols (Modbus/RS232) and no push channels: the Fröling Connect
  cloud API is the single supported path.

## Distribution

Distributed via HACS as a custom repository; manual file-copy installation is
not a supported path.

## Success criteria

- Reliable monitoring that survives API quirks (localized labels,
  string-typed values, session expiry) without user intervention.
- Cloud traffic that stays within normal app-like usage at the default
  polling cadence.
- Entities keep their identity across label and language changes.
