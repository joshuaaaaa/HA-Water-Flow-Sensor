"""Sensor platform for Water Flow Meter integration."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    RestoreEntity,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
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
    MANUFACTURER,
    MODEL,
)

_LOGGER = logging.getLogger(__name__)


class WaterFlowStatistics:
    """Shared statistics tracker for all sensors."""

    def __init__(self, pulses_per_liter: float):
        """Initialize statistics."""
        self.pulses_per_liter = pulses_per_liter
        self.start_time = dt_util.utcnow()

        # Daily statistics
        self.max_flow_today: float = 0.0
        self.total_flow_duration_today: float = 0.0  # seconds
        self.flow_start_time: datetime | None = None
        self.last_reset_date: datetime = dt_util.now().date()

        # Flow history for average calculation
        self.flow_history: list[tuple[datetime, float]] = []

        # Pulse tracking
        self.all_pulse_times: deque = deque(maxlen=1000)  # Keep last 1000 pulses
        self.flow_pulse_times: deque = deque()  # Shared deque for flow rate window
        self.last_pulse_time: datetime | None = None
        self.last_pulse_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert statistics to dictionary for persistence."""
        return {
            "max_flow_today": self.max_flow_today,
            "total_flow_duration_today": self.total_flow_duration_today,
            "flow_start_time": self.flow_start_time.isoformat() if self.flow_start_time else None,
            "last_reset_date": self.last_reset_date.isoformat(),
            "last_pulse_time": self.last_pulse_time.isoformat() if self.last_pulse_time else None,
            "start_time": self.start_time.isoformat(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore statistics from dictionary."""
        try:
            self.max_flow_today = data.get("max_flow_today", 0.0)
            self.total_flow_duration_today = data.get("total_flow_duration_today", 0.0)

            if flow_start := data.get("flow_start_time"):
                self.flow_start_time = dt_util.parse_datetime(flow_start)

            if last_reset := data.get("last_reset_date"):
                self.last_reset_date = dt_util.parse_date(last_reset)

            if last_pulse := data.get("last_pulse_time"):
                self.last_pulse_time = dt_util.parse_datetime(last_pulse)

            if start := data.get("start_time"):
                self.start_time = dt_util.parse_datetime(start)
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Failed to restore statistics: %s", err)

    def reset_daily_stats(self) -> None:
        """Reset daily statistics."""
        self.max_flow_today = 0.0
        self.total_flow_duration_today = 0.0
        self.flow_start_time = None
        self.flow_history.clear()
        self.last_reset_date = dt_util.now().date()

    def check_and_reset_daily(self) -> None:
        """Check if we need to reset daily statistics."""
        today = dt_util.now().date()
        if today > self.last_reset_date:
            self.reset_daily_stats()

    def update_flow_stats(self, current_flow: float) -> None:
        """Update flow statistics."""
        self.check_and_reset_daily()
        now = dt_util.utcnow()

        # Update max flow
        if current_flow > self.max_flow_today:
            self.max_flow_today = current_flow

        # Track flow duration (flow > 0.1 L/min)
        if current_flow > 0.1:
            if self.flow_start_time is None:
                self.flow_start_time = now
        else:
            if self.flow_start_time is not None:
                duration = (now - self.flow_start_time).total_seconds()
                self.total_flow_duration_today += duration
                self.flow_start_time = None

        # Add to history for average
        self.flow_history.append((now, current_flow))

        # Keep only last 24 hours of history
        cutoff = now - timedelta(hours=24)
        self.flow_history = [(t, f) for t, f in self.flow_history if t > cutoff]

    def get_average_flow_today(self) -> float:
        """Calculate average flow for today."""
        self.check_and_reset_daily()
        today_start = dt_util.start_of_local_day()

        today_flows = [f for t, f in self.flow_history if t >= today_start and f > 0]

        if not today_flows:
            return 0.0

        return sum(today_flows) / len(today_flows)

    def add_pulse(self, pulse_time: datetime, pulse_count: int = 1) -> None:
        """Add pulse(s) to tracking."""
        for _ in range(pulse_count):
            self.all_pulse_times.append(pulse_time)
            self.flow_pulse_times.append(pulse_time)
        self.last_pulse_time = pulse_time

    def clean_old_flow_pulses(self, window_seconds: int) -> None:
        """Remove pulses older than the window."""
        cutoff_time = dt_util.utcnow() - timedelta(seconds=window_seconds)
        while self.flow_pulse_times and self.flow_pulse_times[0] < cutoff_time:
            self.flow_pulse_times.popleft()

    def get_average_pulse_interval(self) -> float | None:
        """Get average interval between pulses in seconds."""
        if len(self.all_pulse_times) < 2:
            return None

        # Calculate intervals for last 100 pulses
        recent_pulses = list(self.all_pulse_times)[-100:]
        intervals = []

        for i in range(1, len(recent_pulses)):
            interval = (recent_pulses[i] - recent_pulses[i-1]).total_seconds()
            if interval > 0:
                intervals.append(interval)

        if not intervals:
            return None

        return sum(intervals) / len(intervals)

    def get_time_since_last_pulse(self) -> float | None:
        """Get time since last pulse in seconds."""
        if self.last_pulse_time is None:
            return None

        return (dt_util.utcnow() - self.last_pulse_time).total_seconds()

    def get_uptime(self) -> float:
        """Get uptime in seconds."""
        return (dt_util.utcnow() - self.start_time).total_seconds()




def get_device_info(source_sensor: str, entry_id: str) -> DeviceInfo:
    """Get device info for all sensors."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=f"Water Flow Meter ({source_sensor.split('.')[-1]})",
        manufacturer=MANUFACTURER,
        model=MODEL,
        configuration_url="https://github.com/yourusername/HA-Water-Flow-Sensor",
    )

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

    # Create shared statistics tracker
    stats = WaterFlowStatistics(pulses_per_liter)

    # Store in hass.data for potential future use
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][config_entry.entry_id] = {"stats": stats}

    entities = [
        WaterFlowRateSensor(source_sensor, pulses_per_liter, flow_rate_window, config_entry.entry_id, stats),
        WaterFlowRateHourlySensor(source_sensor, pulses_per_liter, flow_rate_window, config_entry.entry_id, stats),
        WaterFlowRateSecondarySensor(source_sensor, pulses_per_liter, flow_rate_window, config_entry.entry_id, stats),
        WaterPulseRateSensor(source_sensor, flow_rate_window, config_entry.entry_id, stats),
        WaterTotalVolumeSensor(source_sensor, pulses_per_liter, config_entry.entry_id, stats),
        WaterTimeSinceLastPulseSensor(source_sensor, config_entry.entry_id, stats),
        WaterAveragePulseIntervalSensor(source_sensor, config_entry.entry_id, stats),
        WaterUptimeSensor(source_sensor, config_entry.entry_id, stats),
    ]

    # Store entities for service calls
    hass.data[DOMAIN][config_entry.entry_id]["entities"] = entities

    async_add_entities(entities, True)


