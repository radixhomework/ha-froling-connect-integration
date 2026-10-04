## Purpose

The user-facing monitoring surface in Home Assistant: setting the integration
up, the read-only entities it creates, how they are identified and grouped, and
how alarms become visible.

## ADDED Requirements

### Requirement: Configure through the UI
The integration SHALL be set up entirely through the Home Assistant UI using
the account's email address and password. When the account manages more than
one installation, the user SHALL be able to choose which installation to
monitor.

#### Scenario: Successful setup
- **WHEN** the user submits valid credentials
- **THEN** a config entry is created and the installation is monitored

#### Scenario: Invalid credentials
- **WHEN** the user submits invalid credentials
- **THEN** an authentication error is shown and no config entry is created

#### Scenario: Multiple installations
- **WHEN** the account manages more than one installation
- **THEN** the user selects which installation to monitor during setup

### Requirement: Reauthentication
The integration SHALL trigger Home Assistant's reauthentication flow when the
stored credentials stop working, without requiring the user to remove and
re-add the integration.

#### Scenario: Credentials become invalid
- **WHEN** the cloud service rejects both the stored token and a re-login
- **THEN** Home Assistant prompts the user to re-enter their credentials

### Requirement: Read-only entity surface
The integration SHALL create read-only entities from the installation's
components and parameters: sensors for numeric readings (temperatures, charge
percentages, operating hours), binary sensors for on/off states (e.g. pumps),
and diagnostic sensors for multi-state values (e.g. the boiler state with its
state enumeration). No entity SHALL expose commands or write actions.

#### Scenario: Boiler readings
- **WHEN** the installation includes a boiler component
- **THEN** its numeric parameters appear as sensors (e.g. boiler temperature,
  flue gas temperature, operating hours)
- **AND** its multi-state parameter appears as a diagnostic sensor showing the
  state's meaning

#### Scenario: Pump states
- **WHEN** a component reports on/off parameters such as pump states
- **THEN** they appear as binary sensors

#### Scenario: No write actions offered
- **WHEN** any entity of the integration is inspected
- **THEN** it offers no set-value, command, or configuration action

### Requirement: Stable identity independent of labels
The integration SHALL derive entity identities from the stable identifiers the
cloud service assigns to components and parameters, and MUST NOT use localized
display labels as identifiers. Human-facing names MAY come from the
integration's own translations.

#### Scenario: Labels change or language differs
- **WHEN** the cloud service changes a display label or reports in another
  language
- **THEN** entity unique IDs are unchanged and no entities are duplicated

### Requirement: Alarm visibility
The integration SHALL make fault and alarm conditions observable: the boiler
state sensor SHALL reflect fault states from the state enumeration, and the
installation's notification list from the cloud service SHALL be surfaced (for
example as a sensor) within the normal refresh cadence.

#### Scenario: Boiler enters a fault state
- **WHEN** the boiler reports a fault state
- **THEN** the boiler state sensor shows the fault meaning

#### Scenario: New notification
- **WHEN** a new notification appears in the cloud account
- **THEN** the surfaced notification information reflects it within a few
  refresh cycles

### Requirement: Device grouping by component
The integration SHALL group entities into devices by installation component
(e.g. boiler, DHW tank, heating circuit, buffer tank, pellet storage), and
facility-level readings (e.g. outside temperature) SHALL appear on a device
representing the installation itself.

#### Scenario: Entities grouped per component
- **WHEN** the installation provides several components
- **THEN** each component's entities belong to that component's device

#### Scenario: Facility-level reading
- **WHEN** the installation reports outside temperature
- **THEN** it appears on the installation's own device rather than on a
  component device
