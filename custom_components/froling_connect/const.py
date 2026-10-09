"""Constants for the Fröling Connect integration."""

DOMAIN = "froling_connect"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_FACILITY_ID = "facility_id"
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 60
MIN_UPDATE_INTERVAL = 30

API_BASE_URL = "https://connect-api.froeling.com"

LOGIN_URL = f"{API_BASE_URL}/connect/v1.0/resources/login"

USER_URL = f"{API_BASE_URL}/connect/v1.0/resources/service/user/{{user_id}}"
FACILITY_LIST_URL = f"{API_BASE_URL}/connect/v1.0/resources/service/user/{{user_id}}/facility"
NOTIFICATION_COUNT_URL = (
    f"{API_BASE_URL}/connect/v1.0/resources/service/user/{{user_id}}/notification/count"
)
NOTIFICATION_LIST_URL = (
    f"{API_BASE_URL}/connect/v1.0/resources/service/user/{{user_id}}/notification"
)

OVERVIEW_URL = f"{API_BASE_URL}/fcs/v1.0/resources/user/{{user_id}}/facility/{{facility_id}}/overview"
COMPONENT_LIST_URL = (
    f"{API_BASE_URL}/fcs/v1.0/resources/user/{{user_id}}/facility/{{facility_id}}/componentList"
)
COMPONENT_URL = (
    f"{API_BASE_URL}/fcs/v1.0/resources/user/{{user_id}}/facility/{{facility_id}}"
    f"/component/{{component_id}}"
)

# The API also offers a write endpoint for component parameters, but this
# client is read-only by design (see PRODUCT.md): no write path is implemented,
# not even as a constant.
