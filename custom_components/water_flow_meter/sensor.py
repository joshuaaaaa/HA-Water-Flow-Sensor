"""Sensor platform for Water Flow Meter integration."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_PULSES_PER_LITER,
    CONF_FLOW_RATE_WINDOW,
    DEFAULT_PULSES_PER_LITER,
    DEFAULT_FLOW_RATE_WINDOW,
    ATTR_LAST_PULSE_TIME,
    ATTR_PULSE_COUNT,
    ATTR_PULSES_PER_LITER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Water Flow Meter sensors."""
    source_sensor = config_entry.data[CONF_SOURCE_SENSOR]
    pulses_per_liter = config_entry.options.get(
        CONF_PULSES_PER_LITER,
        config_entry.data.get(CONF_PULSES_PER_LITER, DEFAULT_PULSES_PER_LITER),
    )
    flow_rate_window = config_entry.options.get(
        CONF_FLOW_RATE_WINDOW,
        config_entry.data.get(CONF_FLOW_RATE_WINDOW, DEFAULT_FLOW_RATE_WINDOW),
    )

    async_add_entities(
        [
            WaterFlowRateSensor(
                source_sensor,
                pulses_per_liter,
                flow_rate_window,
                config_entry.entry_id,
            ),
            WaterPulseRateSensor(
                source_sensor,
                flow_rate_window,
                config_entry.entry_id,
            ),
            WaterTotalVolumeSensor(
                source_sensor,
                pulses_per_liter,
                config_entry.entry_id,
            ),
        ],
        True,
    )


class WaterFlowRateSensor(SensorEntity):
    """Sensor for water flow rate in liters per minute."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    _attr_icon = "mdi:water-pump"

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id

        self._attr_name = f"Water Flow Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate"

        self._pulse_times: deque = deque()
        self._last_pulse_time: datetime | None = None
        self._last_pulse_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

        # Initialize from current state
        if state := self.hass.states.get(self._source_sensor):
            try:
                self._last_pulse_value = float(state.state)
            except (ValueError, TypeError):
                pass

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        try:
            new_value = float(new_state.state)
        except (ValueError, TypeError):
            return

        # Detect pulse (increment in value)
        if self._last_pulse_value is not None and new_value > self._last_pulse_value:
            pulse_count = new_value - self._last_pulse_value
            now = dt_util.utcnow()

            # Add pulse times to the deque
            for _ in range(int(pulse_count)):
                self._pulse_times.append(now)

            self._last_pulse_time = now

        self._last_pulse_value = new_value

        # Clean old pulses outside the time window
        cutoff_time = dt_util.utcnow() - timedelta(seconds=self._flow_rate_window)
        while self._pulse_times and self._pulse_times[0] < cutoff_time:
            self._pulse_times.popleft()

        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per minute."""
        if not self._pulse_times:
            return 0.0

        # Calculate pulses per minute based on the time window
        pulses_in_window = len(self._pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0
        liters_per_minute = pulses_per_minute / self._pulses_per_liter

        return round(liters_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._pulse_times),
        }

        if self._last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._last_pulse_time.isoformat()

        return attrs


class WaterPulseRateSensor(SensorEntity):
    """Sensor for pulse rate per minute."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pulses/min"
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        source_sensor: str,
        flow_rate_window: int,
        entry_id: str,
    ) -> None:
        """Initialize the pulse rate sensor."""
        self._source_sensor = source_sensor
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id

        self._attr_name = f"Water Pulse Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_pulse_rate"

        self._pulse_times: deque = deque()
        self._last_pulse_time: datetime | None = None
        self._last_pulse_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

        # Initialize from current state
        if state := self.hass.states.get(self._source_sensor):
            try:
                self._last_pulse_value = float(state.state)
            except (ValueError, TypeError):
                pass

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        try:
            new_value = float(new_state.state)
        except (ValueError, TypeError):
            return

        # Detect pulse (increment in value)
        if self._last_pulse_value is not None and new_value > self._last_pulse_value:
            pulse_count = new_value - self._last_pulse_value
            now = dt_util.utcnow()

            # Add pulse times to the deque
            for _ in range(int(pulse_count)):
                self._pulse_times.append(now)

            self._last_pulse_time = now

        self._last_pulse_value = new_value

        # Clean old pulses outside the time window
        cutoff_time = dt_util.utcnow() - timedelta(seconds=self._flow_rate_window)
        while self._pulse_times and self._pulse_times[0] < cutoff_time:
            self._pulse_times.popleft()

        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the pulse rate per minute."""
        if not self._pulse_times:
            return 0.0

        # Calculate pulses per minute based on the time window
        pulses_in_window = len(self._pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0

        return round(pulses_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSE_COUNT: len(self._pulse_times),
        }

        if self._last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._last_pulse_time.isoformat()

        return attrs


class WaterTotalVolumeSensor(SensorEntity):
    """Sensor for total water volume in liters."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_icon = "mdi:water"

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        entry_id: str,
    ) -> None:
        """Initialize the total volume sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._entry_id = entry_id

        self._attr_name = f"Water Total Volume ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_total_volume"

        self._total_pulses: float = 0.0
        self._last_pulse_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

        # Initialize from current state
        if state := self.hass.states.get(self._source_sensor):
            try:
                self._last_pulse_value = float(state.state)
                self._total_pulses = self._last_pulse_value
            except (ValueError, TypeError):
                pass

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        try:
            new_value = float(new_state.state)
        except (ValueError, TypeError):
            return

        # Detect pulse (increment in value)
        if self._last_pulse_value is not None and new_value > self._last_pulse_value:
            pulse_count = new_value - self._last_pulse_value
            self._total_pulses += pulse_count

        self._last_pulse_value = new_value
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the total volume in liters."""
        total_liters = self._total_pulses / self._pulses_per_liter
        return round(total_liters, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: self._total_pulses,
        }
