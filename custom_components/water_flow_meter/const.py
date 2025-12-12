"""Constants for the Water Flow Meter integration."""

DOMAIN = "water_flow_meter"

# Configuration keys
CONF_SOURCE_SENSOR = "source_sensor"
CONF_PULSES_PER_LITER = "pulses_per_liter"
CONF_FLOW_RATE_WINDOW = "flow_rate_window"

# Default values
DEFAULT_PULSES_PER_LITER = 1.0
DEFAULT_FLOW_RATE_WINDOW = 60  # seconds

# Sensor types
SENSOR_TYPE_FLOW_RATE = "flow_rate"
SENSOR_TYPE_PULSE_RATE = "pulse_rate"
SENSOR_TYPE_TOTAL_VOLUME = "total_volume"

# Attributes
ATTR_LAST_PULSE_TIME = "last_pulse_time"
ATTR_PULSE_COUNT = "pulse_count"
ATTR_PULSES_PER_LITER = "pulses_per_liter"
