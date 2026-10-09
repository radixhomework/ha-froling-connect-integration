# Fröling Connect

A read-only Home Assistant integration for heating installations connected to
the [Fröling Connect](https://www.froeling.com) cloud service — the same
backend the official Fröling Connect mobile app uses.

## What it does

- **Sensors** for every numeric reading of your installation: boiler, flue gas
  and circuit temperatures, buffer and DHW tank temperatures, charge
  percentages, operation hours, outside temperature.
- **Diagnostic sensors** for multi-state values such as the boiler state
  (including fault states) and operating modes.
- **Binary sensors** for on/off signals such as pump controls.
- **Notifications sensor** surfacing the installation's alarms and notices
  from the Fröling Connect account (unread count + recent list), refreshed on
  a slower sub-cadence than the values.
- One **device per installation component** (boiler, heating circuits, DHW
  tank, buffer tank, pellet storage), grouped under a device representing the
  installation itself.

## What it deliberately does not do

**This integration is read-only.** It cannot and will not change any boiler
setting. There is no write path in the code — not for setpoints, not for
modes, not for anything. Boiler settings belong to you and your installer; a
cloud-connected generic write surface is a risk this integration refuses to
carry.

## Installation

### HACS (custom repository)

1. Make sure [HACS](https://hacs.xyz) is installed.
2. Add this repository to HACS as a custom repository of type
   **Integration** (`hacs.json` lives at the repository root, so HACS offers
   it right away).
3. Install **Fröling Connect** from HACS and restart Home Assistant.

### Manual

Copy `custom_components/froling_connect/` into the `custom_components/`
directory of your Home Assistant configuration and restart. (Manual copying
is not a supported distribution path — releases go through HACS.)

## Configuration

1. *Settings → Devices & Services → Add Integration → Fröling Connect.*
2. Enter the **email and password of your Fröling Connect app account**.
3. If the account manages several installations, pick the one to monitor.

### Options

The polling interval is configurable in the integration's options
(default **60 seconds**, values below **30 seconds** are raised to 30). The
Fröling Connect API is undocumented and its rate limits are unknown, so the
integration paces its requests, backs off on rate-limit responses (up to a
15-minute interval) and restores the configured cadence automatically.

If your stored credentials stop working, Home Assistant will ask you to
re-authenticate — no need to remove and re-add the integration.

## Supported hardware

Developed and tested against a **Fröling Pellet PE1** with DHW tank, heating
circuit, buffer tank and pellet storage. Other installations reachable
through the Fröling Connect app are expected to work (entities are derived
from the installation's own parameter data), but they are untested.

## Development

```bash
python -m venv venv
venv/Scripts/pip install -r requirements_test.txt   # on Windows
venv/bin/pip install -r requirements_test.txt       # on Linux/macOS
venv/Scripts/python -m pytest                       # or venv/bin/python
```

The test suite runs fully offline against recorded API fixtures. Development
follows the OpenSpec workflow under `openspec/`; see `AGENTS.md`,
`PRODUCT.md`, and `ARCHITECTURE.md` for the project rules and architecture.