class WaterFlowRateSensor(SensorEntity):
    """Sensor for water flow rate in liters per minute."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

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
                self._stats.last_pulse_value = float(state.state)
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
        if self._stats.last_pulse_value is not None and new_value > self._stats.last_pulse_value:
            pulse_count = int(new_value - self._stats.last_pulse_value)
            now = dt_util.utcnow()

            # Update shared statistics (adds to both all_pulse_times and flow_pulse_times)
            self._stats.add_pulse(now, pulse_count)

        self._stats.last_pulse_value = new_value

        # Clean old pulses outside the time window
        self._stats.clean_old_flow_pulses(self._flow_rate_window)

        # Update flow statistics
        current_flow = self.native_value or 0.0
        self._stats.update_flow_stats(current_flow)

        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per minute."""
        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate pulses per minute based on the time window
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0
        liters_per_minute = pulses_per_minute / self._pulses_per_liter

        return round(liters_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
            "max_flow_today": round(self._stats.max_flow_today, 2),
            "average_flow_today": round(self._stats.get_average_flow_today(), 2),
            "total_flow_duration_today": round(self._stats.total_flow_duration_today, 1),
        }

        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()

        return attrs


class WaterFlowRateHourlySensor(SensorEntity):
    """Sensor for water flow rate in liters per hour."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "L/h"
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Rate Hourly ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate_hourly"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per hour."""
        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate pulses per hour based on the time window
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_hours = self._flow_rate_window / 3600.0

        pulses_per_hour = pulses_in_window / window_hours if window_hours > 0 else 0
        liters_per_hour = pulses_per_hour / self._pulses_per_liter

        return round(liters_per_hour, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
        }


class WaterFlowRateSecondarySensor(SensorEntity):
    """Sensor for water flow rate in liters per second."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "L/s"
    _attr_icon = "mdi:water-pump"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the flow rate sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Flow Rate Secondary ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_flow_rate_secondary"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the flow rate in liters per second."""
        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate pulses per second based on the time window
        pulses_in_window = len(self._stats.flow_pulse_times)

        pulses_per_second = pulses_in_window / self._flow_rate_window if self._flow_rate_window > 0 else 0
        liters_per_second = pulses_per_second / self._pulses_per_liter

        return round(liters_per_second, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_PULSES_PER_LITER: self._pulses_per_liter,
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
        }


