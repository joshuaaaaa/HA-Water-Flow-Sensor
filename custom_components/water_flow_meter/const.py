"""Constants for the Water Flow Meter integration."""

DOMAIN = "water_flow_meter"

# Configuration keys
CONF_SOURCE_SENSOR = "source_sensor"
CONF_PULSES_PER_LITER = "pulses_per_liter"
CONF_FLOW_RATE_WINDOW = "flow_rate_window"
CONF_MIN_FLOW_THRESHOLD = "min_flow_threshold"

# Default values
DEFAULT_PULSES_PER_LITER = 1.0
DEFAULT_FLOW_RATE_WINDOW = 60  # seconds
DEFAULT_MIN_FLOW_THRESHOLD = 0.5  # L/min - minimum expected flow rate

# Sensor types
SENSOR_TYPE_FLOW_RATE = "flow_rate"
SENSOR_TYPE_PULSE_RATE = "pulse_rate"
SENSOR_TYPE_TOTAL_VOLUME = "total_volume"

# Attributes
ATTR_LAST_PULSE_TIME = "last_pulse_time"
ATTR_PULSE_COUNT = "pulse_count"
ATTR_PULSES_PER_LITER = "pulses_per_liter"

# Services
SERVICE_RESET_TOTAL_VOLUME = "reset_total_volume"
SERVICE_SET_TOTAL_VOLUME = "set_total_volume"
SERVICE_RESET_DAILY_STATISTICS = "reset_daily_statistics"

# Service attributes
ATTR_VOLUME = "volume"
ATTR_ENTITY_ID = "entity_id"

# Device info
MANUFACTURER = "Water Flow Meter"
MODEL = "Custom Integration"
