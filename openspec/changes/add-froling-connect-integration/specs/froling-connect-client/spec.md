## Purpose

Communicates with the unofficial Fröling Connect cloud API on behalf of the
integration, providing strictly read-only access to the installation's data
using the same endpoints the official mobile app uses.

## ADDED Requirements

### Requirement: Authenticate with account credentials
The client SHALL obtain a session token from the Fröling Connect cloud service
using the account's email address and password, and SHALL present that token on
every subsequent data request.

#### Scenario: Successful login
- **WHEN** the user's email and password are valid
- **THEN** the client obtains a session token from the login endpoint
- **AND** subsequent data requests carry that token

#### Scenario: Invalid credentials
- **WHEN** the cloud service rejects the credentials at login
- **THEN** the client raises an authentication error and no data is fetched

### Requirement: Re-authenticate after session loss
The client SHALL, upon receiving an authentication failure (HTTP 401) during a
data request, log in again once with the stored credentials and retry the
original request. If the retried request fails with HTTP 401 again, the client
MUST surface an authentication error instead of retrying further.

#### Scenario: Transparent re-login
- **WHEN** a data request returns HTTP 401 and a fresh login succeeds
- **THEN** the original request is retried with the new token and its data is returned

#### Scenario: Re-login fails
- **WHEN** a data request returns HTTP 401 and the re-login also returns HTTP 401
- **THEN** the client raises an authentication error without looping

### Requirement: Fetch installation data
The client SHALL fetch the account's facilities, the components of a facility,
and each component's parameters, including current values, units, permitted
value ranges, and enumeration value maps where present.

#### Scenario: Component listing with parameters
- **WHEN** the client fetches the installation's components
- **THEN** each component includes its parameters with value, unit, and type
- **AND** enumerable parameters include their value-to-label maps
- **AND** editable numeric parameters include their permitted ranges

### Requirement: Parse the string-typed parameter model
The client SHALL interpret every value according to the parameter's declared
type, because the cloud service encodes all values (numeric and textual) as
JSON strings.

#### Scenario: Numeric parameter
- **WHEN** a numeric parameter arrives with value "78" and unit "°C"
- **THEN** the client exposes the value as the number 78 with unit "°C"

#### Scenario: Enumerated parameter
- **WHEN** an enumerated parameter arrives with raw value "2"
- **THEN** the client exposes both the raw value and its meaning from the
  parameter's enumeration map

### Requirement: Read-only client surface
The client MUST NOT provide any operation that writes a parameter value or any
other state to the cloud service. Setting values (e.g. boiler setpoints) is
explicitly out of scope for the integration.

#### Scenario: No write operations available
- **WHEN** the client's public interface is inspected
- **THEN** no generic or per-parameter write operation exists