class WaterPulseRateSensor(SensorEntity):
    """Sensor for pulse rate per minute."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pulses/min"
    _attr_icon = "mdi:counter"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        flow_rate_window: int,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the pulse rate sensor."""
        self._source_sensor = source_sensor
        self._flow_rate_window = flow_rate_window
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Pulse Rate ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_pulse_rate"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the pulse rate per minute."""
        if not self._stats.flow_pulse_times:
            return 0.0

        # Calculate pulses per minute based on the time window
        pulses_in_window = len(self._stats.flow_pulse_times)
        window_minutes = self._flow_rate_window / 60.0

        pulses_per_minute = pulses_in_window / window_minutes if window_minutes > 0 else 0

        return round(pulses_per_minute, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_PULSE_COUNT: len(self._stats.flow_pulse_times),
        }

        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()

        return attrs


class WaterTotalVolumeSensor(RestoreEntity, SensorEntity):
    """Sensor for total water volume in liters."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_icon = "mdi:water"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        pulses_per_liter: float,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the total volume sensor."""
        self._source_sensor = source_sensor
        self._pulses_per_liter = pulses_per_liter
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Total Volume ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_total_volume"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

        self._total_pulses: float = 0.0

    async def async_added_to_hass(self) -> None:
        """Restore state and register state listener."""
        await super().async_added_to_hass()

        # Restore previous state
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                # Restore total pulses
                if last_state.state not in ("unknown", "unavailable"):
                    last_volume = float(last_state.state)
                    self._total_pulses = last_volume * self._pulses_per_liter

                # Restore statistics
                if "statistics" in last_state.attributes:
                    self._stats.from_dict(last_state.attributes["statistics"])

            except (ValueError, TypeError) as err:
                _LOGGER.warning("Failed to restore state: %s", err)

        # Register state change listener
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

        # Initialize from current state
        if state := self.hass.states.get(self._source_sensor):
            try:
                self._stats.last_pulse_value = float(state.state)
            except (ValueError, TypeError):
                pass

    async def async_reset_total_volume(self) -> None:
        """Reset total volume to zero."""
        self._total_pulses = 0.0
        self.async_write_ha_state()

    async def async_set_total_volume(self, volume: float) -> None:
        """Set total volume to a specific value."""
        self._total_pulses = volume * self._pulses_per_liter
        self.async_write_ha_state()

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
        if self._stats.last_pulse_value is not None and new_value > self._stats.last_pulse_value:
            pulse_count = new_value - self._stats.last_pulse_value
            self._total_pulses += pulse_count

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
            "statistics": self._stats.to_dict(),
        }

    async def async_reset_daily_statistics(self) -> None:
        """Reset daily statistics."""
        self._stats.reset_daily_stats()
        self.async_write_ha_state()


class WaterTimeSinceLastPulseSensor(SensorEntity):
    """Sensor for time since last pulse."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-outline"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Time Since Last Pulse ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_time_since_last_pulse"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return time since last pulse in seconds."""
        time_since = self._stats.get_time_since_last_pulse()
        if time_since is None:
            return None
        return round(time_since, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {}
        if self._stats.last_pulse_time:
            attrs[ATTR_LAST_PULSE_TIME] = self._stats.last_pulse_time.isoformat()
        return attrs


class WaterAveragePulseIntervalSensor(SensorEntity):
    """Sensor for average pulse interval."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Average Pulse Interval ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_average_pulse_interval"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return average pulse interval in seconds."""
        avg_interval = self._stats.get_average_pulse_interval()
        if avg_interval is None:
            return None
        return round(avg_interval, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "pulse_count": len(self._stats.all_pulse_times),
        }


class WaterUptimeSensor(SensorEntity):
    """Sensor for component uptime."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:clock-outline"
    _attr_has_entity_name = True

    def __init__(
        self,
        source_sensor: str,
        entry_id: str,
        stats: WaterFlowStatistics,
    ) -> None:
        """Initialize the sensor."""
        self._source_sensor = source_sensor
        self._entry_id = entry_id
        self._stats = stats

        self._attr_name = f"Water Meter Uptime ({source_sensor.split('.')[-1]})"
        self._attr_unique_id = f"{entry_id}_uptime"
        self._attr_device_info = get_device_info(source_sensor, entry_id)

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_sensor, self._async_sensor_changed
            )
        )

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return uptime in seconds."""
        return round(self._stats.get_uptime(), 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        uptime = self._stats.get_uptime()
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)

        return {
            "start_time": self._stats.start_time.isoformat(),
            "uptime_formatted": f"{days}d {hours}h {minutes}m",
        }
